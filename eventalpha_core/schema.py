from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class AssetClass(str, Enum):
    FX = "fx"
    RATES = "rates"
    CRYPTO = "crypto"
    OIL = "oil"
    INDEX = "index"


class EventType(str, Enum):
    CPI = "cpi"
    FOMC = "fomc"
    NFP = "nfp"
    GDP = "gdp"
    TREASURY_AUCTION = "treasury_auction"
    CENTRAL_BANK = "central_bank"
    OPEC = "opec"
    EIA_INVENTORY = "eia_inventory"
    GEOPOLITICAL = "geopolitical"
    LIQUIDITY_SHOCK = "liquidity_shock"
    REGULATORY = "regulatory"
    EARNINGS_SHOCK = "earnings_shock"
    UNKNOWN = "unknown"


class EventGrade(str, Enum):
    IGNORE = "ignore"
    WATCH = "watch"
    TRADE_CANDIDATE = "trade_candidate"
    HIGH_CONVICTION = "high_conviction"
    EXTREME = "extreme"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class DecisionAction(str, Enum):
    IGNORE = "ignore"
    WATCH = "watch"
    PAPER_TRADE = "paper_trade"
    ENTER_SMALL = "enter_small"
    ENTER_NORMAL = "enter_normal"
    ENTER_HEAVY = "enter_heavy"
    REDUCE = "reduce"
    EXIT = "exit"


class MacroRegime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    INFLATION_SHOCK = "inflation_shock"
    LIQUIDITY_STRESS = "liquidity_stress"
    WAR_SHOCK = "war_shock"
    MIXED = "mixed"


class EventStage(str, Enum):
    EMERGING = "emerging"
    CONFIRMED = "confirmed"
    ESCALATING = "escalating"
    FADING = "fading"
    INVALIDATED = "invalidated"


@dataclass
class MacroEvent:
    event_id: str
    event_type: EventType
    title: str
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "manual_or_api"
    source_confidence: float = 0.50
    surprise_score: float = 0.0
    geopolitical_score: float = 0.0
    liquidity_score: float = 0.0
    policy_score: float = 0.0
    novelty_score: float = 0.50
    credibility_score: float = 0.50
    escalation_score: float = 0.0
    narrative_bias: float = 0.0
    stage: EventStage = EventStage.EMERGING
    human_thesis: Optional[str] = None
    expected_assets: List[AssetClass] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegimeState:
    regime: MacroRegime
    confidence: float
    inflation_pressure: float
    growth_pressure: float
    liquidity_stress: float
    geopolitical_stress: float
    risk_sentiment: float
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketState:
    asset: AssetClass
    symbol: str
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    price: float = 0.0
    spread_bps: float = 0.0
    volatility_z: float = 0.0
    momentum_score: float = 0.50
    reversal_score: float = 0.0
    liquidity_score: float = 0.50
    cross_asset_alignment: float = 0.50
    news_alignment: float = 0.50
    orderbook_pressure: float = 0.50
    trend_persistence: float = 0.50
    execution_quality: float = 0.50
    breakout_quality: float = 0.50
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventDecision:
    action: DecisionAction
    grade: EventGrade
    asset: AssetClass
    symbol: str
    direction: Direction
    raw_score: float
    calibrated_confidence: float
    execution_confidence: float
    wait_seconds: int
    max_risk_fraction: float
    reasons: List[str]
    invalidation_rules: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionState:
    asset: AssetClass
    symbol: str
    direction: Direction
    entry_price: float
    current_price: float
    max_price_since_entry: float
    min_price_since_entry: float
    seconds_in_trade: int
    confidence_at_entry: float
    confidence_now: float
    spread_bps: float
    momentum_score: float
    reversal_score: float
    cross_asset_alignment: float
    news_alignment: float
    thesis_validity: float = 0.50
    market_quality: float = 0.50
    momentum_persistence: float = 0.50
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExitDecision:
    action: DecisionAction
    urgency: int
    reason: str
    reduce_fraction: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
