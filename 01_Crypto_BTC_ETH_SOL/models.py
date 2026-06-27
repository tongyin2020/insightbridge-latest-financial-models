"""
Core data models for the Crypto AI Trading System
Based on the user's design specification
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid


# ===================== ENUMS =====================
class Regime(str, Enum):
    NORMAL = "NORMAL"
    MOMENTUM = "MOMENTUM"
    SQUEEZE_RISK = "SQUEEZE_RISK"
    UNSTABLE = "UNSTABLE"


class EventState(str, Enum):
    IDLE = "IDLE"
    WAIT = "WAIT"
    READY = "READY"
    INVALID = "INVALID"


class FragilityState(str, Enum):
    LOW = "LOW_FRAGILITY"
    MEDIUM = "MEDIUM_FRAGILITY"
    HIGH = "HIGH_FRAGILITY"


class GateAction(str, Enum):
    ALLOW = "ALLOW"
    ALLOW_REDUCED = "ALLOW_REDUCED"
    BLOCK = "BLOCK"
    EXIT_NOW = "EXIT_NOW"
    FREEZE = "FREEZE"


class SignalType(str, Enum):
    LONG_CANDIDATE = "LONG_CANDIDATE"
    SHORT_CANDIDATE = "SHORT_CANDIDATE"
    NO_TRADE = "NO_TRADE"


# ===================== DATACLASSES =====================
@dataclass
class FeatureSnapshot:
    """Real-time market feature snapshot for a symbol"""
    symbol: str
    ts: str
    price: float = 0.0
    price_change_24h: float = 0.0
    volume_24h: float = 0.0
    spread_ratio: float = 0.0
    depth_shrink_ratio: float = 0.0
    taker_buy_ratio: float = 0.5
    taker_sell_ratio: float = 0.5
    oi_delta_ratio: float = 0.0
    funding_rate: float = 0.0
    liquidation_proximity: float = 0.0
    venue_divergence: float = 0.0
    stale_quote: bool = False
    abnormal_wick_score: float = 0.0
    network_incident_flag: bool = False
    exchange_incident_flag: bool = False
    bid_volume: float = 0.0
    ask_volume: float = 0.0


@dataclass
class SignalCandidate:
    """Trading signal candidate output"""
    symbol: str
    ts: str
    side: Optional[str]
    direction_score: float
    conviction_score: float
    fragility_score: float
    candidate_type: str
    reason_codes: List[str] = field(default_factory=list)


@dataclass
class GateInput:
    """Input for the Execution Gate"""
    symbol: str
    ts: str
    regime: Regime
    event_state: EventState
    fragility: FragilityState
    trade_allowed: bool
    signal_side: Optional[str]
    signal_confidence: float
    stale_quote: bool
    venue_divergence: float
    daily_drawdown_hit: bool
    deterioration_triggered: bool
    cooldown_state: str
    risk_multiplier: float
    position_open: bool
    position_side: Optional[str]
    position_age_minutes: float
    max_position_age_minutes: float
    exchange_incident_flag: bool = False
    network_incident_flag: bool = False


@dataclass
class GateDecision:
    """Execution Gate decision output"""
    action: GateAction
    approved_side: Optional[str]
    size_multiplier: float
    reason_codes: List[str] = field(default_factory=list)


# ===================== PYDANTIC MODELS FOR API =====================
class MarketDataResponse(BaseModel):
    symbol: str
    price: float
    price_change_24h: float
    volume_24h: float
    high_24h: float
    low_24h: float
    timestamp: str


class SignalResponse(BaseModel):
    symbol: str
    side: Optional[str]
    direction_score: float
    conviction_score: float
    fragility_score: float
    candidate_type: str
    reason_codes: List[str]
    timestamp: str


class SystemStateResponse(BaseModel):
    symbol: str
    regime: str
    event_state: str
    fragility_state: str
    gate_action: str
    gate_reason: List[str]
    timestamp: str


class AIAnalysisResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    analysis: str
    sentiment: str
    confidence: float
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TradeSignalLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    side: str
    direction_score: float
    conviction_score: float
    fragility_score: float
    regime: str
    gate_action: str
    ai_recommendation: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
