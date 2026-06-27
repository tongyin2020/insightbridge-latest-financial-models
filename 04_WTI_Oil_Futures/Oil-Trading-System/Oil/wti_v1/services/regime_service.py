"""
WTI v1 — 环境识别服务（我的改进：量化判断标准）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
与方案书的不同：方案书只列出文字描述，这里给出具体量化条件。
人工判断放在 override 接口，程序只执行量化规则。

四种状态：
  NORMAL  → 常规波动，允许技术信号
  EVENT   → 重要事件窗口，启动事件驱动模式
  TREND   → 单边强趋势，允许顺势信号
  BLOCKED → 异常极端，停止所有执行
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Deque
from collections import deque

from config.settings import REGIME, RegimeConfig
from models.core import Regime, Indicators, MarketEvent, EventPriority

logger = logging.getLogger(__name__)


class RegimeService:
    """
    环境识别服务。
    持续监控市场状态，维护当前 regime。
    所有信号模块在生成信号前必须查询当前 regime。
    """

    def __init__(self, config: RegimeConfig = REGIME):
        self.config = config
        self._current_regime: Regime = Regime.NORMAL
        self._regime_entered_at: datetime = datetime.utcnow()
        self._active_event: Optional[MarketEvent] = None
        self._event_window_end: Optional[datetime] = None

        # 人工 override（你的宏观判断接入点）
        self._human_override: Optional[Regime] = None
        self._human_override_reason: str = ""
        self._human_override_expiry: Optional[datetime] = None

        # 历史状态记录
        self._history: Deque[dict] = deque(maxlen=100)

        logger.info("[Regime] 初始化，默认状态: NORMAL")

    # ─────────────────────────────────────────
    # 主要接口
    # ─────────────────────────────────────────

    @property
    def current(self) -> Regime:
        """获取当前市场环境（优先返回人工override）"""
        if self._human_override is not None:
            if self._human_override_expiry and datetime.utcnow() > self._human_override_expiry:
                self._clear_override()
            else:
                return self._human_override
        return self._current_regime

    def update(self, indicators: Indicators, latest_event: Optional[MarketEvent] = None):
        """
        每根新K线后调用，根据量化条件更新环境状态。
        """
        new_regime = self._evaluate(indicators, latest_event)

        if new_regime != self._current_regime:
            self._transition(self._current_regime, new_regime, indicators)

    def on_market_event(self, event: MarketEvent, confirm_window_sec: int):
        """
        收到市场事件时调用。
        A类事件直接切换到EVENT，B类事件设置等待窗口。
        """
        if event.priority == EventPriority.C:
            logger.debug(f"[Regime] C类事件忽略: {event.headline}")
            return

        if event.priority in (EventPriority.A, EventPriority.B):
            self._active_event = event
            self._event_window_end = datetime.utcnow() + timedelta(seconds=confirm_window_sec)
            self._set_regime(Regime.EVENT, f"事件触发: {event.headline[:50]}")
            logger.info(
                f"[Regime] 切换到 EVENT 模式 | 优先级={event.priority} | "
                f"窗口={confirm_window_sec}s | 事件={event.headline[:60]}"
            )

    def check_event_window_expiry(self):
        """检查事件窗口是否过期（每次心跳调用）"""
        if self._current_regime == Regime.EVENT:
            if self._event_window_end and datetime.utcnow() > self._event_window_end:
                self._active_event = None
                self._event_window_end = None
                self._set_regime(Regime.NORMAL, "事件窗口过期，回归NORMAL")

    # ─────────────────────────────────────────
    # 人工 Override（你的宏观判断接入点）
    # ─────────────────────────────────────────

    def set_human_override(
        self,
        regime: Regime,
        reason: str,
        duration_hours: float = 4.0,
    ):
        """
        人工设置市场环境判断（覆盖程序的自动判断）。
        适合场景：
          - 你判断当前处于地缘政治主导阶段 → BLOCKED
          - 你认为今天风险偏好明显下降 → BLOCKED
          - 你认为单边趋势已形成 → TREND
          - 你想临时禁止交易 → BLOCKED

        duration_hours: override有效期，到期后自动恢复程序判断
        """
        self._human_override = regime
        self._human_override_reason = reason
        self._human_override_expiry = datetime.utcnow() + timedelta(hours=duration_hours)

        logger.warning(
            f"[Regime] 人工Override: {regime.value} | "
            f"原因={reason} | 有效={duration_hours}小时"
        )

    def clear_human_override(self):
        """人工解除override，恢复程序自动判断"""
        self._clear_override()
        logger.info("[Regime] 人工Override已清除")

    # ─────────────────────────────────────────
    # 量化判断逻辑（我的核心改进）
    # ─────────────────────────────────────────

    def _evaluate(self, ind: Indicators, event: Optional[MarketEvent]) -> Regime:
        """
        根据量化指标判断市场环境。
        优先级：BLOCKED > EVENT > TREND > NORMAL
        """

        # ① BLOCKED：异常极端，停止执行
        if self._is_blocked(ind):
            return Regime.BLOCKED

        # ② EVENT：处于活跃事件窗口
        if self._current_regime == Regime.EVENT:
            if self._event_window_end and datetime.utcnow() <= self._event_window_end:
                return Regime.EVENT

        # ③ TREND：强趋势阶段（改进：加入方向一致性判断）
        if self._is_trend(ind):
            return Regime.TREND

        # ④ NORMAL：默认状态
        return Regime.NORMAL

    def _is_blocked(self, ind: Indicators) -> bool:
        """
        BLOCKED判断：以下任一条件触发
        - 波动率超过历史基准4倍（市场极度混乱）
        - 缺少指标数据（数据异常）
        """
        if ind.atr_baseline <= 0:
            return True  # 无基准数据

        vol_ratio = ind.atr / ind.atr_baseline
        if vol_ratio > self.config.blocked_vol_multiplier:
            logger.warning(f"[Regime] 波动率比={vol_ratio:.1f}x，超过BLOCKED阈值{self.config.blocked_vol_multiplier}x")
            return True

        return False

    def _is_trend(self, ind: Indicators) -> bool:
        """
        TREND判断：量化标准（比方案书更精确）
        需同时满足：
        - ADX > 28（趋势强度高于一般阈值）
        - EMA方向一致
        - 波动率在合理范围（不是极端混乱）
        """
        if ind.adx < 28:
            return False
        if ind.atr_baseline > 0 and (ind.atr / ind.atr_baseline) > 3.0:
            return False  # 波动太大，不算干净趋势
        return True

    # ─────────────────────────────────────────
    # 内部状态管理
    # ─────────────────────────────────────────

    def _transition(self, old: Regime, new: Regime, ind: Indicators):
        self._history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "from": old.value,
            "to": new.value,
            "adx": round(ind.adx, 2),
            "vol_ratio": round(ind.volatility_ratio, 2),
        })
        self._set_regime(new, f"量化触发: ADX={ind.adx:.1f}, vol_ratio={ind.volatility_ratio:.2f}")

    def _set_regime(self, regime: Regime, reason: str):
        if regime != self._current_regime:
            logger.info(f"[Regime] {self._current_regime.value} → {regime.value} | {reason}")
        self._current_regime = regime
        self._regime_entered_at = datetime.utcnow()

    def _clear_override(self):
        self._human_override = None
        self._human_override_reason = ""
        self._human_override_expiry = None

    @property
    def summary(self) -> dict:
        return {
            "current_regime": self.current.value,
            "auto_regime": self._current_regime.value,
            "human_override": self._human_override.value if self._human_override else None,
            "override_reason": self._human_override_reason,
            "active_event": self._active_event.headline if self._active_event else None,
            "event_window_remaining_sec": (
                max(0, (self._event_window_end - datetime.utcnow()).total_seconds())
                if self._event_window_end else 0
            ),
        }
