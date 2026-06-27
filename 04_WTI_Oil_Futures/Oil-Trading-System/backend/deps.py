"""
Shared dependencies and state for all routers.
Centralizes service instances and DB access.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import Request, HTTPException, WebSocket
from typing import List, Optional, Dict
from datetime import datetime, timezone
import os
import logging

from trading_engine import RiskService, RegimeService, SignalService, PaperBroker, MarketDataGenerator, EconomicCalendarService
from ml_service import MLEnhancementService
from backtest_engine import BacktestEngine, generate_historical_data
from multi_asset import MultiAssetDataGenerator, PortfolioAnalyzer, ASSETS
from options_service import OptionsService, OptionType, StrategyType, OptionsBacktester, options_backtester
from real_data_service import RealDataService
from email_service import EmailService, generate_verification_token
from notification_service import NotificationService, NotificationType, notification_service
from auto_strategy_service import AutoStrategySelector, auto_strategy_selector
from tradovate_service import TradovateService, tradovate_service
from fragility_engine import FragilityEngine, fragility_engine
from event_engine import EventEngine, event_engine
from risk_control import RiskControlCenter, risk_control
from execution_gate import ExecutionGate, SignalScorer, execution_gate, signal_scorer
from trading_bot import TradingBot, trading_bot, OpportunityStatus
from replay_engine import ReplayEngine, replay_engine
from payoff_calculator import calculate_payoff
from auth_service import get_current_user
from models import SystemState

logger = logging.getLogger("WTI_Platform")

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Services
multi_asset_generator = MultiAssetDataGenerator()
portfolio_analyzer = PortfolioAnalyzer(multi_asset_generator)
risk_service = RiskService()
regime_service = RegimeService()
signal_service = SignalService()
broker = PaperBroker(initial_equity=50000.0)
calendar_service = EconomicCalendarService()
ml_service = MLEnhancementService()
options_service = OptionsService()
real_data_service = RealDataService()
email_service = EmailService()

# System state
system_state = SystemState()
current_symbol = "CL"

# Background task state
simulation_task = None
simulation_running = False
take_profit_levels: Dict[str, Dict] = {}
last_regime_notified = None


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
            except Exception:
                pass

manager = ConnectionManager()


async def get_optional_user(request: Request) -> Optional[dict]:
    """Get current user if authenticated, None otherwise"""
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None
