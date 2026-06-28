"""
Live Paper Trader
─────────────────────────────────────────────────────────────────────────────
Streams real-time market data from IBKR (using your free subscriptions):
  • ZEROHASH Cryptocurrency TP  → BTC / ETH / SOL
  • IDEALPRO FX                 → AUD/USD / NZD/USD
  • US & EU Bond Quotes (L1)    → ZN Treasury futures
  • CME Event Contracts         → CL WTI Crude futures
  • CME Equity Index Futures    → MES Micro E-mini S&P 500

Flow:
  IBKR Real-Time Prices → Signal Engines → SignalRouter → Paper Orders → TWS

Usage:
  python3 ibkr_paper_trading/live_trader.py

Requirements:
  • TWS open, Paper Trading account logged in (port 7497)
  • API enabled, Read-Only unchecked
  • Market data subscriptions active (ZEROHASH, IDEALPRO, Bond, CME)
"""

import asyncio
import logging
import sys
import os
import math
from datetime import datetime, timezone
from typing import Dict, Optional

# Add parent dir so ibkr_connector and signal_engines are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ib_insync import util
from ibkr_connector import IBKRConnector, SignalRouter, CONTRACTS
from signal_engines import (
    CryptoSignalEngine, FXSignalEngine,
    BondSignalEngine, OilSignalEngine, IndexSignalEngine,
    Signal
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger("LiveTrader")

# ─── Position Sizes ────────────────────────────────────────────────────────────
# Adjust these to scale up/down exposure
# Crypto : USD cash amount (cashQty)
# FX     : currency units  (min 25,000 for IDEALPRO)
# Futures: number of contracts
POSITION_SIZES = {
    "BTC":    100,      # $100 USD per trade
    "ETH":    100,
    "SOL":    100,
    "AUDUSD": 25000,    # 25,000 AUD per trade
    "NZDUSD": 25000,
    "ZN":     1,        # 1 contract (~$111K notional)
    "CL":     1,        # 1 contract (~$70K notional)
    "MES":    1,        # 1 micro equity index contract
}

# How often to check prices and run signal logic (seconds)
SCAN_INTERVAL = 60   # every 60 seconds


class LiveTrader:
    """
    Orchestrates real-time data streaming and signal routing
    for all five financial models simultaneously.
    """

    def __init__(self):
        self.connector = IBKRConnector()
        self.router    = SignalRouter(self.connector)
        self.ib        = self.connector.ib

        # One signal engine per symbol
        self.engines: Dict[str, object] = {
            "BTC":    CryptoSignalEngine("BTC",    POSITION_SIZES["BTC"]),
            "ETH":    CryptoSignalEngine("ETH",    POSITION_SIZES["ETH"]),
            "SOL":    CryptoSignalEngine("SOL",    POSITION_SIZES["SOL"]),
            "AUDUSD": FXSignalEngine("AUDUSD",     POSITION_SIZES["AUDUSD"]),
            "NZDUSD": FXSignalEngine("NZDUSD",     POSITION_SIZES["NZDUSD"]),
            "ZN":     BondSignalEngine(             POSITION_SIZES["ZN"]),
            "CL":     OilSignalEngine(              POSITION_SIZES["CL"]),
            "MES":    IndexSignalEngine(            POSITION_SIZES["MES"]),
        }

        self.tickers: Dict[str, object] = {}
        self.market_state: Dict[str, dict] = {}
        self.contract_symbol_map: Dict[str, str] = {}
        self.running  = False
        self.scan_count = 0
        self.total_signals = 0
        self.total_orders  = 0
        self.ib.errorEvent += self._on_ib_error

    # ── Startup ────────────────────────────────────────────────────────────────

    async def start(self):
        logger.info("Connecting to IBKR Paper Trading (port 7497)...")
        connected = await self.connector.connect()
        if not connected:
            logger.error("❌ Cannot connect. Ensure TWS is running with Paper Trading.")
            return

        summary = await self.connector.get_account_summary()
        logger.info(
            f"💰 Account {self.connector.account} — "
            f"Net=${summary.get('NetLiquidation', 0):,.2f} | "
            f"Cash=${summary.get('AvailableFunds', 0):,.2f}"
        )

        await self._subscribe_market_data()
        logger.info("⏳ Waiting 5s for initial market data...")
        await asyncio.sleep(5)

        self.running = True
        logger.info(f"🚀 Live Trader running — scan every {SCAN_INTERVAL}s — Ctrl+C to stop\n")

        try:
            while self.running:
                await self._scan_and_trade()
                await asyncio.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            logger.info("\n⛔ Stopping live trader (KeyboardInterrupt)...")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            self._unsubscribe_market_data()
            await self._print_session_summary()
            await self.connector.disconnect()

    # ── Market Data ────────────────────────────────────────────────────────────

    async def _subscribe_market_data(self):
        logger.info("📡 Subscribing to real-time market data...")
        for symbol in self.engines.keys():
            try:
                contract = await self.connector.get_contract(symbol)
                # genericTickList="": standard ticks
                # snapshot=False: streaming
                # regulatorySnapshot=False
                # Switch to delayed data (4) if competing live session blocks real-time
                self.ib.reqMarketDataType(4)   # 4 = delayed-frozen (works even with live session)
                ticker = self.ib.reqMktData(contract, "", False, False)
                self.tickers[symbol] = ticker
                self.market_state[symbol] = {
                    "status": "subscribed",
                    "detail": (
                        f"waiting_for_first_tick | localSymbol={getattr(contract, 'localSymbol', '')} "
                        f"| conId={getattr(contract, 'conId', 0)}"
                    ),
                }
                self._index_contract(symbol, contract)
                logger.info(
                    f"   ✅ {symbol} -> {getattr(contract, 'localSymbol', symbol)} "
                    f"(conId={getattr(contract, 'conId', 0)})"
                )
            except Exception as e:
                logger.warning(f"   ⚠️  {symbol}: {e}")
                self.market_state[symbol] = {
                    "status": "subscription_error",
                    "detail": str(e),
                }

    def _unsubscribe_market_data(self):
        for symbol, contract in self.connector.resolved_contracts.items():
            try:
                self.ib.cancelMktData(contract)
            except Exception:
                pass

    def _index_contract(self, symbol: str, contract) -> None:
        for key in {
            symbol,
            getattr(contract, "symbol", None),
            getattr(contract, "localSymbol", None),
            getattr(contract, "tradingClass", None),
        }:
            if key:
                self.contract_symbol_map[str(key)] = symbol

    def _resolve_symbol_from_contract(self, contract) -> Optional[str]:
        for key in (
            getattr(contract, "localSymbol", None),
            getattr(contract, "tradingClass", None),
            getattr(contract, "symbol", None),
        ):
            if key and str(key) in self.contract_symbol_map:
                return self.contract_symbol_map[str(key)]
        return None

    def _on_ib_error(self, reqId, errorCode, errorString, contract=None):
        symbol = self._resolve_symbol_from_contract(contract) if contract is not None else None
        if errorCode == 10197:
            detail = "competing_live_session_blocked"
            if symbol:
                self.market_state[symbol] = {"status": "competing_session", "detail": detail}
        elif errorCode == 10167:
            detail = "delayed_market_data"
            if symbol:
                self.market_state[symbol] = {"status": "delayed", "detail": detail}
        elif errorCode in {354, 10090}:
            detail = "subscription_missing_or_partial"
            if symbol:
                self.market_state[symbol] = {"status": "subscription_limited", "detail": detail}

    def _is_valid_number(self, value) -> bool:
        return value is not None and isinstance(value, (int, float)) and not math.isnan(value) and not math.isinf(value)

    def _get_price(self, symbol: str) -> Optional[float]:
        ticker = self.tickers.get(symbol)
        if not ticker:
            return None
        for field in ("last", "bid", "close", "ask"):
            value = getattr(ticker, field, None)
            if self._is_valid_number(value) and value > 0:
                return float(value)
        return None

    def _get_high_low(self, symbol: str, price: float):
        ticker = self.tickers.get(symbol)
        if not ticker:
            return price, price
        high = getattr(ticker, "high", None)
        low = getattr(ticker, "low", None)
        high = float(high) if self._is_valid_number(high) else price
        low = float(low) if self._is_valid_number(low) else price
        # Fallback: use realistic spread if high==low
        if high == low:
            if symbol in ["BTC", "ETH", "SOL"]:
                high, low = price * 1.002, price * 0.998
            elif symbol in ["AUDUSD", "NZDUSD"]:
                high, low = price + 0.0010, price - 0.0010
            elif symbol == "ZN":
                high, low = price + 0.125, price - 0.125
            elif symbol == "CL":
                high, low = price + 0.50,  price - 0.50
            elif symbol == "MES":
                high, low = price + 8.0, price - 8.0
        return high, low

    # ── Core Scan Loop ─────────────────────────────────────────────────────────

    async def _scan_and_trade(self):
        self.scan_count += 1
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        logger.info(f"\n{'─'*55}")
        logger.info(f"Scan #{self.scan_count} | {ts}")
        logger.info(f"{'─'*55}")

        signals_this_scan = []

        for symbol, engine in self.engines.items():
            price = self._get_price(symbol)
            if price is None or price <= 0:
                state = self.market_state.get(symbol, {})
                status = state.get("status", "waiting")
                detail = state.get("detail", "no_price_yet")
                logger.info(f"  {symbol:8s}: no valid price | status={status} | detail={detail}")
                continue

            if symbol not in self.market_state or self.market_state[symbol]["status"] == "subscribed":
                self.market_state[symbol] = {"status": "live_or_delayed_tick", "detail": "price_available"}

            high, low = self._get_high_low(symbol, price)

            # Feed price to signal engine
            try:
                if isinstance(engine, CryptoSignalEngine):
                    signal = engine.update(price)
                else:
                    signal = engine.update(price, high, low)
            except Exception as e:
                logger.warning(f"  {symbol}: signal engine error: {e}")
                continue

            # Log price
            if symbol in ["BTC", "ETH", "SOL"]:
                logger.info(f"  {symbol:8s}: ${price:>12,.2f}  H=${high:,.2f} L=${low:,.2f} [{self.market_state.get(symbol, {}).get('status', 'ok')}]")
            elif symbol in ["AUDUSD", "NZDUSD"]:
                logger.info(f"  {symbol:8s}:  {price:.5f}    H={high:.5f} L={low:.5f} [{self.market_state.get(symbol, {}).get('status', 'ok')}]")
            else:
                logger.info(f"  {symbol:8s}: {price:>8.4f}     H={high:.4f} L={low:.4f} [{self.market_state.get(symbol, {}).get('status', 'ok')}]")

            if signal:
                signals_this_scan.append(signal)
                self.total_signals += 1

        # Execute signals
        if signals_this_scan:
            logger.info(f"\n🔔 {len(signals_this_scan)} signal(s) generated this scan:")
            for sig in signals_this_scan:
                await self._execute_signal(sig)
        else:
            logger.info("\n  ─ No signals this scan (waiting for crossovers / confirmations)")
        blocked = {k: v for k, v in self.market_state.items() if v.get("status") in {"competing_session", "subscription_limited"}}
        if blocked:
            logger.info(f"  Market data issues: {blocked}")

        # Account snapshot every 5 scans
        if self.scan_count % 5 == 0:
            await self._log_account_snapshot()

    async def _execute_signal(self, sig: Signal):
        logger.info(
            f"  🔔 [{sig.model.upper():6}] {sig.direction} {sig.symbol} "
            f"| qty={sig.quantity} | confidence={sig.confidence:.0%}"
            f"\n       reason: {sig.reason}"
        )
        signal_dict = {
            "model":      sig.model,
            "symbol":     sig.symbol,
            "direction":  sig.direction,
            "quantity":   sig.quantity,
            "order_type": sig.order_type,
            "price":      sig.price,
            "confidence": sig.confidence,
            "reason":     sig.reason,
            "latest_price": self._get_price(sig.symbol),
            "high": self._get_high_low(sig.symbol, self._get_price(sig.symbol) or 0.0)[0],
            "low": self._get_high_low(sig.symbol, self._get_price(sig.symbol) or 0.0)[1],
            "market_status": self.market_state.get(sig.symbol, {}).get("status", "unknown"),
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            result = await self.router.process_signal(signal_dict)
            if result.get("status") == "rejected":
                logger.info(f"  ⚠️  Signal rejected: {result.get('reason')}")
            elif "error" in result:
                logger.warning(f"  ❌ Order error: {result['error']}")
            else:
                self.total_orders += 1
                logger.info(
                    f"  ✅ Order placed — ID={result.get('order_id')} "
                    f"Status={result.get('status')}"
                )
        except Exception as e:
            logger.error(f"  ❌ Execution error: {e}")

    # ── Account Snapshot ───────────────────────────────────────────────────────

    async def _log_account_snapshot(self):
        try:
            summary = await self.connector.get_account_summary()
            logger.info(
                f"\n📊 Account Snapshot | "
                f"Net=${summary.get('NetLiquidation', 0):,.2f} | "
                f"UnrealizedPnL=${summary.get('UnrealizedPnL', 0):+,.2f} | "
                f"RealizedPnL=${summary.get('RealizedPnL', 0):+,.2f} | "
                f"Positions={len(summary.get('positions', []))}"
            )
        except Exception as e:
            logger.warning(f"Could not fetch account snapshot: {e}")

    async def _print_session_summary(self):
        logger.info(f"\n{'='*55}")
        logger.info("SESSION SUMMARY")
        logger.info(f"{'='*55}")
        logger.info(f"  Total scans:   {self.scan_count}")
        logger.info(f"  Signals fired: {self.total_signals}")
        logger.info(f"  Orders placed: {self.total_orders}")
        try:
            summary = await self.connector.get_account_summary()
            logger.info(f"  Final Net Liq: ${summary.get('NetLiquidation', 0):,.2f}")
            logger.info(f"  Realized PnL:  ${summary.get('RealizedPnL', 0):+,.2f}")
            logger.info(f"  Unrealized:    ${summary.get('UnrealizedPnL', 0):+,.2f}")
        except Exception:
            pass
        logger.info(f"{'='*55}\n")


# ─── Entry Point ───────────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 60)
    print("  IBKR LIVE PAPER TRADER — Real Market Data")
    print("=" * 60)
    print("  Data sources (free IBKR subscriptions):")
    print("    • ZEROHASH Crypto  → BTC / ETH / SOL")
    print("    • IDEALPRO FX      → AUD/USD / NZD/USD")
    print("    • Bond Quotes L1   → ZN Treasury Futures")
    print("    • CME Contracts    → CL WTI Crude Futures")
    print("    • CME Equity Index → MES Micro E-mini S&P 500")
    print("=" * 60)
    print(f"  Scan interval : every {SCAN_INTERVAL} seconds")
    print(f"  Position sizes: BTC/ETH/SOL=$100 | FX=25K | ZN/CL/MES=1 contract")
    print("  Press Ctrl+C to stop\n")

    trader = LiveTrader()
    await trader.start()


if __name__ == "__main__":
    util.startLoop()
    asyncio.run(main())
