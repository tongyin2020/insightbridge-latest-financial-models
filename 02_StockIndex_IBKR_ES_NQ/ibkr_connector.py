"""
IBKR Paper Trading Connector
Connects all four financial models to Interactive Brokers Paper Trading
via TWS API (port 7497)

Requirements:
- TWS must be running and logged in with Paper Trading account
- Edit > Global Configuration > API > Settings:
  ✅ Enable ActiveX and Socket Clients
  Port: 7497
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from ib_insync import IB, Stock, Forex, Future, Contract, Crypto, MarketOrder, LimitOrder, util

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger("IBKR_Connector")

# ─── Connection Settings ───────────────────────────────────────────────────────
TWS_HOST      = "127.0.0.1"
TWS_PORT      = 7497          # Paper Trading port (live = 7496)
CLIENT_ID     = 1

# ─── Contract Definitions ──────────────────────────────────────────────────────
# Crypto: use ib_insync Crypto contract (PAXOS exchange, USD currency)
# FX:     Forex pair contracts
# Futures: active front-month as of Q2 2026 (Jun-2026 = 202606)
CONTRACTS = {
    # Crypto Model — IBKR Crypto contracts (not Forex)
    "BTC":  Crypto("BTC", "PAXOS", "USD"),
    "ETH":  Crypto("ETH", "PAXOS", "USD"),
    "SOL":  Crypto("SOL", "PAXOS", "USD"),

    # FX Model
    "AUDUSD": Forex("AUDUSD"),
    "NZDUSD": Forex("NZDUSD"),

    # Bond Model (10Y Treasury Note Future — Jun 2026 front month)
    "ZN":   Future("ZN", "202606", "CBOT"),

    # Oil Model (WTI Crude Future — Jun 2026 front month)
    "CL":   Future("CL", "202606", "NYMEX"),
}


class IBKRConnector:
    """
    Central connector between four financial models and IBKR Paper Trading.
    Receives signals from models and executes paper trades.
    """

    def __init__(self):
        self.ib = IB()
        self.connected = False
        self.account = None

    # ── Connection ─────────────────────────────────────────────────────────────

    async def connect(self):
        """Connect to TWS Paper Trading"""
        try:
            await self.ib.connectAsync(TWS_HOST, TWS_PORT, clientId=CLIENT_ID)
            self.connected = True
            self.account = self.ib.managedAccounts()[0]
            logger.info(f"✅ Connected to IBKR Paper Trading | Account: {self.account}")
            return True
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            logger.error("Make sure TWS is running and Paper Trading API is enabled (port 7497)")
            return False

    async def disconnect(self):
        self.ib.disconnect()
        self.connected = False
        logger.info("Disconnected from IBKR")

    # ── Account Info ───────────────────────────────────────────────────────────

    async def get_account_summary(self) -> dict:
        """Get paper trading account balance and positions"""
        summary = {}
        values = await self.ib.accountSummaryAsync()
        for v in values:
            if v.tag in ["NetLiquidation", "TotalCashValue",
                         "UnrealizedPnL", "RealizedPnL", "AvailableFunds"]:
                summary[v.tag] = float(v.value)

        positions = self.ib.positions()
        summary["positions"] = [
            {
                "symbol":   p.contract.symbol,
                "size":     p.position,
                "avg_cost": p.avgCost,
                "pnl":      p.unrealizedPNL if hasattr(p, "unrealizedPNL") else 0,
            }
            for p in positions
        ]

        logger.info(f"Account: Net=${summary.get('NetLiquidation', 0):,.2f} | "
                    f"Cash=${summary.get('TotalCashValue', 0):,.2f} | "
                    f"UnrealizedPnL=${summary.get('UnrealizedPnL', 0):,.2f}")
        return summary

    # ── Market Data ────────────────────────────────────────────────────────────

    async def get_market_price(self, symbol: str) -> Optional[float]:
        """Get real-time price for a symbol"""
        contract = CONTRACTS.get(symbol)
        if not contract:
            logger.warning(f"Unknown symbol: {symbol}")
            return None

        self.ib.qualifyContracts(contract)
        ticker = self.ib.reqMktData(contract, "", False, False)
        await asyncio.sleep(2)  # wait for data

        price = ticker.last or ticker.bid or ticker.close
        self.ib.cancelMktData(contract)
        logger.info(f"Market price {symbol}: {price}")
        return price

    # ── Order Execution ────────────────────────────────────────────────────────

    async def place_market_order(self, symbol: str, direction: str,
                                  quantity: float, model: str) -> dict:
        """
        Place a paper market order
        direction: 'BUY' or 'SELL'
        model: 'crypto' | 'fx' | 'bond' | 'oil'
        """
        contract = CONTRACTS.get(symbol)
        if not contract:
            return {"error": f"Unknown symbol: {symbol}"}

        self.ib.qualifyContracts(contract)
        order = MarketOrder(direction.upper(), quantity)
        # IBKR crypto contracts (PAXOS) require cashQty + IOC time-in-force
        if isinstance(contract, Crypto):
            order.totalQuantity = 0
            order.cashQty = quantity   # quantity = USD amount for crypto (e.g. 100 = $100)
            order.tif = 'IOC'          # PAXOS requires IOC (Immediate or Cancel), not DAY
        order.orderRef = f"{model}_{symbol}_{datetime.now(timezone.utc).strftime('%H%M%S')}"

        trade = self.ib.placeOrder(contract, order)
        await asyncio.sleep(1)

        result = {
            "model":     model,
            "symbol":    symbol,
            "direction": direction,
            "quantity":  quantity,
            "order_id":  trade.order.orderId,
            "status":    trade.orderStatus.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"📤 [{model.upper()}] {direction} {quantity} {symbol} "
                    f"→ OrderID={trade.order.orderId} Status={trade.orderStatus.status}")
        return result

    async def place_limit_order(self, symbol: str, direction: str,
                                 quantity: float, limit_price: float, model: str) -> dict:
        """Place a paper limit order"""
        contract = CONTRACTS.get(symbol)
        if not contract:
            return {"error": f"Unknown symbol: {symbol}"}

        self.ib.qualifyContracts(contract)
        order = LimitOrder(direction.upper(), quantity, limit_price)
        order.orderRef = f"{model}_{symbol}_{datetime.now(timezone.utc).strftime('%H%M%S')}"

        trade = self.ib.placeOrder(contract, order)
        await asyncio.sleep(1)

        result = {
            "model":       model,
            "symbol":      symbol,
            "direction":   direction,
            "quantity":    quantity,
            "limit_price": limit_price,
            "order_id":    trade.order.orderId,
            "status":      trade.orderStatus.status,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"📤 [{model.upper()}] LIMIT {direction} {quantity} {symbol} "
                    f"@ {limit_price} → OrderID={trade.order.orderId}")
        return result

    async def cancel_order(self, order_id: int):
        """Cancel an open order"""
        trades = self.ib.trades()
        for trade in trades:
            if trade.order.orderId == order_id:
                self.ib.cancelOrder(trade.order)
                logger.info(f"Cancelled order {order_id}")
                return True
        return False

    async def close_all_positions(self):
        """Close all open positions (end of day / emergency)"""
        positions = self.ib.positions()
        for pos in positions:
            if pos.position == 0:
                continue
            direction = "SELL" if pos.position > 0 else "BUY"
            qty = abs(pos.position)
            order = MarketOrder(direction, qty)
            self.ib.placeOrder(pos.contract, order)
            logger.info(f"Closing {pos.contract.symbol}: {direction} {qty}")
        logger.info("All positions closed")


# ─── Signal Router ─────────────────────────────────────────────────────────────

class SignalRouter:
    """
    Receives trading signals from the four models
    and routes them to IBKR paper trading
    """

    def __init__(self, connector: IBKRConnector):
        self.connector = connector
        self.trade_log = []

    async def process_signal(self, signal: dict) -> dict:
        """
        Process a signal from any of the four models.

        Signal format:
        {
            "model":      "crypto" | "fx" | "bond" | "oil",
            "symbol":     "BTC" | "AUDUSD" | "ZN" | "CL",
            "direction":  "BUY" | "SELL",
            "quantity":   1,
            "order_type": "market" | "limit",
            "price":      75.50,  # only for limit orders
            "confidence": 0.75,
            "reason":     "EMA crossover + ADX > 25"
        }
        """
        model     = signal.get("model", "unknown")
        symbol    = signal.get("symbol")
        direction = signal.get("direction")
        quantity  = signal.get("quantity", 1)
        order_type = signal.get("order_type", "market")
        confidence = signal.get("confidence", 0)

        # Minimum confidence threshold
        if confidence < 0.60:
            logger.info(f"[{model}] Signal rejected: confidence {confidence:.0%} < 60%")
            return {"status": "rejected", "reason": "low_confidence"}

        logger.info(f"🔔 Signal from {model.upper()}: {direction} {symbol} "
                    f"(confidence={confidence:.0%})")

        # Route to appropriate order type
        if order_type == "limit" and signal.get("price"):
            result = await self.connector.place_limit_order(
                symbol, direction, quantity, signal["price"], model
            )
        else:
            result = await self.connector.place_market_order(
                symbol, direction, quantity, model
            )

        self.trade_log.append(result)
        return result


# ─── Main Test ────────────────────────────────────────────────────────────────

async def main():
    """
    Test connection and send one sample signal from each model.
    Run this AFTER TWS is open and logged in with Paper Trading account.
    """
    connector = IBKRConnector()
    router    = SignalRouter(connector)

    print("\n" + "="*60)
    print("IBKR Paper Trading — Connection Test")
    print("="*60)

    # Connect
    connected = await connector.connect()
    if not connected:
        print("\n❌ Cannot connect. Please check:")
        print("   1. TWS is open and running")
        print("   2. Logged in with Paper Trading account (DU...)")
        print("   3. Edit > Global Configuration > API:")
        print("      ✅ Enable ActiveX and Socket Clients")
        print("      Port: 7497")
        return

    # Account summary
    print("\n📊 Account Summary:")
    summary = await connector.get_account_summary()
    print(f"   Net Liquidation:  ${summary.get('NetLiquidation', 0):>12,.2f}")
    print(f"   Cash Available:   ${summary.get('AvailableFunds', 0):>12,.2f}")
    print(f"   Unrealized PnL:   ${summary.get('UnrealizedPnL', 0):>12,.2f}")
    print(f"   Open Positions:   {len(summary.get('positions', []))}")

    # Test signals from all four models
    print("\n📤 Sending test signals from all four models...")

    test_signals = [
        {
            "model": "crypto", "symbol": "BTC",
            "direction": "BUY", "quantity": 100,   # $100 USD cash qty (IBKR crypto uses cashQty)
            "order_type": "market", "confidence": 0.75,
            "reason": "RegimeEngine MOMENTUM + BTCSignalEngine LONG_CANDIDATE"
        },
        {
            "model": "fx", "symbol": "AUDUSD",
            "direction": "BUY", "quantity": 10000,
            "order_type": "limit", "price": 0.6390,
            "confidence": 0.72,
            "reason": "EventResponseEngine READY + ExecutionGate ALLOW"
        },
        {
            "model": "bond", "symbol": "ZN",
            "direction": "BUY", "quantity": 1,
            "order_type": "market", "confidence": 0.68,
            "reason": "YieldCurve inverted -50bps + mean reversion signal"
        },
        {
            "model": "oil", "symbol": "CL",
            "direction": "BUY", "quantity": 1,
            "order_type": "limit", "price": 74.50,
            "confidence": 0.71,
            "reason": "FragilityEngine LOW + RegimeService trend + EIA draw bullish"
        },
    ]

    results = []
    for signal in test_signals:
        result = await router.process_signal(signal)
        results.append(result)
        await asyncio.sleep(0.5)

    # Summary
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    for r in results:
        if "error" in r:
            print(f"  ❌ {r}")
        elif r.get("status") == "rejected":
            print(f"  ⚠️  Rejected: {r.get('reason')}")
        else:
            print(f"  ✅ [{r.get('model','').upper():6}] "
                  f"{r.get('direction')} {r.get('quantity')} {r.get('symbol')} "
                  f"→ OrderID={r.get('order_id')} Status={r.get('status')}")

    await connector.disconnect()
    print("\n✅ Test complete. Check TWS for paper orders.\n")


if __name__ == "__main__":
    util.startLoop()
    asyncio.run(main())
