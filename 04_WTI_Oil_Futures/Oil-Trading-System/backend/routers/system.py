"""System, market, trading, and misc routes."""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from datetime import datetime, timezone, timedelta
import asyncio

from deps import (
    db, broker, risk_service, regime_service, signal_service, multi_asset_generator,
    portfolio_analyzer, calendar_service, ml_service, real_data_service,
    notification_service, tradovate_service, risk_control, system_state,
    get_optional_user, logger
)
from multi_asset import ASSETS
from models import RegimeOverrideRequest, BacktestConfig, ExitReason, TradeRecord
from notification_service import NotificationType
from backtest_engine import BacktestEngine, generate_historical_data

router = APIRouter()

# These mutable globals are accessed via deps module
import deps


async def save_trade_to_db(trade: TradeRecord, user_id=None):
    trade_doc = trade.model_dump()
    trade_doc["user_id"] = user_id
    trade_doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.trades.insert_one(trade_doc)


async def get_user_trades(user_id, limit=100):
    trades = await db.trades.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return trades


# --- Root ---
@router.get("/")
async def root():
    return {"message": "WTI AI Trading Platform API", "version": "2.0.0"}


# --- System ---
@router.get("/system/status")
async def get_system_status():
    return {
        "is_running": deps.simulation_running,
        "mode": system_state.mode,
        "current_symbol": deps.current_symbol,
        "current_regime": regime_service.current.value,
        "regime_override": regime_service._human_override.value if regime_service._human_override else None,
        "override_reason": regime_service._human_override_reason,
        "equity": broker.equity,
        "daily_pnl": risk_service.state.daily_pnl,
        "is_halted": risk_service.state.is_halted,
        "kill_switch": risk_service.state.kill_switch_active,
        "open_positions": len(broker.open_positions),
        "total_trades": len(broker.trade_records),
        "available_assets": list(ASSETS.keys()),
    }

@router.post("/system/start")
async def start_system():
    if deps.simulation_running:
        return {"message": "System already running"}
    deps.simulation_running = True
    # Import the simulation loop from server (set at app startup)
    from server import market_simulation_loop
    deps.simulation_task = asyncio.create_task(market_simulation_loop())
    return {"message": "System started", "status": "running"}

@router.post("/system/stop")
async def stop_system():
    deps.simulation_running = False
    return {"message": "System stopped", "status": "stopped"}

@router.post("/system/mode/{mode}")
async def set_mode(mode: str):
    if mode not in ["paper", "live"]:
        raise HTTPException(status_code=400, detail="Mode must be 'paper' or 'live'")
    system_state.mode = mode
    return {"message": f"Mode set to {mode}", "mode": mode}

@router.post("/system/symbol/{symbol}")
async def set_symbol(symbol: str):
    if symbol not in ASSETS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Available: {list(ASSETS.keys())}")
    deps.current_symbol = symbol
    return {"message": f"Symbol set to {symbol}", "symbol": symbol}


# --- Assets ---
@router.get("/assets")
async def get_assets():
    return multi_asset_generator.get_asset_info()

@router.get("/assets/correlations")
async def get_correlations():
    return multi_asset_generator.get_correlation_matrix()

@router.get("/assets/{symbol}")
async def get_asset(symbol: str):
    if symbol not in ASSETS:
        raise HTTPException(status_code=404, detail="Asset not found")
    tick = multi_asset_generator.generate_tick(symbol)
    indicators = multi_asset_generator.generate_indicators(symbol)
    config = ASSETS[symbol]
    return {
        "symbol": symbol, "name": config.name, "exchange": config.exchange,
        "price": tick.last, "bid": tick.bid, "ask": tick.ask,
        "spread": round(tick.spread, 4),
        "indicators": {"ema_fast": indicators.ema_fast, "ema_slow": indicators.ema_slow, "adx": indicators.adx, "atr": indicators.atr, "volatility_ratio": indicators.volatility_ratio}
    }


# --- Portfolio ---
@router.get("/portfolio/analysis")
async def get_portfolio_analysis():
    positions_value = {}
    for pos in broker.open_positions:
        symbol = pos.symbol
        value = pos.current_price * pos.quantity * ASSETS.get(symbol, ASSETS["CL"]).contract_size
        positions_value[symbol] = positions_value.get(symbol, 0) + value
    var_95 = portfolio_analyzer.calculate_portfolio_var(positions_value, 0.95, 1)
    var_99 = portfolio_analyzer.calculate_portfolio_var(positions_value, 0.99, 1)
    spread_opportunity = portfolio_analyzer.calculate_spread_opportunity()
    return {
        "positions_value": positions_value, "total_value": sum(positions_value.values()),
        "var_95_1d": var_95, "var_99_1d": var_99,
        "spread_opportunity": spread_opportunity,
        "correlations": multi_asset_generator.get_correlation_matrix(),
    }


# --- Risk ---
@router.post("/risk/kill-switch")
async def activate_kill_switch(request: Request):
    user = await get_optional_user(request)
    risk_service.activate_kill_switch(f"API request by {user['email'] if user else 'anonymous'}")
    for pos in broker.open_positions:
        record = broker.close_position(pos.id, ExitReason.RISK_CONTROL)
        if record:
            await save_trade_to_db(record, user["_id"] if user else None)
    return {"message": "KILL SWITCH ACTIVATED", "positions_closed": len(broker.open_positions), "status": "halted"}

@router.post("/risk/reset")
async def reset_risk():
    success = risk_service.reset_halt()
    if success:
        return {"message": "Risk halt reset", "status": "active"}
    return {"message": "Cannot reset - kill switch is active", "status": "blocked"}

@router.get("/risk/state")
async def get_risk_state():
    return {
        "daily_pnl": round(risk_service.state.daily_pnl, 2),
        "daily_loss_pct": round(risk_service.state.daily_loss_used_pct * 100, 2),
        "consecutive_losses": risk_service.state.consecutive_losses,
        "total_trades_today": risk_service.state.total_trades_today,
        "is_halted": risk_service.state.is_halted,
        "halt_reason": risk_service.state.halt_reason,
        "kill_switch_active": risk_service.state.kill_switch_active,
    }


# --- Regime ---
@router.get("/regime/current")
async def get_current_regime():
    return regime_service.summary

@router.post("/regime/override")
async def set_regime_override(request_data: RegimeOverrideRequest):
    regime_service.set_human_override(regime=request_data.regime, reason=request_data.reason, duration_hours=request_data.duration_hours)
    return {"message": f"Regime override set to {request_data.regime.value}", "reason": request_data.reason, "expires_in_hours": request_data.duration_hours}

@router.post("/regime/clear-override")
async def clear_regime_override():
    regime_service.clear_human_override()
    return {"message": "Regime override cleared", "current_regime": regime_service.current.value}


# --- Positions & Trades ---
@router.get("/positions")
async def get_positions():
    return [
        {"id": p.id, "symbol": p.symbol, "direction": p.direction.value, "quantity": p.quantity, "entry_price": p.entry_price, "current_price": p.current_price, "stop_loss": p.stop_loss_price, "unrealized_pnl": round(p.unrealized_pnl, 2), "opened_at": p.opened_at.isoformat()}
        for p in broker.open_positions
    ]

@router.post("/positions/{position_id}/close")
async def close_position(position_id: str, request: Request):
    user = await get_optional_user(request)
    record = broker.close_position(position_id, ExitReason.MANUAL)
    if record:
        risk_service.register_trade_result(record.pnl_usd, broker.equity)
        await save_trade_to_db(record, user["_id"] if user else None)
        return {"message": "Position closed", "pnl": record.pnl_usd, "exit_price": record.exit_price}
    raise HTTPException(status_code=404, detail="Position not found")

@router.get("/trades")
async def get_trades(request: Request, limit: int = 50):
    user = await get_optional_user(request)
    if user:
        db_trades = await get_user_trades(user["_id"], limit)
        if db_trades:
            return db_trades
    records = broker.trade_records[-limit:]
    return [
        {"id": r.id, "date": r.date, "symbol": r.symbol, "direction": r.direction, "entry_price": r.entry_price, "exit_price": r.exit_price, "quantity": r.quantity, "pnl": r.pnl_usd, "hold_minutes": r.hold_minutes, "exit_reason": r.exit_reason}
        for r in reversed(records)
    ]

@router.get("/trades/summary")
async def get_trade_summary():
    return broker.get_summary()


# --- Market Data ---
@router.get("/market/current")
async def get_current_market():
    tick = multi_asset_generator.generate_tick(deps.current_symbol)
    indicators = multi_asset_generator.generate_indicators(deps.current_symbol)
    return {
        "symbol": deps.current_symbol,
        "timestamp": tick.timestamp.isoformat(),
        "price": tick.last, "bid": tick.bid, "ask": tick.ask,
        "spread": round(tick.spread, 4),
        "indicators": {"ema_fast": indicators.ema_fast, "ema_slow": indicators.ema_slow, "adx": indicators.adx, "atr": indicators.atr, "volatility_ratio": indicators.volatility_ratio, "volume_ratio": indicators.volume_ratio, "vwap": indicators.vwap}
    }

@router.get("/market/history")
async def get_market_history(symbol: Optional[str] = None, bars: int = 100):
    sym = symbol or deps.current_symbol
    if sym not in ASSETS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    recent_bars = multi_asset_generator.bars.get(sym, [])[-bars:]
    return [{"timestamp": b.timestamp.isoformat(), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in recent_bars]


# --- Calendar ---
@router.get("/calendar/events")
async def get_calendar_events(days: int = 7):
    events = calendar_service.get_upcoming_events(days)
    return [{"id": e.id, "event_name": e.event_name, "country": e.country, "date": e.date.isoformat(), "importance": e.importance, "actual": e.actual, "forecast": e.forecast, "previous": e.previous, "event_type": e.event_type} for e in events]

@router.post("/calendar/trigger/{event_id}")
async def trigger_calendar_event(event_id: str):
    market_event = calendar_service.trigger_event(event_id)
    if market_event:
        tick = multi_asset_generator.generate_tick(deps.current_symbol)
        regime_service.on_market_event(market_event, 60)
        signal_service.on_event(market_event, tick)
        for symbol in ASSETS.keys():
            multi_asset_generator.set_trend(symbol, "up" if market_event.surprise_pct > 0 else "down")
        return {"message": "Event triggered", "event": market_event.headline, "priority": market_event.priority.value, "regime": regime_service.current.value}
    raise HTTPException(status_code=404, detail="Event not found")


# --- ML ---
@router.get("/ml/prediction")
async def get_ml_prediction():
    tick = multi_asset_generator.generate_tick(deps.current_symbol)
    indicators = multi_asset_generator.generate_indicators(deps.current_symbol)
    prediction = await ml_service.analyze_market(indicators=indicators, current_price=tick.last, current_regime=regime_service.current)
    return {"predicted_regime": prediction.predicted_regime.value, "confidence": prediction.confidence, "signal_direction": prediction.signal_direction.value if prediction.signal_direction else None, "signal_confidence": prediction.signal_confidence, "reasoning": prediction.reasoning}

@router.post("/ml/insight")
async def get_ml_insight(question: dict):
    insight = await ml_service.get_market_insight(question.get("question", ""))
    return {"insight": insight}


# --- Backtest ---
@router.post("/backtest/run")
async def run_backtest(config: BacktestConfig, request: Request):
    user = await get_optional_user(request)
    bars, events = generate_historical_data(start_date=config.start_date, end_date=config.end_date, include_events=True)
    engine = BacktestEngine(config)
    result = engine.run(bars, events)
    result_doc = {
        "config": config.model_dump(), "final_equity": result.final_equity,
        "total_trades": result.total_trades, "win_rate": result.win_rate,
        "profit_factor": result.profit_factor, "max_drawdown": result.max_drawdown,
        "sharpe_ratio": result.sharpe_ratio, "user_id": user["_id"] if user else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.backtest_results.insert_one(result_doc)
    return {
        "final_equity": result.final_equity, "total_trades": result.total_trades,
        "win_rate": round(result.win_rate * 100, 1), "profit_factor": round(result.profit_factor, 2),
        "max_drawdown": round(result.max_drawdown * 100, 1), "sharpe_ratio": round(result.sharpe_ratio, 2),
        "return_pct": round((result.final_equity - config.initial_equity) / config.initial_equity * 100, 1),
        "equity_curve": result.equity_curve[-50:], "trades": result.trade_records[-20:],
    }

@router.get("/backtest/history")
async def get_backtest_history(request: Request, limit: int = 10):
    user = await get_optional_user(request)
    query = {}
    if user:
        query["user_id"] = user["_id"]
    results = await db.backtest_results.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return results


# --- Notifications ---
@router.get("/notifications")
async def get_notifications(request: Request, limit: int = 50, unread_only: bool = False):
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    notifications = await notification_service.get_notifications(user_id, limit, unread_only)
    unread_count = await notification_service.get_unread_count(user_id)
    return {"notifications": notifications, "unread_count": unread_count}

@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, request: Request):
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    success = await notification_service.mark_read(notification_id, user_id)
    return {"success": success}

@router.post("/notifications/read-all")
async def mark_all_notifications_read(request: Request):
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    count = await notification_service.mark_all_read(user_id)
    return {"marked_read": count}

@router.post("/notifications/test")
async def send_test_notification(request: Request):
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    notif = await notification_service.send_notification(
        user_id=user_id, notification_type=NotificationType.SYSTEM,
        title="Test Notification",
        message="Push notifications are working. You will receive alerts for trade signals, regime changes, and risk warnings.",
        severity="info",
    )
    return notif.to_dict()


# --- Tradovate ---
@router.get("/tradovate/status")
async def get_tradovate_status():
    return tradovate_service.get_status()


# --- Real Data ---
@router.get("/realdata/prices")
async def get_real_prices():
    prices = await real_data_service.get_current_prices()
    return {"is_real_data": real_data_service.is_using_real_data, "prices": prices, "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/realdata/calendar")
async def get_real_calendar(days: int = 14):
    events = await real_data_service.get_economic_calendar(days)
    return {"is_real_data": real_data_service.is_using_real_data, "events": events}

@router.get("/realdata/inventory")
async def get_inventory_data():
    return await real_data_service.get_inventory_update()


# --- PnL ---
@router.get("/pnl/realtime")
async def get_realtime_pnl(request: Request):
    user = await get_optional_user(request)
    positions_pnl = [
        {"position_id": pos.id, "symbol": pos.symbol, "direction": pos.direction.value, "entry_price": pos.entry_price, "current_price": pos.current_price, "quantity": pos.quantity, "unrealized_pnl": round(pos.unrealized_pnl, 2)}
        for pos in broker.open_positions
    ]
    today_trades = [t for t in broker.trade_records if t.date == datetime.now(timezone.utc).strftime("%Y-%m-%d")]
    realized_pnl = sum(t.pnl_usd for t in today_trades)
    total_unrealized = sum(p["unrealized_pnl"] for p in positions_pnl)
    pnl_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(), "equity": broker.equity,
        "realized_pnl_today": round(realized_pnl, 2), "unrealized_pnl": round(total_unrealized, 2),
        "total_pnl_today": round(realized_pnl + total_unrealized, 2),
        "positions": positions_pnl, "trades_today": len(today_trades),
    }
    if user:
        pnl_doc = {**pnl_data, "user_id": user["_id"]}
        await db.pnl_history.insert_one(pnl_doc)
    return pnl_data

@router.get("/pnl/history")
async def get_pnl_history(request: Request, days: int = 7):
    user = await get_optional_user(request)
    if not user:
        return {"message": "Login required for P&L history", "history": []}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    history = await db.pnl_history.find(
        {"user_id": user["_id"], "timestamp": {"$gte": cutoff.isoformat()}},
        {"_id": 0}
    ).sort("timestamp", -1).limit(100).to_list(100)
    return {"history": history}
