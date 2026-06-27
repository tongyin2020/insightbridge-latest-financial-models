"""
Interactive Brokers TWS/Gateway Adapter

Connects to IB TWS or IB Gateway via the ib_insync library and bridges
real-time market data, news, orders, and account information to the
Python FastAPI backend at http://localhost:8000.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

import httpx
from ib_insync import IB, Forex, LimitOrder, MarketOrder, StopOrder, util
from ib_insync.ticker import Ticker

from news_classifier import classify_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("IBAdapter")

# Mapping from our pair notation to IB Forex contract arguments
PAIR_MAP = {
    "AUD/USD": ("AUD", "USD"),
    "NZD/USD": ("NZD", "USD"),
}

# IB news providers that carry macro / central-bank headlines
NEWS_PROVIDERS = [
    "BrfG",   # Briefing.com General
    "BrfB",   # Briefing.com Bonds
    "DJ-N",   # Dow Jones News
    "DJ-RTA", # Dow Jones Real-Time
]


class IBAdapter:
    """Bridge between Interactive Brokers TWS/Gateway and the FastAPI backend."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        backend_url: str = "http://localhost:8000",
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.backend_url = backend_url.rstrip("/")

        self.ib = IB()
        self.http = httpx.AsyncClient(base_url=self.backend_url, timeout=10.0)

        self._tickers: dict[str, Ticker] = {}
        self._running = False
        self._sync_interval = 30  # seconds between reconciliation cycles

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to TWS / IB Gateway."""
        logger.info(
            "Connecting to IB on %s:%s (client_id=%s) ...",
            self.host,
            self.port,
            self.client_id,
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.ib.connect(
                self.host, self.port, clientId=self.client_id, readonly=False
            ),
        )
        logger.info("Connected -- account: %s", self.ib.managedAccounts())

    async def disconnect(self) -> None:
        """Gracefully disconnect from TWS."""
        logger.info("Disconnecting from IB ...")
        self.ib.disconnect()
        await self.http.aclose()
        logger.info("Disconnected.")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def subscribe_market_data(self, pair: str) -> None:
        """Subscribe to streaming market data for *pair* (e.g. 'AUD/USD')."""
        if pair not in PAIR_MAP:
            logger.error("Unknown pair: %s", pair)
            return

        base, quote = PAIR_MAP[pair]
        contract = Forex(base, quote)
        self.ib.qualifyContracts(contract)

        ticker = self.ib.reqMktData(contract, genericTickList="", snapshot=False)
        self._tickers[pair] = ticker

        ticker.updateEvent += lambda t: asyncio.ensure_future(self.on_tick(pair, t))
        logger.info("Subscribed to market data for %s", pair)

    async def on_tick(self, pair: str, ticker: Ticker) -> None:
        """Called on every tick update. Forwards bid/ask/last to the backend."""
        bid = ticker.bid if ticker.bid and ticker.bid > 0 else None
        ask = ticker.ask if ticker.ask and ticker.ask > 0 else None
        last = ticker.last if ticker.last and ticker.last > 0 else None

        if bid is None and ask is None:
            return  # no useful data yet

        payload = {
            "pair": pair,
            "bid": bid,
            "ask": ask,
            "last": last,
            "spread": round(ask - bid, 6) if (bid and ask) else None,
            "volume": ticker.volume if ticker.volume and ticker.volume >= 0 else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            resp = await self.http.post("/api/market-data/tick", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to forward tick for %s: %s", pair, exc)

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    async def subscribe_news(self) -> None:
        """Subscribe to IB news bulletins and headline feeds."""
        # Request news bulletins (exchange-level alerts)
        self.ib.reqNewsBulletins(allMessages=True)
        self.ib.newsBulletinEvent += lambda bulletin: asyncio.ensure_future(
            self._handle_bulletin(bulletin)
        )

        # Subscribe to headline feeds for each provider
        for provider in NEWS_PROVIDERS:
            try:
                sub = self.ib.reqNewsArticle(provider, "", "")
            except Exception:
                pass  # not all providers may be available on every account

            # Per-contract headline subscription (broad FX)
            contract = Forex("AUD", "USD")
            self.ib.qualifyContracts(contract)
            self.ib.reqMktData(contract, genericTickList="mdoff,292", snapshot=False)

        # Attach the pending-tickers handler for news headline ticks
        self.ib.pendingTickersEvent += lambda tickers: asyncio.ensure_future(
            self._scan_news_tickers(tickers)
        )
        logger.info("Subscribed to IB news feeds.")

    async def _handle_bulletin(self, bulletin) -> None:
        """Process an IB news bulletin."""
        headline = bulletin.message if hasattr(bulletin, "message") else str(bulletin)
        await self.on_news(headline, "")

    async def _scan_news_tickers(self, tickers) -> None:
        """Check pending tickers for news-headline generic ticks (tick type 292)."""
        for ticker in tickers:
            if hasattr(ticker, "lastGreeks"):
                continue
            # Generic tick 292 delivers news headline strings
            headline = getattr(ticker, "lastNewsHeadline", None)
            if headline:
                await self.on_news(headline, "")

    async def on_news(self, headline: str, body: str) -> None:
        """Classify an incoming news item and forward it to the backend."""
        impact_level, pairs_affected, category = classify_event(headline, body)

        payload = {
            "headline": headline,
            "body": body,
            "impact_level": impact_level,
            "pairs_affected": pairs_affected,
            "category": category,
            "source": "IB_TWS",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "News [%s] (%s) %s -- affects %s",
            impact_level,
            category,
            headline[:80],
            pairs_affected,
        )

        try:
            resp = await self.http.post("/api/news/event", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to forward news event: %s", exc)

    # ------------------------------------------------------------------
    # Economic calendar
    # ------------------------------------------------------------------

    async def get_economic_calendar(self) -> list[dict]:
        """Fetch upcoming economic events from IB's Wall Street Horizon / Econoday.

        IB exposes calendar data through the reqHistoricalNews and
        reqNewsArticle endpoints.  We pull the last 7 days of headlines
        from the BrfG provider and return them in a normalised list that
        the backend can ingest.
        """
        events: list[dict] = []

        for pair_label, (base, quote) in PAIR_MAP.items():
            contract = Forex(base, quote)
            self.ib.qualifyContracts(contract)

            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt.replace(hour=0, minute=0, second=0)

            try:
                headlines = self.ib.reqHistoricalNews(
                    contract.conId,
                    providerCodes="BrfG+BrfB+DJ-N",
                    startDateTime=start_dt.strftime("%Y%m%d-00:00:00"),
                    endDateTime=end_dt.strftime("%Y%m%d-%H:%M:%S"),
                    totalResults=50,
                )
            except Exception as exc:
                logger.warning("Calendar fetch failed for %s: %s", pair_label, exc)
                continue

            for hl in headlines:
                article_text = ""
                try:
                    article = self.ib.reqNewsArticle(hl.providerCode, hl.articleId)
                    article_text = article.articleText if article else ""
                except Exception:
                    pass

                impact, pairs, cat = classify_event(hl.headline, article_text)
                events.append(
                    {
                        "datetime": hl.time.isoformat() if hasattr(hl, "time") else None,
                        "headline": hl.headline,
                        "provider": hl.providerCode,
                        "impact_level": impact,
                        "pairs_affected": pairs,
                        "category": cat,
                    }
                )

        # Also push to the backend
        try:
            resp = await self.http.post("/api/calendar/events", json=events)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to push calendar events: %s", exc)

        return events

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def place_order(
        self,
        pair: str,
        direction: str,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """Place a bracket order (market entry + stop-loss + take-profit).

        Args:
            pair: e.g. 'AUD/USD'
            direction: 'BUY' or 'SELL'
            quantity: lot size in base currency units
            stop_loss: stop-loss price (optional)
            take_profit: take-profit limit price (optional)
        """
        if pair not in PAIR_MAP:
            raise ValueError(f"Unknown pair: {pair}")

        base, quote = PAIR_MAP[pair]
        contract = Forex(base, quote)
        self.ib.qualifyContracts(contract)

        action = direction.upper()
        reverse_action = "SELL" if action == "BUY" else "BUY"

        # Parent order -- market entry
        parent = MarketOrder(action, quantity)
        parent.transmit = False if (stop_loss or take_profit) else True
        parent.tif = "GTC"

        trades = []
        parent_trade = self.ib.placeOrder(contract, parent)
        trades.append(parent_trade)
        logger.info(
            "Placed %s %s %s (parent orderId=%s)",
            action,
            quantity,
            pair,
            parent_trade.order.orderId,
        )

        # Take-profit child
        if take_profit is not None:
            tp_order = LimitOrder(reverse_action, quantity, take_profit)
            tp_order.parentId = parent_trade.order.orderId
            tp_order.tif = "GTC"
            tp_order.transmit = False if stop_loss else True
            tp_trade = self.ib.placeOrder(contract, tp_order)
            trades.append(tp_trade)
            logger.info("  Take-profit at %s", take_profit)

        # Stop-loss child
        if stop_loss is not None:
            sl_order = StopOrder(reverse_action, quantity, stop_loss)
            sl_order.parentId = parent_trade.order.orderId
            sl_order.tif = "GTC"
            sl_order.transmit = True  # last child transmits the bracket
            sl_trade = self.ib.placeOrder(contract, sl_order)
            trades.append(sl_trade)
            logger.info("  Stop-loss  at %s", stop_loss)

        result = {
            "pair": pair,
            "direction": action,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "parent_order_id": parent_trade.order.orderId,
            "status": parent_trade.orderStatus.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Notify backend
        try:
            resp = await self.http.post("/api/orders/placed", json=result)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to notify backend of order: %s", exc)

        return result

    async def close_position(self, pair: str) -> dict:
        """Close all positions for *pair* by submitting a reversing market order."""
        if pair not in PAIR_MAP:
            raise ValueError(f"Unknown pair: {pair}")

        base, quote = PAIR_MAP[pair]
        contract = Forex(base, quote)
        self.ib.qualifyContracts(contract)

        positions = [
            p for p in self.ib.positions() if p.contract.symbol == base and p.contract.currency == quote
        ]

        if not positions:
            logger.info("No open position for %s -- nothing to close.", pair)
            return {"pair": pair, "closed": False, "reason": "no_position"}

        closed = []
        for pos in positions:
            qty = abs(pos.position)
            action = "SELL" if pos.position > 0 else "BUY"
            order = MarketOrder(action, qty)
            order.tif = "GTC"
            trade = self.ib.placeOrder(contract, order)
            closed.append(
                {
                    "order_id": trade.order.orderId,
                    "action": action,
                    "quantity": qty,
                }
            )
            logger.info("Closing %s %s %s (orderId=%s)", action, qty, pair, trade.order.orderId)

        result = {
            "pair": pair,
            "closed": True,
            "orders": closed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            resp = await self.http.post("/api/positions/closed", json=result)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to notify backend of position close: %s", exc)

        return result

    # ------------------------------------------------------------------
    # Account & positions
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[dict]:
        """Return current IB positions normalised to our pair format."""
        raw_positions = self.ib.positions()
        result = []
        for pos in raw_positions:
            symbol = pos.contract.symbol
            currency = pos.contract.currency
            pair_label = f"{symbol}/{currency}"
            result.append(
                {
                    "pair": pair_label,
                    "quantity": float(pos.position),
                    "avg_cost": float(pos.avgCost),
                    "account": pos.account,
                }
            )
        return result

    async def get_account_summary(self) -> dict:
        """Fetch key account metrics: equity, margin, cash, P&L."""
        self.ib.reqAccountSummary()
        await asyncio.sleep(1)  # give IB time to populate

        summary_values = self.ib.accountSummary()

        parsed: dict[str, float] = {}
        tag_keys = [
            "NetLiquidation",
            "TotalCashValue",
            "GrossPositionValue",
            "MaintMarginReq",
            "AvailableFunds",
            "BuyingPower",
            "UnrealizedPnL",
            "RealizedPnL",
        ]
        for item in summary_values:
            if item.tag in tag_keys:
                try:
                    parsed[item.tag] = float(item.value)
                except (ValueError, TypeError):
                    parsed[item.tag] = 0.0

        self.ib.cancelAccountSummary()
        return {
            "equity": parsed.get("NetLiquidation", 0.0),
            "cash": parsed.get("TotalCashValue", 0.0),
            "gross_position_value": parsed.get("GrossPositionValue", 0.0),
            "maintenance_margin": parsed.get("MaintMarginReq", 0.0),
            "available_funds": parsed.get("AvailableFunds", 0.0),
            "buying_power": parsed.get("BuyingPower", 0.0),
            "unrealised_pnl": parsed.get("UnrealizedPnL", 0.0),
            "realised_pnl": parsed.get("RealizedPnL", 0.0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    async def sync_with_backend(self) -> None:
        """Push current positions and account state to the backend for reconciliation."""
        positions = await self.get_positions()
        account = await self.get_account_summary()

        payload = {
            "positions": positions,
            "account": account,
            "open_orders": [
                {
                    "order_id": t.order.orderId,
                    "pair": f"{t.contract.symbol}/{t.contract.currency}",
                    "action": t.order.action,
                    "quantity": float(t.order.totalQuantity),
                    "order_type": t.order.orderType,
                    "status": t.orderStatus.status,
                }
                for t in self.ib.openTrades()
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            resp = await self.http.post("/api/reconciliation/sync", json=payload)
            resp.raise_for_status()
            logger.info("Reconciliation sync OK -- %d positions.", len(positions))
        except httpx.HTTPError as exc:
            logger.warning("Reconciliation sync failed: %s", exc)

    # ------------------------------------------------------------------
    # Main event loop
    # ------------------------------------------------------------------

    async def _reconciliation_loop(self) -> None:
        """Periodically sync state with the backend."""
        while self._running:
            try:
                await self.sync_with_backend()
            except Exception as exc:
                logger.error("Reconciliation error: %s", exc)
            await asyncio.sleep(self._sync_interval)

    async def _calendar_loop(self) -> None:
        """Fetch the economic calendar every 15 minutes."""
        while self._running:
            try:
                await self.get_economic_calendar()
            except Exception as exc:
                logger.error("Calendar fetch error: %s", exc)
            await asyncio.sleep(900)

    async def _listen_for_backend_commands(self) -> None:
        """Poll the backend for pending order commands."""
        while self._running:
            try:
                resp = await self.http.get("/api/orders/pending")
                resp.raise_for_status()
                commands = resp.json()

                for cmd in commands:
                    action = cmd.get("action")
                    if action == "place_order":
                        await self.place_order(
                            pair=cmd["pair"],
                            direction=cmd["direction"],
                            quantity=cmd["quantity"],
                            stop_loss=cmd.get("stop_loss"),
                            take_profit=cmd.get("take_profit"),
                        )
                    elif action == "close_position":
                        await self.close_position(pair=cmd["pair"])
                    else:
                        logger.warning("Unknown backend command: %s", action)

            except httpx.HTTPError:
                pass  # backend may not be up yet
            except Exception as exc:
                logger.error("Backend command listener error: %s", exc)

            await asyncio.sleep(2)

    async def run(self) -> None:
        """Start the adapter: connect, subscribe, and enter the event loop."""
        await self.connect()
        self._running = True

        # Subscribe to market data for both pairs
        for pair in PAIR_MAP:
            await self.subscribe_market_data(pair)

        # Subscribe to news
        await self.subscribe_news()

        # Initial calendar fetch
        try:
            await self.get_economic_calendar()
        except Exception as exc:
            logger.warning("Initial calendar fetch failed: %s", exc)

        # Initial reconciliation
        await self.sync_with_backend()

        # Launch background tasks
        tasks = [
            asyncio.create_task(self._reconciliation_loop()),
            asyncio.create_task(self._calendar_loop()),
            asyncio.create_task(self._listen_for_backend_commands()),
        ]

        logger.info("IB Adapter running. Press Ctrl+C to stop.")

        # Keep the ib_insync event loop spinning
        try:
            while self._running:
                self.ib.sleep(0.1)
                await asyncio.sleep(0.1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Shutdown requested.")
        finally:
            self._running = False
            for t in tasks:
                t.cancel()
            await self.disconnect()


def main() -> None:
    """Entry point -- reads config from environment or defaults."""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    host = os.getenv("IB_HOST", "127.0.0.1")
    port = int(os.getenv("IB_PORT", "7497"))
    client_id = int(os.getenv("IB_CLIENT_ID", "1"))
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")

    adapter = IBAdapter(
        host=host,
        port=port,
        client_id=client_id,
        backend_url=backend_url,
    )

    loop = asyncio.new_event_loop()

    def _shutdown(sig, frame):
        logger.info("Received signal %s, shutting down ...", sig)
        adapter._running = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        loop.run_until_complete(adapter.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
