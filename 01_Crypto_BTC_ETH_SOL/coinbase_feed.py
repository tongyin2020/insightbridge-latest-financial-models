"""
Coinbase 实时行情 feed（替代 SimulatedMarketFeed 的假数据）
接口与 SimulatedMarketFeed 完全一致，但价格来自 Coinbase 交易所真实行情。
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import httpx

from models import FeatureSnapshot

logger = logging.getLogger(__name__)

TICKER_URL = "https://api.exchange.coinbase.com/products/{pair}/ticker"
STATS_URL = "https://api.exchange.coinbase.com/products/{pair}/stats"


def _default_data(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "price": 0.0,
        "price_change_24h": 0.0,
        "volume_24h": 0.0,
        "high_24h": 0.0,
        "low_24h": 0.0,
        "taker_buy_ratio": 0.5,
        "taker_sell_ratio": 0.5,
        "spread_ratio": 0.0,
        "depth_shrink_ratio": 0.1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "coinbase",
    }


class CoinbaseMarketFeed:
    """从 Coinbase 交易所拉真实 BTC/ETH/SOL 行情，接口对齐 SimulatedMarketFeed。"""

    SUPPORTED = ["BTC", "ETH", "SOL", "LTC", "BCH", "ADA", "XRP", "DOGE", "LINK", "AVAX"]

    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = [s.upper() for s in (symbols or ["BTC", "ETH", "SOL"])]
        self.running = False
        self.callbacks: List[Callable] = []
        self.latest_data: Dict[str, dict] = {s: _default_data(s) for s in self.symbols}
        self._http: Optional[httpx.AsyncClient] = None

    def add_callback(self, callback: Callable):
        self.callbacks.append(callback)

    def add_symbol(self, symbol: str) -> bool:
        symbol = symbol.upper()
        if symbol not in self.symbols:
            self.symbols.append(symbol)
            self.latest_data.setdefault(symbol, _default_data(symbol))
            return True
        return False

    def remove_symbol(self, symbol: str) -> bool:
        symbol = symbol.upper()
        if symbol in self.symbols and len(self.symbols) > 1:
            self.symbols.remove(symbol)
            self.latest_data.pop(symbol, None)
            return True
        return False

    def get_active_symbols(self) -> List[str]:
        return list(self.symbols)

    def get_supported_symbols(self) -> List[str]:
        return list(self.SUPPORTED)

    def get_latest_data(self, symbol: str) -> dict:
        symbol = symbol.upper()
        return self.latest_data.get(symbol, _default_data(symbol))

    def get_all_latest_data(self) -> Dict[str, dict]:
        return self.latest_data.copy()

    async def connect(self):
        self.running = True
        self._http = httpx.AsyncClient(timeout=10.0)
        logger.info(f"Coinbase real feed started for {self.symbols}")
        asyncio.create_task(self._update_loop())

    async def _update_loop(self):
        while self.running:
            try:
                for s in list(self.symbols):
                    try:
                        data = await self._fetch(s)
                        if data:
                            self.latest_data[s] = data
                            for cb in self.callbacks:
                                try:
                                    await cb(s, data)
                                except Exception as e:
                                    logger.error(f"callback error {s}: {e}")
                    except Exception as e:
                        logger.warning(f"coinbase fetch {s} failed: {e}")
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break

    async def _fetch(self, symbol: str) -> Optional[dict]:
        pair = f"{symbol}-USD"
        t = (await self._http.get(TICKER_URL.format(pair=pair))).json()
        if "price" not in t:
            return None
        price = float(t["price"])
        bid = float(t.get("bid") or price)
        ask = float(t.get("ask") or price)
        vol = float(t.get("volume") or 0)
        open24 = high = low = None
        try:
            st = (await self._http.get(STATS_URL.format(pair=pair))).json()
            open24 = float(st.get("open") or 0)
            high = float(st.get("high") or 0)
            low = float(st.get("low") or 0)
        except Exception:
            pass
        change = ((price - open24) / open24 * 100) if open24 else 0.0
        spread = ((ask - bid) / price * 100) if price else 0.0
        return {
            "symbol": symbol,
            "price": price,
            "price_change_24h": round(change, 4),
            "volume_24h": vol,
            "high_24h": high or price,
            "low_24h": low or price,
            "taker_buy_ratio": 0.5,
            "taker_sell_ratio": 0.5,
            "spread_ratio": round(spread, 4),
            "depth_shrink_ratio": 0.1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "coinbase",
        }

    def create_feature_snapshot(self, symbol: str) -> FeatureSnapshot:
        symbol = symbol.upper()
        d = self.latest_data.get(symbol, _default_data(symbol))
        return FeatureSnapshot(
            symbol=symbol,
            ts=d["timestamp"],
            price=d["price"],
            price_change_24h=d["price_change_24h"],
            volume_24h=d["volume_24h"],
            spread_ratio=d.get("spread_ratio", 0.0),
            depth_shrink_ratio=d.get("depth_shrink_ratio", 0.1),
            taker_buy_ratio=d.get("taker_buy_ratio", 0.5),
            taker_sell_ratio=d.get("taker_sell_ratio", 0.5),
            oi_delta_ratio=0.0,
            funding_rate=0.0,
            liquidation_proximity=0.0,
            venue_divergence=0.0,
            stale_quote=False,
            abnormal_wick_score=0.0,
            bid_volume=100,
            ask_volume=100,
        )

    async def stop(self):
        self.running = False
        if self._http:
            await self._http.aclose()
        logger.info("Coinbase real feed stopped")
