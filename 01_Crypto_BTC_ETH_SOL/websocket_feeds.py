"""
Simulated market data feed with realistic crypto prices
Uses cached reference prices and simulates realistic market movements
"""
import asyncio
import logging
import random
from typing import Dict, Callable, Optional, List
from datetime import datetime, timezone
from models import FeatureSnapshot

logger = logging.getLogger(__name__)


class SimulatedMarketFeed:
    """
    Simulated market data feed with realistic price movements
    Uses realistic reference prices and simulates market dynamics
    """
    
    # Reference prices (approximately current market prices)
    REFERENCE_PRICES = {
        "BTC": 95000,
        "ETH": 3400,
        "SOL": 180,
        "BNB": 605,
        "XRP": 2.15,
        "DOGE": 0.20,
        "ADA": 0.70,
        "AVAX": 35,
        "DOT": 6.5,
        "MATIC": 0.55,
        "LINK": 14,
        "UNI": 8,
        "SHIB": 0.000022,
        "LTC": 95,
        "ATOM": 7.5,
        "TRX": 0.24,
    }
    
    def __init__(self, symbols: List[str] = None):
        """Initialize with specific symbols"""
        self.symbols = symbols or ["BTC", "ETH", "SOL"]
        self.running = False
        self.callbacks: List[Callable] = []
        
        # Initialize latest data with reference prices
        self.latest_data: Dict[str, dict] = {}
        for symbol in self.symbols:
            self._initialize_symbol(symbol)
    
    def _initialize_symbol(self, symbol: str):
        """Initialize data for a symbol with realistic starting values"""
        ref_price = self.REFERENCE_PRICES.get(symbol, 100)
        # Add some initial variance
        price = ref_price * (1 + (random.random() - 0.5) * 0.02)
        
        self.latest_data[symbol] = {
            "symbol": symbol,
            "price": price,
            "price_change_24h": random.uniform(-5, 5),
            "volume_24h": ref_price * random.uniform(5000000, 50000000),
            "high_24h": price * 1.02,
            "low_24h": price * 0.98,
            "taker_buy_ratio": 0.5,
            "taker_sell_ratio": 0.5,
            "spread_ratio": random.uniform(0.02, 0.08),
            "depth_shrink_ratio": random.uniform(0.05, 0.15),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "simulated"
        }
    
    def add_symbol(self, symbol: str) -> bool:
        """Add a new symbol to track"""
        symbol = symbol.upper()
        if symbol in self.REFERENCE_PRICES and symbol not in self.symbols:
            self.symbols.append(symbol)
            self._initialize_symbol(symbol)
            return True
        return False
    
    def remove_symbol(self, symbol: str) -> bool:
        """Remove a symbol from tracking"""
        symbol = symbol.upper()
        if symbol in self.symbols and len(self.symbols) > 1:
            self.symbols.remove(symbol)
            if symbol in self.latest_data:
                del self.latest_data[symbol]
            return True
        return False
    
    def add_callback(self, callback: Callable):
        """Add a callback function"""
        self.callbacks.append(callback)
    
    async def connect(self):
        """Start the simulated feed"""
        self.running = True
        logger.info(f"Starting simulated market feed for {len(self.symbols)} symbols: {self.symbols}")
        asyncio.create_task(self._update_loop())
    
    async def _update_loop(self):
        """Main update loop for simulated data"""
        while self.running:
            try:
                for symbol in self.symbols:
                    await self._update_symbol(symbol)
                
                await asyncio.sleep(2)  # Update every 2 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Update error: {e}")
                await asyncio.sleep(5)
    
    async def _update_symbol(self, symbol: str):
        """Update price data for a symbol with realistic movements"""
        data = self.latest_data.get(symbol)
        if not data:
            return
        
        # Simulate realistic price movement (random walk with mean reversion)
        ref_price = self.REFERENCE_PRICES.get(symbol, data["price"])
        current_price = data["price"]
        
        # Random component
        random_move = (random.random() - 0.5) * 0.003  # ±0.15% per tick
        
        # Mean reversion component (pulls price back toward reference)
        deviation = (current_price - ref_price) / ref_price
        reversion = -deviation * 0.001
        
        # Apply movement
        price_change = random_move + reversion
        new_price = current_price * (1 + price_change)
        
        # Update 24h change
        old_change = data["price_change_24h"]
        new_change = old_change + price_change * 100
        new_change = max(-15, min(15, new_change))  # Cap at ±15%
        
        # Update taker ratios based on price movement
        if price_change > 0:
            buy_ratio = min(0.65, data["taker_buy_ratio"] + 0.01)
        else:
            buy_ratio = max(0.35, data["taker_buy_ratio"] - 0.01)
        
        # Update spread and depth based on volatility
        volatility = abs(price_change) * 100
        spread = max(0.02, min(0.15, data["spread_ratio"] + (volatility - 0.1) * 0.1))
        depth = max(0.05, min(0.3, data["depth_shrink_ratio"] + (volatility - 0.1) * 0.05))
        
        # Update data
        old_price = data["price"]
        data.update({
            "price": new_price,
            "price_change_24h": new_change,
            "high_24h": max(data["high_24h"], new_price),
            "low_24h": min(data["low_24h"], new_price),
            "taker_buy_ratio": buy_ratio,
            "taker_sell_ratio": 1 - buy_ratio,
            "spread_ratio": spread,
            "depth_shrink_ratio": depth,
            "volume_24h": data["volume_24h"] + new_price * random.uniform(1000, 10000),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Notify callbacks
        if new_price != old_price:
            for callback in self.callbacks:
                try:
                    await callback(symbol, data)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
    
    def get_latest_data(self, symbol: str) -> dict:
        """Get latest market data for a symbol"""
        symbol = symbol.upper()
        if symbol not in self.latest_data and symbol in self.REFERENCE_PRICES:
            self._initialize_symbol(symbol)
        return self.latest_data.get(symbol, self._default_data(symbol))
    
    def _default_data(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "price": 0.0,
            "price_change_24h": 0.0,
            "volume_24h": 0.0,
            "high_24h": 0.0,
            "low_24h": 0.0,
            "taker_buy_ratio": 0.5,
            "taker_sell_ratio": 0.5,
            "spread_ratio": 0.05,
            "depth_shrink_ratio": 0.1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "simulated"
        }
    
    def get_all_latest_data(self) -> Dict[str, dict]:
        """Get latest data for all tracked symbols"""
        return self.latest_data.copy()
    
    def create_feature_snapshot(self, symbol: str) -> FeatureSnapshot:
        """Create a FeatureSnapshot from latest data"""
        symbol = symbol.upper()
        data = self.latest_data.get(symbol, self._default_data(symbol))
        
        # Simulate additional features
        oi_delta = (data["taker_buy_ratio"] - 0.5) * random.uniform(0.5, 1.5)
        funding = (data["taker_buy_ratio"] - 0.5) * random.uniform(-0.0005, 0.0005)
        liq_prox = abs(oi_delta) * random.uniform(0.3, 0.6)
        
        return FeatureSnapshot(
            symbol=symbol,
            ts=data["timestamp"],
            price=data["price"],
            price_change_24h=data["price_change_24h"],
            volume_24h=data["volume_24h"],
            spread_ratio=data.get("spread_ratio", 0.05),
            depth_shrink_ratio=data.get("depth_shrink_ratio", 0.1),
            taker_buy_ratio=data.get("taker_buy_ratio", 0.5),
            taker_sell_ratio=data.get("taker_sell_ratio", 0.5),
            oi_delta_ratio=oi_delta,
            funding_rate=funding,
            liquidation_proximity=liq_prox,
            venue_divergence=random.uniform(0, 0.3),
            stale_quote=False,
            abnormal_wick_score=random.uniform(0, 0.2),
            bid_volume=data.get("bid_volume", 100),
            ask_volume=data.get("ask_volume", 100)
        )
    
    def get_supported_symbols(self) -> List[str]:
        """Get list of all supported symbols"""
        return list(self.REFERENCE_PRICES.keys())
    
    def get_active_symbols(self) -> List[str]:
        """Get list of currently tracked symbols"""
        return self.symbols.copy()
    
    async def stop(self):
        """Stop the feed"""
        self.running = False
        logger.info("Simulated market feed stopped")


# Global feed instance
market_feed: Optional[SimulatedMarketFeed] = None


def get_market_feed(symbols: List[str] = None) -> SimulatedMarketFeed:
    """Get or create the global market feed instance"""
    global market_feed
    if market_feed is None:
        market_feed = SimulatedMarketFeed(symbols or ["BTC", "ETH", "SOL"])
    return market_feed


def reset_market_feed(symbols: List[str] = None) -> SimulatedMarketFeed:
    """Reset the market feed with new symbols"""
    global market_feed
    if market_feed:
        asyncio.create_task(market_feed.stop())
    market_feed = SimulatedMarketFeed(symbols or ["BTC", "ETH", "SOL"])
    return market_feed
