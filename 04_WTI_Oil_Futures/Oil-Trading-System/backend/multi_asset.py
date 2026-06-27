"""
WTI Trading Platform - Multi-Asset Support
Supports WTI, Brent Crude, and Natural Gas
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timezone
import random
import math

from models import Bar, Tick, Indicators


@dataclass
class AssetConfig:
    """Configuration for a tradable asset"""
    symbol: str
    name: str
    exchange: str
    currency: str
    contract_size: float
    tick_size: float
    base_price: float
    volatility: float
    correlation_wti: float  # Correlation with WTI for portfolio analysis


# Asset configurations
ASSETS = {
    "CL": AssetConfig(
        symbol="CL",
        name="WTI Crude Oil",
        exchange="NYMEX",
        currency="USD",
        contract_size=1000,  # barrels
        tick_size=0.01,
        base_price=75.0,
        volatility=0.002,
        correlation_wti=1.0
    ),
    "BZ": AssetConfig(
        symbol="BZ",
        name="Brent Crude Oil",
        exchange="ICE",
        currency="USD",
        contract_size=1000,  # barrels
        tick_size=0.01,
        base_price=78.0,
        volatility=0.0018,
        correlation_wti=0.95
    ),
    "NG": AssetConfig(
        symbol="NG",
        name="Natural Gas",
        exchange="NYMEX",
        currency="USD",
        contract_size=10000,  # MMBtu
        tick_size=0.001,
        base_price=3.5,
        volatility=0.003,
        correlation_wti=0.45
    )
}


class MultiAssetDataGenerator:
    """Generates correlated price data for multiple assets"""
    
    def __init__(self):
        self.assets: Dict[str, AssetConfig] = ASSETS
        self.current_prices: Dict[str, float] = {}
        self.bars: Dict[str, List[Bar]] = {}
        self.drift: Dict[str, float] = {}
        
        # Initialize
        for symbol, config in self.assets.items():
            self.current_prices[symbol] = config.base_price
            self.bars[symbol] = []
            self.drift[symbol] = 0.0
    
    def generate_tick(self, symbol: str) -> Tick:
        """Generate a new tick for specified asset"""
        if symbol not in self.assets:
            raise ValueError(f"Unknown symbol: {symbol}")
        
        config = self.assets[symbol]
        
        # Generate correlated price movement
        wti_change = random.gauss(self.drift.get("CL", 0), self.assets["CL"].volatility)
        
        if symbol == "CL":
            change = wti_change * self.current_prices[symbol]
        else:
            # Apply correlation
            correlated_change = wti_change * config.correlation_wti
            independent_change = random.gauss(self.drift[symbol], config.volatility) * (1 - abs(config.correlation_wti))
            change = (correlated_change + independent_change) * self.current_prices[symbol]
        
        # Update price with bounds
        min_price = config.base_price * 0.5
        max_price = config.base_price * 2.0
        self.current_prices[symbol] = max(min_price, min(max_price, self.current_prices[symbol] + change))
        
        # Generate spread based on asset
        spread_factor = 1.0 if symbol == "CL" else (0.8 if symbol == "BZ" else 1.5)
        spread = random.uniform(0.02, 0.06) * spread_factor
        
        price = self.current_prices[symbol]
        bid = price - spread / 2
        ask = price + spread / 2
        
        return Tick(
            timestamp=datetime.now(timezone.utc),
            bid=round(bid, 3 if symbol == "NG" else 2),
            ask=round(ask, 3 if symbol == "NG" else 2),
            last=round(price, 3 if symbol == "NG" else 2),
            volume=random.randint(100, 1000),
            symbol=symbol
        )
    
    def generate_bar(self, symbol: str, timeframe_minutes: int = 1) -> Bar:
        """Generate a new bar for specified asset"""
        if symbol not in self.assets:
            raise ValueError(f"Unknown symbol: {symbol}")
        
        config = self.assets[symbol]
        now = datetime.now(timezone.utc)
        
        open_price = self.current_prices[symbol]
        prices = [open_price]
        
        for _ in range(10):
            change = random.gauss(self.drift[symbol], config.volatility) * prices[-1]
            min_price = config.base_price * 0.5
            max_price = config.base_price * 2.0
            new_price = max(min_price, min(max_price, prices[-1] + change))
            prices.append(new_price)
        
        self.current_prices[symbol] = prices[-1]
        
        decimals = 3 if symbol == "NG" else 2
        bar = Bar(
            timestamp=now,
            open=round(open_price, decimals),
            high=round(max(prices), decimals),
            low=round(min(prices), decimals),
            close=round(self.current_prices[symbol], decimals),
            volume=random.randint(5000, 50000),
            symbol=symbol
        )
        
        if symbol not in self.bars:
            self.bars[symbol] = []
        self.bars[symbol].append(bar)
        
        # Keep only last 500 bars
        if len(self.bars[symbol]) > 500:
            self.bars[symbol] = self.bars[symbol][-500:]
        
        return bar
    
    def generate_indicators(self, symbol: str) -> Indicators:
        """Generate indicators for specified asset"""
        if symbol not in self.bars:
            self.bars[symbol] = []
        
        bars = self.bars[symbol][-60:] if len(self.bars[symbol]) >= 60 else self.bars[symbol]
        
        if not bars:
            bars = [self.generate_bar(symbol) for _ in range(20)]
        
        closes = [b.close for b in bars]
        
        ema_fast = self._ema(closes, 20)
        ema_slow = self._ema(closes, 50) if len(closes) >= 50 else ema_fast * 0.99
        
        atr = self._atr(bars, 14)
        atr_baseline = self._atr(bars, min(60, len(bars)))
        
        # ADX with some variance
        adx = 20 + random.uniform(-5, 15)
        
        vwap = sum(b.close * b.volume for b in bars[-20:]) / max(1, sum(b.volume for b in bars[-20:]))
        
        avg_vol = sum(b.volume for b in bars[-20:]) / max(1, len(bars[-20:]))
        current_vol = bars[-1].volume if bars else 10000
        volume_ratio = current_vol / max(1, avg_vol)
        
        volatility_ratio = atr / max(0.001, atr_baseline)
        
        decimals = 3 if symbol == "NG" else 2
        
        return Indicators(
            timestamp=datetime.now(timezone.utc),
            ema_fast=round(ema_fast, decimals),
            ema_slow=round(ema_slow, decimals),
            adx=round(adx, 2),
            atr=round(atr, 4),
            atr_baseline=round(atr_baseline, 4),
            vwap=round(vwap, decimals),
            volume_ratio=round(volume_ratio, 2),
            volatility_ratio=round(volatility_ratio, 2),
        )
    
    def _ema(self, prices: List[float], period: int) -> float:
        if not prices:
            return 0
        if len(prices) < period:
            return sum(prices) / len(prices)
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def _atr(self, bars: List[Bar], period: int) -> float:
        if len(bars) < 2:
            return 0.1
        
        trs = []
        for i in range(1, min(period + 1, len(bars))):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        
        return sum(trs) / len(trs) if trs else 0.1
    
    def set_volatility(self, symbol: str, vol_level: str):
        """Set volatility level for an asset"""
        if symbol not in self.assets:
            return
        
        base_vol = self.assets[symbol].volatility
        multipliers = {"low": 0.5, "normal": 1.0, "high": 2.0, "extreme": 4.0}
        # Note: We can't modify dataclass in place, so we track volatility separately
        
    def set_trend(self, symbol: str, direction: str):
        """Set trend direction for an asset"""
        trends = {"up": 0.0002, "down": -0.0002, "neutral": 0}
        self.drift[symbol] = trends.get(direction, 0)
    
    def get_all_ticks(self) -> Dict[str, Tick]:
        """Get current ticks for all assets"""
        return {symbol: self.generate_tick(symbol) for symbol in self.assets}
    
    def get_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """Get correlation matrix between assets"""
        symbols = list(self.assets.keys())
        matrix = {}
        
        for s1 in symbols:
            matrix[s1] = {}
            for s2 in symbols:
                if s1 == s2:
                    matrix[s1][s2] = 1.0
                else:
                    # Use defined correlations
                    if s1 == "CL":
                        matrix[s1][s2] = self.assets[s2].correlation_wti
                    elif s2 == "CL":
                        matrix[s1][s2] = self.assets[s1].correlation_wti
                    else:
                        # Estimate correlation between non-WTI assets
                        matrix[s1][s2] = self.assets[s1].correlation_wti * self.assets[s2].correlation_wti
        
        return matrix
    
    def get_asset_info(self) -> List[Dict]:
        """Get information about all available assets"""
        return [
            {
                "symbol": config.symbol,
                "name": config.name,
                "exchange": config.exchange,
                "currency": config.currency,
                "contract_size": config.contract_size,
                "tick_size": config.tick_size,
                "current_price": round(self.current_prices[config.symbol], 3 if config.symbol == "NG" else 2),
            }
            for config in self.assets.values()
        ]


class PortfolioAnalyzer:
    """Analyzes portfolio risk across multiple assets"""
    
    def __init__(self, multi_asset_generator: MultiAssetDataGenerator):
        self.generator = multi_asset_generator
    
    def calculate_portfolio_var(
        self,
        positions: Dict[str, float],  # symbol -> position value in USD
        confidence: float = 0.95,
        horizon_days: int = 1
    ) -> float:
        """Calculate Value at Risk for portfolio"""
        import math
        
        # Get correlations
        correlations = self.generator.get_correlation_matrix()
        
        # Get volatilities (annualized, approximated from daily)
        volatilities = {}
        for symbol, config in self.generator.assets.items():
            volatilities[symbol] = config.volatility * math.sqrt(252)  # Annualize
        
        # Calculate portfolio variance
        symbols = list(positions.keys())
        total_value = sum(positions.values())
        
        if total_value == 0:
            return 0.0
        
        # Weights
        weights = {s: positions[s] / total_value for s in symbols}
        
        # Portfolio variance
        portfolio_variance = 0.0
        for s1 in symbols:
            for s2 in symbols:
                w1, w2 = weights[s1], weights[s2]
                v1, v2 = volatilities.get(s1, 0.02), volatilities.get(s2, 0.02)
                corr = correlations.get(s1, {}).get(s2, 0.5)
                portfolio_variance += w1 * w2 * v1 * v2 * corr
        
        portfolio_std = math.sqrt(portfolio_variance)
        
        # Z-score for confidence level
        z_scores = {0.90: 1.28, 0.95: 1.65, 0.99: 2.33}
        z = z_scores.get(confidence, 1.65)
        
        # VaR
        var = total_value * portfolio_std * z * math.sqrt(horizon_days / 252)
        
        return round(var, 2)
    
    def calculate_spread_opportunity(self) -> Optional[Dict]:
        """Check for spread trading opportunities between correlated assets"""
        wti_price = self.generator.current_prices.get("CL", 75)
        brent_price = self.generator.current_prices.get("BZ", 78)
        
        # Historical average spread is around $3
        spread = brent_price - wti_price
        avg_spread = 3.0
        spread_std = 1.5
        
        z_score = (spread - avg_spread) / spread_std
        
        if abs(z_score) > 2:
            return {
                "type": "spread",
                "spread": round(spread, 2),
                "z_score": round(z_score, 2),
                "signal": "SHORT BZ / LONG CL" if z_score > 2 else "LONG BZ / SHORT CL",
                "expected_convergence": round(spread - avg_spread, 2),
                "confidence": min(0.95, 0.5 + abs(z_score) * 0.15)
            }
        
        return None
