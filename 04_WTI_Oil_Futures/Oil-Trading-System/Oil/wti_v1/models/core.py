"""
WTI v1 — 核心数据模型
所有对象用dataclass定义，保证字段明确、可序列化、可日志记录。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


# ─────────────────────────────────────────────
# 枚举类型
# ─────────────────────────────────────────────

class Regime(str, Enum):
    """市场环境状态"""
    NORMAL = "normal"           # 常规波动，技术信号主导
    EVENT = "event"             # 重要事件窗口，事件驱动模式
    TREND = "trend"             # 单边趋势阶段，顺势跟随
    BLOCKED = "blocked"         # 极端异常，停止执行


class EventPriority(str, Enum):
    A = "A"     # 最高优先级
    B = "B"     # 中高优先级
    C = "C"     # 低优先级，通常忽略


class SignalStatus(str, Enum):
    ACCEPTED = "accepted"   # 信号通过确认，可执行
    REJECTED = "rejected"   # 信号未通过确认
    SKIPPED = "skipped"     # 因环境或风控跳过
    PENDING = "pending"     # 等待确认中


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ExitReason(str, Enum):
    STOP_LOSS = "stop_loss"
    TIME_EXIT = "time_exit"
    NO_MOMENTUM = "no_momentum"
    REVERSE_SHOCK = "reverse_shock"
    PARTIAL_PROFIT = "partial_profit"
    RISK_CONTROL = "risk_control"       # 风控强制平仓
    MANUAL = "manual"                   # 人工干预


# ─────────────────────────────────────────────
# 市场数据
# ─────────────────────────────────────────────

@dataclass
class Bar:
    """单根K线"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    symbol: str = "CL"

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)


@dataclass
class Tick:
    """实时报价"""
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


@dataclass
class Indicators:
    """指标计算结果（每根新K线后更新）"""
    timestamp: datetime
    ema_fast: float             # EMA20
    ema_slow: float             # EMA50
    adx: float                  # ADX(14)
    atr: float                  # ATR(14)
    atr_baseline: float         # 历史基准ATR（60周期均值）
    vwap: float                 # VWAP（当日）
    volume_ratio: float         # 当前量 / 20周期均量
    volatility_ratio: float     # atr / atr_baseline

    @property
    def ema_bullish(self) -> bool:
        return self.ema_fast > self.ema_slow

    @property
    def trend_strong(self) -> bool:
        return self.adx > 22.0

    @property
    def is_high_vol(self) -> bool:
        return self.volatility_ratio > 1.8


# ─────────────────────────────────────────────
# 事件
# ─────────────────────────────────────────────

@dataclass
class MarketEvent:
    """市场事件（新闻/经济数据/地缘政治）"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: str = ""                    # 如 "EIA_crude_inventory"
    priority: EventPriority = EventPriority.C
    headline: str = ""
    actual_value: Optional[float] = None
    forecast_value: Optional[float] = None
    surprise_pct: Optional[float] = None   # (actual - forecast) / |forecast|
    raw_source: str = ""                   # 数据来源标识
    confirmed: bool = False                # 是否已经过价格确认

    def compute_surprise(self):
        if self.actual_value is not None and self.forecast_value and self.forecast_value != 0:
            self.surprise_pct = (self.actual_value - self.forecast_value) / abs(self.forecast_value)


# ─────────────────────────────────────────────
# 信号
# ─────────────────────────────────────────────

@dataclass
class Signal:
    """交易信号（由信号服务生成）"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    symbol: str = "CL"
    direction: Optional[Direction] = None
    status: SignalStatus = SignalStatus.PENDING

    # 触发条件记录（用于复盘）
    trigger_event: Optional[MarketEvent] = None
    trigger_regime: Optional[Regime] = None
    entry_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    initial_target_price: Optional[float] = None

    # 确认条件快照
    ema_aligned: bool = False
    adx_confirmed: bool = False
    volume_confirmed: bool = False
    vwap_ok: bool = False
    spread_ok: bool = False
    breakout_confirmed: bool = False

    # 拒绝原因（方便复盘）
    reject_reason: str = ""

    @property
    def all_confirmed(self) -> bool:
        return all([
            self.ema_aligned,
            self.adx_confirmed,
            self.volume_confirmed,
            self.vwap_ok,
            self.spread_ok,
            self.breakout_confirmed,
        ])


# ─────────────────────────────────────────────
# 订单与持仓
# ─────────────────────────────────────────────

@dataclass
class Order:
    """订单"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    symbol: str = "CL"
    direction: Direction = Direction.LONG
    quantity: int = 1
    order_type: str = "market"      # "market" | "limit" | "stop"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_at: Optional[datetime] = None
    broker_order_id: Optional[str] = None
    signal_id: Optional[str] = None    # 关联信号


@dataclass
class Position:
    """持仓"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    opened_at: datetime = field(default_factory=datetime.utcnow)
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

    @property
    def unrealized_pnl(self) -> float:
        if self.direction == Direction.LONG:
            return (self.current_price - self.entry_price) * self.quantity * 1000
        else:
            return (self.entry_price - self.current_price) * self.quantity * 1000

    @property
    def risk_amount(self) -> float:
        """当前订单的风险金额（美元）"""
        return abs(self.entry_price - self.stop_loss_price) * self.quantity * 1000

    @property
    def hold_minutes(self) -> float:
        if self.opened_at:
            return (datetime.utcnow() - self.opened_at).total_seconds() / 60
        return 0.0


# ─────────────────────────────────────────────
# 风控状态（运行时状态，不持久化）
# ─────────────────────────────────────────────

@dataclass
class RiskState:
    """当日风控状态追踪"""
    daily_pnl: float = 0.0
    daily_loss_used_pct: float = 0.0
    consecutive_losses: int = 0
    total_trades_today: int = 0
    is_halted: bool = False             # 风控停手
    halt_reason: str = ""
    kill_switch_active: bool = False    # 人工紧急关闭

    def register_trade_result(self, pnl: float, equity: float):
        self.daily_pnl += pnl
        self.total_trades_today += 1
        self.daily_loss_used_pct = abs(min(0, self.daily_pnl)) / equity if equity > 0 else 0
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0


# ─────────────────────────────────────────────
# 交易记录（复盘用）
# ─────────────────────────────────────────────

@dataclass
class TradeRecord:
    """完整交易记录（入场到出场）"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
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
    # 确认条件记录
    ema_aligned: bool = False
    adx_confirmed: bool = False
    breakout_confirmed: bool = False
    # 复盘标注（可人工添加）
    notes: str = ""
