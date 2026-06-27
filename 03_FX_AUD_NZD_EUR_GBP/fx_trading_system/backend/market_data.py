"""
Market data service: fetches live prices from Twelve Data or generates simulated data.
Stores prices in the database and broadcasts via WebSocket.
"""
from __future__ import annotations

import asyncio
import random
import time
import httpx
import numpy as np
from datetime import datetime, timezone
from typing import Optional
from config import settings
from database import insert_price, get_recent_prices, insert_log
from indicators import TechnicalIndicators


class MarketDataService:
    """Fetches or simulates FX price data and computes indicators."""

    BASE_PRICES = {
        "AUD/USD": 0.6300,
        "NZD/USD": 0.5700,
    }

    def __init__(self):
        self._sim_prices: dict[str, float] = {
            pair: base for pair, base in self.BASE_PRICES.items()
        }
        self._connected_clients: list[asyncio.Queue] = []
        self._running = False
        self._indicators = TechnicalIndicators()
        self._http_client: Optional[httpx.AsyncClient] = None

    # ─── WebSocket client management ──────────────────────────────────────

    def register_client(self, queue: asyncio.Queue) -> None:
        self._connected_clients.append(queue)

    def unregister_client(self, queue: asyncio.Queue) -> None:
        if queue in self._connected_clients:
            self._connected_clients.remove(queue)

    async def broadcast(self, message: dict) -> None:
        dead: list[asyncio.Queue] = []
        for q in self._connected_clients:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._connected_clients.remove(q)

    # ─── Live API ─────────────────────────────────────────────────────────

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=15.0)
        return self._http_client

    async def fetch_price_live(self, pair: str) -> Optional[dict]:
        """Fetch current price from Twelve Data REST API."""
        client = await self._get_http_client()
        symbol = pair.replace("/", "")
        try:
            resp = await client.get(
                "https://api.twelvedata.com/price",
                params={
                    "symbol": symbol,
                    "apikey": settings.twelve_data_api_key,
                },
            )
            data = resp.json()
            if "price" not in data:
                await insert_log("ERROR", "market_data", f"Twelve Data error for {pair}: {data}")
                return None

            mid = float(data["price"])
            # Twelve Data returns mid price; simulate a spread
            half_spread = random.uniform(0.00006, 0.000125)  # 0.6-1.25 pips
            return {
                "pair": pair,
                "bid": round(mid - half_spread, 5),
                "ask": round(mid + half_spread, 5),
                "mid": round(mid, 5),
                "spread_pips": round(half_spread * 2 * 10000, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "twelvedata",
            }
        except Exception as e:
            await insert_log("ERROR", "market_data", f"Failed to fetch {pair}: {e}")
            return None

    async def fetch_ohlc_live(self, pair: str, interval: str = "5min", outputsize: int = 100) -> Optional[list[dict]]:
        """Fetch OHLC bars from Twelve Data REST API."""
        client = await self._get_http_client()
        symbol = pair.replace("/", "")
        try:
            resp = await client.get(
                "https://api.twelvedata.com/time_series",
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "outputsize": outputsize,
                    "apikey": settings.twelve_data_api_key,
                },
            )
            data = resp.json()
            if "values" not in data:
                await insert_log("ERROR", "market_data", f"Twelve Data OHLC error for {pair}: {data}")
                return None

            bars = []
            for v in reversed(data["values"]):  # Reverse to chronological order
                bars.append({
                    "timestamp": v["datetime"],
                    "open": float(v["open"]),
                    "high": float(v["high"]),
                    "low": float(v["low"]),
                    "close": float(v["close"]),
                    "volume": float(v.get("volume", 0)),
                })
            return bars
        except Exception as e:
            await insert_log("ERROR", "market_data", f"Failed to fetch OHLC {pair}: {e}")
            return None

    # ─── Simulated data ──────────────────────────────────────────────────

    def fetch_price_simulated(self, pair: str) -> dict:
        """Generate a realistic simulated price with random walk."""
        current = self._sim_prices[pair]

        # Random walk: drift + volatility
        drift = random.gauss(0, 0.00002)
        volatility = random.gauss(0, 0.00015)
        change = drift + volatility

        # Mean reversion toward base
        base = self.BASE_PRICES[pair]
        reversion = (base - current) * 0.002
        new_price = current + change + reversion

        self._sim_prices[pair] = new_price

        # Simulate realistic spread (1.2-2.5 pips)
        half_spread = random.uniform(0.00006, 0.000125)
        spread_pips = round(half_spread * 2 * 10000, 2)

        mid = round(new_price, 5)
        return {
            "pair": pair,
            "bid": round(mid - half_spread, 5),
            "ask": round(mid + half_spread, 5),
            "mid": mid,
            "spread_pips": spread_pips,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "simulated",
        }

    def generate_ohlc_bar(self, pair: str) -> dict:
        """Generate a simulated OHLC bar from the current price."""
        mid = self._sim_prices[pair]
        # Simulate intra-bar movement
        moves = [random.gauss(0, 0.00012) for _ in range(20)]
        prices = [mid + sum(moves[:i+1]) for i in range(len(moves))]
        prices.insert(0, mid)

        open_ = prices[0]
        high = max(prices)
        low = min(prices)
        close = prices[-1]
        self._sim_prices[pair] = close

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "open": round(open_, 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "close": round(close, 5),
            "volume": round(random.uniform(100, 5000), 0),
        }

    # ─── Unified fetch ────────────────────────────────────────────────────

    async def fetch_price(self, pair: str) -> dict:
        """Fetch price from live API or simulation."""
        if settings.use_simulated_data:
            return self.fetch_price_simulated(pair)
        result = await self.fetch_price_live(pair)
        if result is None:
            # Fallback to simulated
            await insert_log("WARN", "market_data", f"Falling back to simulated data for {pair}")
            return self.fetch_price_simulated(pair)
        return result

    async def fetch_ohlc(self, pair: str, interval: str = "5min", outputsize: int = 100) -> list[dict]:
        """Fetch OHLC from live API or generate simulated bars."""
        if not settings.use_simulated_data:
            result = await self.fetch_ohlc_live(pair, interval, outputsize)
            if result is not None:
                return result

        # Generate simulated bars
        bars = []
        for _ in range(outputsize):
            bars.append(self.generate_ohlc_bar(pair))
        return bars

    # ─── Indicator computation ────────────────────────────────────────────

    def compute_indicators(self, bars: list[dict]) -> dict:
        """
        Compute all technical indicators from a list of OHLC bars.
        Returns the latest values of each indicator plus full arrays.
        """
        if len(bars) < 2:
            return {
                "sma20": None, "sma50": None, "adx": None,
                "atr": None, "rsi": None, "regime": "RANGE",
                "bollinger_upper": None, "bollinger_middle": None, "bollinger_lower": None,
            }

        closes = np.array([b["close"] for b in bars], dtype=np.float64)
        highs = np.array([b["high"] for b in bars], dtype=np.float64)
        lows = np.array([b["low"] for b in bars], dtype=np.float64)
        volumes = np.array([b.get("volume", 0) for b in bars], dtype=np.float64)

        sma20 = self._indicators.calculate_sma(closes, 20)
        sma50 = self._indicators.calculate_sma(closes, 50)
        adx = self._indicators.calculate_adx(highs, lows, closes, 14)
        atr = self._indicators.calculate_atr(highs, lows, closes, 14)
        rsi = self._indicators.calculate_rsi(closes, 14)
        bb_upper, bb_middle, bb_lower = self._indicators.calculate_bollinger(closes, 20, 2.0)
        regime = self._indicators.detect_regime(sma20, sma50, adx)

        def latest_valid(arr: np.ndarray) -> Optional[float]:
            for v in reversed(arr):
                if not np.isnan(v):
                    return round(float(v), 5)
            return None

        return {
            "sma20": latest_valid(sma20),
            "sma50": latest_valid(sma50),
            "adx": latest_valid(adx),
            "atr": latest_valid(atr),
            "rsi": latest_valid(rsi),
            "regime": regime,
            "bollinger_upper": latest_valid(bb_upper),
            "bollinger_middle": latest_valid(bb_middle),
            "bollinger_lower": latest_valid(bb_lower),
            # Full arrays for signal engine
            "_sma20": sma20,
            "_sma50": sma50,
            "_adx": adx,
            "_atr": atr,
            "_rsi": rsi,
            "_bb_upper": bb_upper,
            "_bb_middle": bb_middle,
            "_bb_lower": bb_lower,
            "_closes": closes,
            "_highs": highs,
            "_lows": lows,
            "_volumes": volumes,
        }

    # ─── Poll loop ────────────────────────────────────────────────────────

    async def poll_once(self, pair: str) -> Optional[dict]:
        """Fetch price, compute indicators, store in DB, broadcast."""
        price_data = await self.fetch_price(pair)
        if price_data is None:
            return None

        # Get recent history for indicators
        recent = await get_recent_prices(pair, limit=100)

        # Build bars list (use stored history + current)
        bars = []
        for row in recent:
            bars.append({
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("volume", 0),
            })

        # Add current price as a new bar
        mid = price_data["mid"]
        spread = price_data.get("spread_pips", 1.5) / 10000
        current_bar = {
            "open": mid,
            "high": mid + abs(random.gauss(0, 0.00005)),
            "low": mid - abs(random.gauss(0, 0.00005)),
            "close": mid,
            "volume": random.uniform(100, 1000),
        }
        bars.append(current_bar)

        # Compute indicators
        indicators = self.compute_indicators(bars)

        # Store in DB
        await insert_price(
            pair=pair,
            timestamp=price_data["timestamp"],
            open_=current_bar["open"],
            high=current_bar["high"],
            low=current_bar["low"],
            close=current_bar["close"],
            volume=current_bar["volume"],
            sma20=indicators["sma20"],
            sma50=indicators["sma50"],
            adx=indicators["adx"],
            atr=indicators["atr"],
            rsi=indicators["rsi"],
        )

        # Build broadcast message
        broadcast_data = {
            "type": "price_update",
            "data": {
                **price_data,
                "indicators": {
                    k: v for k, v in indicators.items() if not k.startswith("_")
                },
            },
        }
        await self.broadcast(broadcast_data)

        return {**price_data, "indicators": indicators}

    async def start_polling(self) -> None:
        """Main polling loop for all pairs."""
        self._running = True
        interval = settings.sim_poll_interval if settings.use_simulated_data else settings.api_poll_interval
        source = "simulated" if settings.use_simulated_data else "twelvedata"
        await insert_log("INFO", "market_data", f"Starting price polling ({source}, interval={interval}s)")

        while self._running:
            for pair in settings.pairs:
                try:
                    await self.poll_once(pair)
                except Exception as e:
                    await insert_log("ERROR", "market_data", f"Poll error for {pair}: {e}")
            await asyncio.sleep(interval)

    def stop_polling(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        self.stop_polling()
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
