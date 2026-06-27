"""
WTI v1 — 信号服务（核心：动态确认逻辑）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
我的改进：用基于价格行为的动态确认替代纯固定时间等待。
固定30秒有盲区：行情慢时30秒还没确认，行情快时30秒已过头。
动态确认：在时间窗口内，等待价格行为满足多个量化条件。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Deque
from collections import deque

from config.settings import CONFIRM, HOLDING, ConfirmationConfig
from models.core import (
    Signal, MarketEvent, Bar, Tick, Indicators,
    Regime, Direction, SignalStatus, EventPriority
)

logger = logging.getLogger(__name__)


class SignalService:
    """
    信号服务。
    负责在被允许的环境里，寻找并确认具体交易信号。

    核心逻辑：
    1. 事件进来 → 记录事件后价格基准
    2. 动态观察价格行为（时间窗口内）
    3. 满足全部确认条件 → ACCEPTED
    4. 超时或不满足 → REJECTED/SKIPPED
    """

    def __init__(self, config: ConfirmationConfig = CONFIRM):
        self.config = config
        self._pending_signal: Optional[Signal] = None
        self._event_baseline_price: Optional[float] = None
        self._event_high: Optional[float] = None
        self._event_low: Optional[float] = None
        self._confirmation_start: Optional[datetime] = None
        self._recent_bars: Deque[Bar] = deque(maxlen=20)
        self._generated_signals: List[Signal] = []

    # ─────────────────────────────────────────
    # 主要接口
    # ─────────────────────────────────────────

    def on_event(self, event: MarketEvent, current_tick: Tick):
        """
        收到A/B类事件时调用。
        记录价格基准，开始确认窗口。
        """
        if event.priority == EventPriority.C:
            return

        # 如果已有待确认信号，先放弃（新事件优先）
        if self._pending_signal and self._pending_signal.status == SignalStatus.PENDING:
            self._reject_pending("新事件打断，放弃前一个待确认信号")

        # 记录事件后价格基准
        self._event_baseline_price = current_tick.mid
        self._event_high = current_tick.ask
        self._event_low = current_tick.bid
        self._confirmation_start = datetime.utcnow()

        logger.info(
            f"[Signal] 事件进入确认窗口 | 基准价={self._event_baseline_price:.2f} | "
            f"事件={event.headline[:50]}"
        )

    def on_tick(self, tick: Tick, indicators: Indicators, current_regime: Regime) -> Optional[Signal]:
        """
        每个新报价时调用。
        在确认窗口内持续检查确认条件。
        返回已确认信号，或None。
        """
        if self._pending_signal is None:
            self._update_price_range(tick)
            # 没有待确认信号，检查是否能生成新信号
            if current_regime == Regime.BLOCKED:
                return None
            return None  # v1仅事件触发，不主动生成常规信号

        if self._pending_signal.status != SignalStatus.PENDING:
            return None

        # 检查超时
        if self._is_confirmation_timeout():
            self._reject_pending("确认窗口超时")
            return None

        # 更新价格范围追踪
        self._update_price_range(tick)

        # 尝试确认
        return self._try_confirm(tick, indicators, current_regime)

    def on_bar(self, bar: Bar, indicators: Indicators, current_regime: Regime) -> Optional[Signal]:
        """
        新K线形成时调用（常规信号检测，v1先用于监控）
        """
        self._recent_bars.append(bar)
        return None  # v1暂不从K线主动生成信号

    def start_confirmation(
        self,
        event: MarketEvent,
        initial_direction_hint: Optional[Direction],
        current_price: float,
        indicators: Indicators,
    ):
        """
        明确启动一个待确认信号。
        direction_hint：来自事件逻辑的方向预判（非强制，价格行为才最终决定）
        """
        sig = Signal()
        sig.trigger_event = event
        sig.status = SignalStatus.PENDING
        self._pending_signal = sig
        logger.info(f"[Signal] 开始确认信号 | 方向预判={initial_direction_hint}")

    # ─────────────────────────────────────────
    # 动态确认逻辑（核心改进）
    # ─────────────────────────────────────────

    def _try_confirm(
        self,
        tick: Tick,
        ind: Indicators,
        regime: Regime,
    ) -> Optional[Signal]:
        """
        多条件动态确认。每次新报价都检查一次。
        只要所有条件在时间窗口内同时满足，立即确认。
        """
        sig = self._pending_signal
        if sig is None:
            return None

        # 最短等待时间（避免抢第一下）
        elapsed = (datetime.utcnow() - self._confirmation_start).total_seconds()
        if elapsed < self.config.min_wait_sec:
            return None

        # ── 条件1：方向突破（最关键）──
        # 必须突破事件后初始振幅的60%以上
        direction, breakout_ok = self._check_breakout(tick)
        if not breakout_ok:
            return None

        sig.direction = direction
        sig.breakout_confirmed = True

        # ── 条件2：EMA方向一致 ──
        if direction == Direction.LONG:
            sig.ema_aligned = ind.ema_fast > ind.ema_slow
        else:
            sig.ema_aligned = ind.ema_fast < ind.ema_slow

        # ── 条件3：ADX确认趋势 ──
        sig.adx_confirmed = ind.adx >= self.config.adx_threshold

        # ── 条件4：成交量确认 ──
        sig.volume_confirmed = ind.volume_ratio >= self.config.min_volume_ratio

        # ── 条件5：VWAP偏离合理 ──
        if direction == Direction.LONG:
            vwap_deviation = (tick.mid - ind.vwap) / ind.atr if ind.atr > 0 else 0
        else:
            vwap_deviation = (ind.vwap - tick.mid) / ind.atr if ind.atr > 0 else 0
        sig.vwap_ok = vwap_deviation <= self.config.vwap_atr_max_deviation

        # ── 条件6：点差合理 ──
        spread_ticks = tick.spread / 0.01
        sig.spread_ok = spread_ticks <= self.config.max_spread_ticks

        # ── 综合判断 ──
        if sig.all_confirmed:
            sig.entry_price = tick.ask if direction == Direction.LONG else tick.bid
            sig.stop_loss_price = self._calc_stop(direction, ind)
            sig.status = SignalStatus.ACCEPTED
            sig.trigger_regime = regime
            self._generated_signals.append(sig)
            self._pending_signal = None
            logger.info(
                f"[Signal] ✅ 信号确认 | 方向={direction.value} | "
                f"入场={sig.entry_price:.2f} | 止损={sig.stop_loss_price:.2f} | "
                f"确认耗时={elapsed:.0f}s"
            )
            return sig
        else:
            # 记录未通过的条件（不拒绝，继续等待）
            failed = [
                k for k, v in {
                    "EMA": sig.ema_aligned,
                    "ADX": sig.adx_confirmed,
                    "Volume": sig.volume_confirmed,
                    "VWAP": sig.vwap_ok,
                    "Spread": sig.spread_ok,
                }.items() if not v
            ]
            logger.debug(f"[Signal] 等待确认，未通过条件: {failed}")
            return None

    # ─────────────────────────────────────────
    # 辅助计算
    # ─────────────────────────────────────────

    def _check_breakout(self, tick: Tick):
        """
        判断是否有效突破（方向 + 幅度）
        比较当前价格与事件后初始振幅的关系
        """
        if not all([self._event_high, self._event_low, self._event_baseline_price]):
            return None, False

        range_size = self._event_high - self._event_low
        if range_size <= 0:
            return None, False

        min_breakout = range_size * self.config.breakout_pct_of_range

        # 向上突破
        if tick.ask > self._event_high + min_breakout:
            return Direction.LONG, True

        # 向下突破
        if tick.bid < self._event_low - min_breakout:
            return Direction.SHORT, True

        return None, False

    def _calc_stop(self, direction: Direction, ind: Indicators) -> float:
        """
        止损价格计算（基于ATR，比固定点数更适应市场）
        v1：入场价 ± 1.5倍ATR
        """
        if self._pending_signal and self._pending_signal.entry_price:
            entry = self._pending_signal.entry_price
        else:
            return 0.0

        stop_distance = ind.atr * 1.5

        if direction == Direction.LONG:
            return round(entry - stop_distance, 2)
        else:
            return round(entry + stop_distance, 2)

    def _update_price_range(self, tick: Tick):
        """追踪事件后的价格范围"""
        if self._event_high is not None:
            self._event_high = max(self._event_high, tick.ask)
        if self._event_low is not None:
            self._event_low = min(self._event_low, tick.bid)

    def _is_confirmation_timeout(self) -> bool:
        if not self._confirmation_start:
            return False
        elapsed = (datetime.utcnow() - self._confirmation_start).total_seconds()
        return elapsed > self.config.max_wait_sec

    def _reject_pending(self, reason: str):
        if self._pending_signal:
            self._pending_signal.status = SignalStatus.REJECTED
            self._pending_signal.reject_reason = reason
            self._generated_signals.append(self._pending_signal)
            logger.info(f"[Signal] ❌ 信号拒绝: {reason}")
            self._pending_signal = None
            self._reset_event_state()

    def _reset_event_state(self):
        self._event_baseline_price = None
        self._event_high = None
        self._event_low = None
        self._confirmation_start = None
