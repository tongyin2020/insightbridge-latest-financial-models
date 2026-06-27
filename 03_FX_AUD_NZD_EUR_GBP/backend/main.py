"""
FX Trading System - Main FastAPI Application

Provides REST endpoints and WebSocket streaming for a real-time
AUD/USD and NZD/USD trading system.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from database import (
    init_db, get_trades, get_open_trades, get_signals, get_recent_prices,
    get_latest_price, get_upcoming_events, get_all_events, get_all_settings,
    get_setting, set_setting, get_logs, insert_log, insert_event, close_trade,
)
from market_data import MarketDataService
from signal_engine import SignalEngine
from event_engine import EventEngine
from alert_service import AlertService

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fx_main")

# ─── Service instances ────────────────────────────────────────────────────────

market_data = MarketDataService()
event_engine = EventEngine()
signal_engine = SignalEngine(market_data)
alert_service = AlertService()

# ─── Background tasks ────────────────────────────────────────────────────────

_background_tasks: list[asyncio.Task] = []


async def signal_evaluation_loop():
    """Periodically evaluate signals for all pairs."""
    await insert_log("INFO", "main", "Signal evaluation loop started")
    interval = settings.sim_poll_interval if settings.use_simulated_data else settings.api_poll_interval
    # Run signal evaluation slightly offset from price polling
    await asyncio.sleep(interval / 2)

    while True:
        try:
            event_state = event_engine.get_event_state()
            signals = await signal_engine.evaluate_all(event_state)
            for sig in signals:
                if sig.direction != "WAIT" and sig.confidence >= 50:
                    await alert_service.alert_signal(sig.to_dict())
        except Exception as e:
            logger.error(f"Signal evaluation error: {e}")
            await insert_log("ERROR", "signal_engine", f"Evaluation error: {e}")
        await asyncio.sleep(interval)


async def event_calendar_check_loop():
    """Periodically check for upcoming economic events."""
    await insert_log("INFO", "main", "Event calendar check loop started")
    while True:
        try:
            events = await get_upcoming_events(limit=5)
            now = datetime.now(timezone.utc)
            for ev in events:
                event_time = datetime.fromisoformat(ev["datetime"].replace("Z", "+00:00"))
                diff = (event_time - now).total_seconds()
                # If event is within 60 seconds and we're in NORMAL state, trigger pre-event
                if 0 < diff <= 60 and event_engine.state == "NORMAL":
                    impact = ev.get("impact", "C")
                    if impact in ("A", "B"):
                        await event_engine.start_event_cooldown(
                            event_level=impact,
                            title=ev.get("title", "Unknown Event"),
                        )
                        state = event_engine.get_event_state()
                        await alert_service.alert_event_state(state)
                        await market_data.broadcast({"type": "event_state", "data": state})
        except Exception as e:
            logger.error(f"Event calendar check error: {e}")
        await asyncio.sleep(30)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Startup
    await init_db()
    await insert_log("INFO", "main", "FX Trading System starting up")
    source = "simulated" if settings.use_simulated_data else "Twelve Data API"
    await insert_log("INFO", "main", f"Data source: {source}")
    logger.info(f"FX Trading System started - data source: {source}")

    # Start background tasks
    _background_tasks.append(asyncio.create_task(market_data.start_polling()))
    _background_tasks.append(asyncio.create_task(signal_evaluation_loop()))
    _background_tasks.append(asyncio.create_task(event_calendar_check_loop()))

    yield

    # Shutdown
    logger.info("Shutting down FX Trading System...")
    await insert_log("INFO", "main", "FX Trading System shutting down")
    market_data.stop_polling()
    for task in _background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await market_data.shutdown()
    await alert_service.shutdown()


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="FX Trading System",
    description="AUD/USD and NZD/USD trading system with technical analysis, event management, and real-time signals.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic models ─────────────────────────────────────────────────────────


class SettingUpdate(BaseModel):
    value: str


class EventTrigger(BaseModel):
    level: str  # A, B, or C
    title: str = "Manual trigger"


class DirectionConfirm(BaseModel):
    pair: str
    prices_before: list[float] = []
    prices_after: list[float] = []


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """System health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_source": "simulated" if settings.use_simulated_data else "twelvedata",
        "telegram_configured": settings.telegram_configured,
        "pairs": settings.pairs,
        "event_state": event_engine.get_event_state()["state"],
    }


# ─── Prices ──────────────────────────────────────────────────────────────────

def _normalize_pair(pair: str) -> str:
    """Normalize pair format: aud_usd -> AUD/USD"""
    return pair.upper().replace("_", "/").replace("-", "/")


@app.get("/api/prices/{pair}")
async def get_price(pair: str):
    """Get the latest price and indicators for a pair. Use aud_usd or nzd_usd format."""
    pair = _normalize_pair(pair)
    if pair not in settings.pairs:
        raise HTTPException(status_code=404, detail=f"Pair {pair} not supported. Supported: {settings.pairs}")

    latest = await get_latest_price(pair)
    if latest is None:
        # Fetch one now
        result = await market_data.poll_once(pair)
        if result is None:
            raise HTTPException(status_code=503, detail="Unable to fetch price data")
        return {
            "pair": pair,
            "price": result,
            "indicators": {k: v for k, v in result.get("indicators", {}).items() if not k.startswith("_")},
        }

    return {
        "pair": pair,
        "price": {
            "mid": latest["close"],
            "open": latest["open"],
            "high": latest["high"],
            "low": latest["low"],
            "timestamp": latest["timestamp"],
        },
        "indicators": {
            "sma20": latest.get("sma20"),
            "sma50": latest.get("sma50"),
            "adx": latest.get("adx"),
            "atr": latest.get("atr"),
            "rsi": latest.get("rsi"),
        },
    }


@app.get("/api/prices/{pair}/history")
async def get_price_history(pair: str, minutes: int = Query(60, ge=1, le=1440)):
    """Get price history for a pair. Use aud_usd or nzd_usd format."""
    pair = _normalize_pair(pair)
    if pair not in settings.pairs:
        raise HTTPException(status_code=404, detail=f"Pair {pair} not supported")

    # Estimate number of bars needed
    interval = settings.sim_poll_interval if settings.use_simulated_data else settings.api_poll_interval
    limit = max((minutes * 60) // interval, 10)
    prices = await get_recent_prices(pair, limit=int(limit))
    return {"pair": pair, "count": len(prices), "prices": prices}


# ─── Signals ─────────────────────────────────────────────────────────────────

@app.get("/api/signals")
async def list_signals(pair: Optional[str] = None, limit: int = Query(50, ge=1, le=500)):
    """Get recent signals for both pairs."""
    if pair:
        pair = pair.upper().replace("_", "/")
    signals = await get_signals(pair=pair, limit=limit)
    return {"count": len(signals), "signals": signals}


@app.get("/api/signals/current")
async def current_signals():
    """Get the current signal state for both pairs."""
    return {
        "signals": signal_engine.get_all_latest_signals(),
        "event_state": event_engine.get_event_state(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Trades ──────────────────────────────────────────────────────────────────

@app.get("/api/trades")
async def list_trades(
    status: Optional[str] = None,
    pair: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """Get trade history with optional filters."""
    if pair:
        pair = pair.upper().replace("_", "/")
    trades = await get_trades(status=status, pair=pair, limit=limit)
    return {"count": len(trades), "trades": trades}


@app.get("/api/trades/stats")
async def trade_stats():
    """Get trading statistics: win rate, total PnL, avg hold time, etc."""
    all_trades = await get_trades(status="CLOSED", limit=10000)

    if not all_trades:
        return {
            "total_trades": 0,
            "open_trades": len(await get_open_trades()),
            "win_rate": 0.0,
            "total_pnl_pips": 0.0,
            "total_pnl_usd": 0.0,
            "avg_pnl_pips": 0.0,
            "avg_hold_minutes": 0.0,
            "best_trade_pips": 0.0,
            "worst_trade_pips": 0.0,
            "by_pair": {},
        }

    wins = [t for t in all_trades if (t.get("pnl_pips") or 0) > 0]
    total_pnl_pips = sum(t.get("pnl_pips", 0) or 0 for t in all_trades)
    total_pnl_usd = sum(t.get("pnl_usd", 0) or 0 for t in all_trades)
    pnl_values = [t.get("pnl_pips", 0) or 0 for t in all_trades]

    # Average hold time
    hold_times = []
    for t in all_trades:
        if t.get("entry_time") and t.get("exit_time"):
            try:
                entry = datetime.fromisoformat(t["entry_time"].replace("Z", "+00:00"))
                exit_ = datetime.fromisoformat(t["exit_time"].replace("Z", "+00:00"))
                hold_times.append((exit_ - entry).total_seconds() / 60)
            except (ValueError, TypeError):
                pass

    # Stats by pair
    by_pair = {}
    for pair_name in settings.pairs:
        pair_trades = [t for t in all_trades if t.get("pair") == pair_name]
        if pair_trades:
            pair_wins = [t for t in pair_trades if (t.get("pnl_pips") or 0) > 0]
            by_pair[pair_name] = {
                "total": len(pair_trades),
                "wins": len(pair_wins),
                "win_rate": round(len(pair_wins) / len(pair_trades) * 100, 1),
                "total_pnl_pips": round(sum(t.get("pnl_pips", 0) or 0 for t in pair_trades), 1),
            }

    open_trades = await get_open_trades()

    return {
        "total_trades": len(all_trades),
        "open_trades": len(open_trades),
        "win_rate": round(len(wins) / len(all_trades) * 100, 1) if all_trades else 0.0,
        "total_pnl_pips": round(total_pnl_pips, 1),
        "total_pnl_usd": round(total_pnl_usd, 2),
        "avg_pnl_pips": round(total_pnl_pips / len(all_trades), 1) if all_trades else 0.0,
        "avg_hold_minutes": round(sum(hold_times) / len(hold_times), 1) if hold_times else 0.0,
        "best_trade_pips": round(max(pnl_values), 1) if pnl_values else 0.0,
        "worst_trade_pips": round(min(pnl_values), 1) if pnl_values else 0.0,
        "by_pair": by_pair,
    }


# ─── Events ──────────────────────────────────────────────────────────────────

@app.get("/api/events")
async def list_events():
    """Get upcoming economic events."""
    events = await get_all_events(limit=50)
    return {"count": len(events), "events": events}


@app.get("/api/events/state")
async def event_state():
    """Get the current event engine state."""
    return event_engine.get_event_state()


@app.post("/api/event/trigger")
async def trigger_event(body: EventTrigger):
    """Manually trigger event mode (for testing)."""
    if body.level not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="Level must be A, B, or C")

    result = await event_engine.start_event_cooldown(
        event_level=body.level,
        title=body.title,
    )
    # Broadcast event state
    state = event_engine.get_event_state()
    await market_data.broadcast({"type": "event_state", "data": state})
    await alert_service.alert_event_state(state)

    return result


@app.post("/api/event/confirm")
async def confirm_event_direction(body: DirectionConfirm):
    """Manually confirm direction after the 30-second window."""
    pair = body.pair.upper().replace("_", "/")
    if pair not in settings.pairs:
        raise HTTPException(status_code=400, detail=f"Pair {pair} not supported")

    # If no prices provided, use recent history
    prices_before = body.prices_before
    prices_after = body.prices_after

    if not prices_before or not prices_after:
        recent = await get_recent_prices(pair, limit=30)
        if len(recent) >= 10:
            all_closes = [r["close"] for r in recent]
            mid = len(all_closes) // 2
            prices_before = all_closes[:mid]
            prices_after = all_closes[mid:]
        else:
            raise HTTPException(status_code=400, detail="Insufficient price data for confirmation")

    result = await event_engine.confirm_direction(pair, prices_before, prices_after)

    # Broadcast
    state = event_engine.get_event_state()
    await market_data.broadcast({"type": "event_state", "data": state})

    return result


# ─── Settings ────────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def list_settings():
    """Get all system settings."""
    return await get_all_settings()


@app.put("/api/settings/{key}")
async def update_setting(key: str, body: SettingUpdate):
    """Update a system setting."""
    valid_keys = {
        "aud_usd_direction", "nzd_usd_direction", "override_mode",
        "max_hold_minutes", "stop_loss_pips", "take_profit_pips",
        "spread_threshold_pips", "event_a_cooldown_seconds",
        "event_b_cooldown_seconds", "kill_switch",
    }
    if key not in valid_keys:
        raise HTTPException(status_code=400, detail=f"Invalid setting key: {key}. Valid: {sorted(valid_keys)}")

    # Validate values
    if key in ("aud_usd_direction", "nzd_usd_direction"):
        if body.value not in ("LONG_ONLY", "SHORT_ONLY", "BOTH"):
            raise HTTPException(status_code=400, detail="Direction must be LONG_ONLY, SHORT_ONLY, or BOTH")
    elif key == "override_mode":
        if body.value not in ("NORMAL", "OBSERVE_ONLY", "REDUCE_ONLY", "FLATTEN_ALL"):
            raise HTTPException(
                status_code=400,
                detail="Override mode must be NORMAL, OBSERVE_ONLY, REDUCE_ONLY, or FLATTEN_ALL",
            )
    elif key == "kill_switch":
        if body.value.lower() not in ("true", "false"):
            raise HTTPException(status_code=400, detail="Kill switch must be true or false")
        # Alert on kill switch activation
        if body.value.lower() == "true":
            await alert_service.alert_kill_switch("Manually activated via API")

    await set_setting(key, body.value)
    await insert_log("INFO", "settings", f"Setting '{key}' updated to '{body.value}'")

    # Broadcast settings change
    await market_data.broadcast({
        "type": "alert",
        "data": {"message": f"Setting updated: {key} = {body.value}"},
    })

    return {"key": key, "value": body.value, "status": "updated"}


# ─── System ──────────────────────────────────────────────────────────────────

@app.get("/api/system/logs")
async def system_logs(
    level: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """Get recent system logs."""
    logs = await get_logs(level=level, source=source, limit=limit)
    return {"count": len(logs), "logs": logs}


@app.get("/api/broker/status")
async def broker_status():
    """Get broker connection status (placeholder for Phase 2)."""
    return {
        "dukascopy": {
            "configured": settings.dukascopy_api_url != "http://localhost:9090",
            "connected": False,
            "url": settings.dukascopy_api_url,
        },
        "interactive_brokers": {
            "configured": False,
            "connected": False,
            "host": settings.ib_tws_host,
            "port": settings.ib_tws_port,
        },
        "status": "Phase 2 - not yet implemented",
    }


# ─── Additional endpoints for frontend ───────────────────────────────────────

@app.get("/api/news")
async def list_news():
    """Get recent news (placeholder - populated when IB adapter is connected)."""
    return {"count": 0, "news": []}


@app.get("/api/broker/dukascopy/status")
async def dukascopy_status():
    """Get Dukascopy connection status."""
    return {
        "connected": False,
        "name": "Dukascopy",
        "url": settings.dukascopy_api_url,
        "features": ["SWFX 实时行情", "ECN 市场深度", "点差监控", "SWFX 情绪", "订单执行", "历史 Tick"],
    }


@app.get("/api/broker/ib/status")
async def ib_status():
    """Get Interactive Brokers connection status."""
    return {
        "connected": False,
        "name": "Interactive Brokers",
        "host": settings.ib_tws_host,
        "port": settings.ib_tws_port,
        "features": ["新闻推送", "经济日历", "实时行情", "历史 K 线", "订单执行", "账户监控"],
    }


@app.get("/api/broker/datasources")
async def data_sources():
    """Get data source status."""
    return [
        {"name": "Dukascopy SWFX", "type": "行情", "status": "未连接", "role": "主源"},
        {"name": "IB TWS", "type": "行情", "status": "未连接", "role": "备源"},
        {"name": "IB Econoday", "type": "日历", "status": "未连接", "role": "主源"},
        {"name": "IB News", "type": "新闻", "status": "未连接", "role": "主源"},
        {"name": "模拟数据", "type": "行情", "status": "运行中" if settings.use_simulated_data else "待机", "role": "开发"},
    ]


@app.get("/api/broker/positions")
async def broker_positions():
    """Get current broker positions (placeholder for Phase 2)."""
    return {"positions": [], "total_equity": 0, "used_margin": 0, "free_margin": 0}


@app.get("/api/model/drivers")
async def model_drivers():
    """Get macro driver weights for each pair."""
    return {
        "AUD/USD": [
            {"factor": "中国经济与商品", "weight": 35},
            {"factor": "RBA 政策预期", "weight": 27},
            {"factor": "美联储与美元", "weight": 23},
            {"factor": "全球风险偏好", "weight": 15},
        ],
        "NZD/USD": [
            {"factor": "出口商品与需求", "weight": 32},
            {"factor": "RBNZ 政策预期", "weight": 28},
            {"factor": "中国/亚洲需求", "weight": 18},
            {"factor": "美联储与美元", "weight": 12},
            {"factor": "全球风险偏好", "weight": 10},
        ],
    }


@app.get("/api/model/regime")
async def model_regime():
    """Get current detected regime for each pair."""
    all_signals = signal_engine.get_all_latest_signals()
    return {
        pair: {"regime": sig.get("regime", "RANGE"), "adx": sig.get("adx", 0)}
        for pair, sig in all_signals.items()
    }


@app.get("/api/trades/daily_pnl")
async def daily_pnl():
    """Get daily PnL for the last 7 days."""
    all_trades = await get_trades(status="CLOSED", limit=10000)
    from collections import defaultdict
    daily: dict[str, float] = defaultdict(float)
    for t in all_trades:
        if t.get("exit_time"):
            day = t["exit_time"][:10]
            daily[day] += t.get("pnl_pips", 0)
    result = [{"date": k, "pnl": v} for k, v in sorted(daily.items())[-7:]]
    return result


@app.get("/api/events/history")
async def events_history():
    """Get historical events with confirmation results."""
    events = await get_all_events(limit=20)
    return [
        {
            **evt,
            "price_confirmed": True,
            "spread_confirmed": True,
            "structure_confirmed": False,
            "decision": "观望",
            "result_pips": 0,
        }
        for evt in events
        if evt.get("actual")
    ]


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time streaming.
    Sends: price_update, signal, event_state, trade, alert messages.
    """
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    market_data.register_client(queue)

    try:
        # Send initial state
        await websocket.send_json({
            "type": "alert",
            "data": {"message": "Connected to FX Trading System WebSocket"},
        })

        # Send current signals if available
        current_signals = signal_engine.get_all_latest_signals()
        if current_signals:
            await websocket.send_json({
                "type": "signal",
                "data": current_signals,
            })

        # Send current event state
        await websocket.send_json({
            "type": "event_state",
            "data": event_engine.get_event_state(),
        })

        # Stream updates
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(message)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "data": {"timestamp": datetime.now(timezone.utc).isoformat()},
                })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        market_data.unregister_client(queue)


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
