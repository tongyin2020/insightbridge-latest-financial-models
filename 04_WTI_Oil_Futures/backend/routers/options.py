"""Options trading routes."""
from fastapi import APIRouter, HTTPException
from typing import Optional
import math

from deps import multi_asset_generator, options_service, regime_service, auto_strategy_selector
from multi_asset import ASSETS
from options_service import OptionType, options_backtester
from payoff_calculator import calculate_payoff

router = APIRouter()


@router.get("/options/chain/{symbol}")
async def get_option_chain(symbol: str, expiry_days: int = 30):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    chain = options_service.generate_option_chain(symbol, underlying_price, expiry_days)
    return {
        "symbol": symbol,
        "underlying_price": underlying_price,
        "expiry_days": expiry_days,
        "options": [
            {
                "type": opt.option_type.value, "strike": opt.strike,
                "premium": opt.premium, "iv": opt.implied_vol,
                "delta": opt.delta, "gamma": opt.gamma,
                "theta": opt.theta, "vega": opt.vega,
                "expiry": opt.expiry.isoformat(),
            }
            for opt in chain
        ]
    }


@router.post("/options/strategy/straddle")
async def create_straddle(symbol: str, strike: Optional[float] = None, expiry_days: int = 30):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    strategy = options_service.create_straddle(symbol, underlying_price, strike, expiry_days)
    return {
        "name": strategy.name, "type": strategy.strategy_type.value,
        "underlying_price": strategy.underlying_price,
        "max_loss": strategy.max_loss, "breakeven_points": strategy.breakeven_points,
        "greeks": {"delta": strategy.net_delta, "gamma": strategy.net_gamma, "theta": strategy.net_theta, "vega": strategy.net_vega},
        "legs": [{"type": leg.contract.option_type.value, "strike": leg.contract.strike, "premium": leg.entry_premium} for leg in strategy.legs]
    }


@router.post("/options/strategy/strangle")
async def create_strangle(symbol: str, call_strike: Optional[float] = None, put_strike: Optional[float] = None, expiry_days: int = 30):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    strategy = options_service.create_strangle(symbol, underlying_price, call_strike, put_strike, expiry_days)
    return {
        "name": strategy.name, "type": strategy.strategy_type.value,
        "underlying_price": strategy.underlying_price,
        "max_loss": strategy.max_loss, "breakeven_points": strategy.breakeven_points,
        "greeks": {"delta": strategy.net_delta, "gamma": strategy.net_gamma, "theta": strategy.net_theta, "vega": strategy.net_vega}
    }


@router.get("/options/strategies")
async def get_all_strategies():
    return options_service.get_all_strategies()


@router.post("/options/strategy/iron-condor")
async def create_iron_condor(symbol: str, put_sell_strike: Optional[float] = None, put_buy_strike: Optional[float] = None, call_sell_strike: Optional[float] = None, call_buy_strike: Optional[float] = None, expiry_days: int = 30):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    strategy = options_service.create_iron_condor(symbol, underlying_price, put_sell_strike, put_buy_strike, call_sell_strike, call_buy_strike, expiry_days)
    return {
        "name": strategy.name, "type": strategy.strategy_type.value,
        "underlying_price": strategy.underlying_price,
        "max_profit": strategy.max_profit, "max_loss": strategy.max_loss,
        "breakeven_points": strategy.breakeven_points,
        "greeks": {"delta": strategy.net_delta, "gamma": strategy.net_gamma, "theta": strategy.net_theta, "vega": strategy.net_vega},
        "legs": [{"type": leg.contract.option_type.value, "strike": leg.contract.strike, "quantity": leg.quantity, "premium": leg.entry_premium} for leg in strategy.legs]
    }


@router.post("/options/strategy/butterfly")
async def create_butterfly(symbol: str, option_type: str = "call", center_strike: Optional[float] = None, wing_width: float = 2.5, expiry_days: int = 30):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    opt_type = OptionType.CALL if option_type.lower() == "call" else OptionType.PUT
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    strategy = options_service.create_butterfly(symbol, underlying_price, opt_type, center_strike, wing_width, expiry_days)
    return {
        "name": strategy.name, "type": "butterfly", "option_type": option_type,
        "underlying_price": strategy.underlying_price,
        "max_profit": strategy.max_profit, "max_loss": strategy.max_loss,
        "breakeven_points": strategy.breakeven_points,
        "greeks": {"delta": strategy.net_delta, "gamma": strategy.net_gamma, "theta": strategy.net_theta, "vega": strategy.net_vega},
        "legs": [{"type": leg.contract.option_type.value, "strike": leg.contract.strike, "quantity": leg.quantity, "premium": leg.entry_premium} for leg in strategy.legs]
    }


@router.post("/options/strategy/calendar-spread")
async def create_calendar_spread(symbol: str, option_type: str = "call", strike: Optional[float] = None, near_expiry_days: int = 30, far_expiry_days: int = 60):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    opt_type = OptionType.CALL if option_type.lower() == "call" else OptionType.PUT
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    strategy = options_service.create_calendar_spread(symbol, underlying_price, strike, opt_type, near_expiry_days, far_expiry_days)
    return {
        "name": strategy.name, "type": "calendar_spread", "option_type": option_type,
        "underlying_price": strategy.underlying_price,
        "max_profit": strategy.max_profit, "max_loss": strategy.max_loss,
        "breakeven_points": strategy.breakeven_points,
        "greeks": {"delta": strategy.net_delta, "gamma": strategy.net_gamma, "theta": strategy.net_theta, "vega": strategy.net_vega},
        "legs": [{"type": leg.contract.option_type.value, "strike": leg.contract.strike, "quantity": leg.quantity, "premium": leg.entry_premium, "expiry": leg.contract.expiry.isoformat()} for leg in strategy.legs]
    }


@router.post("/options/strategy/ratio-spread")
async def create_ratio_spread(symbol: str, option_type: str = "call", long_strike: Optional[float] = None, short_strike: Optional[float] = None, ratio: int = 2, expiry_days: int = 30):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    opt_type = OptionType.CALL if option_type.lower() == "call" else OptionType.PUT
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    strategy = options_service.create_ratio_spread(symbol, underlying_price, opt_type, long_strike, short_strike, ratio, expiry_days)
    return {
        "name": strategy.name, "type": "ratio_spread", "option_type": option_type,
        "ratio": f"1x{ratio}",
        "underlying_price": strategy.underlying_price,
        "max_profit": strategy.max_profit, "max_loss": strategy.max_loss,
        "breakeven_points": strategy.breakeven_points,
        "greeks": {"delta": strategy.net_delta, "gamma": strategy.net_gamma, "theta": strategy.net_theta, "vega": strategy.net_vega},
        "legs": [{"type": leg.contract.option_type.value, "strike": leg.contract.strike, "quantity": leg.quantity, "premium": leg.entry_premium} for leg in strategy.legs]
    }


@router.post("/options/backtest")
async def backtest_options_strategy(strategy_type: str, symbol: str, num_simulations: int = 50):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    if strategy_type not in ["straddle", "strangle", "iron_condor", "butterfly", "calendar_spread", "ratio_spread"]:
        raise HTTPException(status_code=400, detail="Invalid strategy type")
    price_history = [{"close": bar.close, "high": bar.high, "low": bar.low} for bar in multi_asset_generator.bars.get(symbol, [])]
    vol_history = []
    for i, bar in enumerate(multi_asset_generator.bars.get(symbol, [])):
        if i > 0:
            daily_return = abs(bar.close - multi_asset_generator.bars[symbol][i-1].close) / multi_asset_generator.bars[symbol][i-1].close
            vol_history.append(daily_return * math.sqrt(252))
        else:
            vol_history.append(0.25)
    return options_backtester.backtest_strategy(strategy_type=strategy_type, symbol=symbol, price_history=price_history, vol_history=vol_history, num_simulations=num_simulations)


@router.get("/options/volatility/{symbol}")
async def get_volatility_analysis(symbol: str):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    indicators = multi_asset_generator.generate_indicators(symbol)
    current_iv = indicators.volatility_ratio * 0.15 + 0.15
    historical_vol = 0.22
    return options_service.analyze_volatility_trade(symbol, underlying_price, current_iv, historical_vol)


@router.get("/options/volatility-surface/{symbol}")
async def get_volatility_surface(symbol: str):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    surface = options_service.get_volatility_surface(symbol, underlying_price)
    return {"symbol": symbol, "underlying_price": underlying_price, **surface}


@router.get("/options/delta-hedge")
async def calculate_delta_hedge(symbol: str):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    option_positions = []
    for strategy in options_service._strategies:
        if strategy.legs and strategy.legs[0].contract.symbol == symbol:
            option_positions.extend(strategy.legs)
    if not option_positions:
        return {"message": "No option positions to hedge", "futures_needed": 0}
    return options_service.calculate_delta_hedge(symbol, underlying_price, option_positions)


@router.get("/options/auto-strategy/{symbol}")
async def get_auto_strategy_recommendation(symbol: str):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    indicators = multi_asset_generator.generate_indicators(symbol)
    current_iv = indicators.volatility_ratio * 0.15 + 0.15
    historical_vol = 0.22
    iv_percentile = options_service._calculate_iv_percentile(current_iv)
    bars = multi_asset_generator.bars.get(symbol, [])
    recent_change = 0.0
    if len(bars) >= 2:
        recent_change = (bars[-1].close - bars[-2].close) / bars[-2].close * 100
    return await auto_strategy_selector.recommend_strategy(
        symbol=symbol, underlying_price=underlying_price,
        current_iv=current_iv, historical_vol=historical_vol, iv_percentile=iv_percentile,
        regime=regime_service.current.value, adx=indicators.adx,
        volatility_ratio=indicators.volatility_ratio, ema_fast=indicators.ema_fast,
        ema_slow=indicators.ema_slow, recent_price_change_pct=recent_change,
    )


@router.get("/options/payoff/{strategy_type}")
async def get_options_payoff(strategy_type: str, symbol: str = "CL", expiry_days: int = 30):
    if strategy_type not in ["straddle", "strangle", "iron_condor", "butterfly", "calendar_spread", "ratio_spread"]:
        raise HTTPException(status_code=400, detail="Invalid strategy type")
    underlying_price = multi_asset_generator.current_prices.get(symbol, 75.0)
    result = calculate_payoff(strategy_type=strategy_type, underlying_price=underlying_price, expiry_days=expiry_days)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
