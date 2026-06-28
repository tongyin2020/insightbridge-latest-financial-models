"""
event_right_side_engine.py
═══════════════════════════════════════════════════════════════════════════════
事件后"右侧确认"信号闸门 (Production-grade rewrite)

设计目标：重大事件后不抢第一秒，先进冷静期，等噪声衰减、K线实体突破、
影线变短、成交量确认、点差/滑点/时段达标，方向一致后再右侧进场。

本版本相对最初骨架修正了以下问题：
  1. base_atr 不再用"事件触发当根"（已被首冲击污染），改用事件前窗口均值。
  2. ATR 衰减判定允许在窗口内出现新高时重置确认，避免"假峰值"过早进场。
  3. 实体突破新增"成交量确认"门槛。
  4. 新增交易时段过滤（每品种可配置 session）。
  5. 信号成立后 **不** 立即关闭事件；只有在外部确认成交后才调用 mark_filled()。
     —— 解决"下单失败却永久丢失机会"的问题。
  6. 点差/滑点上限改为按品种"tick 数"表达，而非统一 bps（对国债/SOFR 更合理）。
  7. evaluate() 是纯函数式判定，不产生副作用（除 ATR 峰值跟踪）；下单与状态推进
     由调用方在拿到券商成交回报后驱动。

注意：本模块只输出 HOLD / BUY / SELL / REJECT 判定，**不直接下单**。
真正下单前必须再串联 HardStopController + CorrectPositionSizer（见 README）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Literal, Optional, Tuple

import pandas as pd


Direction = Literal["LONG", "SHORT"]
SignalStatus = Literal["HOLD", "BUY", "SELL", "REJECT"]


# ══════════════════════════════════════════════════════════════════════════════
#  品种规则
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AssetRule:
    symbol: str
    asset_class: str
    min_cooldown_minutes: int          # 硬冷静期（事件后最少等待）
    max_wait_minutes: int              # 最大等待，超时放弃，不硬交易
    tick_size: float                   # 最小变动价位（用于点差/滑点换算成 tick 数）
    atr_period: int = 14
    atr_decay_threshold: float = 0.60  # 衰减到峰值区间的 60% 以下视为噪声出清
    base_atr_lookback: int = 5         # base_atr 用事件前 N 根均值
    body_break_period: int = 10        # 实体突破对比的回看根数
    max_shadow_ratio: float = 0.40     # 影线占整根比例上限（过滤插针）
    min_body_ratio: float = 0.45       # 实体占整根比例下限（要求实体突破）
    vol_confirm_period: int = 10       # 成交量确认对比的回看根数
    min_vol_mult: float = 1.10         # 突破K线量 >= 前N根均量 * 该倍数
    max_spread_ticks: float = 4.0      # 点差上限（tick 数）
    max_slippage_ticks: float = 6.0    # 滑点上限（tick 数）
    risk_fraction: float = 0.0025      # 单笔风险预算（占权益比例，交给 sizer 用）
    # 交易时段（UTC）。None 表示 24h（如 FX/Crypto）。
    session_start_utc: Optional[time] = None
    session_end_utc: Optional[time] = None


# 8 个核心品种的初始默认参数（经验先验，必须用真实模拟盘数据 walk-forward 校准）
DEFAULT_RULES: Dict[str, AssetRule] = {
    # FX —— 24h，但可选只在伦敦/纽约重叠时段交易
    "EURUSD": AssetRule("EURUSD", "FX", 10, 45, tick_size=0.00005,
                        max_spread_ticks=3.0, max_slippage_ticks=4.0),
    "USDJPY": AssetRule("USDJPY", "FX", 10, 45, tick_size=0.005,
                        max_spread_ticks=3.0, max_slippage_ticks=4.0),

    # Index —— CME 主时段（RTH 约 13:30–20:00 UTC）；Globex 深夜流动性差，默认只在 RTH
    "MES": AssetRule("MES", "INDEX", 15, 60, tick_size=0.25,
                     max_spread_ticks=2.0, max_slippage_ticks=4.0,
                     session_start_utc=time(13, 30), session_end_utc=time(20, 0)),
    "MNQ": AssetRule("MNQ", "INDEX", 15, 60, tick_size=0.25,
                     max_spread_ticks=3.0, max_slippage_ticks=5.0,
                     session_start_utc=time(13, 30), session_end_utc=time(20, 0)),

    # Treasury —— CBOT；亚洲时段流动性弱，默认只在欧美时段
    "ZT": AssetRule("ZT", "TREASURY", 5, 35, tick_size=0.0078125,
                    max_spread_ticks=2.0, max_slippage_ticks=3.0,
                    session_start_utc=time(7, 0), session_end_utc=time(20, 0)),
    "ZN": AssetRule("ZN", "TREASURY", 5, 35, tick_size=0.015625,
                    max_spread_ticks=2.0, max_slippage_ticks=3.0,
                    session_start_utc=time(7, 0), session_end_utc=time(20, 0)),

    # Rates —— SOFR 3M 期货
    "SR3": AssetRule("SR3", "RATES", 3, 25, tick_size=0.0025,
                     max_spread_ticks=2.0, max_slippage_ticks=3.0,
                     session_start_utc=time(7, 0), session_end_utc=time(20, 0)),

    # Crypto futures —— CME Micro Bitcoin，24h
    "MBT": AssetRule("MBT", "CRYPTO_FUT", 25, 90, tick_size=5.0,
                     max_spread_ticks=6.0, max_slippage_ticks=10.0),
}


# ══════════════════════════════════════════════════════════════════════════════
#  事件状态
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EventState:
    symbol: str
    event_name: str
    event_time: datetime
    base_atr: float
    peak_atr: float
    active: bool = True
    confirmed_pending: bool = False     # 已产生信号、等待成交确认
    reason: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class RightSideEventEngine:
    """事件后右侧确认引擎。判定与状态推进分离：evaluate() 给判定，
    mark_filled()/mark_abandoned() 由调用方在拿到券商回报后驱动。"""

    def __init__(self, rules: Optional[Dict[str, AssetRule]] = None):
        self.rules = rules or DEFAULT_RULES
        self.states: Dict[str, EventState] = {}

    # ── ATR ────────────────────────────────────────────────────────────────
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    # ── 事件触发 ──────────────────────────────────────────────────────────
    def trigger_event(self, symbol: str, event_name: str,
                      event_time: datetime, df: pd.DataFrame) -> None:
        if symbol not in self.rules:
            raise KeyError(f"未配置品种规则: {symbol}")
        rule = self.rules[symbol]
        atr_series = self.calculate_atr(df, rule.atr_period)

        # base_atr 用事件触发"之前"的窗口均值，避免被首冲击污染
        prior = atr_series.iloc[-(rule.base_atr_lookback + 1):-1].dropna()
        if len(prior) == 0:
            base = atr_series.dropna()
            if len(base) == 0:
                raise ValueError(f"ATR 数据不足: {symbol}")
            base_atr = float(base.iloc[-1])
        else:
            base_atr = float(prior.mean())

        if base_atr <= 0:
            raise ValueError(f"ATR 非正: {symbol}")

        self.states[symbol] = EventState(
            symbol=symbol, event_name=event_name, event_time=event_time,
            base_atr=base_atr, peak_atr=base_atr, active=True,
            reason="macro_event_triggered",
        )

    # ── 状态推进（由调用方在券商回报后调用）───────────────────────────────
    def mark_filled(self, symbol: str) -> None:
        """母单成交确认后调用：关闭该事件，进入持仓管理阶段。"""
        st = self.states.get(symbol)
        if st:
            st.active = False
            st.confirmed_pending = False
            st.reason = "filled_confirmed"

    def mark_abandoned(self, symbol: str, reason: str) -> None:
        """下单失败/被拒后调用：回退 pending，允许后续窗口内再尝试。"""
        st = self.states.get(symbol)
        if st:
            st.confirmed_pending = False
            st.reason = f"order_failed:{reason}"

    # ── 各层判定 ──────────────────────────────────────────────────────────
    def _cooldown_ready(self, rule: AssetRule, st: EventState, now: datetime) -> bool:
        return now >= st.event_time + timedelta(minutes=rule.min_cooldown_minutes)

    def _max_wait_expired(self, rule: AssetRule, st: EventState, now: datetime) -> bool:
        return now >= st.event_time + timedelta(minutes=rule.max_wait_minutes)

    @staticmethod
    def _in_session(rule: AssetRule, now: datetime) -> bool:
        if rule.session_start_utc is None or rule.session_end_utc is None:
            return True  # 24h 品种
        t = now.astimezone(timezone.utc).time()
        if rule.session_start_utc <= rule.session_end_utc:
            return rule.session_start_utc <= t <= rule.session_end_utc
        # 跨午夜时段
        return t >= rule.session_start_utc or t <= rule.session_end_utc

    def _atr_whipsaw_finished(self, rule: AssetRule, st: EventState,
                              current_atr: float) -> Tuple[bool, str]:
        # 出现新高 → 重置峰值，要求重新等待衰减（避免假峰值进场）
        if current_atr > st.peak_atr:
            st.peak_atr = float(current_atr)
            return False, "atr_new_peak_reset"

        atr_range = st.peak_atr - st.base_atr
        if atr_range <= 0:
            return False, "atr_range_not_established"

        decay_pos = (current_atr - st.base_atr) / atr_range
        if decay_pos <= rule.atr_decay_threshold:
            return True, f"atr_decayed_to_{decay_pos:.2f}"
        return False, f"atr_decay_not_enough_{decay_pos:.2f}"

    def _volume_confirmed(self, rule: AssetRule, df: pd.DataFrame) -> Tuple[bool, str]:
        if "volume" not in df.columns:
            return True, "volume_not_available_skip"  # 无量数据则不阻断（FX 现货常见）
        if len(df) < rule.vol_confirm_period + 1:
            return False, "not_enough_volume_history"
        last_vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].iloc[-(rule.vol_confirm_period + 1):-1].mean())
        if avg_vol <= 0:
            return True, "avg_volume_zero_skip"
        if last_vol >= avg_vol * rule.min_vol_mult:
            return True, f"volume_ok_{last_vol / avg_vol:.2f}x"
        return False, f"volume_too_low_{last_vol / avg_vol:.2f}x"

    def _market_quality_ok(self, rule: AssetRule, bid: Optional[float],
                           ask: Optional[float], expected_entry: float
                           ) -> Tuple[bool, str]:
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            return False, "missing_bid_ask"
        mid = (bid + ask) / 2.0
        spread_ticks = (ask - bid) / rule.tick_size
        if spread_ticks > rule.max_spread_ticks:
            return False, f"spread_too_wide_{spread_ticks:.1f}t"
        slip_ticks = abs(expected_entry - mid) / rule.tick_size
        if slip_ticks > rule.max_slippage_ticks:
            return False, f"slippage_too_high_{slip_ticks:.1f}t"
        return True, f"market_ok_spread_{spread_ticks:.1f}t"

    def _body_breakout(self, rule: AssetRule, df: pd.DataFrame) -> Dict[str, Any]:
        if len(df) < rule.body_break_period + 2:
            return {"status": "HOLD", "reason": "not_enough_candles"}

        last = df.iloc[-1]
        hist = df.iloc[-(rule.body_break_period + 1):-1]
        body_high = hist[["open", "close"]].max(axis=1).max()
        body_low = hist[["open", "close"]].min(axis=1).min()

        total_range = float(last["high"] - last["low"])
        body_size = float(abs(last["close"] - last["open"]))
        if total_range <= 0:
            return {"status": "HOLD", "reason": "zero_range_candle"}

        body_ratio = body_size / total_range
        if body_ratio < rule.min_body_ratio:
            return {"status": "HOLD", "reason": f"body_too_small_{body_ratio:.2f}"}

        upper_shadow = float(last["high"] - max(last["open"], last["close"]))
        lower_shadow = float(min(last["open"], last["close"]) - last["low"])
        upper_ratio = upper_shadow / total_range
        lower_ratio = lower_shadow / total_range

        if last["close"] > last["open"] and last["close"] > body_high:
            if upper_ratio > rule.max_shadow_ratio:
                return {"status": "REJECT", "reason": f"long_upper_shadow_{upper_ratio:.2f}"}
            return {"status": "BUY", "direction": "LONG",
                    "entry_price": float(last["close"]),
                    "stop_loss": float(min(last["open"], last["low"])),
                    "reason": "bullish_body_breakout"}

        if last["close"] < last["open"] and last["close"] < body_low:
            if lower_ratio > rule.max_shadow_ratio:
                return {"status": "REJECT", "reason": f"long_lower_shadow_{lower_ratio:.2f}"}
            return {"status": "SELL", "direction": "SHORT",
                    "entry_price": float(last["close"]),
                    "stop_loss": float(max(last["open"], last["high"])),
                    "reason": "bearish_body_breakout"}

        return {"status": "HOLD", "reason": "no_body_breakout"}

    # ── 主判定 ────────────────────────────────────────────────────────────
    def evaluate(self, symbol: str, now: datetime, df: pd.DataFrame,
                 bid: Optional[float] = None, ask: Optional[float] = None
                 ) -> Dict[str, Any]:
        st = self.states.get(symbol)
        if st is None or not st.active:
            return {"status": "HOLD", "reason": "no_active_event", "symbol": symbol}
        if st.confirmed_pending:
            return {"status": "HOLD", "reason": "awaiting_fill_confirmation", "symbol": symbol}

        rule = self.rules[symbol]

        if self._max_wait_expired(rule, st, now):
            st.active = False
            return {"status": "HOLD", "reason": "max_wait_expired_no_trade",
                    "symbol": symbol, "event": st.event_name}

        if not self._in_session(rule, now):
            return {"status": "HOLD", "reason": "out_of_session", "symbol": symbol}

        if not self._cooldown_ready(rule, st, now):
            return {"status": "HOLD", "reason": "hard_cooldown_active",
                    "symbol": symbol, "cooldown_minutes": rule.min_cooldown_minutes}

        atr = self.calculate_atr(df, rule.atr_period).iloc[-1]
        if pd.isna(atr) or atr <= 0:
            return {"status": "HOLD", "reason": "atr_unavailable", "symbol": symbol}

        done, atr_reason = self._atr_whipsaw_finished(rule, st, float(atr))
        if not done:
            return {"status": "HOLD", "reason": atr_reason, "symbol": symbol,
                    "current_atr": float(atr), "peak_atr": st.peak_atr}

        signal = self._body_breakout(rule, df)
        if signal["status"] not in ("BUY", "SELL"):
            return {**signal, "symbol": symbol, "event": st.event_name,
                    "atr_reason": atr_reason}

        vol_ok, vol_reason = self._volume_confirmed(rule, df)
        if not vol_ok:
            return {"status": "HOLD", "symbol": symbol, "reason": vol_reason,
                    "pre_signal": signal}

        mkt_ok, mkt_reason = self._market_quality_ok(
            rule, bid, ask, signal["entry_price"])
        if not mkt_ok:
            return {"status": "HOLD", "symbol": symbol, "reason": mkt_reason,
                    "pre_signal": signal}

        # 关键：不在此处关闭事件。标记 pending，等待调用方成交确认后 mark_filled()。
        st.confirmed_pending = True
        return {**signal, "symbol": symbol, "event": st.event_name,
                "atr_reason": atr_reason, "volume_reason": vol_reason,
                "market_reason": mkt_reason, "risk_fraction": rule.risk_fraction,
                "asset_class": rule.asset_class, "tick_size": rule.tick_size,
                "requires_fill_confirmation": True}
