"""
WTI Trading Platform - Advanced Risk Control Center
Multi-layered risk management: daily drawdown, equity stops, cooldown periods, tiered exits.
Inspired by the FX Trading Dashboard's 风控中心 and 多层退出结构.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    NORMAL = "normal"           # Green: Full trading
    REDUCED = "reduced"         # Amber: Reduced position sizes
    DEGRADED = "degraded"       # Orange: Only close/reduce positions
    HALTED = "halted"           # Red: No trading allowed


class ExitTier(str, Enum):
    WARNING = "warning"           # -50% of max loss → alert
    PRE_REDUCE = "pre_reduce"     # -70% → reduce half position
    MAIN_STOP = "main_stop"       # -100% → close position
    DISASTER = "disaster"         # -150% → emergency flatten all


@dataclass
class DailyPnL:
    date: str
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    trades_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    max_drawdown: float = 0.0
    peak_equity: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "date": self.date,
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "trades_count": self.trades_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "max_drawdown": round(self.max_drawdown, 2),
            "peak_equity": round(self.peak_equity, 2),
        }


@dataclass
class RiskRule:
    name: str
    enabled: bool
    threshold: float
    current_value: float
    triggered: bool
    action: str

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "threshold": self.threshold,
            "current_value": round(self.current_value, 4),
            "triggered": self.triggered,
            "action": self.action,
        }


@dataclass
class SlippageRecord:
    expected_price: float
    actual_price: float
    slippage_ticks: float
    timestamp: str


class RiskControlCenter:
    """
    Comprehensive risk management center.
    Manages daily limits, drawdown protection, cooldown periods, and execution quality.
    """

    def __init__(self, initial_equity: float = 50000.0):
        self._initial_equity = initial_equity
        self._current_equity = initial_equity
        self._peak_equity = initial_equity

        # Daily tracking
        self._daily_pnl_history: deque = deque(maxlen=30)
        self._today_pnl = DailyPnL(date=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        self._today_pnl.peak_equity = initial_equity

        # Cooldown
        self._cooldown_until: Optional[datetime] = None
        self._cooldown_reason = ""

        # Slippage tracking
        self._slippage_history: deque = deque(maxlen=100)
        self._total_slippage = 0.0
        self._slippage_count = 0

        # Risk thresholds
        self._max_daily_loss_pct = 0.015      # 1.5% daily loss limit
        self._max_drawdown_pct = 0.05          # 5% max drawdown from peak
        self._max_consecutive_losses = 3
        self._max_slippage_ticks = 4.0
        self._cooldown_minutes = 15

        # Tiered exit levels
        self._exit_tiers = {
            ExitTier.WARNING: 0.50,       # 50% of max loss
            ExitTier.PRE_REDUCE: 0.70,    # 70% → reduce half
            ExitTier.MAIN_STOP: 1.00,     # 100% → close
            ExitTier.DISASTER: 1.50,      # 150% → emergency
        }

        # Current state
        self._level = RiskLevel.NORMAL
        self._consecutive_losses = 0
        self._rules_state: Dict[str, bool] = {}

    def update_equity(self, new_equity: float):
        """Update current equity and track peaks/drawdowns"""
        self._current_equity = new_equity
        if new_equity > self._peak_equity:
            self._peak_equity = new_equity

        # Update today's PnL
        self._today_pnl.unrealized_pnl = new_equity - self._initial_equity - self._today_pnl.realized_pnl
        self._today_pnl.total_pnl = self._today_pnl.realized_pnl + self._today_pnl.unrealized_pnl

        dd = (self._peak_equity - new_equity) / self._peak_equity if self._peak_equity > 0 else 0
        if dd > self._today_pnl.max_drawdown:
            self._today_pnl.max_drawdown = dd

    def record_trade(self, pnl: float):
        """Record a completed trade"""
        self._today_pnl.realized_pnl += pnl
        self._today_pnl.trades_count += 1
        if pnl >= 0:
            self._today_pnl.win_count += 1
            self._consecutive_losses = 0
        else:
            self._today_pnl.loss_count += 1
            self._consecutive_losses += 1

            if self._consecutive_losses >= self._max_consecutive_losses:
                self._activate_cooldown(f"连续{self._consecutive_losses}次亏损")

    def record_slippage(self, expected: float, actual: float):
        """Track execution slippage"""
        slippage = abs(actual - expected) * 100  # Convert to ticks
        self._slippage_history.append(SlippageRecord(
            expected_price=expected,
            actual_price=actual,
            slippage_ticks=slippage,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        self._total_slippage += slippage
        self._slippage_count += 1

    def _activate_cooldown(self, reason: str):
        """Activate trading cooldown"""
        self._cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=self._cooldown_minutes)
        self._cooldown_reason = reason
        logger.warning(f"[RiskControl] Cooldown activated: {reason}")

    def check_rules(self) -> Dict:
        """Evaluate all risk rules and determine trading level"""
        rules = []
        now = datetime.now(timezone.utc)

        # Rule 1: Daily Loss Limit
        daily_loss_pct = abs(min(0, self._today_pnl.total_pnl)) / self._initial_equity
        r1 = RiskRule(
            name="日内亏损限额",
            enabled=True,
            threshold=self._max_daily_loss_pct,
            current_value=daily_loss_pct,
            triggered=daily_loss_pct >= self._max_daily_loss_pct,
            action="停止交易" if daily_loss_pct >= self._max_daily_loss_pct else "正常",
        )
        rules.append(r1)

        # Rule 2: Max Drawdown
        dd_pct = (self._peak_equity - self._current_equity) / self._peak_equity if self._peak_equity > 0 else 0
        r2 = RiskRule(
            name="最大回撤限制",
            enabled=True,
            threshold=self._max_drawdown_pct,
            current_value=dd_pct,
            triggered=dd_pct >= self._max_drawdown_pct,
            action="权益止损" if dd_pct >= self._max_drawdown_pct else "正常",
        )
        rules.append(r2)

        # Rule 3: Consecutive Losses
        r3 = RiskRule(
            name="连续亏损限制",
            enabled=True,
            threshold=float(self._max_consecutive_losses),
            current_value=float(self._consecutive_losses),
            triggered=self._consecutive_losses >= self._max_consecutive_losses,
            action="冷静期" if self._consecutive_losses >= self._max_consecutive_losses else "正常",
        )
        rules.append(r3)

        # Rule 4: Cooldown Active
        cooldown_active = self._cooldown_until is not None and now < self._cooldown_until
        r4 = RiskRule(
            name="冷静期状态",
            enabled=True,
            threshold=1.0,
            current_value=1.0 if cooldown_active else 0.0,
            triggered=cooldown_active,
            action=f"冷静期中: {self._cooldown_reason}" if cooldown_active else "无冷静期",
        )
        rules.append(r4)

        # Rule 5: Slippage Monitor
        avg_slippage = self._total_slippage / max(1, self._slippage_count)
        r5 = RiskRule(
            name="滑点监控",
            enabled=True,
            threshold=self._max_slippage_ticks,
            current_value=avg_slippage,
            triggered=avg_slippage > self._max_slippage_ticks,
            action="滑点异常" if avg_slippage > self._max_slippage_ticks else "正常",
        )
        rules.append(r5)

        # Determine overall level
        critical_triggered = any(r.triggered for r in rules[:2])  # Daily loss or drawdown
        warning_triggered = any(r.triggered for r in rules[2:])

        if critical_triggered:
            self._level = RiskLevel.HALTED
        elif cooldown_active:
            self._level = RiskLevel.DEGRADED
        elif warning_triggered:
            self._level = RiskLevel.REDUCED
        else:
            self._level = RiskLevel.NORMAL

        return {
            "level": self._level.value,
            "rules": [r.to_dict() for r in rules],
            "can_trade": self._level in (RiskLevel.NORMAL, RiskLevel.REDUCED),
            "size_multiplier": self._get_size_multiplier(),
        }

    def _get_size_multiplier(self) -> float:
        if self._level == RiskLevel.HALTED:
            return 0.0
        elif self._level == RiskLevel.DEGRADED:
            return 0.25
        elif self._level == RiskLevel.REDUCED:
            return 0.5
        return 1.0

    def get_exit_tiers(self, entry_price: float, direction: str, max_loss_per_unit: float) -> List[Dict]:
        """Calculate multi-tier exit levels for a position"""
        tiers = []
        for tier, multiplier in self._exit_tiers.items():
            loss_amount = max_loss_per_unit * multiplier
            if direction == "long":
                exit_price = entry_price - loss_amount
            else:
                exit_price = entry_price + loss_amount

            action_map = {
                ExitTier.WARNING: "预警通知",
                ExitTier.PRE_REDUCE: "减仓50%",
                ExitTier.MAIN_STOP: "全部平仓",
                ExitTier.DISASTER: "灾难保护: 紧急清仓",
            }

            tiers.append({
                "tier": tier.value,
                "multiplier": f"-{int(multiplier*100)}%",
                "exit_price": round(exit_price, 2),
                "action": action_map.get(tier, ""),
                "loss_amount": round(loss_amount, 2),
            })
        return tiers

    def get_daily_pnl_history(self) -> List[Dict]:
        """Get daily P&L for the last 7 days"""
        history = list(self._daily_pnl_history)
        history.append(self._today_pnl)
        return [d.to_dict() for d in history[-7:]]

    def get_slippage_stats(self) -> Dict:
        """Get slippage statistics"""
        if not self._slippage_history:
            return {"count": 0, "avg_ticks": 0, "max_ticks": 0, "total_ticks": 0}

        slippages = [s.slippage_ticks for s in self._slippage_history]
        return {
            "count": len(slippages),
            "avg_ticks": round(sum(slippages) / len(slippages), 2),
            "max_ticks": round(max(slippages), 2),
            "total_ticks": round(sum(slippages), 2),
            "recent": [
                {
                    "expected": s.expected_price,
                    "actual": s.actual_price,
                    "slippage": round(s.slippage_ticks, 2),
                    "time": s.timestamp,
                }
                for s in list(self._slippage_history)[-5:]
            ],
        }

    def get_status(self) -> Dict:
        """Get full risk control center status"""
        rules = self.check_rules()
        now = datetime.now(timezone.utc)
        cooldown_remaining = 0
        if self._cooldown_until and now < self._cooldown_until:
            cooldown_remaining = int((self._cooldown_until - now).total_seconds())

        return {
            "level": rules["level"],
            "can_trade": rules["can_trade"],
            "size_multiplier": rules["size_multiplier"],
            "rules": rules["rules"],
            "equity": {
                "current": round(self._current_equity, 2),
                "peak": round(self._peak_equity, 2),
                "drawdown_pct": round((self._peak_equity - self._current_equity) / self._peak_equity * 100, 2) if self._peak_equity > 0 else 0,
            },
            "today_pnl": self._today_pnl.to_dict(),
            "cooldown": {
                "active": cooldown_remaining > 0,
                "reason": self._cooldown_reason if cooldown_remaining > 0 else "",
                "remaining_sec": cooldown_remaining,
            },
            "consecutive_losses": self._consecutive_losses,
        }

    def reset_daily(self):
        """Reset daily counters (call at market open)"""
        if self._today_pnl.trades_count > 0:
            self._daily_pnl_history.append(self._today_pnl)
        self._today_pnl = DailyPnL(
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            peak_equity=self._current_equity,
        )
        self._consecutive_losses = 0
        self._cooldown_until = None
        self._cooldown_reason = ""


# Global instance
risk_control = RiskControlCenter()
