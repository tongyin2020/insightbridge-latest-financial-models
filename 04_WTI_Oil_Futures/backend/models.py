"""
WTI Trading Platform - Data Models
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import uuid


class Regime(str, Enum):
    NORMAL = "normal"
    EVENT = "event"
    TREND = "trend"
    BLOCKED = "blocked"


class EventPriority(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


class SignalStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    PENDING = "pending"


class ExitReason(str, Enum):
    STOP_LOSS = "stop_loss"
    TIME_EXIT = "time_exit"
    NO_MOMENTUM = "no_momentum"
    REVERSE_SHOCK = "reverse_shock"
    PARTIAL_PROFIT = "partial_profit"
    RISK_CONTROL = "risk_control"
    MANUAL = "manual"


# Market Data Models
class Bar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    symbol: str = "CL"


class Tick(BaseModel):
    timestamp: datetime
    bid: float
    ask: float
    last: float
    volume: int
    symbol: str = "CL"

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


class Indicators(BaseModel):
    timestamp: datetime
    ema_fast: float
    ema_slow: float
    adx: float
    atr: float
    atr_baseline: float
    vwap: float
    volume_ratio: float
    volatility_ratio: float


# Event Models
class MarketEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""
    priority: EventPriority = EventPriority.C
    headline: str = ""
    actual_value: Optional[float] = None
    forecast_value: Optional[float] = None
    surprise_pct: Optional[float] = None
    raw_source: str = ""
    confirmed: bool = False


# Signal Models
class Signal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str = "CL"
    direction: Optional[Direction] = None
    status: SignalStatus = SignalStatus.PENDING
    trigger_event: Optional[str] = None
    trigger_regime: Optional[Regime] = None
    entry_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    initial_target_price: Optional[float] = None
    ema_aligned: bool = False
    adx_confirmed: bool = False
    volume_confirmed: bool = False
    vwap_ok: bool = False
    spread_ok: bool = False
    breakout_confirmed: bool = False
    reject_reason: str = ""
    confidence_score: float = 0.0


# Position Models
class Position(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str = "CL"
    direction: Direction = Direction.LONG
    quantity: int = 1
    entry_price: float = 0.0
    stop_loss_price: float = 0.0
    current_price: float = 0.0
    signal_id: Optional[str] = None
    is_open: bool = True
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    unrealized_pnl: float = 0.0


# Risk State
class RiskState(BaseModel):
    daily_pnl: float = 0.0
    daily_loss_used_pct: float = 0.0
    consecutive_losses: int = 0
    total_trades_today: int = 0
    is_halted: bool = False
    halt_reason: str = ""
    kill_switch_active: bool = False
    max_drawdown: float = 0.0


# Trade Record
class TradeRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    date: str = ""
    symbol: str = "CL"
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 1
    pnl_usd: float = 0.0
    hold_minutes: float = 0.0
    trigger_event: str = ""
    exit_reason: str = ""
    regime_at_entry: str = ""
    notes: str = ""


# Economic Calendar Event
class EconomicEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_name: str
    country: str
    date: datetime
    importance: str  # high, medium, low
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None
    event_type: str = ""  # EIA, OPEC, FED, etc.


# Backtest Models
class BacktestConfig(BaseModel):
    start_date: str
    end_date: str
    in_sample_end: Optional[str] = None
    initial_equity: float = 50000.0
    slippage_ticks: float = 1.5
    commission_per_rt: float = 4.0


class BacktestResult(BaseModel):
    config: BacktestConfig
    trade_records: List[TradeRecord] = []
    equity_curve: List[Dict[str, Any]] = []
    final_equity: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0


# System State
class SystemState(BaseModel):
    is_running: bool = False
    mode: str = "paper"  # paper or live
    current_regime: Regime = Regime.NORMAL
    regime_override: Optional[Regime] = None
    override_reason: str = ""
    override_expiry: Optional[datetime] = None
    equity: float = 50000.0
    daily_pnl: float = 0.0


# API Response Models
class RegimeOverrideRequest(BaseModel):
    regime: Regime
    reason: str
    duration_hours: float = 4.0


class MLPrediction(BaseModel):
    predicted_regime: Regime
    confidence: float
    signal_direction: Optional[Direction] = None
    signal_confidence: float = 0.0
    reasoning: str = ""
