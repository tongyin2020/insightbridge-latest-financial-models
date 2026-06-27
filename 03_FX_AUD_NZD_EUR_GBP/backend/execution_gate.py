"""
Execution Gate - 执行闸门
统一裁决层，夹在 Signal Engine 和 Execution 之间
按优先级决定: 能不能开仓、开多大、是否必须立刻退出

优先级:
P0: 系统安全 (stale quote, session)
P1: 恶化接管 (deterioration override)
P2: 冷却/恢复 (cooldown/recovery)
P3: 事件就绪 (event readiness)
P4: 组合限制 (portfolio limits, loss streak)
P5: 时间止损 (position lifetime)
P6: 信号审批 (signal approval)
"""
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("fx_main")

# ─── Per-Pair Risk Configuration ───────────────────────────────────────────────

PAIR_RISK_CONFIG = {
    "AUD/USD": {
        "base_risk_percent": 0.3,    # 单笔风险预算 (账户%)
        "risk_multiplier": 0.7,      # 品种风险乘数
        "max_consecutive_losses": 6,  # 冻结阈值
        "reduced_at_losses": 4,      # 降档阈值
    },
    "NZD/USD": {
        "base_risk_percent": 0.25,
        "risk_multiplier": 0.6,
        "max_consecutive_losses": 5,
        "reduced_at_losses": 3,
    },
}

# ─── Regime Risk Multipliers ──────────────────────────────────────────────────

REGIME_MULTIPLIERS = {
    "NORMAL": 1.0,
    "TREND": 1.0,
    "RANGE": 0.8,
    "EVENT": 0.6,       # 事件期间降低风险到60%
    "UNSTABLE": 0.0,    # 不稳定时禁止交易
}

# ─── Recovery Steps ───────────────────────────────────────────────────────────

RECOVERY_MULTIPLIERS = {
    "GREEN": 1.0,
    "RECOVERY_75": 0.75,
    "RECOVERY_50": 0.50,
    "RECOVERY_30": 0.30,
    "COOLDOWN": 0.0,
}


@dataclass
class GateInput:
    """执行闸门输入 - 汇总所有决策维度"""
    symbol: str
    ts: float

    # 事件响应引擎状态
    event_state: str = "IDLE"          # IDLE/EVENT_DETECTED/IMPULSE.../READY/INVALID
    event_direction: str = ""          # BUY/SELL
    event_confidence: float = 0.0

    # Regime 状态
    regime: str = "NORMAL"
    trade_allowed: bool = True

    # 信号
    signal_side: str = ""              # BUY/SELL/WAIT
    signal_confidence: float = 0.0

    # 市场结构
    spread_ratio: float = 1.0
    vol_ratio: float = 1.0
    stale_quote: bool = False

    # 组合状态
    daily_drawdown_hit: bool = False
    consecutive_losses: int = 0
    daily_trade_count: int = 0
    max_daily_trades: int = 10

    # 风控状态
    cooldown_state: str = "GREEN"      # GREEN/COOLDOWN/RECOVERY_30/50/75
    risk_multiplier: float = 1.0

    # 持仓状态
    position_open: bool = False
    position_side: str = ""
    position_age_minutes: float = 0.0
    max_position_age_minutes: float = 40.0
    unrealized_pnl_pips: float = 0.0

    # 恶化检测
    deterioration_triggered: bool = False
    deterioration_reasons: list = field(default_factory=list)

    # Kill switch
    kill_switch: bool = False


@dataclass
class GateDecision:
    """执行闸门输出"""
    action: str                     # ALLOW / ALLOW_REDUCED / BLOCK / EXIT_NOW / FREEZE
    approved_side: str = ""
    size_multiplier: float = 1.0
    risk_percent: float = 0.0       # 实际单笔风险%
    reason_codes: list = field(default_factory=list)
    priority_level: str = ""        # P0-P6

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "approved_side": self.approved_side,
            "size_multiplier": round(self.size_multiplier, 3),
            "risk_percent": round(self.risk_percent, 4),
            "reason_codes": self.reason_codes,
            "priority_level": self.priority_level,
        }


class ExecutionGate:
    """
    执行闸门 - 最终裁决层
    策略永远没有权力覆盖风控
    """

    def __init__(self):
        self._state: str = "OPEN"  # OPEN / THROTTLED / CLOSED / FORCED_EXIT / FROZEN
        self._last_decisions: dict[str, GateDecision] = {}

    @property
    def gate_state(self) -> str:
        return self._state

    def decide(self, gi: GateInput) -> GateDecision:
        """按优先级逐层裁决"""

        # P0: Kill Switch
        if gi.kill_switch:
            decision = GateDecision("FREEZE", "", 0.0, 0.0, ["KILL_SWITCH_ACTIVE"], "P0")
            self._state = "FROZEN"
            self._last_decisions[gi.symbol] = decision
            return decision

        # P0: 系统安全
        decision = self._check_system_guards(gi)
        if decision:
            self._last_decisions[gi.symbol] = decision
            return decision

        # P1: 恶化接管
        decision = self._check_deterioration(gi)
        if decision:
            self._last_decisions[gi.symbol] = decision
            return decision

        # P2: 冷却/恢复
        decision = self._check_cooldown(gi)
        if decision:
            self._last_decisions[gi.symbol] = decision
            return decision

        # P3: 事件就绪
        decision = self._check_event_readiness(gi)
        if decision:
            self._last_decisions[gi.symbol] = decision
            return decision

        # P4: 组合限制
        decision = self._check_portfolio_limits(gi)
        if decision:
            self._last_decisions[gi.symbol] = decision
            return decision

        # P5: 时间止损 (持仓存活期)
        decision = self._check_position_lifetime(gi)
        if decision:
            self._last_decisions[gi.symbol] = decision
            return decision

        # P6: 信号审批
        decision = self._approve_signal(gi)
        self._last_decisions[gi.symbol] = decision
        return decision

    def _check_system_guards(self, gi: GateInput):
        """P0: 系统安全检查"""
        if gi.stale_quote:
            self._state = "CLOSED"
            return GateDecision("BLOCK", "", 0.0, 0.0, ["STALE_QUOTE"], "P0")
        return None

    def _check_deterioration(self, gi: GateInput):
        """P1: 市场恶化接管"""
        if gi.deterioration_triggered or gi.regime == "UNSTABLE":
            reasons = gi.deterioration_reasons or ["MARKET_UNSTABLE"]
            if gi.position_open:
                self._state = "FORCED_EXIT"
                return GateDecision("EXIT_NOW", gi.position_side, 0.0, 0.0,
                                    reasons + ["FORCE_EXIT"], "P1")
            self._state = "FROZEN"
            return GateDecision("FREEZE", "", 0.0, 0.0,
                                reasons + ["FREEZE_NO_POSITION"], "P1")
        return None

    def _check_cooldown(self, gi: GateInput):
        """P2: 冷却期和恢复状态"""
        if gi.cooldown_state == "COOLDOWN":
            self._state = "CLOSED"
            return GateDecision("BLOCK", "", 0.0, 0.0, ["COOLDOWN_ACTIVE"], "P2")
        return None

    def _check_event_readiness(self, gi: GateInput):
        """P3: 事件响应引擎就绪检查"""
        active_event_states = ("EVENT_DETECTED", "IMPULSE_PHASE", "LIQUIDITY_REBUILD", "DIRECTION_CONFIRM")
        if gi.event_state in active_event_states:
            self._state = "CLOSED"
            return GateDecision("BLOCK", "", 0.0, 0.0,
                                [f"EVENT_{gi.event_state}", "WAITING_STRUCTURE"], "P3")
        if gi.event_state == "INVALID":
            self._state = "CLOSED"
            return GateDecision("BLOCK", "", 0.0, 0.0,
                                ["EVENT_INVALID", "NO_TRADE_OPPORTUNITY"], "P3")
        return None

    def _check_portfolio_limits(self, gi: GateInput):
        """P4: 组合和连亏限制"""
        if gi.daily_drawdown_hit:
            self._state = "FROZEN"
            return GateDecision("FREEZE", "", 0.0, 0.0, ["DAILY_DD_LIMIT"], "P4")

        pair_config = PAIR_RISK_CONFIG.get(gi.symbol, PAIR_RISK_CONFIG["AUD/USD"])

        if gi.consecutive_losses >= pair_config["max_consecutive_losses"]:
            self._state = "FROZEN"
            return GateDecision("FREEZE", "", 0.0, 0.0,
                                [f"LOSS_STREAK_{gi.consecutive_losses}", "SYMBOL_FROZEN"], "P4")

        if gi.daily_trade_count >= gi.max_daily_trades:
            self._state = "CLOSED"
            return GateDecision("BLOCK", "", 0.0, 0.0, ["MAX_DAILY_TRADES"], "P4")

        return None

    def _check_position_lifetime(self, gi: GateInput):
        """P5: 40分钟时间止损 + 结构退出"""
        if gi.position_open and gi.position_age_minutes >= gi.max_position_age_minutes:
            return GateDecision("EXIT_NOW", gi.position_side, 0.0, 0.0,
                                [f"TIME_STOP_{gi.max_position_age_minutes:.0f}M"], "P5")
        return None

    def _approve_signal(self, gi: GateInput) -> GateDecision:
        """P6: 最终信号审批 - 计算允许的仓位大小"""
        if not gi.signal_side or gi.signal_side == "WAIT":
            self._state = "OPEN"
            return GateDecision("BLOCK", "", 0.0, 0.0, ["NO_SIGNAL"], "P6")

        if not gi.trade_allowed:
            self._state = "CLOSED"
            return GateDecision("BLOCK", "", 0.0, 0.0, ["TRADE_NOT_ALLOWED"], "P6")

        # 计算风险乘数
        pair_config = PAIR_RISK_CONFIG.get(gi.symbol, PAIR_RISK_CONFIG["AUD/USD"])
        base_risk = pair_config["base_risk_percent"]
        pair_mult = pair_config["risk_multiplier"]

        # Regime 乘数
        regime_mult = REGIME_MULTIPLIERS.get(gi.regime, 0.8)

        # Recovery 乘数
        recovery_mult = RECOVERY_MULTIPLIERS.get(gi.cooldown_state, 1.0)

        # 连亏降档
        loss_mult = 1.0
        if gi.consecutive_losses >= pair_config["reduced_at_losses"]:
            loss_mult = 0.5

        # 最终乘数
        final_mult = pair_mult * regime_mult * recovery_mult * loss_mult
        final_risk = base_risk * final_mult

        if final_mult <= 0 or final_risk <= 0:
            self._state = "CLOSED"
            return GateDecision("BLOCK", gi.signal_side, 0.0, 0.0,
                                ["ZERO_RISK_BUDGET"], "P6")

        # 事件信号优先使用事件方向
        approved_side = gi.signal_side
        if gi.event_state == "READY" and gi.event_direction:
            approved_side = gi.event_direction

        action = "ALLOW_REDUCED" if final_mult < 1.0 else "ALLOW"
        self._state = "OPEN" if action == "ALLOW" else "THROTTLED"

        reasons = ["ALL_CHECKS_PASS"]
        if recovery_mult < 1.0:
            reasons.append(f"RECOVERY_{gi.cooldown_state}")
        if loss_mult < 1.0:
            reasons.append(f"LOSS_STREAK_{gi.consecutive_losses}")
        if regime_mult < 1.0:
            reasons.append(f"REGIME_{gi.regime}")

        return GateDecision(action, approved_side, round(final_mult, 3),
                            round(final_risk, 4), reasons, "P6")

    def get_status(self) -> dict:
        """获取闸门状态"""
        decisions = {}
        for pair, dec in self._last_decisions.items():
            decisions[pair] = dec.to_dict()
        return {
            "gate_state": self._state,
            "pair_decisions": decisions,
            "pair_risk_config": {
                pair: {
                    "base_risk_percent": cfg["base_risk_percent"],
                    "risk_multiplier": cfg["risk_multiplier"],
                }
                for pair, cfg in PAIR_RISK_CONFIG.items()
            },
            "regime_multipliers": REGIME_MULTIPLIERS,
            "recovery_multipliers": RECOVERY_MULTIPLIERS,
        }
