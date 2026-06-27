from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum
from bson import ObjectId


class SystemStatus(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    EXIT_ONLY = "EXIT_ONLY"
    HALT = "HALT"

class Lifecycle(str, Enum):
    PRE_LIVE = "PRE-LIVE"
    GO_LIVE = "GO-LIVE"

class TradingMode(str, Enum):
    NORMAL = "NORMAL"
    REDUCE = "REDUCE"
    RESTART = "RESTART"

class SignalType(str, Enum):
    BOND_BUY = "BOND_BUY"
    BOND_SELL = "BOND_SELL"
    RATE_LONG = "RATE_LONG"
    RATE_SHORT = "RATE_SHORT"

class StrategyType(str, Enum):
    MEAN_REVERSION = "MEAN_REVERSION"
    MOMENTUM = "MOMENTUM"
    SPREAD_ARBITRAGE = "SPREAD_ARBITRAGE"
    AI_HYBRID = "AI_HYBRID"

class AssetType(str, Enum):
    BOND = "BOND"
    COMMODITY = "COMMODITY"
    FOREX = "FOREX"
    INDEX = "INDEX"
    CRYPTO = "CRYPTO"

class TradingModeType(str, Enum):
    LIVE = "LIVE"
    PAPER = "PAPER"


# ---- Pydantic Models ----

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str = Field(alias="_id")
    email: str
    name: str
    role: str
    created_at: datetime
    model_config = ConfigDict(populate_by_name=True)

class MarketData(BaseModel):
    timestamp: datetime
    wti_price: float
    bond_yield: float
    ispread: float
    risk_score: float
    source: str = "simulated"

class TradingSignal(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    signal_type: SignalType
    confidence: float
    status: str
    timestamp: datetime
    ai_reasoning: Optional[str] = None
    execution_price: Optional[float] = None
    strategy: Optional[str] = None

class SystemState(BaseModel):
    status: SystemStatus = SystemStatus.SAFE
    lifecycle: Lifecycle = Lifecycle.PRE_LIVE
    mode: TradingMode = TradingMode.NORMAL
    is_locked: bool = True
    black_swan_probability: float = 0.012
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StrategyConfig(BaseModel):
    strategy_type: StrategyType
    ispread_upper: float = 15.0
    ispread_lower: float = 10.0
    confidence_threshold: float = 0.8
    max_position_size: int = 100
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    use_ai: bool = True
    momentum_period: int = 14
    mean_reversion_window: int = 20

class BacktestRequest(BaseModel):
    strategy_type: StrategyType
    start_date: str
    end_date: str
    initial_capital: float = 100000.0
    strategy_params: Optional[Dict[str, Any]] = None

class BacktestResult(BaseModel):
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    profitable_trades: int
    average_trade_return: float
    volatility: float
    trades: List[Dict[str, Any]]
    equity_curve: List[Dict[str, Any]]

class PortfolioPosition(BaseModel):
    asset: str
    quantity: int
    avg_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

class Portfolio(BaseModel):
    user_id: str
    cash: float
    positions: List[PortfolioPosition]
    total_value: float
    total_pnl: float
    total_pnl_pct: float
    updated_at: datetime

class AlertSettings(BaseModel):
    telegram_enabled: bool = True
    alert_on_signal: bool = True
    alert_on_execution: bool = True
    alert_on_risk: bool = True
    alert_on_system: bool = True

class Asset(BaseModel):
    symbol: str
    name: str
    asset_type: AssetType
    yahoo_symbol: str
    multiplier: float = 1.0
    enabled: bool = True

class PublishedStrategy(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    user_id: str
    user_name: str
    name: str
    description: str
    strategy_type: StrategyType
    config: Dict[str, Any]
    is_public: bool = True
    subscribers: int = 0
    rating: float = 0.0
    total_ratings: int = 0
    performance: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StrategySubscription(BaseModel):
    user_id: str
    strategy_id: str
    subscribed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    auto_execute: bool = False

class StrategyRating(BaseModel):
    user_id: str
    strategy_id: str
    rating: int
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TwoFactorSetup(BaseModel):
    secret: str
    qr_code: str
    backup_codes: List[str]

class UserFollow(BaseModel):
    follower_id: str
    following_id: str
    followed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ActivityFeed(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    user_id: str
    user_name: str
    activity_type: str
    description: str
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TraderStats(BaseModel):
    user_id: str
    user_name: str
    total_trades: int = 0
    profitable_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    followers: int = 0
    following: int = 0
    strategies_published: int = 0
    rank: int = 0

class AutoExecuteLog(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    user_id: str
    strategy_id: str
    strategy_name: str
    signal_type: str
    execution_price: float
    quantity: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Available assets for multi-asset support
AVAILABLE_ASSETS = {
    "10Y_BOND": Asset(symbol="10Y_BOND", name="10-Year Treasury Bond", asset_type=AssetType.BOND, yahoo_symbol="^TNX"),
    "WTI": Asset(symbol="WTI", name="WTI Crude Oil", asset_type=AssetType.COMMODITY, yahoo_symbol="CL=F"),
    "GOLD": Asset(symbol="GOLD", name="Gold", asset_type=AssetType.COMMODITY, yahoo_symbol="GC=F"),
    "EUR_USD": Asset(symbol="EUR_USD", name="EUR/USD", asset_type=AssetType.FOREX, yahoo_symbol="EURUSD=X"),
    "SP500": Asset(symbol="SP500", name="S&P 500 Index", asset_type=AssetType.INDEX, yahoo_symbol="^GSPC"),
    "BTC": Asset(symbol="BTC", name="Bitcoin", asset_type=AssetType.CRYPTO, yahoo_symbol="BTC-USD"),
    "30Y_BOND": Asset(symbol="30Y_BOND", name="30-Year Treasury Bond", asset_type=AssetType.BOND, yahoo_symbol="^TYX"),
    "SILVER": Asset(symbol="SILVER", name="Silver", asset_type=AssetType.COMMODITY, yahoo_symbol="SI=F"),
    "JPY_USD": Asset(symbol="JPY_USD", name="USD/JPY", asset_type=AssetType.FOREX, yahoo_symbol="JPY=X"),
    "NASDAQ": Asset(symbol="NASDAQ", name="NASDAQ 100", asset_type=AssetType.INDEX, yahoo_symbol="^NDX"),
}
