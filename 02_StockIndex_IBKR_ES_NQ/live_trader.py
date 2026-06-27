"""
Live Paper Trader
─────────────────────────────────────────────────────────────────────────────
Streams real-time market data from IBKR (using your free subscriptions):
  • ZEROHASH Cryptocurrency TP  → BTC / ETH / SOL
  • IDEALPRO FX                 → AUD/USD / NZD/USD
  • US & EU Bond Quotes (L1)    → ZN Treasury futures
  • CME Event Contracts         → CL WTI Crude futures

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
from datetime import datetime, timezone
from typing import Dict, Optional

# Add parent dir so ibkr_connector and signal_engines are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ib_insync import util
from ibkr_connector import IBKRConnector, SignalRouter, CONTRACTS
from signal_engines import (
    CryptoSignalEngine, FXSignalEngine,
    BondSignalEngine, OilSignalEngine,
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
}

# How often to check prices and run signal logic (seconds)
SCAN_INTERVAL = 60   # every 60 seconds


class LiveTrader:
    """
    Orchestrates real-time data streaming and signal routing
    for all four financial models simultaneously.
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
        }

        self.tickers: Dict[str, object] = {}
        self.running  = False
        self.scan_count = 0
        self.total_signals = 0
        self.total_orders  = 0

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
        for symbol, contract in CONTRACTS.items():
            try:
                self.ib.qualifyContracts(contract)
                # genericTickList="": standard ticks
                # snapshot=False: streaming
                # regulatorySnapshot=False
                # Switch to delayed data (4) if competing live session blocks real-time
                self.ib.reqMarketDataType(4)   # 4 = delayed-frozen (works even with live session)
                ticker = self.ib.reqMktData(contract, "", False, False)
                self.tickers[symbol] = ticker
                logger.info(f"   ✅ {symbol}")
            except Exception as e:
                logger.warning(f"   ⚠️  {symbol}: {e}")

    def _unsubscribe_market_data(self):
        for symbol, contract in CONTRACTS.items():
            try:
                self.ib.cancelMktData(contract)
            except Exception:
                pass

    def _get_price(self, symbol: str) -> Optional[float]:
        ticker = self.tickers.get(symbol)
        if not ticker:
            return None
        return ticker.last or ticker.bid or ticker.close or None

    def _get_high_low(self, symbol: str, price: float):
        ticker = self.tickers.get(symbol)
        if not ticker:
            return price, price
        high = getattr(ticker, "high", None) or price
        low  = getattr(ticker, "low",  None) or price
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
                logger.info(f"  {symbol:8s}: no price yet (waiting for market data)")
                continue

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
                logger.info(f"  {symbol:8s}: ${price:>12,.2f}  H=${high:,.2f} L=${low:,.2f}")
            elif symbol in ["AUDUSD", "NZDUSD"]:
                logger.info(f"  {symbol:8s}:  {price:.5f}    H={high:.5f} L={low:.5f}")
            else:
                logger.info(f"  {symbol:8s}: {price:>8.4f}     H={high:.4f} L={low:.4f}")

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
    print("=" * 60)
    print(f"  Scan interval : every {SCAN_INTERVAL} seconds")
    print(f"  Position sizes: BTC/ETH/SOL=$100 | FX=25K | ZN/CL=1 contract")
    print("  Press Ctrl+C to stop\n")

    trader = LiveTrader()
    await trader.start()


if __name__ == "__main__":
    util.startLoop()
    asyncio.run(main())
