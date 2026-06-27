"""
Crypto AI Trading System - Main Server
Complete implementation based on user's design specification
"""
from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr
import os
import logging
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from models import (
    MarketDataResponse, SignalResponse, SystemStateResponse,
    AIAnalysisResponse, TradeSignalLog, FeatureSnapshot, GateInput,
    Regime, EventState, FragilityState
)
from engines import (
    regime_engine, event_response_engine, fragility_engine,
    execution_gate, risk_engine, get_signal_engine
)
from websocket_feeds import get_market_feed, SimulatedMarketFeed
from ai_analyzer import ai_analyzer
from telegram_alerts import telegram_alert_service
from scheduler import trading_scheduler
from auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    get_current_user, check_brute_force, record_failed_attempt, clear_failed_attempts,
    seed_admin
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Default symbols to track
DEFAULT_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]

# Global state
market_feed: Optional[SimulatedMarketFeed] = None
connected_websockets: List[WebSocket] = []
system_state: Dict[str, dict] = {}
signal_history: List[dict] = []

# Initialize system state for all default symbols
for sym in DEFAULT_SYMBOLS:
    system_state[sym] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global market_feed
    
    # Startup
    logger.info("Starting Crypto AI Trading System...")
    logger.info(f"Tracking symbols: {DEFAULT_SYMBOLS}")
    
    market_feed = get_market_feed(DEFAULT_SYMBOLS)
    market_feed.add_callback(on_market_update)
    await market_feed.connect()
    
    # Start background tasks
    asyncio.create_task(process_signals_loop())
    
    # Setup and start scheduler for daily summaries (Beijing time)
    def get_current_states():
        return system_state
    
    trading_scheduler.set_callbacks(
        summary_callback=telegram_alert_service.send_scheduled_summary,
        get_states_callback=get_current_states
    )
    trading_scheduler.start()
    
    logger.info("System initialized successfully")
    logger.info(f"Scheduled summaries at 08:00, 12:00, 18:00, 21:00 Beijing time")
    
    # Seed admin user
    await seed_admin(db)
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    trading_scheduler.stop()
    if market_feed:
        await market_feed.stop()
    client.close()


# Create the main app
app = FastAPI(
    title="Crypto AI Trading System",
    description="Real-time crypto trading system with AI analysis for BTC, ETH, SOL",
    version="1.0.0",
    lifespan=lifespan
)

# Create API router
api_router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/api/auth")


# ==================== AUTH MODELS ====================

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str


# ==================== AUTH ENDPOINTS ====================

@auth_router.post("/login")
async def login(request: Request, login_data: LoginRequest, response: Response):
    """Login with email and password"""
    email = login_data.email.lower().strip()
    password = login_data.password
    
    # Get client IP for brute force protection
    client_ip = request.client.host if request.client else "unknown"
    identifier = f"{client_ip}:{email}"
    
    # Check brute force lockout
    if await check_brute_force(db, identifier):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again in 15 minutes.")
    
    # Find user
    user = await db.users.find_one({"email": email})
    
    if not user or not verify_password(password, user.get("password_hash", "")):
        await record_failed_attempt(db, identifier)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Clear failed attempts on success
    await clear_failed_attempts(db, identifier)
    
    # Create tokens
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    # Set cookies
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    return {
        "id": user_id,
        "email": user["email"],
        "name": user.get("name", "User"),
        "role": user.get("role", "user")
    }


@auth_router.post("/logout")
async def logout(response: Response):
    """Logout and clear cookies"""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}


@auth_router.get("/me")
async def get_me(request: Request):
    """Get current authenticated user"""
    user = await get_current_user(request, db)
    return {
        "id": user["_id"],
        "email": user["email"],
        "name": user.get("name", "User"),
        "role": user.get("role", "user")
    }


@auth_router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    """Refresh the access token"""
    import jwt
    from auth import get_jwt_secret
    
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")
    
    try:
        payload = jwt.decode(refresh_token, get_jwt_secret(), algorithms=["HS256"])
        
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        user_id = payload["sub"]
        from bson import ObjectId
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Create new access token
        new_access_token = create_access_token(user_id, user["email"])
        
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
        
        return {"message": "Token refreshed"}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


# ==================== MARKET DATA CALLBACKS ====================

async def on_market_update(symbol: str, data: dict):
    """Callback when market data updates"""
    # Broadcast to all connected WebSocket clients
    message = {
        "type": "market_update",
        "symbol": symbol,
        "data": data
    }
    
    for ws in connected_websockets[:]:
        try:
            await ws.send_json(message)
        except Exception:
            try:
                connected_websockets.remove(ws)
            except ValueError:
                pass  # Already removed


async def process_signals_loop():
    """Background loop to process trading signals"""
    global system_state, signal_history
    
    while True:
        try:
            # Get active symbols from market feed
            active_symbols = market_feed.get_active_symbols() if market_feed else DEFAULT_SYMBOLS
            
            for symbol in active_symbols:
                if market_feed:
                    # Get feature snapshot
                    snapshot = market_feed.create_feature_snapshot(symbol)
                    
                    # Run through engines
                    regime = regime_engine.evaluate(snapshot)
                    fragility = fragility_engine.evaluate(snapshot)
                    event_state = event_response_engine.evaluate(snapshot, 0, False)
                    
                    # Generate signal
                    signal_engine = get_signal_engine(symbol)
                    signal = signal_engine.generate(snapshot, regime, fragility)
                    
                    # Run execution gate
                    gate_input = GateInput(
                        symbol=symbol,
                        ts=snapshot.ts,
                        regime=regime,
                        event_state=event_state,
                        fragility=fragility,
                        trade_allowed=signal.candidate_type != "NO_TRADE",
                        signal_side=signal.side,
                        signal_confidence=signal.conviction_score,
                        stale_quote=snapshot.stale_quote,
                        venue_divergence=snapshot.venue_divergence,
                        daily_drawdown_hit=False,
                        deterioration_triggered=False,
                        cooldown_state="NORMAL",
                        risk_multiplier=1.0,
                        position_open=False,
                        position_side=None,
                        position_age_minutes=0,
                        max_position_age_minutes=30,
                        exchange_incident_flag=snapshot.exchange_incident_flag,
                        network_incident_flag=snapshot.network_incident_flag
                    )
                    
                    gate_decision = execution_gate.decide(gate_input)
                    
                    # Update system state
                    system_state[symbol] = {
                        "symbol": symbol,
                        "price": snapshot.price,
                        "price_change_24h": snapshot.price_change_24h,
                        "volume_24h": snapshot.volume_24h,
                        "regime": regime.value,
                        "event_state": event_state.value,
                        "fragility_state": fragility.value,
                        "direction_score": signal.direction_score,
                        "conviction_score": signal.conviction_score,
                        "fragility_score": signal.fragility_score,
                        "signal_type": signal.candidate_type,
                        "signal_side": signal.side,
                        "gate_action": gate_decision.action.value,
                        "gate_reasons": gate_decision.reason_codes,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Check for significant changes and send Telegram alerts
                    try:
                        await telegram_alert_service.check_and_alert(symbol, system_state[symbol])
                    except Exception as alert_error:
                        logger.error(f"Telegram alert error: {alert_error}")
                    
                    # Broadcast state update
                    for ws in connected_websockets[:]:
                        try:
                            await ws.send_json({
                                "type": "system_state",
                                "data": system_state[symbol]
                            })
                        except Exception:
                            try:
                                connected_websockets.remove(ws)
                            except ValueError:
                                pass
            
            await asyncio.sleep(1)  # Process every second
            
        except Exception as e:
            logger.error(f"Signal processing error: {e}")
            await asyncio.sleep(5)


# ==================== REST API ENDPOINTS ====================

@api_router.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "Crypto AI Trading System",
        "version": "1.0.0",
        "status": "operational",
        "assets": ["BTC", "ETH", "SOL"]
    }


@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "websocket_connections": len(connected_websockets),
        "telegram_alerts": telegram_alert_service.enabled
    }


@api_router.post("/telegram/test")
async def test_telegram():
    """Send a test message to Telegram"""
    success = await telegram_alert_service.send_test_message()
    if success:
        return {"status": "success", "message": "Test alert sent to Telegram"}
    raise HTTPException(status_code=500, detail="Failed to send Telegram message")


@api_router.post("/telegram/status")
async def send_telegram_status():
    """Send current system status to Telegram"""
    await telegram_alert_service.send_system_status(system_state)
    return {"status": "success", "message": "Status sent to Telegram"}


@api_router.post("/telegram/summary")
async def send_telegram_summary():
    """Manually trigger a trading summary to Telegram"""
    await telegram_alert_service.send_scheduled_summary(system_state)
    return {"status": "success", "message": "Trading summary sent to Telegram"}


@api_router.get("/telegram/schedule")
async def get_telegram_schedule():
    """Get scheduled summary times"""
    return trading_scheduler.get_schedule_info()


@api_router.post("/telegram/timezone")
async def set_telegram_timezone(timezone: str = "Asia/Shanghai"):
    """Set timezone for scheduled summaries (default: Beijing time)"""
    success = trading_scheduler.set_timezone(timezone)
    if success:
        return {
            "status": "success",
            "message": f"Timezone set to {timezone}",
            "schedule": trading_scheduler.get_schedule_info()
        }
    raise HTTPException(status_code=400, detail=f"Invalid timezone: {timezone}")


@api_router.get("/symbols")
async def get_symbols():
    """Get all supported and active symbols"""
    if market_feed:
        return {
            "supported": market_feed.get_supported_symbols(),
            "active": market_feed.get_active_symbols()
        }
    return {"supported": list(SimulatedMarketFeed.REFERENCE_PRICES.keys()), "active": DEFAULT_SYMBOLS}


@api_router.post("/symbols/{symbol}")
async def add_symbol(symbol: str):
    """Add a symbol to track"""
    symbol = symbol.upper()
    if market_feed and market_feed.add_symbol(symbol):
        system_state[symbol] = {}
        return {"status": "success", "message": f"Added {symbol}", "active": market_feed.get_active_symbols()}
    raise HTTPException(status_code=400, detail=f"Cannot add symbol: {symbol}")


@api_router.delete("/symbols/{symbol}")
async def remove_symbol(symbol: str):
    """Remove a symbol from tracking"""
    symbol = symbol.upper()
    if market_feed and market_feed.remove_symbol(symbol):
        if symbol in system_state:
            del system_state[symbol]
        return {"status": "success", "message": f"Removed {symbol}", "active": market_feed.get_active_symbols()}
    raise HTTPException(status_code=400, detail=f"Cannot remove symbol: {symbol}")


@api_router.get("/market/{symbol}", response_model=MarketDataResponse)
async def get_market_data(symbol: str):
    """Get current market data for a symbol"""
    symbol = symbol.upper()
    
    # Check if symbol is supported
    if market_feed:
        supported = market_feed.get_supported_symbols()
        if symbol not in supported:
            raise HTTPException(status_code=400, detail=f"Unsupported symbol: {symbol}. Supported: {supported}")
    
    if market_feed:
        data = market_feed.get_latest_data(symbol)
        return MarketDataResponse(
            symbol=symbol,
            price=data.get("price", 0),
            price_change_24h=data.get("price_change_24h", 0),
            volume_24h=data.get("volume_24h", 0),
            high_24h=data.get("high_24h", 0),
            low_24h=data.get("low_24h", 0),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat())
        )
    
    raise HTTPException(status_code=503, detail="Market feed not available")


@api_router.get("/market", response_model=List[MarketDataResponse])
async def get_all_market_data():
    """Get market data for all symbols"""
    results = []
    for symbol in ["BTC", "ETH", "SOL"]:
        if market_feed:
            data = market_feed.get_latest_data(symbol)
            results.append(MarketDataResponse(
                symbol=symbol,
                price=data.get("price", 0),
                price_change_24h=data.get("price_change_24h", 0),
                volume_24h=data.get("volume_24h", 0),
                high_24h=data.get("high_24h", data.get("price", 0)),
                low_24h=data.get("low_24h", data.get("price", 0)),
                timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat())
            ))
    return results


@api_router.get("/signal/{symbol}", response_model=SignalResponse)
async def get_signal(symbol: str):
    """Get current trading signal for a symbol"""
    symbol = symbol.upper()
    if symbol not in ["BTC", "ETH", "SOL"]:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    state = system_state.get(symbol, {})
    
    return SignalResponse(
        symbol=symbol,
        side=state.get("signal_side"),
        direction_score=state.get("direction_score", 50),
        conviction_score=state.get("conviction_score", 50),
        fragility_score=state.get("fragility_score", 0),
        candidate_type=state.get("signal_type", "NO_TRADE"),
        reason_codes=state.get("gate_reasons", []),
        timestamp=state.get("timestamp", datetime.now(timezone.utc).isoformat())
    )


@api_router.get("/signals", response_model=List[SignalResponse])
async def get_all_signals():
    """Get trading signals for all symbols"""
    results = []
    for symbol in ["BTC", "ETH", "SOL"]:
        state = system_state.get(symbol, {})
        results.append(SignalResponse(
            symbol=symbol,
            side=state.get("signal_side"),
            direction_score=state.get("direction_score", 50),
            conviction_score=state.get("conviction_score", 50),
            fragility_score=state.get("fragility_score", 0),
            candidate_type=state.get("signal_type", "NO_TRADE"),
            reason_codes=state.get("gate_reasons", []),
            timestamp=state.get("timestamp", datetime.now(timezone.utc).isoformat())
        ))
    return results


@api_router.get("/state/{symbol}", response_model=SystemStateResponse)
async def get_system_state(symbol: str):
    """Get full system state for a symbol"""
    symbol = symbol.upper()
    if symbol not in ["BTC", "ETH", "SOL"]:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    state = system_state.get(symbol, {})
    
    return SystemStateResponse(
        symbol=symbol,
        regime=state.get("regime", "NORMAL"),
        event_state=state.get("event_state", "READY"),
        fragility_state=state.get("fragility_state", "LOW_FRAGILITY"),
        gate_action=state.get("gate_action", "BLOCK"),
        gate_reason=state.get("gate_reasons", []),
        timestamp=state.get("timestamp", datetime.now(timezone.utc).isoformat())
    )


@api_router.get("/states")
async def get_all_system_states():
    """Get system state for all symbols"""
    results = []
    for symbol in ["BTC", "ETH", "SOL"]:
        state = system_state.get(symbol, {})
        results.append({
            "symbol": symbol,
            "price": state.get("price", 0),
            "price_change_24h": state.get("price_change_24h", 0),
            "volume_24h": state.get("volume_24h", 0),
            "regime": state.get("regime", "NORMAL"),
            "event_state": state.get("event_state", "READY"),
            "fragility_state": state.get("fragility_state", "LOW_FRAGILITY"),
            "direction_score": state.get("direction_score", 50),
            "conviction_score": state.get("conviction_score", 50),
            "fragility_score": state.get("fragility_score", 0),
            "signal_type": state.get("signal_type", "NO_TRADE"),
            "signal_side": state.get("signal_side"),
            "gate_action": state.get("gate_action", "BLOCK"),
            "gate_reasons": state.get("gate_reasons", []),
            "timestamp": state.get("timestamp", datetime.now(timezone.utc).isoformat())
        })
    return results


@api_router.get("/analysis/{symbol}", response_model=AIAnalysisResponse)
async def get_ai_analysis(symbol: str):
    """Get AI-powered market analysis for a symbol"""
    symbol = symbol.upper()
    if symbol not in ["BTC", "ETH", "SOL"]:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    state = system_state.get(symbol, {})
    
    if market_feed:
        snapshot = market_feed.create_feature_snapshot(symbol)
        signal_engine = get_signal_engine(symbol)
        regime = regime_engine.evaluate(snapshot)
        fragility = fragility_engine.evaluate(snapshot)
        signal = signal_engine.generate(snapshot, regime, fragility)
        
        analysis = await ai_analyzer.analyze_market_state(
            symbol=symbol,
            snapshot=snapshot,
            signal=signal,
            regime=state.get("regime", "NORMAL"),
            fragility=state.get("fragility_state", "LOW_FRAGILITY"),
            gate_action=state.get("gate_action", "BLOCK")
        )
        
        return AIAnalysisResponse(**analysis)
    
    raise HTTPException(status_code=503, detail="Analysis not available")


@api_router.get("/analysis")
async def get_all_ai_analysis():
    """Get AI analysis for all symbols"""
    results = []
    for symbol in ["BTC", "ETH", "SOL"]:
        state = system_state.get(symbol, {})
        
        if market_feed:
            snapshot = market_feed.create_feature_snapshot(symbol)
            signal_engine = get_signal_engine(symbol)
            regime = regime_engine.evaluate(snapshot)
            fragility = fragility_engine.evaluate(snapshot)
            signal = signal_engine.generate(snapshot, regime, fragility)
            
            analysis = await ai_analyzer.analyze_market_state(
                symbol=symbol,
                snapshot=snapshot,
                signal=signal,
                regime=state.get("regime", "NORMAL"),
                fragility=state.get("fragility_state", "LOW_FRAGILITY"),
                gate_action=state.get("gate_action", "BLOCK")
            )
            results.append(analysis)
    
    return results


@api_router.get("/signal-history")
async def get_signal_history(limit: int = 50):
    """Get recent signal history from database"""
    signals = await db.signal_history.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return signals


@api_router.post("/signal-log")
async def log_signal(signal: TradeSignalLog):
    """Log a trade signal to the database"""
    doc = signal.model_dump()
    doc['timestamp'] = doc['timestamp'] if isinstance(doc['timestamp'], str) else doc['timestamp'].isoformat()
    await db.signal_history.insert_one(doc)
    return {"status": "logged", "id": signal.id}


# ==================== WEBSOCKET ENDPOINT ====================

@api_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    connected_websockets.append(websocket)
    logger.info(f"WebSocket connected. Total connections: {len(connected_websockets)}")
    
    try:
        # Send initial state
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to Crypto AI Trading System",
            "assets": ["BTC", "ETH", "SOL"]
        })
        
        # Send current states
        for symbol in ["BTC", "ETH", "SOL"]:
            if symbol in system_state and system_state[symbol]:
                await websocket.send_json({
                    "type": "system_state",
                    "data": system_state[symbol]
                })
        
        # Keep connection alive and handle messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "subscribe":
                    # Handle subscription requests
                    pass
                    
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
        logger.info(f"WebSocket removed. Total connections: {len(connected_websockets)}")


# Include the routers
app.include_router(auth_router)
app.include_router(api_router)

# Include security router
try:
    from security_routes import security_router, set_security_instance
    from security_integration import get_security_integration
    
    # Initialize security integration
    async def init_security():
        security = get_security_integration(db)
        await security.initialize()
        set_security_instance(security)
        logger.info("Security integration initialized successfully")
    
    # Add startup event for security
    @app.on_event("startup")
    async def startup_security():
        await init_security()
    
    app.include_router(security_router)
    logger.info("Security router included")
except ImportError as e:
    logger.warning(f"Security module not available: {e}")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
