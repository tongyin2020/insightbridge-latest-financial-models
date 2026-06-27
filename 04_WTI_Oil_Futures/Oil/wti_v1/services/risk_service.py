"""
WTI v1 — 风控服务
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
重要原则：风控是独立守门人，不是信号的附属品。
所有风控检查必须在执行任何订单之前通过。
风控停手一旦触发，只有人工确认才能解除（kill switch除外，它不可解除）。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
from datetime import datetime, date
from typing import Optional, Tuple
from dataclasses import dataclass

from config.settings import RISK, RiskConfig
from models.core import Signal, Tick, Indicators, RiskState, Direction

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    allowed: bool
    reason: str = ""
    position_size: int = 0      # 建议仓位（手数）


class RiskService:
    """
    风控服务。
    职责：判断是否允许交易、计算合规仓位、追踪当日风控状态。

    【不可绕过的硬性停止条件】
    1. Kill switch 激活
    2. 已触发风控停手
    3. 当日亏损超限
    4. 连续亏损超限
    5. 点差过宽
    6. 数据异常
    """

    def __init__(self, config: RiskConfig = RISK):
        self.config = config
        self.state = RiskState()
        self._current_date = date.today()

    # ─────────────────────────────────────────
    # 核心检查：是否允许执行信号
    # ─────────────────────────────────────────

    def check_signal(
        self,
        signal: Signal,
        current_tick: Tick,
        equity: float,
    ) -> RiskCheckResult:
        """
        信号执行前的完整风控检查。
        返回 RiskCheckResult，allowed=False 则绝对不得执行。
        """
        # 1. Kill switch（最高优先级，不可解除）
        if self.state.kill_switch_active:
            return RiskCheckResult(False, "Kill switch 已激活，系统全面停止")

        # 2. 风控停手
        if self.state.is_halted:
            return RiskCheckResult(False, f"风控停手中: {self.state.halt_reason}")

        # 3. 新的一天：重置当日状态
        self._check_day_reset()

        # 4. 当日亏损限制
        daily_loss_pct = abs(min(0, self.state.daily_pnl)) / equity if equity > 0 else 0
        if daily_loss_pct >= self.config.max_daily_loss_pct:
            self._halt(f"当日亏损达到 {daily_loss_pct:.1%}，超过限制 {self.config.max_daily_loss_pct:.1%}")
            return RiskCheckResult(False, self.state.halt_reason)

        # 5. 连续亏损
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            self._halt(f"连续亏损 {self.state.consecutive_losses} 笔，自动停手")
            return RiskCheckResult(False, self.state.halt_reason)

        # 6. 点差检查
        spread_ticks = current_tick.spread / 0.01  # WTI最小变动0.01
        if spread_ticks > self.config.max_spread_ticks:
            reason = f"点差过宽: {spread_ticks:.1f} ticks（限制 {self.config.max_spread_ticks}）"
            logger.warning(f"[Risk] 信号被拒: {reason}")
            return RiskCheckResult(False, reason)

        # 7. 计算仓位
        size = self._calc_position_size(signal, equity)
        if size < 1:
            reason = "按风控规则仓位为0，跳过"
            return RiskCheckResult(False, reason)

        return RiskCheckResult(True, "通过风控检查", size)

    # ─────────────────────────────────────────
    # 实时监控（持仓中持续调用）
    # ─────────────────────────────────────────

    def check_position_health(
        self,
        spread_ticks: float,
        data_gap_sec: float,
        is_connected: bool,
    ) -> Tuple[bool, str]:
        """
        持仓存续检查。返回 (should_exit, reason)
        任何异常都应立即退出并停手。
        """
        if self.state.kill_switch_active:
            return True, "Kill switch 激活"

        if not is_connected:
            return True, "平台断连，立即平仓"

        if data_gap_sec > self.config.data_gap_timeout_sec:
            return True, f"数据中断 {data_gap_sec:.0f}秒，超过容忍限制"

        if spread_ticks > self.config.max_spread_ticks * 2:
            return True, f"极端点差 {spread_ticks:.1f} ticks，退出保护"

        return False, ""

    # ─────────────────────────────────────────
    # 交易结果登记
    # ─────────────────────────────────────────

    def register_trade_result(self, pnl_usd: float, equity: float):
        """每笔交易完成后调用，更新风控状态"""
        self.state.register_trade_result(pnl_usd, equity)

        logger.info(
            f"[Risk] 交易结果: PnL={pnl_usd:+.2f} | "
            f"当日累计={self.state.daily_pnl:+.2f} | "
            f"连续亏损={self.state.consecutive_losses} | "
            f"总笔数={self.state.total_trades_today}"
        )

    # ─────────────────────────────────────────
    # Kill Switch（人工紧急停止）
    # ─────────────────────────────────────────

    def activate_kill_switch(self, reason: str = "human_triggered"):
        """
        人工紧急停止。
        一旦激活，本次运行不可解除，必须重启程序并人工确认。
        """
        self.state.kill_switch_active = True
        self.state.is_halted = True
        self.state.halt_reason = f"KILL SWITCH: {reason}"
        logger.critical(f"[Risk] ⚠️  KILL SWITCH 激活: {reason}")

    def reset_halt(self, operator: str = "manual"):
        """
        人工解除风控停手（kill switch除外）。
        解除后需要操作员确认记录。
        """
        if self.state.kill_switch_active:
            logger.error("[Risk] Kill switch 不可人工解除，需重启系统")
            return False

        logger.warning(f"[Risk] 风控停手被解除 by {operator}")
        self.state.is_halted = False
        self.state.halt_reason = ""
        return True

    # ─────────────────────────────────────────
    # 内部方法
    # ─────────────────────────────────────────

    def _calc_position_size(self, signal: Signal, equity: float) -> int:
        """
        Kelly/固定风险仓位计算。
        v1 使用固定风险比例，不用Kelly（需要充分样本才用Kelly）。
        """
        if signal.entry_price is None or signal.stop_loss_price is None:
            return 0

        risk_per_trade = equity * self.config.max_risk_per_trade_pct
        risk_per_contract = abs(signal.entry_price - signal.stop_loss_price) * 1000  # WTI合约价值

        if risk_per_contract <= 0:
            return 0

        size = int(risk_per_trade / risk_per_contract)
        return max(0, min(size, 5))  # v1 最多5手上限

    def _halt(self, reason: str):
        self.state.is_halted = True
        self.state.halt_reason = reason
        logger.error(f"[Risk] 🛑 风控停手: {reason}")

    def _check_day_reset(self):
        """新的交易日自动重置"""
        today = date.today()
        if today != self._current_date:
            logger.info(f"[Risk] 新的交易日，重置风控状态")
            self._current_date = today
            # 保留kill switch状态，重置其他
            was_killed = self.state.kill_switch_active
            self.state = RiskState()
            self.state.kill_switch_active = was_killed

    @property
    def summary(self) -> dict:
        return {
            "is_halted": self.state.is_halted,
            "kill_switch": self.state.kill_switch_active,
            "daily_pnl": round(self.state.daily_pnl, 2),
            "consecutive_losses": self.state.consecutive_losses,
            "total_trades": self.state.total_trades_today,
            "halt_reason": self.state.halt_reason,
        }
