"""
AI Bond Trading System V5 - Refactored
Main application file with routes, WebSocket, and app lifecycle.
Services and models are imported from their respective modules.
"""
from dotenv import load_dotenv
load_dotenv()

import os
import random
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from bson import ObjectId

# Import from our modules
from config import (
    db, client, logger, 
    hash_password, verify_password, 
    create_access_token, create_refresh_token, get_current_user, get_jwt_secret, JWT_ALGORITHM
)
from models.schemas import (
    SystemStatus, Lifecycle, TradingMode, SignalType, StrategyType,
    UserRegister, UserLogin, MarketData, TradingSignal, SystemState,
    StrategyConfig, BacktestRequest, BacktestResult, AlertSettings,
    AVAILABLE_ASSETS, TwoFactorSetup
)
from services.telegram import TelegramNotifier
from services.market_data import MarketDataService, BondAnalyticsService
from services.ai_engine import AITradingEngine
from services.multi_asset import MultiAssetDataService
from services.backtest import BacktestEngine
from services.portfolio import PortfolioManager
from services.paper_trading import PaperTradingManager
from services.marketplace import StrategyMarketplace
from services.social import TwoFactorAuthService, SocialService, AutoExecuteService
from services.yield_curve import YieldCurveService, BondAuctionService
from services.risk_analytics import RiskAnalyticsService
from services.ai_brief import AIBriefService
from services.risk_alerts import RiskAlertService
from services.email_digest import EmailDigestService
from services.risk_trends import RiskTrendService
from services.portfolio_optimizer import PortfolioOptimizer

import jwt as pyjwt

# ===================== SERVICE INSTANCES =====================

telegram_notifier = TelegramNotifier()
market_service = MarketDataService()
bond_analytics_service = BondAnalyticsService()
ai_engine = AITradingEngine()
multi_asset_service = MultiAssetDataService()
backtest_engine = BacktestEngine()
portfolio_manager = PortfolioManager(db)
paper_trading_manager = PaperTradingManager(db, multi_asset_service)
strategy_marketplace = StrategyMarketplace(db)
two_factor_service = TwoFactorAuthService()
social_service = SocialService(db)
auto_execute_service = AutoExecuteService(db, paper_trading_manager, social_service)
yield_curve_service = YieldCurveService()
bond_auction_service = BondAuctionService(db)
risk_analytics_service = RiskAnalyticsService(db)
ai_brief_service = AIBriefService(db)
risk_alert_service = RiskAlertService(db, risk_analytics_service, telegram_notifier)
email_digest_service = EmailDigestService(db)
risk_trend_service = RiskTrendService(db)
portfolio_optimizer = PortfolioOptimizer(db)

# ===================== GLOBAL STATE =====================

system_state = SystemState()
current_strategy = StrategyConfig(strategy_type=StrategyType.AI_HYBRID)
market_data_history: List[MarketData] = []
trading_signals: List[TradingSignal] = []
execution_logs: List[str] = []

# ===================== WEBSOCKET MANAGER =====================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# ===================== STARTUP =====================

async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@trading.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123456")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        hashed = hash_password(admin_password)
        await db.users.insert_one({
            "email": admin_email, "password_hash": hashed,
            "name": "Admin", "role": "admin",
            "created_at": datetime.now(timezone.utc)
        })
        logger.info(f"Admin user created: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}}
        )
        logger.info(f"Admin password updated: {admin_email}")
    
    credentials_content = f"""# Test Credentials for AI Bond Trading System

## Admin Account
- Email: {admin_email}
- Password: {admin_password}
- Role: admin

## Auth Endpoints
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me
- POST /api/auth/refresh
"""
    Path("/app/memory").mkdir(exist_ok=True)
    Path("/app/memory/test_credentials.md").write_text(credentials_content)

async def create_indexes():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.trades.create_index("user_id")
    await db.trades.create_index("timestamp")
    await db.alerts.create_index("user_id")
    await db.alerts.create_index("timestamp")
    await db.portfolios.create_index("user_id", unique=True)
    await db.backtests.create_index("user_id")
    await db.user_follows.create_index([("follower_id", 1), ("following_id", 1)], unique=True)
    await db.activities.create_index("user_id")
    await db.activities.create_index("created_at")
    await db.auto_execute_logs.create_index("user_id")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_admin()
    await create_indexes()
    await ai_engine.initialize_llm()
    await ai_brief_service.initialize()
    await telegram_notifier.initialize()
    logger.info("AI Bond Trading System V5 started")
    yield
    await telegram_notifier.close()
    client.close()
    logger.info("AI Bond Trading System V5 shutdown")

# ===================== APP & ROUTER =====================

app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== BRUTE FORCE PROTECTION =====================

async def check_brute_force(identifier: str):
    """Check and enforce brute force protection"""
    window = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    record = await db.login_attempts.find_one({"identifier": identifier, "window": window})
    if record and record.get("count", 0) >= 10:
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

async def record_login_attempt(identifier: str, success: bool):
    """Record a login attempt"""
    window = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    if not success:
        await db.login_attempts.update_one(
            {"identifier": identifier, "window": window},
            {"$inc": {"count": 1}, "$set": {"last_attempt": datetime.now(timezone.utc)}},
            upsert=True
        )

# ===================== AUTH ROUTES =====================

@api_router.post("/auth/register")
async def register(user: UserRegister):
    email = user.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    doc = {
        "email": email, "password_hash": hashed,
        "name": user.name, "role": "user",
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.users.insert_one(doc)
    user_id = str(result.inserted_id)
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    response = JSONResponse(content={
        "_id": user_id, "email": email, "name": user.name, "role": "user"
    })
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return response

@api_router.post("/auth/login")
async def login(user: UserLogin):
    email = user.email.lower()
    await check_brute_force(email)
    db_user = await db.users.find_one({"email": email})
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        await record_login_attempt(email, False)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await record_login_attempt(email, True)
    user_id = str(db_user["_id"])
    
    # Check if 2FA is enabled
    if db_user.get("two_factor_enabled"):
        return JSONResponse(content={
            "requires_2fa": True,
            "user_id": user_id,
            "message": "2FA verification required"
        })
    
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    response = JSONResponse(content={
        "_id": user_id, "email": email,
        "name": db_user["name"], "role": db_user["role"],
        "two_factor_enabled": db_user.get("two_factor_enabled", False)
    })
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return response

@api_router.post("/auth/logout")
async def logout():
    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return response

@api_router.get("/auth/me")
async def get_me(request: Request):
    return await get_current_user(request)

@api_router.post("/auth/refresh")
async def refresh_token(request: Request):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = pyjwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user_id = str(user["_id"])
        new_access = create_access_token(user_id, user["email"])
        response = JSONResponse(content={
            "_id": user_id, "email": user["email"], "name": user["name"], "role": user["role"]
        })
        response.set_cookie(key="access_token", value=new_access, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
        return response
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# ===================== 2FA ROUTES =====================

@api_router.post("/auth/2fa/setup")
async def setup_2fa(request: Request):
    user = await get_current_user(request)
    db_user = await db.users.find_one({"_id": ObjectId(user["_id"])})
    if db_user.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    setup = await two_factor_service.setup_2fa(db, user["_id"], user["email"])
    return {"qr_code": setup.qr_code, "secret": setup.secret, "backup_codes": setup.backup_codes}

@api_router.post("/auth/2fa/confirm")
async def confirm_2fa(code: str, request: Request):
    user = await get_current_user(request)
    await two_factor_service.confirm_2fa(db, user["_id"], code)
    return {"message": "2FA enabled successfully"}

@api_router.post("/auth/2fa/disable")
async def disable_2fa(code: str, request: Request):
    user = await get_current_user(request)
    await two_factor_service.disable_2fa(db, user["_id"], code)
    return {"message": "2FA disabled successfully"}

@api_router.post("/auth/2fa/verify")
async def verify_2fa_login(user_id: str, code: str):
    verified = await two_factor_service.verify_login_2fa(db, user_id, code)
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid 2FA code")
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    access_token = create_access_token(user_id, user["email"])
    refresh_token = create_refresh_token(user_id)
    response = JSONResponse(content={
        "_id": user_id, "email": user["email"], "name": user["name"], "role": user["role"]
    })
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return response

@api_router.get("/auth/2fa/status")
async def get_2fa_status(request: Request):
    user = await get_current_user(request)
    db_user = await db.users.find_one({"_id": ObjectId(user["_id"])})
    return {
        "enabled": db_user.get("two_factor_enabled", False),
        "backup_codes_remaining": len(db_user.get("two_factor_backup_codes", []))
    }

# ===================== MARKET DATA ROUTES =====================

@api_router.get("/market/current")
async def get_current_market():
    data = await market_service.get_real_market_data()
    return data.model_dump()

@api_router.get("/market/history")
async def get_market_history(period: str = "1mo"):
    return await market_service.get_historical_data(period)

@api_router.get("/market/historical")
async def get_historical_market(period: str = "1mo"):
    return await market_service.get_historical_data(period)

@api_router.get("/market/bond-analytics")
async def get_bond_analytics():
    return await bond_analytics_service.get_bond_analytics()

# ===================== YIELD CURVE ROUTES =====================

@api_router.get("/yield-curve/current")
async def get_current_yield_curve():
    """Get current full yield curve with shape analysis"""
    return await yield_curve_service.get_current_yield_curve()

@api_router.get("/yield-curve/historical")
async def get_historical_curves(period: str = "3mo"):
    """Get historical yield curve data"""
    return await yield_curve_service.get_historical_curves(period)

@api_router.get("/yield-curve/heatmap")
async def get_yield_curve_heatmap(period: str = "6mo"):
    """Get yield change heatmap data"""
    return await yield_curve_service.get_curve_heatmap(period)

# ===================== BOND AUCTION ROUTES =====================

@api_router.get("/auctions/upcoming")
async def get_upcoming_auctions():
    """Get upcoming Treasury auction schedule"""
    return await bond_auction_service.get_upcoming_auctions()

@api_router.get("/auctions/results")
async def get_auction_results(limit: int = 20):
    """Get recent auction results"""
    return await bond_auction_service.get_auction_results(limit)

@api_router.get("/auctions/calendar")
async def get_auction_calendar():
    """Get auction calendar summary"""
    return await bond_auction_service.get_auction_calendar_summary()

# ===================== SYSTEM STATE ROUTES =====================

@api_router.get("/system/state")
async def get_system_state():
    return {
        "status": system_state.status.value,
        "lifecycle": system_state.lifecycle.value,
        "mode": system_state.mode.value,
        "is_locked": system_state.is_locked,
        "black_swan_probability": system_state.black_swan_probability,
        "last_updated": system_state.last_updated.isoformat()
    }

@api_router.post("/system/toggle-lock")
async def toggle_lock(request: Request):
    await get_current_user(request)
    system_state.is_locked = not system_state.is_locked
    system_state.last_updated = datetime.now(timezone.utc)
    return {"is_locked": system_state.is_locked}

@api_router.post("/system/toggle-lifecycle")
async def toggle_lifecycle(request: Request):
    await get_current_user(request)
    if system_state.is_locked:
        raise HTTPException(status_code=403, detail="System is locked")
    if system_state.lifecycle == Lifecycle.PRE_LIVE:
        system_state.lifecycle = Lifecycle.GO_LIVE
        await telegram_notifier.send_system_alert("GO-LIVE", "Trading system switched to LIVE mode.")
    else:
        system_state.lifecycle = Lifecycle.PRE_LIVE
        await telegram_notifier.send_system_alert("PRE-LIVE", "Trading system switched to PRE-LIVE mode.")
    system_state.last_updated = datetime.now(timezone.utc)
    return {"lifecycle": system_state.lifecycle.value}

@api_router.post("/system/kill-switch")
async def activate_kill_switch(request: Request):
    user = await get_current_user(request)
    if system_state.is_locked:
        raise HTTPException(status_code=403, detail="System is locked")
    system_state.status = SystemStatus.HALT
    system_state.mode = TradingMode.REDUCE
    system_state.last_updated = datetime.now(timezone.utc)
    alert = {
        "user_id": user["_id"], "alert_type": "SYSTEM", "title": "KILL SWITCH ACTIVATED",
        "message": "Emergency halt engaged.", "severity": "CRITICAL",
        "is_read": False, "timestamp": datetime.now(timezone.utc)
    }
    await db.alerts.insert_one(alert)
    log_entry = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] !!! EMERGENCY HALT ENGAGED by {user['email']} !!!"
    execution_logs.insert(0, log_entry)
    await telegram_notifier.send_system_alert("HALT", f"KILL SWITCH activated by {user['email']}.")
    await manager.broadcast({"type": "KILL_SWITCH", "status": "HALT", "mode": "REDUCE", "log": log_entry})
    return {"status": "HALT", "mode": "REDUCE", "message": "Kill switch activated"}

@api_router.post("/system/clear-alert")
async def clear_alert(request: Request):
    await get_current_user(request)
    if system_state.is_locked:
        raise HTTPException(status_code=403, detail="System is locked")
    system_state.status = SystemStatus.SAFE
    system_state.mode = TradingMode.NORMAL
    system_state.last_updated = datetime.now(timezone.utc)
    await telegram_notifier.send_system_alert("SAFE", "System status cleared. Normal operations resumed.")
    return {"status": "SAFE", "mode": "NORMAL"}

@api_router.post("/system/set-mode")
async def set_mode(mode: str, request: Request):
    await get_current_user(request)
    if system_state.is_locked:
        raise HTTPException(status_code=403, detail="System is locked")
    try:
        system_state.mode = TradingMode(mode)
        system_state.last_updated = datetime.now(timezone.utc)
        return {"mode": system_state.mode.value}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid mode")

# ===================== STRATEGY CONFIGURATION =====================

@api_router.get("/strategy/config")
async def get_strategy_config():
    return {
        "strategy_type": current_strategy.strategy_type.value,
        "ispread_upper": current_strategy.ispread_upper,
        "ispread_lower": current_strategy.ispread_lower,
        "confidence_threshold": current_strategy.confidence_threshold,
        "max_position_size": current_strategy.max_position_size,
        "stop_loss_pct": current_strategy.stop_loss_pct,
        "take_profit_pct": current_strategy.take_profit_pct,
        "use_ai": current_strategy.use_ai,
        "momentum_period": current_strategy.momentum_period,
        "mean_reversion_window": current_strategy.mean_reversion_window
    }

@api_router.post("/strategy/config")
async def update_strategy_config(config: StrategyConfig, request: Request):
    await get_current_user(request)
    global current_strategy
    current_strategy = config
    await db.strategy_configs.update_one(
        {"active": True},
        {"$set": {**config.model_dump(), "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    return {"message": "Strategy configuration updated", "config": config.model_dump()}

@api_router.get("/strategy/types")
async def get_strategy_types():
    return [
        {"value": "MEAN_REVERSION", "label": "Mean Reversion", "description": "Trade based on Ispread deviation from mean"},
        {"value": "MOMENTUM", "label": "Momentum", "description": "Follow price trend direction"},
        {"value": "SPREAD_ARBITRAGE", "label": "Spread Arbitrage", "description": "Exploit WTI-Bond spread anomalies"},
        {"value": "AI_HYBRID", "label": "AI Hybrid", "description": "Combine rules with GPT-5.2 analysis"}
    ]

# ===================== BACKTEST ROUTES =====================

@api_router.post("/backtest/run")
async def run_backtest(request_data: BacktestRequest, request: Request):
    user = await get_current_user(request)
    result = await backtest_engine.run_backtest(request_data)
    backtest_doc = {
        "user_id": user["_id"], "request": request_data.model_dump(),
        "result": result.model_dump(), "created_at": datetime.now(timezone.utc)
    }
    await db.backtests.insert_one(backtest_doc)
    return result.model_dump()

@api_router.get("/backtest/history")
async def get_backtest_history(request: Request, limit: int = 20):
    user = await get_current_user(request)
    backtests = await db.backtests.find(
        {"user_id": user["_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return backtests

@api_router.post("/backtest/compare")
async def compare_strategies(strategies: List[BacktestRequest], request: Request):
    await get_current_user(request)
    results = []
    for strategy in strategies:
        result = await backtest_engine.run_backtest(strategy)
        results.append(result.model_dump())
    results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    return {"comparison": results, "best_strategy": results[0] if results else None, "compared_at": datetime.now(timezone.utc).isoformat()}

# ===================== PORTFOLIO ROUTES =====================

@api_router.get("/portfolio")
async def get_portfolio(request: Request):
    user = await get_current_user(request)
    portfolio = await portfolio_manager.get_portfolio(user["_id"])
    return portfolio.model_dump()

@api_router.post("/portfolio/trade")
async def portfolio_trade(asset: str, quantity: int, action: str, request: Request):
    user = await get_current_user(request)
    market_data = await market_service.get_real_market_data()
    if asset == "10Y_BOND":
        price = market_data.bond_yield
    elif asset == "WTI":
        price = market_data.wti_price
    else:
        raise HTTPException(status_code=400, detail="Invalid asset")
    portfolio = await portfolio_manager.update_position(user["_id"], asset, quantity, price, action)
    trade = {
        "user_id": user["_id"], "signal_type": f"{asset}_{action}",
        "action": action, "price": price, "quantity": quantity,
        "confidence": 1.0, "ai_reasoning": "Manual trade",
        "status": "COMPLETED", "timestamp": datetime.now(timezone.utc)
    }
    await db.trades.insert_one(trade)
    return portfolio.model_dump()

@api_router.get("/portfolio/pnl")
async def get_portfolio_pnl(request: Request, period: str = "1mo"):
    user = await get_current_user(request)
    trades = await db.trades.find({"user_id": user["_id"]}, {"_id": 0}).sort("timestamp", -1).to_list(100)
    pnl_history = []
    cumulative_pnl = 0
    for trade in reversed(trades):
        if "pnl" in trade:
            cumulative_pnl += trade.get("pnl", 0)
        pnl_history.append({
            "date": trade["timestamp"].strftime("%Y-%m-%d") if isinstance(trade["timestamp"], datetime) else trade["timestamp"],
            "pnl": cumulative_pnl, "trade_type": trade.get("signal_type", "")
        })
    return {"history": pnl_history, "total_pnl": cumulative_pnl, "trade_count": len(trades)}

# ===================== AI SIGNALS ROUTES =====================

@api_router.get("/signals")
async def get_signals():
    return [s.model_dump() for s in trading_signals[-20:]]

@api_router.post("/signals/generate")
async def generate_signal(request: Request):
    user = await get_current_user(request)
    if system_state.lifecycle != Lifecycle.GO_LIVE:
        raise HTTPException(status_code=400, detail="System not in GO-LIVE mode")
    if system_state.status != SystemStatus.SAFE:
        raise HTTPException(status_code=400, detail=f"Cannot generate signals in {system_state.status.value} status")
    market_data = await market_service.get_real_market_data()
    analysis = await ai_engine.analyze_market(market_data, current_strategy, bond_analytics_service)
    if not analysis:
        return {"message": "No signal generated", "reason": "Market conditions neutral"}
    action_map = {
        "BUY_BOND": SignalType.BOND_BUY, "SELL_BOND": SignalType.BOND_SELL,
        "RATE_LONG": SignalType.RATE_LONG, "RATE_SHORT": SignalType.RATE_SHORT
    }
    signal_type = action_map.get(analysis.get("action", ""), SignalType.BOND_BUY)
    signal = TradingSignal(
        signal_type=signal_type, confidence=analysis.get("confidence", 0.8),
        status="PENDING", timestamp=datetime.now(timezone.utc),
        ai_reasoning=analysis.get("reasoning", ""), strategy=current_strategy.strategy_type.value
    )
    trading_signals.append(signal)
    await telegram_notifier.send_signal_alert(signal)
    await manager.broadcast({"type": "NEW_SIGNAL", "signal": signal.model_dump()})
    return signal.model_dump()

@api_router.post("/signals/{signal_id}/execute")
async def execute_signal(signal_id: str, request: Request):
    user = await get_current_user(request)
    if system_state.is_locked:
        raise HTTPException(status_code=403, detail="System is locked")
    signal = next((s for s in trading_signals if s.id == signal_id), None)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    if signal.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Signal already {signal.status}")
    market_data = await market_service.get_real_market_data()
    signal.status = "EXECUTED"
    signal.execution_price = market_data.bond_yield if "BOND" in signal.signal_type.value else market_data.wti_price
    trade = {
        "user_id": user["_id"], "signal_type": signal.signal_type.value,
        "action": "EXECUTED", "price": signal.execution_price,
        "quantity": current_strategy.max_position_size, "confidence": signal.confidence,
        "ai_reasoning": signal.ai_reasoning, "strategy": signal.strategy,
        "status": "COMPLETED", "timestamp": datetime.now(timezone.utc)
    }
    await db.trades.insert_one(trade)
    asset = "10Y_BOND" if "BOND" in signal.signal_type.value else "WTI"
    action = "BUY" if "BUY" in signal.signal_type.value or "LONG" in signal.signal_type.value else "SELL"
    try:
        await portfolio_manager.update_position(user["_id"], asset, current_strategy.max_position_size, signal.execution_price, action)
    except Exception as e:
        logger.error(f"Portfolio update failed: {e}")
    log_entry = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Executed {signal.signal_type.value} @ {signal.execution_price:.3f} | Confidence: {signal.confidence:.4f} | Strategy: {signal.strategy}"
    execution_logs.insert(0, log_entry)
    if len(execution_logs) > 50:
        execution_logs.pop()
    await telegram_notifier.send_execution_alert(signal, signal.execution_price)
    await manager.broadcast({"type": "SIGNAL_EXECUTED", "signal": signal.model_dump(), "log": log_entry})
    return signal.model_dump()

@api_router.get("/execution-logs")
async def get_execution_logs_route():
    return execution_logs[:30]

# ===================== TRADES ROUTES =====================

@api_router.get("/trades")
async def get_trades(request: Request, limit: int = 50):
    user = await get_current_user(request)
    trades = await db.trades.find({"user_id": user["_id"]}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return trades

@api_router.get("/trades/all")
async def get_all_trades(request: Request, limit: int = 100):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    trades = await db.trades.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return trades

# ===================== ALERTS ROUTES =====================

@api_router.get("/alerts")
async def get_alerts(request: Request, limit: int = 20):
    user = await get_current_user(request)
    alerts = await db.alerts.find({"user_id": user["_id"]}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return alerts

@api_router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.alerts.update_one({"id": alert_id, "user_id": user["_id"]}, {"$set": {"is_read": True}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert marked as read"}

@api_router.delete("/alerts/clear")
async def clear_alerts(request: Request):
    user = await get_current_user(request)
    await db.alerts.delete_many({"user_id": user["_id"], "is_read": True})
    return {"message": "Read alerts cleared"}

@api_router.get("/alerts/settings")
async def get_alert_settings(request: Request):
    user = await get_current_user(request)
    settings = await db.alert_settings.find_one({"user_id": user["_id"]})
    if not settings:
        settings = AlertSettings().model_dump()
    else:
        settings.pop("_id", None)
        settings.pop("user_id", None)
    return settings

@api_router.post("/alerts/settings")
async def update_alert_settings(settings: AlertSettings, request: Request):
    user = await get_current_user(request)
    await db.alert_settings.update_one(
        {"user_id": user["_id"]},
        {"$set": {**settings.model_dump(), "user_id": user["_id"]}},
        upsert=True
    )
    return {"message": "Alert settings updated"}

@api_router.post("/alerts/test-telegram")
async def test_telegram(request: Request):
    user = await get_current_user(request)
    success = await telegram_notifier.send_message(
        f"\U0001f514 <b>Test Notification</b>\n\nThis is a test alert from AI Bond Trading System.\nRequested by: {user['email']}\nTime: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    if success:
        return {"message": "Test notification sent successfully"}
    raise HTTPException(status_code=500, detail="Failed to send test notification")

# ===================== SOCIAL ROUTES =====================

@api_router.post("/social/follow/{user_id}")
async def follow_user(user_id: str, request: Request):
    current_user = await get_current_user(request)
    result = await social_service.follow_user(current_user["_id"], user_id)
    target_user = await db.users.find_one({"_id": ObjectId(user_id)})
    await social_service.create_activity(
        current_user["_id"], current_user["name"], "FOLLOW",
        f"Started following {target_user.get('name', 'a trader')}", {"following_id": user_id}
    )
    return result

@api_router.delete("/social/follow/{user_id}")
async def unfollow_user(user_id: str, request: Request):
    current_user = await get_current_user(request)
    return await social_service.unfollow_user(current_user["_id"], user_id)

@api_router.get("/social/followers")
async def get_my_followers(request: Request):
    user = await get_current_user(request)
    return await social_service.get_followers(user["_id"])

@api_router.get("/social/following")
async def get_my_following(request: Request):
    user = await get_current_user(request)
    return await social_service.get_following(user["_id"])

@api_router.get("/social/feed")
async def get_activity_feed(request: Request, limit: int = 50):
    user = await get_current_user(request)
    return await social_service.get_activity_feed(user["_id"], limit)

@api_router.get("/social/feed/global")
async def get_global_feed(limit: int = 50):
    return await social_service.get_global_activity(limit)

@api_router.get("/social/leaderboard")
async def get_leaderboard(limit: int = 20):
    return await social_service.get_leaderboard(limit)

@api_router.get("/social/profile/{user_id}")
async def get_trader_profile(user_id: str, request: Request):
    try:
        current_user = await get_current_user(request)
        current_user_id = current_user["_id"]
    except:
        current_user_id = None
    return await social_service.get_trader_profile(user_id, current_user_id)

@api_router.get("/social/profile")
async def get_my_profile(request: Request):
    user = await get_current_user(request)
    return await social_service.get_trader_profile(user["_id"], user["_id"])

# ===================== AUTO-EXECUTE ROUTES =====================

@api_router.get("/auto-execute/logs")
async def get_auto_execute_logs(request: Request, limit: int = 50):
    user = await get_current_user(request)
    return await auto_execute_service.get_auto_execute_logs(user["_id"], limit)

@api_router.post("/auto-execute/toggle/{strategy_id}")
async def toggle_auto_execute(strategy_id: str, enabled: bool, request: Request):
    user = await get_current_user(request)
    result = await db.strategy_subscriptions.update_one(
        {"user_id": user["_id"], "strategy_id": strategy_id},
        {"$set": {"auto_execute": enabled}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"message": f"Auto-execute {'enabled' if enabled else 'disabled'}", "auto_execute": enabled}

# ===================== PUSH NOTIFICATION ROUTES =====================

@api_router.get("/risk-analytics")
async def get_risk_analytics(request: Request):
    """Get comprehensive portfolio risk analytics"""
    user = await get_current_user(request)
    return await risk_analytics_service.compute_portfolio_risk(user["_id"])

@api_router.get("/ai-brief")
async def get_ai_brief(request: Request):
    """Get AI-generated daily market brief"""
    await get_current_user(request)
    # Gather market context
    bond_data = await bond_analytics_service.get_bond_analytics()
    auction_cal = await bond_auction_service.get_auction_calendar_summary()
    context = {**bond_data, "auctions": auction_cal}
    return await ai_brief_service.generate_brief(context)

# ===================== RISK ALERT ROUTES =====================

@api_router.get("/risk-alerts/config")
async def get_risk_alert_config(request: Request):
    """Get risk alert threshold configuration"""
    user = await get_current_user(request)
    return await risk_alert_service.get_alert_config(user["_id"])

@api_router.post("/risk-alerts/config")
async def save_risk_alert_config(config: Dict[str, Any], request: Request):
    """Save risk alert threshold configuration"""
    user = await get_current_user(request)
    return await risk_alert_service.save_alert_config(user["_id"], config)

@api_router.post("/risk-alerts/check")
async def check_risk_alerts(request: Request):
    """Manually trigger risk check against thresholds"""
    user = await get_current_user(request)
    result = await risk_alert_service.check_risk_and_alert(user["_id"])
    # Save risk snapshot for trend tracking
    try:
        risk_data = await risk_analytics_service.compute_portfolio_risk(user["_id"])
        await risk_trend_service.save_snapshot(user["_id"], risk_data)
    except Exception as e:
        logger.debug(f"Risk snapshot save error: {e}")
    # Broadcast any alerts via WebSocket
    if result.get("alerts_fired", 0) > 0:
        await manager.broadcast({
            "type": "RISK_ALERT",
            "alerts": result.get("alerts", []),
            "risk_snapshot": result.get("risk_snapshot", {})
        })
    return result

@api_router.get("/risk-alerts/history")
async def get_risk_alert_history(request: Request, limit: int = 30):
    """Get risk alert history"""
    user = await get_current_user(request)
    return await risk_alert_service.get_alert_history(user["_id"], limit)

# ===================== RISK TREND ROUTES =====================

@api_router.get("/risk-trends")
async def get_risk_trends(request: Request, days: int = 30):
    """Get historical risk metric trends"""
    user = await get_current_user(request)
    return await risk_trend_service.get_trend_data(user["_id"], days)

@api_router.get("/risk-trends/summary")
async def get_risk_trend_summary(request: Request, days: int = 30):
    """Get risk trend summary with deltas"""
    user = await get_current_user(request)
    return await risk_trend_service.get_trend_summary(user["_id"], days)

@api_router.post("/risk-trends/snapshot")
async def save_risk_snapshot(request: Request):
    """Manually save a risk snapshot for trend tracking"""
    user = await get_current_user(request)
    risk_data = await risk_analytics_service.compute_portfolio_risk(user["_id"])
    await risk_trend_service.save_snapshot(user["_id"], risk_data)
    return {"saved": True, "timestamp": datetime.now(timezone.utc).isoformat()}

# ===================== EMAIL DIGEST ROUTES =====================

@api_router.get("/email-digest/preferences")
async def get_email_preferences(request: Request):
    """Get email digest preferences"""
    user = await get_current_user(request)
    return await email_digest_service.get_email_preferences(user["_id"])

@api_router.post("/email-digest/preferences")
async def save_email_preferences(prefs: Dict[str, Any], request: Request):
    """Save email digest preferences"""
    user = await get_current_user(request)
    return await email_digest_service.save_email_preferences(user["_id"], prefs)

@api_router.post("/email-digest/send")
async def send_digest_now(request: Request):
    """Manually trigger a daily digest email"""
    user = await get_current_user(request)
    risk_data = await risk_analytics_service.compute_portfolio_risk(user["_id"])
    alerts = await risk_alert_service.get_alert_history(user["_id"], 10)
    bond_data = await bond_analytics_service.get_bond_analytics()
    auction_cal = await bond_auction_service.get_auction_calendar_summary()
    ai_brief = await ai_brief_service.generate_brief({**bond_data, "auctions": auction_cal})
    portfolio_data = await portfolio_manager.get_portfolio(user["_id"])
    result = await email_digest_service.generate_and_send_digest(
        user["_id"], user.get("email", ""), risk_data, alerts, ai_brief, portfolio_data.model_dump() if hasattr(portfolio_data, 'model_dump') else portfolio_data
    )
    return result

@api_router.get("/email-digest/history")
async def get_digest_history(request: Request):
    """Get email digest send history"""
    user = await get_current_user(request)
    return await email_digest_service.get_digest_history(user["_id"])

# ===================== PORTFOLIO OPTIMIZATION ROUTES =====================

@api_router.get("/portfolio-optimizer/assets")
async def get_optimizer_assets(request: Request):
    """Get available assets for optimization"""
    await get_current_user(request)
    return {"assets": PortfolioOptimizer.ASSETS}

@api_router.post("/portfolio-optimizer/optimize")
async def run_portfolio_optimization(body: Dict[str, Any], request: Request):
    """Run Black-Litterman portfolio optimization"""
    await get_current_user(request)
    views = body.get("views", [])
    risk_aversion = body.get("risk_aversion", 2.5)
    tau = body.get("tau", 0.05)
    constraints = body.get("constraints")
    return await portfolio_optimizer.optimize(views, risk_aversion, tau, constraints)

@api_router.post("/notifications/subscribe")
async def subscribe_push_notifications(subscription: Dict[str, Any], request: Request):
    user = await get_current_user(request)
    await db.push_subscriptions.update_one(
        {"user_id": user["_id"]},
        {"$set": {"subscription": subscription, "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    return {"message": "Push notifications enabled"}

@api_router.delete("/notifications/unsubscribe")
async def unsubscribe_push_notifications(request: Request):
    user = await get_current_user(request)
    await db.push_subscriptions.delete_one({"user_id": user["_id"]})
    return {"message": "Push notifications disabled"}

@api_router.get("/notifications/status")
async def get_push_status(request: Request):
    user = await get_current_user(request)
    sub = await db.push_subscriptions.find_one({"user_id": user["_id"]})
    return {"enabled": sub is not None}

# ===================== MULTI-ASSET ROUTES =====================

@api_router.get("/assets")
async def get_available_assets():
    return [
        {"symbol": asset.symbol, "name": asset.name, "asset_type": asset.asset_type.value, "enabled": asset.enabled}
        for asset in AVAILABLE_ASSETS.values()
    ]

@api_router.get("/assets/prices")
async def get_all_asset_prices():
    return await multi_asset_service.get_all_assets_prices()

@api_router.get("/assets/{symbol}/price")
async def get_asset_price(symbol: str):
    price = await multi_asset_service.get_asset_price(symbol.upper())
    if not price:
        raise HTTPException(status_code=404, detail=f"Asset {symbol} not found")
    return price

# ===================== PAPER TRADING ROUTES =====================

@api_router.get("/paper-trading/portfolio")
async def get_paper_portfolio(request: Request):
    user = await get_current_user(request)
    return await paper_trading_manager.get_paper_portfolio(user["_id"])

@api_router.post("/paper-trading/trade")
async def execute_paper_trade(asset: str, quantity: int, action: str, request: Request):
    user = await get_current_user(request)
    return await paper_trading_manager.execute_paper_trade(user["_id"], asset.upper(), quantity, action.upper())

@api_router.post("/paper-trading/reset")
async def reset_paper_portfolio(initial_capital: float = 100000.0, request: Request = None):
    user = await get_current_user(request)
    return await paper_trading_manager.reset_paper_portfolio(user["_id"], initial_capital)

@api_router.get("/paper-trading/history")
async def get_paper_trade_history(request: Request, limit: int = 50):
    user = await get_current_user(request)
    return await paper_trading_manager.get_paper_trade_history(user["_id"], limit)

# ===================== STRATEGY MARKETPLACE ROUTES =====================

@api_router.get("/marketplace/strategies")
async def get_marketplace_strategies(limit: int = 50, sort_by: str = "subscribers"):
    return await strategy_marketplace.get_marketplace_strategies(limit, sort_by)

@api_router.get("/marketplace/strategies/{strategy_id}")
async def get_strategy_details(strategy_id: str):
    strategy = await strategy_marketplace.get_strategy_details(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy

@api_router.post("/marketplace/strategies/publish")
async def publish_strategy(name: str, description: str, strategy_type: str, config: Dict[str, Any], request: Request):
    user = await get_current_user(request)
    try:
        st = StrategyType(strategy_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid strategy type")
    return await strategy_marketplace.publish_strategy(user["_id"], user["name"], name, description, st, config)

@api_router.delete("/marketplace/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, request: Request):
    user = await get_current_user(request)
    return await strategy_marketplace.delete_strategy(user["_id"], strategy_id)

@api_router.get("/marketplace/my-strategies")
async def get_my_strategies(request: Request):
    user = await get_current_user(request)
    return await strategy_marketplace.get_user_published_strategies(user["_id"])

@api_router.post("/marketplace/strategies/{strategy_id}/subscribe")
async def subscribe_to_strategy(strategy_id: str, auto_execute: bool = False, request: Request = None):
    user = await get_current_user(request)
    return await strategy_marketplace.subscribe_to_strategy(user["_id"], strategy_id, auto_execute)

@api_router.delete("/marketplace/strategies/{strategy_id}/unsubscribe")
async def unsubscribe_from_strategy(strategy_id: str, request: Request):
    user = await get_current_user(request)
    return await strategy_marketplace.unsubscribe_from_strategy(user["_id"], strategy_id)

@api_router.get("/marketplace/subscriptions")
async def get_my_subscriptions(request: Request):
    user = await get_current_user(request)
    return await strategy_marketplace.get_user_subscriptions(user["_id"])

@api_router.post("/marketplace/strategies/{strategy_id}/rate")
async def rate_strategy(strategy_id: str, rating: int, comment: Optional[str] = None, request: Request = None):
    user = await get_current_user(request)
    return await strategy_marketplace.rate_strategy(user["_id"], strategy_id, rating, comment)

# ===================== WEBSOCKET =====================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await market_service.get_real_market_data()
            previous = market_data_history[-1] if market_data_history else None
            risk_result = ai_engine.scan_risk(data, previous)

            if risk_result["status"] != "SAFE" and system_state.status == SystemStatus.SAFE:
                system_state.status = SystemStatus(risk_result["status"])
                system_state.last_updated = datetime.now(timezone.utc)
                await telegram_notifier.send_risk_alert(
                    risk_result["status"],
                    f"Rate change: {risk_result['change']:.2%}\nReason: {risk_result.get('reason', 'High volatility detected')}"
                )

            market_data_history.append(data)
            if len(market_data_history) > 100:
                market_data_history.pop(0)

            system_state.black_swan_probability = min(0.5, system_state.black_swan_probability + risk_result["change"] * 0.1)
            if risk_result["status"] == "SAFE":
                system_state.black_swan_probability = max(0.01, system_state.black_swan_probability * 0.95)

            await websocket.send_json({
                "type": "MARKET_UPDATE",
                "data": data.model_dump(),
                "system_state": {
                    "status": system_state.status.value,
                    "lifecycle": system_state.lifecycle.value,
                    "mode": system_state.mode.value,
                    "black_swan_probability": system_state.black_swan_probability
                }
            })

            if len(market_data_history) % 10 == 0:
                try:
                    bond_data = await bond_analytics_service.get_bond_analytics()
                    await websocket.send_json({"type": "BOND_ANALYTICS", "data": bond_data})
                except Exception as e:
                    logger.debug(f"Bond analytics WS error: {e}")

            # Periodic risk alert check (every ~20 cycles = ~60 seconds)
            if len(market_data_history) % 20 == 0:
                try:
                    # Check all users with active alert configs
                    configs = await db.risk_alert_configs.find({"enabled": True}).to_list(50)
                    for cfg in configs:
                        uid = cfg["user_id"]
                        result = await risk_alert_service.check_risk_and_alert(uid)
                        if result.get("alerts_fired", 0) > 0:
                            await manager.broadcast({
                                "type": "RISK_ALERT",
                                "user_id": uid,
                                "alerts": result.get("alerts", []),
                                "risk_snapshot": result.get("risk_snapshot", {})
                            })
                except Exception as e:
                    logger.debug(f"Risk alert WS check error: {e}")

            if (system_state.lifecycle == Lifecycle.GO_LIVE and
                system_state.status == SystemStatus.SAFE and
                random.random() > 0.85):
                analysis = await ai_engine.analyze_market(data, current_strategy, bond_analytics_service)
                if analysis and analysis.get("confidence", 0) > current_strategy.confidence_threshold:
                    action_map = {
                        "BUY_BOND": SignalType.BOND_BUY, "SELL_BOND": SignalType.BOND_SELL,
                        "RATE_LONG": SignalType.RATE_LONG, "RATE_SHORT": SignalType.RATE_SHORT
                    }
                    signal_type = action_map.get(analysis.get("action", ""), SignalType.BOND_BUY)
                    signal = TradingSignal(
                        signal_type=signal_type, confidence=analysis.get("confidence", 0.8),
                        status="PENDING", timestamp=datetime.now(timezone.utc),
                        ai_reasoning=analysis.get("reasoning", ""),
                        strategy=current_strategy.strategy_type.value
                    )
                    trading_signals.append(signal)
                    await telegram_notifier.send_signal_alert(signal)
                    await websocket.send_json({"type": "NEW_SIGNAL", "signal": signal.model_dump()})

            await asyncio.sleep(3)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ===================== HEALTH CHECK =====================

@api_router.get("/")
async def root():
    return {"message": "AI Bond Trading System API V5", "version": "5.0.0"}

@api_router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "ai_engine": "initialized" if ai_engine.llm_chat else "rule-based",
        "telegram": "enabled" if telegram_notifier.enabled else "disabled",
        "market_data": "yahoo_finance" if market_service.use_real_data else "simulated",
        "system_status": system_state.status.value,
        "features": ["paper_trading", "multi_asset", "strategy_marketplace", "2fa", "social", "auto_execute", "bond_analytics", "yield_curve", "bond_auctions", "risk_analytics", "ai_brief", "risk_alerts", "email_digest", "risk_trends", "portfolio_optimizer"]
    }

# Include the router
app.include_router(api_router)

# Include security router
try:
    from security_routes import bond_security_router, set_bond_security_instance
    from security_integration import get_bond_security_integration
    
    # Initialize security integration
    async def init_bond_security():
        security = get_bond_security_integration(db)
        await security.initialize()
        set_bond_security_instance(security)
        logger.info("Bond Security integration initialized successfully")
    
    # Add startup event for security
    @app.on_event("startup")
    async def startup_bond_security():
        await init_bond_security()
    
    app.include_router(bond_security_router)
    logger.info("Bond Security router included")
except ImportError as e:
    logger.warning(f"Bond Security module not available: {e}")
