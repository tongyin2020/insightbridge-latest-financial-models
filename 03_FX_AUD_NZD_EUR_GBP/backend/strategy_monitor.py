"""
Strategy Monitor - 策略失效检测器
监控策略表现，自动降档或冻结

核心功能:
- 连续亏损检测 (连亏4笔降档, 连亏6笔冻结)
- 滚动胜率监控
- 恶化触发频率检测 (1天内≥3次触发 → 当日停机)
- 渐进恢复管理 (30% → 50% → 75% → 100%)
"""
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger("fx_main")


@dataclass
class StrategyHealth:
    """策略健康状态"""
    pair: str
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    recent_trades: int = 0
    recent_wins: int = 0
    rolling_win_rate: float = 0.0
    rolling_profit_factor: float = 0.0
    daily_deterioration_count: int = 0
    recovery_state: str = "GREEN"   # GREEN / COOLDOWN / RECOVERY_30 / RECOVERY_50 / RECOVERY_75
    risk_multiplier: float = 1.0
    frozen: bool = False
    frozen_reason: str = ""
    last_trade_time: float = 0.0
    daily_pnl_pips: float = 0.0


class StrategyMonitor:
    """策略失效检测器"""

    # 恢复状态机: COOLDOWN → RECOVERY_30 → RECOVERY_50 → RECOVERY_75 → GREEN
    RECOVERY_CHAIN = ["COOLDOWN", "RECOVERY_30", "RECOVERY_50", "RECOVERY_75", "GREEN"]
    RECOVERY_MULTIPLIERS = {
        "COOLDOWN": 0.0,
        "RECOVERY_30": 0.30,
        "RECOVERY_50": 0.50,
        "RECOVERY_75": 0.75,
        "GREEN": 1.0,
    }
    # 每步恢复至少稳定的交易数
    RECOVERY_STABLE_TRADES = 2

    def __init__(self, pairs: list[str]):
        self.health: dict[str, StrategyHealth] = {
            pair: StrategyHealth(pair=pair) for pair in pairs
        }
        self._recovery_trade_count: dict[str, int] = {pair: 0 for pair in pairs}
        self._daily_reset_date: str = ""

    def record_trade(self, pair: str, pnl_pips: float):
        """记录交易结果"""
        h = self.health.get(pair)
        if not h:
            return

        h.last_trade_time = time.time()
        h.recent_trades += 1
        h.daily_pnl_pips += pnl_pips

        if pnl_pips >= 0:
            h.consecutive_wins += 1
            h.consecutive_losses = 0
            h.recent_wins += 1
        else:
            h.consecutive_losses += 1
            h.consecutive_wins = 0

        # 更新滚动胜率 (最近10笔)
        if h.recent_trades > 0:
            h.rolling_win_rate = h.recent_wins / min(h.recent_trades, 10)

        # 检查连亏冻结
        self._check_loss_streak(pair)

        # 恢复期间计数
        if h.recovery_state != "GREEN" and h.recovery_state != "COOLDOWN":
            self._recovery_trade_count[pair] = self._recovery_trade_count.get(pair, 0) + 1
            if pnl_pips >= 0:
                self._try_advance_recovery(pair)

        logger.info(f"[StrategyMonitor:{pair}] Trade recorded: pnl={pnl_pips:.1f}, "
                    f"consecutive_losses={h.consecutive_losses}, win_rate={h.rolling_win_rate:.1%}")

    def record_deterioration(self, pair: str):
        """记录恶化触发"""
        h = self.health.get(pair)
        if not h:
            return

        h.daily_deterioration_count += 1

        # 1天内恶化≥3次 → 当日停机
        if h.daily_deterioration_count >= 3:
            h.frozen = True
            h.frozen_reason = f"DAILY_DETERIORATION_LIMIT ({h.daily_deterioration_count}x)"
            logger.warning(f"[StrategyMonitor:{pair}] FROZEN: {h.frozen_reason}")

    def enter_cooldown(self, pair: str, reason: str = ""):
        """进入冷却期"""
        h = self.health.get(pair)
        if not h:
            return

        h.recovery_state = "COOLDOWN"
        h.risk_multiplier = 0.0
        self._recovery_trade_count[pair] = 0
        logger.info(f"[StrategyMonitor:{pair}] Enter COOLDOWN: {reason}")

    def end_cooldown(self, pair: str):
        """冷却期结束 → 进入 RECOVERY_30"""
        h = self.health.get(pair)
        if not h or h.recovery_state != "COOLDOWN":
            return

        h.recovery_state = "RECOVERY_30"
        h.risk_multiplier = 0.30
        self._recovery_trade_count[pair] = 0
        logger.info(f"[StrategyMonitor:{pair}] COOLDOWN ended → RECOVERY_30 (30% risk)")

    def _try_advance_recovery(self, pair: str):
        """尝试推进恢复阶段"""
        h = self.health.get(pair)
        if not h:
            return

        count = self._recovery_trade_count.get(pair, 0)
        if count < self.RECOVERY_STABLE_TRADES:
            return

        current_idx = self.RECOVERY_CHAIN.index(h.recovery_state) if h.recovery_state in self.RECOVERY_CHAIN else 0
        next_idx = current_idx + 1
        if next_idx < len(self.RECOVERY_CHAIN):
            new_state = self.RECOVERY_CHAIN[next_idx]
            h.recovery_state = new_state
            h.risk_multiplier = self.RECOVERY_MULTIPLIERS[new_state]
            self._recovery_trade_count[pair] = 0
            logger.info(f"[StrategyMonitor:{pair}] Recovery advanced → {new_state} ({h.risk_multiplier:.0%} risk)")

    def _check_loss_streak(self, pair: str):
        """检查连亏"""
        h = self.health.get(pair)
        if not h:
            return

        pair_config = {
            "AUD/USD": {"reduced_at": 4, "frozen_at": 6},
            "NZD/USD": {"reduced_at": 3, "frozen_at": 5},
        }
        config = pair_config.get(pair, {"reduced_at": 4, "frozen_at": 6})

        if h.consecutive_losses >= config["frozen_at"]:
            h.frozen = True
            h.frozen_reason = f"LOSS_STREAK_{h.consecutive_losses}"
            self.enter_cooldown(pair, h.frozen_reason)
            logger.warning(f"[StrategyMonitor:{pair}] FROZEN: {h.frozen_reason}")

    def unfreeze(self, pair: str):
        """手动解冻"""
        h = self.health.get(pair)
        if not h:
            return
        h.frozen = False
        h.frozen_reason = ""
        h.consecutive_losses = 0
        self.end_cooldown(pair)

    def reset_daily(self):
        """每日重置"""
        for h in self.health.values():
            h.daily_deterioration_count = 0
            h.daily_pnl_pips = 0.0
            h.recent_trades = 0
            h.recent_wins = 0
            if h.frozen and "DAILY_DETERIORATION" in h.frozen_reason:
                h.frozen = False
                h.frozen_reason = ""

    def get_all_health(self) -> dict:
        """获取所有品种健康状态"""
        return {
            pair: {
                "consecutive_losses": h.consecutive_losses,
                "consecutive_wins": h.consecutive_wins,
                "rolling_win_rate": round(h.rolling_win_rate, 3),
                "daily_deterioration_count": h.daily_deterioration_count,
                "recovery_state": h.recovery_state,
                "risk_multiplier": round(h.risk_multiplier, 3),
                "frozen": h.frozen,
                "frozen_reason": h.frozen_reason,
                "daily_pnl_pips": round(h.daily_pnl_pips, 1),
                "recent_trades": h.recent_trades,
            }
            for pair, h in self.health.items()
        }
