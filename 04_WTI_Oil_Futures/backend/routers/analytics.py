"""Analytics routes: fragility, events, risk control, execution gate, signal scoring."""
from fastapi import APIRouter, HTTPException

from deps import (
    multi_asset_generator, fragility_engine, event_engine,
    risk_control, execution_gate, signal_scorer, regime_service,
    broker, notification_service
)
from multi_asset import ASSETS
from notification_service import NotificationType

router = APIRouter()


@router.get("/fragility")
async def get_fragility_status():
    indicators = multi_asset_generator.generate_indicators("CL")
    tick_obj = multi_asset_generator.generate_tick("CL")
    current_spread = tick_obj.spread if tick_obj else 0.03
    price_change = 0.0
    bars = multi_asset_generator.bars.get("CL", [])
    if len(bars) >= 2:
        price_change = bars[-1].close - bars[-2].close
    state = fragility_engine.update(
        current_spread=current_spread, current_vol_ratio=indicators.volatility_ratio,
        atr=indicators.atr, price_change=price_change, adx=indicators.adx,
        regime=regime_service.current.value,
        bid_ask_depth=max(0.3, min(1.0, 1.0 - indicators.volatility_ratio * 0.3)),
    )
    return {
        **state.to_dict(),
        "size_multiplier": fragility_engine.get_size_multiplier(),
        "should_halt": fragility_engine.should_halt_trading(),
        "should_reduce": fragility_engine.should_reduce_size(),
    }


@router.get("/events/calendar")
async def get_event_calendar(hours_ahead: int = 48):
    return {"events": event_engine.get_calendar(hours_ahead), "state": event_engine.get_state()}

@router.post("/events/trigger/{event_id}")
async def trigger_event(event_id: str, actual: str = "", direction: str = "neutral"):
    result = event_engine.trigger_event(event_id, actual, direction)
    if result.get("triggered"):
        await notification_service.broadcast_notification(
            notification_type=NotificationType.REGIME_CHANGE,
            title=f"Event: {result['event']['title']}",
            message=f"Direction: {direction}. Cooldown: {result.get('cooldown_minutes', 0)} min",
            severity="warning", data=result["event"],
        )
    return result

@router.get("/events/state")
async def get_event_state():
    return event_engine.get_state()


@router.get("/risk-control/status")
async def get_risk_control_status():
    risk_control.update_equity(broker.equity)
    return risk_control.get_status()

@router.get("/risk-control/rules")
async def get_risk_rules():
    risk_control.update_equity(broker.equity)
    return risk_control.check_rules()

@router.get("/risk-control/exit-tiers")
async def get_exit_tiers(entry_price: float, direction: str = "long", max_loss: float = 2.0):
    return {"entry_price": entry_price, "direction": direction, "tiers": risk_control.get_exit_tiers(entry_price, direction, max_loss)}

@router.get("/risk-control/daily-pnl")
async def get_daily_pnl():
    return {"history": risk_control.get_daily_pnl_history()}

@router.get("/risk-control/slippage")
async def get_slippage_stats():
    return risk_control.get_slippage_stats()


@router.get("/execution-gate/{symbol}")
async def evaluate_execution_gate(symbol: str):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    indicators = multi_asset_generator.generate_indicators(symbol)
    frag_state = fragility_engine.current_state
    risk_status = risk_control.check_rules()
    event_state = event_engine.get_state()
    tick_obj = multi_asset_generator.generate_tick(symbol)
    current_spread = tick_obj.spread if tick_obj else 0.03
    bars = multi_asset_generator.bars.get(symbol, [])
    price_change_pct = 0.0
    if len(bars) >= 2:
        price_change_pct = (bars[-1].close - bars[-2].close) / bars[-2].close * 100
    score_result = signal_scorer.calculate_score(
        ema_fast=indicators.ema_fast, ema_slow=indicators.ema_slow,
        adx=indicators.adx, regime=regime_service.current.value,
        vol_ratio=indicators.volatility_ratio, recent_price_change_pct=price_change_pct,
        spread=current_spread, fragility_score=frag_state.score,
    )
    return execution_gate.evaluate(
        spread=current_spread, adx=indicators.adx,
        vol_ratio=indicators.volatility_ratio, signal_score=score_result["bullish_pct"],
        fragility_score=frag_state.score, risk_can_trade=risk_status["can_trade"],
        cooldown_active=event_state["cooldown_active"], regime=regime_service.current.value,
    )


@router.get("/signal-score/{symbol}")
async def get_signal_score(symbol: str):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    indicators = multi_asset_generator.generate_indicators(symbol)
    frag_state = fragility_engine.current_state
    tick_obj = multi_asset_generator.generate_tick(symbol)
    current_spread = tick_obj.spread if tick_obj else 0.03
    bars = multi_asset_generator.bars.get(symbol, [])
    price_change_pct = 0.0
    if len(bars) >= 2:
        price_change_pct = (bars[-1].close - bars[-2].close) / bars[-2].close * 100
    return signal_scorer.calculate_score(
        ema_fast=indicators.ema_fast, ema_slow=indicators.ema_slow,
        adx=indicators.adx, regime=regime_service.current.value,
        vol_ratio=indicators.volatility_ratio, recent_price_change_pct=price_change_pct,
        spread=current_spread, fragility_score=frag_state.score,
    )
