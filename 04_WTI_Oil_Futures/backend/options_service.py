"""
WTI Trading Platform - Futures Options Strategy Module
Supports options pricing, Greeks calculation, and trading strategies
"""
import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import random
from scipy.stats import norm
import numpy as np


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class StrategyType(str, Enum):
    LONG_CALL = "long_call"
    LONG_PUT = "long_put"
    SHORT_CALL = "short_call"
    SHORT_PUT = "short_put"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    BULL_CALL_SPREAD = "bull_call_spread"
    BEAR_PUT_SPREAD = "bear_put_spread"
    IRON_CONDOR = "iron_condor"
    DELTA_HEDGE = "delta_hedge"


@dataclass
class OptionContract:
    """Represents a futures option contract"""
    symbol: str  # Underlying symbol (CL, BZ, NG)
    option_type: OptionType
    strike: float
    expiry: datetime
    premium: float = 0.0
    implied_vol: float = 0.25
    quantity: int = 1
    
    # Greeks
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0


@dataclass
class OptionPosition:
    """A position in an option contract"""
    contract: OptionContract
    quantity: int
    entry_premium: float
    current_premium: float = 0.0
    unrealized_pnl: float = 0.0


@dataclass
class OptionStrategy:
    """A multi-leg options strategy"""
    name: str
    strategy_type: StrategyType
    legs: List[OptionPosition]
    underlying_price: float
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    breakeven_points: List[float] = None
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0


class BlackScholesModel:
    """Black-Scholes option pricing model for futures"""
    
    @staticmethod
    def d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate d1 for Black-Scholes"""
        if T <= 0 or sigma <= 0:
            return 0
        return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    
    @staticmethod
    def d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate d2 for Black-Scholes"""
        d1 = BlackScholesModel.d1(S, K, T, r, sigma)
        if T <= 0 or sigma <= 0:
            return 0
        return d1 - sigma * math.sqrt(T)
    
    @staticmethod
    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate call option price"""
        if T <= 0:
            return max(0, S - K)
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma)
        d2 = BlackScholesModel.d2(S, K, T, r, sigma)
        
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    
    @staticmethod
    def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate put option price"""
        if T <= 0:
            return max(0, K - S)
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma)
        d2 = BlackScholesModel.d2(S, K, T, r, sigma)
        
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    @staticmethod
    def delta(S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType) -> float:
        """Calculate option delta"""
        if T <= 0:
            if option_type == OptionType.CALL:
                return 1.0 if S > K else 0.0
            else:
                return -1.0 if S < K else 0.0
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma)
        if option_type == OptionType.CALL:
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1
    
    @staticmethod
    def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate option gamma (same for calls and puts)"""
        if T <= 0 or sigma <= 0:
            return 0
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma)
        return norm.pdf(d1) / (S * sigma * math.sqrt(T))
    
    @staticmethod
    def theta(S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType) -> float:
        """Calculate option theta (per day)"""
        if T <= 0 or sigma <= 0:
            return 0
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma)
        d2 = BlackScholesModel.d2(S, K, T, r, sigma)
        
        term1 = -(S * sigma * norm.pdf(d1)) / (2 * math.sqrt(T))
        
        if option_type == OptionType.CALL:
            term2 = r * K * math.exp(-r * T) * norm.cdf(d2)
            theta_annual = term1 - term2
        else:
            term2 = r * K * math.exp(-r * T) * norm.cdf(-d2)
            theta_annual = term1 + term2
        
        return theta_annual / 365  # Per day
    
    @staticmethod
    def vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate option vega (per 1% change in IV)"""
        if T <= 0 or sigma <= 0:
            return 0
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma)
        return S * math.sqrt(T) * norm.pdf(d1) / 100  # Per 1% change
    
    @staticmethod
    def implied_volatility(
        market_price: float, 
        S: float, 
        K: float, 
        T: float, 
        r: float, 
        option_type: OptionType,
        max_iterations: int = 100,
        tolerance: float = 1e-5
    ) -> float:
        """Calculate implied volatility using Newton-Raphson"""
        sigma = 0.25  # Initial guess
        
        for _ in range(max_iterations):
            if option_type == OptionType.CALL:
                price = BlackScholesModel.call_price(S, K, T, r, sigma)
            else:
                price = BlackScholesModel.put_price(S, K, T, r, sigma)
            
            diff = price - market_price
            if abs(diff) < tolerance:
                return sigma
            
            vega = BlackScholesModel.vega(S, K, T, r, sigma) * 100  # Convert back
            if vega < 1e-10:
                break
            
            sigma = sigma - diff / vega
            sigma = max(0.01, min(sigma, 5.0))  # Bound sigma
        
        return sigma


class OptionsService:
    """Service for managing options and strategies"""
    
    def __init__(self, risk_free_rate: float = 0.045):
        self.risk_free_rate = risk_free_rate
        self.bs = BlackScholesModel()
        self._option_chains: Dict[str, List[OptionContract]] = {}
        self._positions: List[OptionPosition] = []
        self._strategies: List[OptionStrategy] = []
    
    def generate_option_chain(
        self, 
        symbol: str, 
        underlying_price: float,
        expiry_days: int = 30,
        num_strikes: int = 11
    ) -> List[OptionContract]:
        """Generate a synthetic option chain for an underlying"""
        
        expiry = datetime.now(timezone.utc) + timedelta(days=expiry_days)
        T = expiry_days / 365
        
        # Generate strikes around the current price
        strike_step = underlying_price * 0.025  # 2.5% steps
        base_strike = round(underlying_price / strike_step) * strike_step
        
        chain = []
        half_strikes = num_strikes // 2
        
        for i in range(-half_strikes, half_strikes + 1):
            strike = round(base_strike + i * strike_step, 2)
            
            # Add some IV smile
            moneyness = strike / underlying_price
            iv_adjustment = 0.02 * (moneyness - 1) ** 2
            base_iv = 0.25 + random.uniform(-0.02, 0.02)
            iv = base_iv + iv_adjustment
            
            # Create call
            call_premium = self.bs.call_price(underlying_price, strike, T, self.risk_free_rate, iv)
            call = OptionContract(
                symbol=symbol,
                option_type=OptionType.CALL,
                strike=strike,
                expiry=expiry,
                premium=round(call_premium, 2),
                implied_vol=round(iv, 4),
            )
            call.delta = round(self.bs.delta(underlying_price, strike, T, self.risk_free_rate, iv, OptionType.CALL), 4)
            call.gamma = round(self.bs.gamma(underlying_price, strike, T, self.risk_free_rate, iv), 6)
            call.theta = round(self.bs.theta(underlying_price, strike, T, self.risk_free_rate, iv, OptionType.CALL), 4)
            call.vega = round(self.bs.vega(underlying_price, strike, T, self.risk_free_rate, iv), 4)
            chain.append(call)
            
            # Create put
            put_premium = self.bs.put_price(underlying_price, strike, T, self.risk_free_rate, iv)
            put = OptionContract(
                symbol=symbol,
                option_type=OptionType.PUT,
                strike=strike,
                expiry=expiry,
                premium=round(put_premium, 2),
                implied_vol=round(iv, 4),
            )
            put.delta = round(self.bs.delta(underlying_price, strike, T, self.risk_free_rate, iv, OptionType.PUT), 4)
            put.gamma = round(self.bs.gamma(underlying_price, strike, T, self.risk_free_rate, iv), 6)
            put.theta = round(self.bs.theta(underlying_price, strike, T, self.risk_free_rate, iv, OptionType.PUT), 4)
            put.vega = round(self.bs.vega(underlying_price, strike, T, self.risk_free_rate, iv), 4)
            chain.append(put)
        
        self._option_chains[symbol] = chain
        return chain
    
    def create_straddle(
        self, 
        symbol: str, 
        underlying_price: float, 
        strike: Optional[float] = None,
        expiry_days: int = 30
    ) -> OptionStrategy:
        """Create a straddle strategy (long call + long put at same strike)"""
        
        if strike is None:
            strike = round(underlying_price)
        
        T = expiry_days / 365
        iv = 0.25
        
        # Create call leg
        call_premium = self.bs.call_price(underlying_price, strike, T, self.risk_free_rate, iv)
        call = OptionContract(
            symbol=symbol,
            option_type=OptionType.CALL,
            strike=strike,
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
            premium=call_premium,
            implied_vol=iv,
        )
        call.delta = self.bs.delta(underlying_price, strike, T, self.risk_free_rate, iv, OptionType.CALL)
        call.gamma = self.bs.gamma(underlying_price, strike, T, self.risk_free_rate, iv)
        call.theta = self.bs.theta(underlying_price, strike, T, self.risk_free_rate, iv, OptionType.CALL)
        call.vega = self.bs.vega(underlying_price, strike, T, self.risk_free_rate, iv)
        
        # Create put leg
        put_premium = self.bs.put_price(underlying_price, strike, T, self.risk_free_rate, iv)
        put = OptionContract(
            symbol=symbol,
            option_type=OptionType.PUT,
            strike=strike,
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
            premium=put_premium,
            implied_vol=iv,
        )
        put.delta = self.bs.delta(underlying_price, strike, T, self.risk_free_rate, iv, OptionType.PUT)
        put.gamma = self.bs.gamma(underlying_price, strike, T, self.risk_free_rate, iv)
        put.theta = self.bs.theta(underlying_price, strike, T, self.risk_free_rate, iv, OptionType.PUT)
        put.vega = self.bs.vega(underlying_price, strike, T, self.risk_free_rate, iv)
        
        # Create positions
        call_pos = OptionPosition(contract=call, quantity=1, entry_premium=call_premium, current_premium=call_premium)
        put_pos = OptionPosition(contract=put, quantity=1, entry_premium=put_premium, current_premium=put_premium)
        
        total_cost = call_premium + put_premium
        
        strategy = OptionStrategy(
            name=f"Straddle {symbol} @ {strike}",
            strategy_type=StrategyType.STRADDLE,
            legs=[call_pos, put_pos],
            underlying_price=underlying_price,
            max_profit=None,  # Unlimited
            max_loss=total_cost,
            breakeven_points=[strike - total_cost, strike + total_cost],
            net_delta=round(call.delta + put.delta, 4),
            net_gamma=round(call.gamma + put.gamma, 6),
            net_theta=round(call.theta + put.theta, 4),
            net_vega=round(call.vega + put.vega, 4),
        )
        
        self._strategies.append(strategy)
        return strategy
    
    def create_strangle(
        self, 
        symbol: str, 
        underlying_price: float, 
        call_strike: Optional[float] = None,
        put_strike: Optional[float] = None,
        expiry_days: int = 30
    ) -> OptionStrategy:
        """Create a strangle strategy (OTM call + OTM put)"""
        
        if call_strike is None:
            call_strike = round(underlying_price * 1.05, 2)
        if put_strike is None:
            put_strike = round(underlying_price * 0.95, 2)
        
        T = expiry_days / 365
        iv = 0.25
        
        # Create call leg
        call_premium = self.bs.call_price(underlying_price, call_strike, T, self.risk_free_rate, iv)
        call = OptionContract(
            symbol=symbol,
            option_type=OptionType.CALL,
            strike=call_strike,
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
            premium=call_premium,
            implied_vol=iv,
        )
        call.delta = self.bs.delta(underlying_price, call_strike, T, self.risk_free_rate, iv, OptionType.CALL)
        call.gamma = self.bs.gamma(underlying_price, call_strike, T, self.risk_free_rate, iv)
        call.theta = self.bs.theta(underlying_price, call_strike, T, self.risk_free_rate, iv, OptionType.CALL)
        call.vega = self.bs.vega(underlying_price, call_strike, T, self.risk_free_rate, iv)
        
        # Create put leg
        put_premium = self.bs.put_price(underlying_price, put_strike, T, self.risk_free_rate, iv)
        put = OptionContract(
            symbol=symbol,
            option_type=OptionType.PUT,
            strike=put_strike,
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
            premium=put_premium,
            implied_vol=iv,
        )
        put.delta = self.bs.delta(underlying_price, put_strike, T, self.risk_free_rate, iv, OptionType.PUT)
        put.gamma = self.bs.gamma(underlying_price, put_strike, T, self.risk_free_rate, iv)
        put.theta = self.bs.theta(underlying_price, put_strike, T, self.risk_free_rate, iv, OptionType.PUT)
        put.vega = self.bs.vega(underlying_price, put_strike, T, self.risk_free_rate, iv)
        
        call_pos = OptionPosition(contract=call, quantity=1, entry_premium=call_premium, current_premium=call_premium)
        put_pos = OptionPosition(contract=put, quantity=1, entry_premium=put_premium, current_premium=put_premium)
        
        total_cost = call_premium + put_premium
        
        strategy = OptionStrategy(
            name=f"Strangle {symbol} {put_strike}/{call_strike}",
            strategy_type=StrategyType.STRANGLE,
            legs=[call_pos, put_pos],
            underlying_price=underlying_price,
            max_profit=None,
            max_loss=total_cost,
            breakeven_points=[put_strike - total_cost, call_strike + total_cost],
            net_delta=round(call.delta + put.delta, 4),
            net_gamma=round(call.gamma + put.gamma, 6),
            net_theta=round(call.theta + put.theta, 4),
            net_vega=round(call.vega + put.vega, 4),
        )
        
        self._strategies.append(strategy)
        return strategy
    
    def calculate_delta_hedge(
        self, 
        symbol: str,
        underlying_price: float,
        option_positions: List[OptionPosition],
        futures_contract_size: float = 1000
    ) -> Dict:
        """Calculate the delta hedge requirements"""
        
        total_delta = sum(pos.contract.delta * pos.quantity for pos in option_positions)
        
        # Futures contracts needed to hedge
        futures_needed = -total_delta * futures_contract_size
        
        return {
            "total_option_delta": round(total_delta, 4),
            "futures_contracts_needed": round(futures_needed / futures_contract_size, 2),
            "direction": "SHORT" if futures_needed > 0 else "LONG",
            "hedge_value": round(abs(futures_needed) * underlying_price, 2),
            "residual_delta": round(total_delta + futures_needed / futures_contract_size, 6),
        }
    
    def get_strategy_pnl_at_expiry(
        self, 
        strategy: OptionStrategy, 
        price_range: Tuple[float, float],
        num_points: int = 50
    ) -> List[Dict]:
        """Calculate P&L profile at expiry for various prices"""
        
        prices = np.linspace(price_range[0], price_range[1], num_points)
        pnl_data = []
        
        for price in prices:
            total_pnl = 0
            
            for leg in strategy.legs:
                contract = leg.contract
                entry_cost = leg.entry_premium * leg.quantity
                
                if contract.option_type == OptionType.CALL:
                    intrinsic = max(0, price - contract.strike)
                else:
                    intrinsic = max(0, contract.strike - price)
                
                leg_pnl = (intrinsic - leg.entry_premium) * leg.quantity * 1000  # Per contract
                total_pnl += leg_pnl
            
            pnl_data.append({
                "price": round(price, 2),
                "pnl": round(total_pnl, 2),
            })
        
        return pnl_data
    
    def get_volatility_surface(self, symbol: str, underlying_price: float) -> Dict:
        """Generate implied volatility surface data"""
        
        expiries = [7, 14, 30, 60, 90]  # Days
        strikes_pct = [0.90, 0.95, 0.975, 1.0, 1.025, 1.05, 1.10]
        
        surface = {
            "expiries": expiries,
            "strikes": [],
            "ivs": []
        }
        
        for strike_pct in strikes_pct:
            strike = round(underlying_price * strike_pct, 2)
            surface["strikes"].append(strike)
            
            iv_row = []
            for days in expiries:
                # Generate IV with smile/skew
                moneyness = strike_pct
                base_iv = 0.22 + 0.05 * random.random()
                
                # Skew: OTM puts have higher IV
                if moneyness < 1:
                    skew = 0.08 * (1 - moneyness)
                else:
                    skew = 0.02 * (moneyness - 1)
                
                # Term structure: longer dated options have different IV
                term_adj = 0.01 * math.log(days / 30 + 1)
                
                iv = base_iv + skew + term_adj
                iv_row.append(round(iv, 4))
            
            surface["ivs"].append(iv_row)
        
        return surface
    
    def analyze_volatility_trade(
        self, 
        symbol: str, 
        underlying_price: float,
        current_iv: float,
        historical_vol: float
    ) -> Dict:
        """Analyze potential volatility trading opportunities"""
        
        iv_percentile = self._calculate_iv_percentile(current_iv)
        vol_spread = current_iv - historical_vol
        
        recommendation = None
        strategy_type = None
        confidence = 0.5
        
        if current_iv > historical_vol * 1.3:
            # IV is high - consider selling volatility
            recommendation = "SELL VOLATILITY"
            strategy_type = "Iron Condor or Short Strangle"
            confidence = min(0.9, 0.5 + (current_iv / historical_vol - 1))
        elif current_iv < historical_vol * 0.8:
            # IV is low - consider buying volatility
            recommendation = "BUY VOLATILITY"
            strategy_type = "Straddle or Long Strangle"
            confidence = min(0.9, 0.5 + (1 - current_iv / historical_vol))
        else:
            recommendation = "NEUTRAL"
            strategy_type = "No clear edge"
            confidence = 0.3
        
        return {
            "current_iv": round(current_iv, 4),
            "historical_vol": round(historical_vol, 4),
            "iv_percentile": round(iv_percentile, 1),
            "vol_spread": round(vol_spread, 4),
            "recommendation": recommendation,
            "suggested_strategy": strategy_type,
            "confidence": round(confidence, 2),
            "reasoning": f"IV at {iv_percentile:.0f}th percentile. {'High IV favors selling premium.' if current_iv > historical_vol else 'Low IV favors buying premium.' if current_iv < historical_vol else 'IV near fair value.'}"
        }
    
    def _calculate_iv_percentile(self, current_iv: float) -> float:
        """Calculate IV percentile (simplified)"""
        # In production, this would use historical IV data
        # For now, assume normal distribution centered at 0.25
        mean_iv = 0.25
        std_iv = 0.08
        z_score = (current_iv - mean_iv) / std_iv
        return norm.cdf(z_score) * 100
    
    def get_all_strategies(self) -> List[Dict]:
        """Get all active strategies"""
        return [
            {
                "name": s.name,
                "type": s.strategy_type.value,
                "underlying_price": s.underlying_price,
                "max_profit": s.max_profit,
                "max_loss": s.max_loss,
                "breakeven_points": s.breakeven_points,
                "greeks": {
                    "delta": s.net_delta,
                    "gamma": s.net_gamma,
                    "theta": s.net_theta,
                    "vega": s.net_vega,
                },
                "legs": [
                    {
                        "type": leg.contract.option_type.value,
                        "strike": leg.contract.strike,
                        "quantity": leg.quantity,
                        "premium": leg.entry_premium,
                        "delta": leg.contract.delta,
                    }
                    for leg in s.legs
                ]
            }
            for s in self._strategies
        ]
    
    def create_iron_condor(
        self,
        symbol: str,
        underlying_price: float,
        put_sell_strike: Optional[float] = None,
        put_buy_strike: Optional[float] = None,
        call_sell_strike: Optional[float] = None,
        call_buy_strike: Optional[float] = None,
        expiry_days: int = 30
    ) -> OptionStrategy:
        """
        Create an Iron Condor strategy (sell OTM put spread + sell OTM call spread)
        Profits from low volatility / range-bound market
        """
        
        # Default strikes: sell at 5% OTM, buy protection at 10% OTM
        if put_sell_strike is None:
            put_sell_strike = round(underlying_price * 0.95, 2)
        if put_buy_strike is None:
            put_buy_strike = round(underlying_price * 0.90, 2)
        if call_sell_strike is None:
            call_sell_strike = round(underlying_price * 1.05, 2)
        if call_buy_strike is None:
            call_buy_strike = round(underlying_price * 1.10, 2)
        
        T = expiry_days / 365
        iv = 0.25
        
        legs = []
        
        # Short Put (sell)
        short_put_premium = self.bs.put_price(underlying_price, put_sell_strike, T, self.risk_free_rate, iv)
        short_put = OptionContract(
            symbol=symbol, option_type=OptionType.PUT, strike=put_sell_strike,
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
            premium=short_put_premium, implied_vol=iv,
        )
        short_put.delta = self.bs.delta(underlying_price, put_sell_strike, T, self.risk_free_rate, iv, OptionType.PUT)
        short_put.gamma = self.bs.gamma(underlying_price, put_sell_strike, T, self.risk_free_rate, iv)
        short_put.theta = self.bs.theta(underlying_price, put_sell_strike, T, self.risk_free_rate, iv, OptionType.PUT)
        short_put.vega = self.bs.vega(underlying_price, put_sell_strike, T, self.risk_free_rate, iv)
        legs.append(OptionPosition(contract=short_put, quantity=-1, entry_premium=short_put_premium, current_premium=short_put_premium))
        
        # Long Put (buy protection)
        long_put_premium = self.bs.put_price(underlying_price, put_buy_strike, T, self.risk_free_rate, iv)
        long_put = OptionContract(
            symbol=symbol, option_type=OptionType.PUT, strike=put_buy_strike,
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
            premium=long_put_premium, implied_vol=iv,
        )
        long_put.delta = self.bs.delta(underlying_price, put_buy_strike, T, self.risk_free_rate, iv, OptionType.PUT)
        long_put.gamma = self.bs.gamma(underlying_price, put_buy_strike, T, self.risk_free_rate, iv)
        long_put.theta = self.bs.theta(underlying_price, put_buy_strike, T, self.risk_free_rate, iv, OptionType.PUT)
        long_put.vega = self.bs.vega(underlying_price, put_buy_strike, T, self.risk_free_rate, iv)
        legs.append(OptionPosition(contract=long_put, quantity=1, entry_premium=long_put_premium, current_premium=long_put_premium))
        
        # Short Call (sell)
        short_call_premium = self.bs.call_price(underlying_price, call_sell_strike, T, self.risk_free_rate, iv)
        short_call = OptionContract(
            symbol=symbol, option_type=OptionType.CALL, strike=call_sell_strike,
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
            premium=short_call_premium, implied_vol=iv,
        )
        short_call.delta = self.bs.delta(underlying_price, call_sell_strike, T, self.risk_free_rate, iv, OptionType.CALL)
        short_call.gamma = self.bs.gamma(underlying_price, call_sell_strike, T, self.risk_free_rate, iv)
        short_call.theta = self.bs.theta(underlying_price, call_sell_strike, T, self.risk_free_rate, iv, OptionType.CALL)
        short_call.vega = self.bs.vega(underlying_price, call_sell_strike, T, self.risk_free_rate, iv)
        legs.append(OptionPosition(contract=short_call, quantity=-1, entry_premium=short_call_premium, current_premium=short_call_premium))
        
        # Long Call (buy protection)
        long_call_premium = self.bs.call_price(underlying_price, call_buy_strike, T, self.risk_free_rate, iv)
        long_call = OptionContract(
            symbol=symbol, option_type=OptionType.CALL, strike=call_buy_strike,
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
            premium=long_call_premium, implied_vol=iv,
        )
        long_call.delta = self.bs.delta(underlying_price, call_buy_strike, T, self.risk_free_rate, iv, OptionType.CALL)
        long_call.gamma = self.bs.gamma(underlying_price, call_buy_strike, T, self.risk_free_rate, iv)
        long_call.theta = self.bs.theta(underlying_price, call_buy_strike, T, self.risk_free_rate, iv, OptionType.CALL)
        long_call.vega = self.bs.vega(underlying_price, call_buy_strike, T, self.risk_free_rate, iv)
        legs.append(OptionPosition(contract=long_call, quantity=1, entry_premium=long_call_premium, current_premium=long_call_premium))
        
        # Calculate net credit/debit
        net_credit = short_put_premium + short_call_premium - long_put_premium - long_call_premium
        
        # Max profit = net credit received
        max_profit = net_credit * 1000  # Per contract
        
        # Max loss = width of spread - net credit
        put_spread_width = put_sell_strike - put_buy_strike
        call_spread_width = call_buy_strike - call_sell_strike
        max_loss = (max(put_spread_width, call_spread_width) - net_credit) * 1000
        
        # Net Greeks
        net_delta = sum(leg.contract.delta * leg.quantity for leg in legs)
        net_gamma = sum(leg.contract.gamma * abs(leg.quantity) for leg in legs)
        net_theta = sum(leg.contract.theta * leg.quantity for leg in legs)
        net_vega = sum(leg.contract.vega * leg.quantity for leg in legs)
        
        strategy = OptionStrategy(
            name=f"Iron Condor {symbol} {put_buy_strike}/{put_sell_strike}/{call_sell_strike}/{call_buy_strike}",
            strategy_type=StrategyType.IRON_CONDOR,
            legs=legs,
            underlying_price=underlying_price,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakeven_points=[put_sell_strike - net_credit, call_sell_strike + net_credit],
            net_delta=round(net_delta, 4),
            net_gamma=round(net_gamma, 6),
            net_theta=round(net_theta, 4),
            net_vega=round(net_vega, 4),
        )
        
        self._strategies.append(strategy)
        return strategy
    
    def create_butterfly(
        self,
        symbol: str,
        underlying_price: float,
        option_type: OptionType = OptionType.CALL,
        center_strike: Optional[float] = None,
        wing_width: float = 2.5,
        expiry_days: int = 30
    ) -> OptionStrategy:
        """
        Create a Butterfly spread
        Long 1 lower strike, Short 2 center strikes, Long 1 higher strike
        Profits from low volatility with price at center strike
        """
        
        if center_strike is None:
            center_strike = round(underlying_price)
        
        lower_strike = round(center_strike - wing_width, 2)
        upper_strike = round(center_strike + wing_width, 2)
        
        T = expiry_days / 365
        iv = 0.25
        
        legs = []
        
        if option_type == OptionType.CALL:
            # Long lower call
            lower_premium = self.bs.call_price(underlying_price, lower_strike, T, self.risk_free_rate, iv)
            lower_opt = OptionContract(
                symbol=symbol, option_type=OptionType.CALL, strike=lower_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=lower_premium, implied_vol=iv,
            )
            lower_opt.delta = self.bs.delta(underlying_price, lower_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            lower_opt.gamma = self.bs.gamma(underlying_price, lower_strike, T, self.risk_free_rate, iv)
            lower_opt.theta = self.bs.theta(underlying_price, lower_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            lower_opt.vega = self.bs.vega(underlying_price, lower_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=lower_opt, quantity=1, entry_premium=lower_premium, current_premium=lower_premium))
            
            # Short 2 center calls
            center_premium = self.bs.call_price(underlying_price, center_strike, T, self.risk_free_rate, iv)
            center_opt = OptionContract(
                symbol=symbol, option_type=OptionType.CALL, strike=center_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=center_premium, implied_vol=iv,
            )
            center_opt.delta = self.bs.delta(underlying_price, center_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            center_opt.gamma = self.bs.gamma(underlying_price, center_strike, T, self.risk_free_rate, iv)
            center_opt.theta = self.bs.theta(underlying_price, center_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            center_opt.vega = self.bs.vega(underlying_price, center_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=center_opt, quantity=-2, entry_premium=center_premium, current_premium=center_premium))
            
            # Long upper call
            upper_premium = self.bs.call_price(underlying_price, upper_strike, T, self.risk_free_rate, iv)
            upper_opt = OptionContract(
                symbol=symbol, option_type=OptionType.CALL, strike=upper_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=upper_premium, implied_vol=iv,
            )
            upper_opt.delta = self.bs.delta(underlying_price, upper_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            upper_opt.gamma = self.bs.gamma(underlying_price, upper_strike, T, self.risk_free_rate, iv)
            upper_opt.theta = self.bs.theta(underlying_price, upper_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            upper_opt.vega = self.bs.vega(underlying_price, upper_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=upper_opt, quantity=1, entry_premium=upper_premium, current_premium=upper_premium))
        else:
            # Put butterfly
            lower_premium = self.bs.put_price(underlying_price, lower_strike, T, self.risk_free_rate, iv)
            lower_opt = OptionContract(
                symbol=symbol, option_type=OptionType.PUT, strike=lower_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=lower_premium, implied_vol=iv,
            )
            lower_opt.delta = self.bs.delta(underlying_price, lower_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            lower_opt.gamma = self.bs.gamma(underlying_price, lower_strike, T, self.risk_free_rate, iv)
            lower_opt.theta = self.bs.theta(underlying_price, lower_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            lower_opt.vega = self.bs.vega(underlying_price, lower_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=lower_opt, quantity=1, entry_premium=lower_premium, current_premium=lower_premium))
            
            center_premium = self.bs.put_price(underlying_price, center_strike, T, self.risk_free_rate, iv)
            center_opt = OptionContract(
                symbol=symbol, option_type=OptionType.PUT, strike=center_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=center_premium, implied_vol=iv,
            )
            center_opt.delta = self.bs.delta(underlying_price, center_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            center_opt.gamma = self.bs.gamma(underlying_price, center_strike, T, self.risk_free_rate, iv)
            center_opt.theta = self.bs.theta(underlying_price, center_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            center_opt.vega = self.bs.vega(underlying_price, center_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=center_opt, quantity=-2, entry_premium=center_premium, current_premium=center_premium))
            
            upper_premium = self.bs.put_price(underlying_price, upper_strike, T, self.risk_free_rate, iv)
            upper_opt = OptionContract(
                symbol=symbol, option_type=OptionType.PUT, strike=upper_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=upper_premium, implied_vol=iv,
            )
            upper_opt.delta = self.bs.delta(underlying_price, upper_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            upper_opt.gamma = self.bs.gamma(underlying_price, upper_strike, T, self.risk_free_rate, iv)
            upper_opt.theta = self.bs.theta(underlying_price, upper_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            upper_opt.vega = self.bs.vega(underlying_price, upper_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=upper_opt, quantity=1, entry_premium=upper_premium, current_premium=upper_premium))
        
        # Calculate cost and profit
        net_debit = legs[0].entry_premium - 2 * legs[1].entry_premium + legs[2].entry_premium
        max_profit = (wing_width - abs(net_debit)) * 1000
        max_loss = abs(net_debit) * 1000
        
        net_delta = sum(leg.contract.delta * leg.quantity for leg in legs)
        net_gamma = sum(leg.contract.gamma * abs(leg.quantity) for leg in legs)
        net_theta = sum(leg.contract.theta * leg.quantity for leg in legs)
        net_vega = sum(leg.contract.vega * leg.quantity for leg in legs)
        
        strategy = OptionStrategy(
            name=f"Butterfly {symbol} {option_type.value.upper()} {lower_strike}/{center_strike}/{upper_strike}",
            strategy_type=StrategyType.BULL_CALL_SPREAD if option_type == OptionType.CALL else StrategyType.BEAR_PUT_SPREAD,
            legs=legs,
            underlying_price=underlying_price,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakeven_points=[lower_strike + abs(net_debit), upper_strike - abs(net_debit)],
            net_delta=round(net_delta, 4),
            net_gamma=round(net_gamma, 6),
            net_theta=round(net_theta, 4),
            net_vega=round(net_vega, 4),
        )
        
        self._strategies.append(strategy)
        return strategy

    def create_calendar_spread(
        self,
        symbol: str,
        underlying_price: float,
        strike: Optional[float] = None,
        option_type: OptionType = OptionType.CALL,
        near_expiry_days: int = 30,
        far_expiry_days: int = 60
    ) -> OptionStrategy:
        """
        Create a Calendar Spread (Time Spread)
        Sell near-term option, buy far-term option at same strike
        Profits from time decay differential and IV expansion in far leg
        """
        if strike is None:
            strike = round(underlying_price)

        T_near = near_expiry_days / 365
        T_far = far_expiry_days / 365
        iv = 0.25
        legs = []

        if option_type == OptionType.CALL:
            near_premium = self.bs.call_price(underlying_price, strike, T_near, self.risk_free_rate, iv)
            near_opt = OptionContract(
                symbol=symbol, option_type=OptionType.CALL, strike=strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=near_expiry_days),
                premium=near_premium, implied_vol=iv,
            )
            near_opt.delta = self.bs.delta(underlying_price, strike, T_near, self.risk_free_rate, iv, OptionType.CALL)
            near_opt.gamma = self.bs.gamma(underlying_price, strike, T_near, self.risk_free_rate, iv)
            near_opt.theta = self.bs.theta(underlying_price, strike, T_near, self.risk_free_rate, iv, OptionType.CALL)
            near_opt.vega = self.bs.vega(underlying_price, strike, T_near, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=near_opt, quantity=-1, entry_premium=near_premium, current_premium=near_premium))

            far_premium = self.bs.call_price(underlying_price, strike, T_far, self.risk_free_rate, iv)
            far_opt = OptionContract(
                symbol=symbol, option_type=OptionType.CALL, strike=strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=far_expiry_days),
                premium=far_premium, implied_vol=iv,
            )
            far_opt.delta = self.bs.delta(underlying_price, strike, T_far, self.risk_free_rate, iv, OptionType.CALL)
            far_opt.gamma = self.bs.gamma(underlying_price, strike, T_far, self.risk_free_rate, iv)
            far_opt.theta = self.bs.theta(underlying_price, strike, T_far, self.risk_free_rate, iv, OptionType.CALL)
            far_opt.vega = self.bs.vega(underlying_price, strike, T_far, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=far_opt, quantity=1, entry_premium=far_premium, current_premium=far_premium))
        else:
            near_premium = self.bs.put_price(underlying_price, strike, T_near, self.risk_free_rate, iv)
            near_opt = OptionContract(
                symbol=symbol, option_type=OptionType.PUT, strike=strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=near_expiry_days),
                premium=near_premium, implied_vol=iv,
            )
            near_opt.delta = self.bs.delta(underlying_price, strike, T_near, self.risk_free_rate, iv, OptionType.PUT)
            near_opt.gamma = self.bs.gamma(underlying_price, strike, T_near, self.risk_free_rate, iv)
            near_opt.theta = self.bs.theta(underlying_price, strike, T_near, self.risk_free_rate, iv, OptionType.PUT)
            near_opt.vega = self.bs.vega(underlying_price, strike, T_near, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=near_opt, quantity=-1, entry_premium=near_premium, current_premium=near_premium))

            far_premium = self.bs.put_price(underlying_price, strike, T_far, self.risk_free_rate, iv)
            far_opt = OptionContract(
                symbol=symbol, option_type=OptionType.PUT, strike=strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=far_expiry_days),
                premium=far_premium, implied_vol=iv,
            )
            far_opt.delta = self.bs.delta(underlying_price, strike, T_far, self.risk_free_rate, iv, OptionType.PUT)
            far_opt.gamma = self.bs.gamma(underlying_price, strike, T_far, self.risk_free_rate, iv)
            far_opt.theta = self.bs.theta(underlying_price, strike, T_far, self.risk_free_rate, iv, OptionType.PUT)
            far_opt.vega = self.bs.vega(underlying_price, strike, T_far, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=far_opt, quantity=1, entry_premium=far_premium, current_premium=far_premium))

        net_debit = far_premium - near_premium
        max_profit = near_premium * 1000
        max_loss = net_debit * 1000

        net_delta = sum(leg.contract.delta * leg.quantity for leg in legs)
        net_gamma = sum(leg.contract.gamma * abs(leg.quantity) for leg in legs)
        net_theta = sum(leg.contract.theta * leg.quantity for leg in legs)
        net_vega = sum(leg.contract.vega * leg.quantity for leg in legs)

        strategy = OptionStrategy(
            name=f"Calendar {symbol} {option_type.value.upper()} @ {strike} ({near_expiry_days}d/{far_expiry_days}d)",
            strategy_type=StrategyType.STRADDLE,
            legs=legs,
            underlying_price=underlying_price,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakeven_points=[strike - net_debit * 0.5, strike + net_debit * 0.5],
            net_delta=round(net_delta, 4),
            net_gamma=round(net_gamma, 6),
            net_theta=round(net_theta, 4),
            net_vega=round(net_vega, 4),
        )
        self._strategies.append(strategy)
        return strategy

    def create_ratio_spread(
        self,
        symbol: str,
        underlying_price: float,
        option_type: OptionType = OptionType.CALL,
        long_strike: Optional[float] = None,
        short_strike: Optional[float] = None,
        ratio: int = 2,
        expiry_days: int = 30
    ) -> OptionStrategy:
        """
        Create a Ratio Spread (1xN)
        Buy 1 option, sell N options at different strike
        """
        if option_type == OptionType.CALL:
            if long_strike is None:
                long_strike = round(underlying_price)
            if short_strike is None:
                short_strike = round(underlying_price * 1.05, 2)
        else:
            if long_strike is None:
                long_strike = round(underlying_price)
            if short_strike is None:
                short_strike = round(underlying_price * 0.95, 2)

        T = expiry_days / 365
        iv = 0.25
        legs = []

        if option_type == OptionType.CALL:
            long_premium = self.bs.call_price(underlying_price, long_strike, T, self.risk_free_rate, iv)
            long_opt = OptionContract(
                symbol=symbol, option_type=OptionType.CALL, strike=long_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=long_premium, implied_vol=iv,
            )
            long_opt.delta = self.bs.delta(underlying_price, long_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            long_opt.gamma = self.bs.gamma(underlying_price, long_strike, T, self.risk_free_rate, iv)
            long_opt.theta = self.bs.theta(underlying_price, long_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            long_opt.vega = self.bs.vega(underlying_price, long_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=long_opt, quantity=1, entry_premium=long_premium, current_premium=long_premium))

            short_premium = self.bs.call_price(underlying_price, short_strike, T, self.risk_free_rate, iv)
            short_opt = OptionContract(
                symbol=symbol, option_type=OptionType.CALL, strike=short_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=short_premium, implied_vol=iv,
            )
            short_opt.delta = self.bs.delta(underlying_price, short_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            short_opt.gamma = self.bs.gamma(underlying_price, short_strike, T, self.risk_free_rate, iv)
            short_opt.theta = self.bs.theta(underlying_price, short_strike, T, self.risk_free_rate, iv, OptionType.CALL)
            short_opt.vega = self.bs.vega(underlying_price, short_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=short_opt, quantity=-ratio, entry_premium=short_premium, current_premium=short_premium))
        else:
            long_premium = self.bs.put_price(underlying_price, long_strike, T, self.risk_free_rate, iv)
            long_opt = OptionContract(
                symbol=symbol, option_type=OptionType.PUT, strike=long_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=long_premium, implied_vol=iv,
            )
            long_opt.delta = self.bs.delta(underlying_price, long_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            long_opt.gamma = self.bs.gamma(underlying_price, long_strike, T, self.risk_free_rate, iv)
            long_opt.theta = self.bs.theta(underlying_price, long_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            long_opt.vega = self.bs.vega(underlying_price, long_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=long_opt, quantity=1, entry_premium=long_premium, current_premium=long_premium))

            short_premium = self.bs.put_price(underlying_price, short_strike, T, self.risk_free_rate, iv)
            short_opt = OptionContract(
                symbol=symbol, option_type=OptionType.PUT, strike=short_strike,
                expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
                premium=short_premium, implied_vol=iv,
            )
            short_opt.delta = self.bs.delta(underlying_price, short_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            short_opt.gamma = self.bs.gamma(underlying_price, short_strike, T, self.risk_free_rate, iv)
            short_opt.theta = self.bs.theta(underlying_price, short_strike, T, self.risk_free_rate, iv, OptionType.PUT)
            short_opt.vega = self.bs.vega(underlying_price, short_strike, T, self.risk_free_rate, iv)
            legs.append(OptionPosition(contract=short_opt, quantity=-ratio, entry_premium=short_premium, current_premium=short_premium))

        net_credit = ratio * short_premium - long_premium
        spread_width = abs(short_strike - long_strike)

        if net_credit > 0:
            max_profit = (net_credit + spread_width) * 1000
            max_loss = None
        else:
            max_profit = spread_width * 1000
            max_loss = abs(net_credit) * 1000

        net_delta = sum(leg.contract.delta * leg.quantity for leg in legs)
        net_gamma = sum(leg.contract.gamma * abs(leg.quantity) for leg in legs)
        net_theta = sum(leg.contract.theta * leg.quantity for leg in legs)
        net_vega = sum(leg.contract.vega * leg.quantity for leg in legs)

        if option_type == OptionType.CALL:
            be_lower = long_strike + abs(net_credit) if net_credit < 0 else long_strike
            be_upper = short_strike + spread_width / (ratio - 1) if ratio > 1 else short_strike + spread_width
        else:
            be_upper = long_strike - abs(net_credit) if net_credit < 0 else long_strike
            be_lower = short_strike - spread_width / (ratio - 1) if ratio > 1 else short_strike - spread_width

        strategy = OptionStrategy(
            name=f"Ratio {symbol} {option_type.value.upper()} 1x{ratio} {long_strike}/{short_strike}",
            strategy_type=StrategyType.BULL_CALL_SPREAD if option_type == OptionType.CALL else StrategyType.BEAR_PUT_SPREAD,
            legs=legs,
            underlying_price=underlying_price,
            max_profit=round(max_profit, 2) if max_profit else None,
            max_loss=round(max_loss, 2) if max_loss else None,
            breakeven_points=[round(be_lower, 2), round(be_upper, 2)],
            net_delta=round(net_delta, 4),
            net_gamma=round(net_gamma, 6),
            net_theta=round(net_theta, 4),
            net_vega=round(net_vega, 4),
        )
        self._strategies.append(strategy)
        return strategy



class OptionsBacktester:
    """Backtester for options strategies"""
    
    def __init__(self, risk_free_rate: float = 0.045):
        self.risk_free_rate = risk_free_rate
        self.bs = BlackScholesModel()
    
    def backtest_strategy(
        self,
        strategy_type: str,
        symbol: str,
        price_history: List[Dict],
        vol_history: List[float],
        entry_iv_percentile: float = 50,
        exit_days_before_expiry: int = 7,
        num_simulations: int = 100
    ) -> Dict:
        """
        Backtest an options strategy across historical price/vol data
        """
        
        if len(price_history) < 30:
            return {"error": "Insufficient price history"}
        
        results = []
        
        for sim in range(min(num_simulations, len(price_history) - 30)):
            # Entry point
            entry_idx = random.randint(0, len(price_history) - 31)
            entry_price = price_history[entry_idx].get("close", 75.0)
            entry_iv = vol_history[entry_idx] if entry_idx < len(vol_history) else 0.25
            
            # Exit point (30 days later or near expiry)
            exit_idx = min(entry_idx + 30 - exit_days_before_expiry, len(price_history) - 1)
            exit_price = price_history[exit_idx].get("close", entry_price)
            exit_iv = vol_history[exit_idx] if exit_idx < len(vol_history) else entry_iv * 0.9
            
            # Calculate strategy P&L
            pnl = self._calculate_strategy_pnl(
                strategy_type, entry_price, exit_price, entry_iv, exit_iv,
                30, 30 - (exit_idx - entry_idx)
            )
            
            results.append({
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "entry_iv": float(entry_iv),
                "exit_iv": float(exit_iv),
                "price_change_pct": float((exit_price - entry_price) / entry_price * 100) if entry_price != 0 else 0.0,
                "iv_change_pct": float((exit_iv - entry_iv) / entry_iv * 100) if entry_iv != 0 else 0.0,
                "pnl": float(pnl),
                "is_winner": bool(pnl > 0),
            })
        
        # Calculate statistics
        if not results:
            return {"error": "No simulations completed"}
        
        wins = [r for r in results if r["is_winner"]]
        losses = [r for r in results if not r["is_winner"]]
        
        total_pnl = sum(r["pnl"] for r in results)
        avg_pnl = total_pnl / len(results)
        win_rate = len(wins) / len(results) if results else 0
        
        avg_win = sum(r["pnl"] for r in wins) / len(wins) if wins else 0
        avg_loss = sum(r["pnl"] for r in losses) / len(losses) if losses else 0
        
        profit_factor = abs(sum(r["pnl"] for r in wins) / sum(r["pnl"] for r in losses)) if losses and sum(r["pnl"] for r in losses) != 0 else float('inf')
        
        # Analyze best conditions
        best_conditions = self._analyze_best_conditions(results)
        
        return {
            "strategy_type": strategy_type,
            "symbol": symbol,
            "num_trades": len(results),
            "win_rate": round(win_rate * 100, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_per_trade": round(avg_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞",
            "max_win": round(max(r["pnl"] for r in results), 2),
            "max_loss": round(min(r["pnl"] for r in results), 2),
            "best_conditions": best_conditions,
            "sample_trades": results[:10],
        }
    
    def _calculate_strategy_pnl(
        self,
        strategy_type: str,
        entry_price: float,
        exit_price: float,
        entry_iv: float,
        exit_iv: float,
        entry_dte: int,
        exit_dte: int
    ) -> float:
        """Calculate P&L for a specific strategy"""
        
        T_entry = entry_dte / 365
        T_exit = exit_dte / 365
        
        if strategy_type == "straddle":
            # Long straddle: long ATM call + long ATM put
            strike = round(entry_price)
            
            entry_call = self.bs.call_price(entry_price, strike, T_entry, self.risk_free_rate, entry_iv)
            entry_put = self.bs.put_price(entry_price, strike, T_entry, self.risk_free_rate, entry_iv)
            entry_cost = entry_call + entry_put
            
            exit_call = self.bs.call_price(exit_price, strike, T_exit, self.risk_free_rate, exit_iv)
            exit_put = self.bs.put_price(exit_price, strike, T_exit, self.risk_free_rate, exit_iv)
            exit_value = exit_call + exit_put
            
            return (exit_value - entry_cost) * 1000
        
        elif strategy_type == "strangle":
            call_strike = round(entry_price * 1.05, 2)
            put_strike = round(entry_price * 0.95, 2)
            
            entry_call = self.bs.call_price(entry_price, call_strike, T_entry, self.risk_free_rate, entry_iv)
            entry_put = self.bs.put_price(entry_price, put_strike, T_entry, self.risk_free_rate, entry_iv)
            entry_cost = entry_call + entry_put
            
            exit_call = self.bs.call_price(exit_price, call_strike, T_exit, self.risk_free_rate, exit_iv)
            exit_put = self.bs.put_price(exit_price, put_strike, T_exit, self.risk_free_rate, exit_iv)
            exit_value = exit_call + exit_put
            
            return (exit_value - entry_cost) * 1000
        
        elif strategy_type == "iron_condor":
            # Short iron condor profits from low volatility
            put_sell = round(entry_price * 0.95, 2)
            put_buy = round(entry_price * 0.90, 2)
            call_sell = round(entry_price * 1.05, 2)
            call_buy = round(entry_price * 1.10, 2)
            
            # Entry credit
            entry_credit = (
                self.bs.put_price(entry_price, put_sell, T_entry, self.risk_free_rate, entry_iv) -
                self.bs.put_price(entry_price, put_buy, T_entry, self.risk_free_rate, entry_iv) +
                self.bs.call_price(entry_price, call_sell, T_entry, self.risk_free_rate, entry_iv) -
                self.bs.call_price(entry_price, call_buy, T_entry, self.risk_free_rate, entry_iv)
            )
            
            # Exit cost
            exit_cost = (
                self.bs.put_price(exit_price, put_sell, T_exit, self.risk_free_rate, exit_iv) -
                self.bs.put_price(exit_price, put_buy, T_exit, self.risk_free_rate, exit_iv) +
                self.bs.call_price(exit_price, call_sell, T_exit, self.risk_free_rate, exit_iv) -
                self.bs.call_price(exit_price, call_buy, T_exit, self.risk_free_rate, exit_iv)
            )
            
            return (entry_credit - exit_cost) * 1000
        
        elif strategy_type == "butterfly":
            strike = round(entry_price)
            lower = strike - 2.5
            upper = strike + 2.5
            
            entry_cost = (
                self.bs.call_price(entry_price, lower, T_entry, self.risk_free_rate, entry_iv) -
                2 * self.bs.call_price(entry_price, strike, T_entry, self.risk_free_rate, entry_iv) +
                self.bs.call_price(entry_price, upper, T_entry, self.risk_free_rate, entry_iv)
            )
            
            exit_value = (
                self.bs.call_price(exit_price, lower, T_exit, self.risk_free_rate, exit_iv) -
                2 * self.bs.call_price(exit_price, strike, T_exit, self.risk_free_rate, exit_iv) +
                self.bs.call_price(exit_price, upper, T_exit, self.risk_free_rate, exit_iv)
            )
            
            return (exit_value - entry_cost) * 1000

        elif strategy_type == "calendar_spread":
            # Calendar Spread: sell near-term, buy far-term (same strike)
            strike = round(entry_price)
            T_near_entry = T_entry
            T_far_entry = T_entry + 30 / 365  # Far leg is 30 days more
            T_near_exit = T_exit
            T_far_exit = T_exit + 30 / 365

            near_entry = self.bs.call_price(entry_price, strike, T_near_entry, self.risk_free_rate, entry_iv)
            far_entry = self.bs.call_price(entry_price, strike, T_far_entry, self.risk_free_rate, entry_iv)
            entry_debit = far_entry - near_entry

            near_exit = self.bs.call_price(exit_price, strike, T_near_exit, self.risk_free_rate, exit_iv)
            far_exit = self.bs.call_price(exit_price, strike, T_far_exit, self.risk_free_rate, exit_iv)
            exit_value = far_exit - near_exit

            return (exit_value - entry_debit) * 1000

        elif strategy_type == "ratio_spread":
            # Call Ratio Spread: Buy 1 ATM call, Sell 2 OTM calls
            long_strike = round(entry_price)
            short_strike = round(entry_price * 1.05, 2)

            entry_long = self.bs.call_price(entry_price, long_strike, T_entry, self.risk_free_rate, entry_iv)
            entry_short = self.bs.call_price(entry_price, short_strike, T_entry, self.risk_free_rate, entry_iv)
            entry_cost = entry_long - 2 * entry_short

            exit_long = self.bs.call_price(exit_price, long_strike, T_exit, self.risk_free_rate, exit_iv)
            exit_short = self.bs.call_price(exit_price, short_strike, T_exit, self.risk_free_rate, exit_iv)
            exit_value = exit_long - 2 * exit_short

            return (exit_value - entry_cost) * 1000
        
        return 0.0
    
    def _analyze_best_conditions(self, results: List[Dict]) -> Dict:
        """Analyze which market conditions produce best results"""
        
        if not results:
            return {}
        
        # Separate by price movement
        up_moves = [r for r in results if r["price_change_pct"] > 2]
        down_moves = [r for r in results if r["price_change_pct"] < -2]
        sideways = [r for r in results if -2 <= r["price_change_pct"] <= 2]
        
        # Separate by IV change
        iv_up = [r for r in results if r["iv_change_pct"] > 10]
        iv_down = [r for r in results if r["iv_change_pct"] < -10]
        iv_stable = [r for r in results if -10 <= r["iv_change_pct"] <= 10]
        
        def avg_pnl(lst):
            return round(sum(r["pnl"] for r in lst) / len(lst), 2) if lst else 0
        
        return {
            "price_up_avg_pnl": avg_pnl(up_moves),
            "price_down_avg_pnl": avg_pnl(down_moves),
            "price_sideways_avg_pnl": avg_pnl(sideways),
            "iv_increase_avg_pnl": avg_pnl(iv_up),
            "iv_decrease_avg_pnl": avg_pnl(iv_down),
            "iv_stable_avg_pnl": avg_pnl(iv_stable),
            "best_scenario": self._determine_best_scenario(up_moves, down_moves, sideways, iv_up, iv_down, iv_stable),
        }
    
    def _determine_best_scenario(self, up, down, sideways, iv_up, iv_down, iv_stable) -> str:
        scenarios = {
            "Large price moves (up or down)": sum(r["pnl"] for r in up + down) / max(1, len(up + down)),
            "Sideways/range-bound market": sum(r["pnl"] for r in sideways) / max(1, len(sideways)),
            "Rising volatility": sum(r["pnl"] for r in iv_up) / max(1, len(iv_up)),
            "Falling volatility": sum(r["pnl"] for r in iv_down) / max(1, len(iv_down)),
        }
        
        best = max(scenarios, key=scenarios.get)
        return best


# Create global backtester instance
options_backtester = OptionsBacktester()

