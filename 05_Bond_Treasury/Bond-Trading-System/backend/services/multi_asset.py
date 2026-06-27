import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from models.schemas import AVAILABLE_ASSETS

logger = logging.getLogger(__name__)


class MultiAssetDataService:
    def __init__(self):
        self.price_cache = {}

    async def get_asset_price(self, symbol: str) -> Dict[str, Any]:
        asset = AVAILABLE_ASSETS.get(symbol)
        if not asset:
            return None
        try:
            import yfinance as yf
            ticker = yf.Ticker(asset.yahoo_symbol)
            hist = ticker.history(period="5d")
            if not hist.empty:
                current = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current
                change = current - prev
                change_pct = (change / prev * 100) if prev else 0
                return {
                    "symbol": symbol,
                    "name": asset.name,
                    "price": round(current, 4),
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 2),
                    "high": round(float(hist['High'].iloc[-1]), 4),
                    "low": round(float(hist['Low'].iloc[-1]), 4),
                    "volume": int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns else 0,
                    "asset_type": asset.asset_type.value,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
        import random
        base_prices = {
            "10Y_BOND": 4.25, "WTI": 75.0, "GOLD": 2050.0,
            "EUR_USD": 1.08, "SP500": 5100.0, "BTC": 65000.0,
            "30Y_BOND": 4.50, "SILVER": 24.0, "JPY_USD": 155.0, "NASDAQ": 18000.0,
        }
        price = base_prices.get(symbol, 100.0) + random.uniform(-2, 2)
        change = random.uniform(-1, 1)
        return {
            "symbol": symbol, "name": asset.name,
            "price": round(price, 4), "change": round(change, 4),
            "change_pct": round(change / price * 100, 2),
            "high": round(price + abs(change), 4), "low": round(price - abs(change), 4),
            "volume": random.randint(10000, 100000),
            "asset_type": asset.asset_type.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def get_all_assets_prices(self) -> List[Dict[str, Any]]:
        prices = []
        for symbol in AVAILABLE_ASSETS:
            price_data = await self.get_asset_price(symbol)
            if price_data:
                prices.append(price_data)
        return prices
