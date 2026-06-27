"""
WTI Crude Oil AI Trading Platform - Main Server
Modular FastAPI application with APIRouter-based route organization.
"""
from dotenv import load_dotenv
from pathlib import Path

# Load environment FIRST
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import List

# Import shared deps
from deps import (
    db, client, manager, broker, risk_service, regime_service,
    signal_service, multi_asset_generator, portfolio_analyzer,
    calendar_service, ml_service, options_service, fragility_engine,
    event_engine, risk_control, execution_gate, signal_scorer,
    trading_bot, notification_service, system_state,
)
from multi_asset import ASSETS
from notification_service import NotificationType
from auth_service import seed_admin

# Import routers
from routers.auth import router as auth_router
from routers.options import router as options_router
from routers.bot import router as bot_router
from routers.replay import router as replay_router
from routers.analytics import router as analytics_router
from routers.system import router as system_router
from routers.exports_alerts import router as exports_alerts_router, check_price_alerts
from routers.social import router as social_router

import deps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WTI_Platform")

# Create FastAPI app
app = FastAPI(title="WTI AI Trading Platform", version="2.0.0")

# Create API router and include sub-routers
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(options_router)
api_router.include_router(bot_router)
api_router.include_router(replay_router)
api_router.include_router(analytics_router)
api_router.include_router(system_router)
api_router.include_router(exports_alerts_router)
api_router.include_router(social_router)

# Include security router
try:
    from security_routes import oil_security_router, set_oil_security_instance
    from security_integration import get_oil_security_integration
    
    # Initialize security integration
    async def init_oil_security():
        security = get_oil_security_integration(db)
        await security.initialize()
        set_oil_security_instance(security)
        logger.info("Oil Security integration initialized successfully")
    
    # Add startup event for security
    @app.on_event("startup")
    async def startup_oil_security():
        await init_oil_security()
    
    app.include_router(oil_security_router)
    logger.info("Oil Security router included")
except ImportError as e:
    logger.warning(f"Oil Security module not available: {e}")


# ─────────────────────────────────────────
# Background Tasks
# ─────────────────────────────────────────

async def bot_scanner_loop():
    """Background loop: scan market for opportunities every N seconds"""
    while True:
        try:
            # Auto regime change notifications
            current_regime = regime_service.current.value
            if deps.last_regime_notified is None:
                deps.last_regime_notified = current_regime
            if current_regime != deps.last_regime_notified:
                await notification_service.broadcast_notification(
                    notification_type=NotificationType.REGIME_CHANGE,
                    title=f"Regime Change: {deps.last_regime_notified.upper()} → {current_regime.upper()}",
                    message="Market regime changed. Review positions and bot strategy accordingly.",
                    severity="warning" if current_regime in ("spike", "blocked") else "info",
                )
                deps.last_regime_notified = current_regime

            # Check take-profit levels on all open positions
            if deps.take_profit_levels:
                for symbol in ASSETS.keys():
                    tick = multi_asset_generator.generate_tick(symbol)
                    if tick:
                        broker.update_tick(tick)
                triggered = broker.check_take_profits(deps.take_profit_levels)
                for pos_id, tp_level, record in triggered:
                    risk_control.record_trade(record.pnl_usd)
                    await notification_service.broadcast_notification(
                        notification_type=NotificationType.TRADE_ALERT,
                        title=f"TP{tp_level[-1]} Hit: {record.symbol} {'PARTIAL' if tp_level == 'tp1' else 'FULL'} Close",
                        message=f"{'50% closed, SL→breakeven' if tp_level == 'tp1' else 'Remaining closed'} @ ${record.exit_price:.2f} | PnL: ${record.pnl_usd:+.2f}",
                        severity="info",
                    )
                    if tp_level == "tp2":
                        deps.take_profit_levels.pop(pos_id, None)

            # Check price alerts
            try:
                await check_price_alerts()
            except Exception as e:
                logger.error(f"[Alerts] Price alert check error: {e}")

            if trading_bot.enabled:
                for symbol in ASSETS.keys():
                    try:
                        indicators = multi_asset_generator.generate_indicators(symbol)
                        tick_obj = multi_asset_generator.generate_tick(symbol)
                        current_price = tick_obj.mid if tick_obj else multi_asset_generator.current_prices.get(symbol, 75.0)
                        current_spread = tick_obj.spread if tick_obj else 0.03

                        bars = multi_asset_generator.bars.get(symbol, [])
                        price_change_pct = 0.0
                        if len(bars) >= 2:
                            price_change_pct = (bars[-1].close - bars[-2].close) / bars[-2].close * 100

                        frag_state = fragility_engine.current_state
                        sig_score = signal_scorer.calculate_score(
                            ema_fast=indicators.ema_fast, ema_slow=indicators.ema_slow,
                            adx=indicators.adx, regime=regime_service.current.value,
                            vol_ratio=indicators.volatility_ratio,
                            recent_price_change_pct=price_change_pct,
                            spread=current_spread, fragility_score=frag_state.score,
                        )
                        risk_status = risk_control.check_rules()
                        event_state = event_engine.get_state()
                        gate_result = execution_gate.evaluate(
                            spread=current_spread, adx=indicators.adx,
                            vol_ratio=indicators.volatility_ratio,
                            signal_score=sig_score["bullish_pct"],
                            fragility_score=frag_state.score,
                            risk_can_trade=risk_status["can_trade"],
                            cooldown_active=event_state["cooldown_active"],
                            regime=regime_service.current.value,
                        )

                        await trading_bot.scan_market(
                            symbol=symbol, current_price=current_price,
                            signal_score=sig_score, execution_gate=gate_result,
                            fragility=frag_state.to_dict(), risk_control=risk_status,
                            regime=regime_service.current.value, atr=indicators.atr,
                            indicators={"ema_fast": indicators.ema_fast, "ema_slow": indicators.ema_slow, "adx": indicators.adx},
                        )
                    except Exception as e:
                        logger.error(f"[Bot] Scan error for {symbol}: {e}")

            await asyncio.sleep(trading_bot.scan_interval_sec)
        except Exception as e:
            logger.error(f"[Bot] Scanner loop error: {e}")
            await asyncio.sleep(10)


async def market_simulation_loop():
    """Background loop that simulates market data for all assets"""
    logger.info("[Simulation] Starting multi-asset market simulation loop")

    while deps.simulation_running:
        try:
            all_ticks = {}
            all_indicators = {}

            for symbol in ASSETS.keys():
                tick = multi_asset_generator.generate_tick(symbol)
                all_ticks[symbol] = tick
                if len(multi_asset_generator.bars.get(symbol, [])) % 5 == 0:
                    multi_asset_generator.generate_bar(symbol)
                all_indicators[symbol] = multi_asset_generator.generate_indicators(symbol)

            current_tick = all_ticks.get(deps.current_symbol)
            if current_tick:
                broker.update_tick(current_tick)

            current_ind = all_indicators.get(deps.current_symbol)
            if current_ind:
                regime_service.update(current_ind)
                regime_service.check_event_window_expiry()

            ml_prediction = None
            if len(multi_asset_generator.bars.get(deps.current_symbol, [])) % 2 == 0:
                try:
                    ml_prediction = await ml_service.analyze_market(
                        indicators=current_ind,
                        current_price=current_tick.last if current_tick else 75.0,
                        current_regime=regime_service.current,
                    )
                except Exception as e:
                    logger.warning(f"[ML] Prediction error: {e}")

            spread_opportunity = portfolio_analyzer.calculate_spread_opportunity()

            if current_ind and current_tick:
                price_change = 0.0
                bars = multi_asset_generator.bars.get(deps.current_symbol, [])
                if len(bars) >= 2:
                    price_change = bars[-1].close - bars[-2].close
                fragility_engine.update(
                    current_spread=current_tick.spread,
                    current_vol_ratio=current_ind.volatility_ratio,
                    atr=current_ind.atr, price_change=price_change,
                    adx=current_ind.adx, regime=regime_service.current.value,
                    bid_ask_depth=max(0.3, min(1.0, 1.0 - current_ind.volatility_ratio * 0.3)),
                )

            risk_control.update_equity(broker.equity)

            update = {
                "type": "market_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "current_symbol": deps.current_symbol,
                "assets": {
                    symbol: {"bid": tick.bid, "ask": tick.ask, "last": tick.last, "spread": round(tick.spread, 4)}
                    for symbol, tick in all_ticks.items()
                },
                "tick": {
                    "bid": current_tick.bid if current_tick else 0,
                    "ask": current_tick.ask if current_tick else 0,
                    "last": current_tick.last if current_tick else 0,
                    "spread": round(current_tick.spread, 4) if current_tick else 0,
                },
                "indicators": {
                    "ema_fast": current_ind.ema_fast if current_ind else 0,
                    "ema_slow": current_ind.ema_slow if current_ind else 0,
                    "adx": current_ind.adx if current_ind else 0,
                    "atr": current_ind.atr if current_ind else 0,
                    "volatility_ratio": current_ind.volatility_ratio if current_ind else 0,
                    "volume_ratio": current_ind.volume_ratio if current_ind else 0,
                },
                "regime": regime_service.current.value,
                "risk": {
                    "daily_pnl": risk_service.state.daily_pnl,
                    "consecutive_losses": risk_service.state.consecutive_losses,
                    "is_halted": risk_service.state.is_halted,
                    "kill_switch": risk_service.state.kill_switch_active,
                },
                "equity": broker.equity,
                "positions": [
                    {
                        "id": p.id, "symbol": p.symbol, "direction": p.direction.value,
                        "entry_price": p.entry_price, "current_price": p.current_price,
                        "quantity": p.quantity, "unrealized_pnl": round(p.unrealized_pnl, 2),
                        "stop_loss": p.stop_loss_price,
                    }
                    for p in broker.open_positions
                ],
                "ml_prediction": {
                    "regime": ml_prediction.predicted_regime.value if ml_prediction else None,
                    "confidence": ml_prediction.confidence if ml_prediction else 0,
                    "signal_direction": ml_prediction.signal_direction.value if ml_prediction and ml_prediction.signal_direction else None,
                    "signal_confidence": ml_prediction.signal_confidence if ml_prediction else 0,
                    "reasoning": ml_prediction.reasoning if ml_prediction else "",
                } if ml_prediction else None,
                "spread_opportunity": spread_opportunity,
                "correlation_matrix": multi_asset_generator.get_correlation_matrix(),
                "fragility": fragility_engine.current_state.to_dict(),
                "event_state": event_engine.get_state(),
            }

            await manager.broadcast(update)
            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"[Simulation] Error: {e}")
            await asyncio.sleep(5)

    logger.info("[Simulation] Market simulation loop stopped")


# ─────────────────────────────────────────
# WebSocket Endpoint
# ─────────────────────────────────────────

@api_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                command = json.loads(data)
                if command.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif command.get("type") == "set_symbol":
                    symbol = command.get("symbol", "CL")
                    if symbol in ASSETS:
                        deps.current_symbol = symbol
                        await websocket.send_json({"type": "symbol_changed", "symbol": symbol})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Include router
app.include_router(api_router)

# CORS middleware
frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
cors_origins = os.environ.get('CORS_ORIGINS', '*').split(',')
if frontend_url not in cors_origins:
    cors_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info("WTI AI Trading Platform v2.0 starting up...")

    notification_service.set_db(db)

    async def bot_notification_callback(opportunity):
        await notification_service.broadcast_notification(
            notification_type=NotificationType.TRADE_ALERT,
            title=f"{'BUY' if opportunity.direction.value == 'long' else 'SELL'} {opportunity.symbol} @ ${opportunity.entry_price:.2f}",
            message=f"Confidence: {opportunity.confidence:.0f}% | {opportunity.reasoning}",
            severity="warning",
            data=opportunity.to_dict(),
        )
    trading_bot.set_notification_callback(bot_notification_callback)

    asyncio.create_task(bot_scanner_loop())
    deps.simulation_running = True
    asyncio.create_task(market_simulation_loop())

    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.trades.create_index([("user_id", 1), ("created_at", -1)])
    await db.notifications.create_index([("user_id", 1), ("timestamp", -1)])
    await db.price_alerts.create_index([("user_id", 1), ("active", 1)])
    await db.shared_strategies.create_index([("score", -1)])
    await db.followed_strategies.create_index([("user_id", 1)])
    await db.pvp_battles.create_index([("created_at", -1)])

    await seed_admin(db)

    for symbol in ASSETS.keys():
        for _ in range(60):
            multi_asset_generator.generate_bar(symbol)

    logger.info("Initial market data generated for all assets")
    logger.info(f"Available assets: {list(ASSETS.keys())}")


@app.on_event("shutdown")
async def shutdown_event():
    deps.simulation_running = False
    client.close()
    logger.info("WTI AI Trading Platform shut down")
