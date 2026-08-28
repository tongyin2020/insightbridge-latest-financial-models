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
from zoneinfo import ZoneInfo

import pandas as pd

# Selectivity gate deps: the measured impact buckets live in the eventalpha_core
# package (repo root). Import defensively so a missing package degrades the gate
# to a no-op instead of breaking the live engine's import.
_SELECTIVITY_OK = True
try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from eventalpha_core.schema import AssetClass as _AssetClass
    from eventalpha_core.advanced.measured_timing import impact_bucket as _impact_bucket_fn
    from eventalpha_core.advanced.microstructure import (
        FakeoutConfig as _FakeoutConfig,
        is_breakout_fakeout as _is_breakout_fakeout,
        order_book_imbalance as _order_book_imbalance,
    )
    _MEASURED_ASSET = {
        "FX": _AssetClass.FX,
        "CRYPTO_SPOT": _AssetClass.CRYPTO,
        "CRYPTO_FUT": _AssetClass.CRYPTO,
        # INDEX / TREASURY / RATES have no measured impact edges -> gate no-op.
    }
except Exception:                       # noqa: BLE001
    _SELECTIVITY_OK = False
    _MEASURED_ASSET = {}


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
    # 假冲击(fakeout)盘口失衡门槛：突破方向必须有足够的同向挂单支撑才算真突破。
    # None = 用 FakeoutConfig 的占位默认值。**该阈值未经真实数据验证(见 microstructure.py)**，
    # 第二步用历史数据校准前只是占位。仅在 fakeout_filter_enabled=True 时生效。
    min_obi_abs: Optional[float] = None
    risk_fraction: float = 0.0025      # 单笔风险预算（占权益比例，交给 sizer 用）
    # 交易时段。优先用交易所本地时区表达（session_tz + *_local）：事件锚定
    # 美东时间，写死 UTC 会在夏令时切换时整体漂移一小时（CPI 8:30 ET =
    # 12:30/13:30 UTC）。*_utc 字段保留用于兼容旧配置；本地字段优先。
    session_tz: str = "America/New_York"
    session_start_local: Optional[time] = None
    session_end_local: Optional[time] = None
    session_start_utc: Optional[time] = None  # 兼容旧配置；新配置请用 *_local
    session_end_utc: Optional[time] = None


# 8 个核心品种的初始默认参数（经验先验，必须用真实模拟盘数据 walk-forward 校准）
DEFAULT_RULES: Dict[str, AssetRule] = {
    # FX —— 24h，但可选只在伦敦/纽约重叠时段交易
    "EURUSD": AssetRule("EURUSD", "FX", 10, 45, tick_size=0.00005,
                        max_spread_ticks=3.0, max_slippage_ticks=4.0),
    "USDJPY": AssetRule("USDJPY", "FX", 10, 45, tick_size=0.005,
                        max_spread_ticks=3.0, max_slippage_ticks=4.0),

    # Index —— CME 主时段 RTH 9:30–16:00 美东（夏/冬令时自动跟随；
    # 旧配置写死 13:30–20:00 UTC，冬季会错位成 10:30–17:00 ET）。
    # Globex 深夜流动性差，默认只在 RTH
    "MES": AssetRule("MES", "INDEX", 15, 60, tick_size=0.25,
                     max_spread_ticks=2.0, max_slippage_ticks=4.0,
                     session_start_local=time(9, 30), session_end_local=time(16, 0)),
    "MNQ": AssetRule("MNQ", "INDEX", 15, 60, tick_size=0.25,
                     max_spread_ticks=3.0, max_slippage_ticks=5.0,
                     session_start_local=time(9, 30), session_end_local=time(16, 0)),

    # Treasury —— CBOT；亚洲时段流动性弱，默认只在欧美时段。
    # 3:00–16:00 美东 ≈ 旧配置 7:00–20:00 UTC 的夏季窗口，且全年跟随 ET 事件锚点
    "ZT": AssetRule("ZT", "TREASURY", 5, 35, tick_size=0.0078125,
                    max_spread_ticks=2.0, max_slippage_ticks=3.0,
                    session_start_local=time(3, 0), session_end_local=time(16, 0)),
    "ZN": AssetRule("ZN", "TREASURY", 5, 35, tick_size=0.015625,
                    max_spread_ticks=2.0, max_slippage_ticks=3.0,
                    session_start_local=time(3, 0), session_end_local=time(16, 0)),

    # Rates —— SOFR 3M 期货（同 Treasury 时段）
    "SR3": AssetRule("SR3", "RATES", 3, 25, tick_size=0.0025,
                     max_spread_ticks=2.0, max_slippage_ticks=3.0,
                     session_start_local=time(3, 0), session_end_local=time(16, 0)),

    # Commodity —— NYMEX WTI 原油（④号产品，EIA 周度库存/OPEC 事件）。
    # tick 0.01 = $10/手（1000 桶）；RTH 9:00–14:30 ET 流动性最佳。
    # 阈值同为未验证先验，需用 shadow 数据校准；enabled_symbols（主仓库）
    # 需包含 CL 才会真正接线。
    "CL": AssetRule("CL", "COMMODITY", 10, 45, tick_size=0.01,
                    max_spread_ticks=2.0, max_slippage_ticks=3.0,
                    session_start_local=time(9, 0), session_end_local=time(14, 30)),

    # Crypto futures —— CME Micro Bitcoin，24h
    "MBT": AssetRule("MBT", "CRYPTO_FUT", 25, 90, tick_size=5.0,
                     max_spread_ticks=6.0, max_slippage_ticks=10.0),

    # Crypto spot —— 盈透 ZEROHASH BTC/USD，24h；tick 约 0.01；软止损（无原生 STP）
    # 点差/滑点上限用“tick 数”表达；BTC 波动大，阈值略宽（可用真实数据校准）。
    "BTC": AssetRule("BTC", "CRYPTO_SPOT", 25, 90, tick_size=0.01,
                     max_spread_ticks=2000.0, max_slippage_ticks=3000.0),
    # ETH/SOL 现货（ZEROHASH）——tick 为估算值，需对照 IBKR 真实合约规格核实。
    "ETH": AssetRule("ETH", "CRYPTO_SPOT", 25, 90, tick_size=0.01,
                     max_spread_ticks=2000.0, max_slippage_ticks=3000.0),
    "SOL": AssetRule("SOL", "CRYPTO_SPOT", 25, 90, tick_size=0.001,
                     max_spread_ticks=2000.0, max_slippage_ticks=3000.0),
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
    event_id: str = ""
    event_price: float = 0.0            # close at trigger, for early-move magnitude
    active: bool = True
    confirmed_pending: bool = False     # 已产生信号、等待成交确认
    reason: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class RightSideEventEngine:
    """事件后右侧确认引擎。判定与状态推进分离：evaluate() 给判定，
    mark_filled()/mark_abandoned() 由调用方在拿到券商回报后驱动。"""

    def __init__(self, rules: Optional[Dict[str, AssetRule]] = None,
                 selectivity_enabled: bool = False,
                 fakeout_filter_enabled: bool = False,
                 fakeout_require_book: bool = False):
        self.rules = rules or DEFAULT_RULES
        self.states: Dict[str, EventState] = {}
        # Fakeout (false-breakout) filter: after the K-line breakout + volume +
        # market-quality checks pass, require the order book to actually support
        # the breakout direction (OBI gate). Default OFF so the live judgement is
        # unchanged unless a caller opts in (paper first). Degrades to a no-op
        # when no Level-2 sizes are supplied (never blocks a trade it can't judge).
        # Thresholds are UNVALIDATED placeholders pending Step-2 calibration.
        self.fakeout_filter_enabled = fakeout_filter_enabled and _SELECTIVITY_OK
        # Optional fail-closed mode.  When explicitly enabled, inability to
        # observe a usable Level-2 book means WATCH, never "cannot tell -> buy".
        # It remains opt-in until venue-specific depth quality is verified.
        self.fakeout_require_book = bool(fakeout_require_book)
        # Selectivity gate: stand down on 'small' early-move events (the only
        # logic change the 2024-2025 P&L study proved adds edge). Default OFF so
        # the live judgement is byte-for-byte unchanged unless a caller opts in
        # (paper first). Only crypto/FX symbols have measured edges; others no-op.
        self.selectivity_enabled = selectivity_enabled

    # ── selectivity helpers ─────────────────────────────────────────────────
    @staticmethod
    def _early_move_bps(st: EventState, df: pd.DataFrame) -> Optional[float]:
        """Absolute post-event price reaction (bps): the executable, price-derived
        proxy for the macro surprise. Measured from the trigger-bar close."""
        if not st.event_price or st.event_price <= 0 or len(df) == 0:
            return None
        last_close = float(df["close"].iloc[-1])
        return abs(last_close / st.event_price - 1.0) * 1e4

    @staticmethod
    def _impact_bucket(asset_class: str, early_move_bps: Optional[float]) -> Optional[str]:
        if not _SELECTIVITY_OK or early_move_bps is None:
            return None
        ac = _MEASURED_ASSET.get(asset_class)
        if ac is None:
            return None
        return _impact_bucket_fn(ac, early_move_bps)

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
                      event_time: datetime, df: pd.DataFrame,
                      event_id: Optional[str] = None) -> None:
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

        event_price = float(df["close"].iloc[-1]) if len(df) else 0.0
        stable_event_id = event_id or f"{event_name}@{event_time.isoformat()}"
        self.states[symbol] = EventState(
            symbol=symbol, event_name=event_name, event_time=event_time,
            base_atr=base_atr, peak_atr=base_atr, event_price=event_price,
            event_id=stable_event_id,
            active=True, reason="macro_event_triggered",
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
        # 优先用交易所本地时区窗口（夏令时安全：窗口跟随 session_tz 的
        # UTC 偏移自动伸缩）；本地字段缺省时回退到旧 UTC 字段（兼容旧配置）。
        if rule.session_start_local is not None and rule.session_end_local is not None:
            if now.tzinfo is None:
                raise ValueError("now must be timezone-aware")
            t = now.astimezone(ZoneInfo(rule.session_tz)).time()
            start, end = rule.session_start_local, rule.session_end_local
        elif rule.session_start_utc is not None and rule.session_end_utc is not None:
            t = now.astimezone(timezone.utc).time()
            start, end = rule.session_start_utc, rule.session_end_utc
        else:
            return True  # 24h 品种
        if start <= end:
            return start <= t <= end
        # 跨午夜时段
        return t >= start or t <= end

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
                 bid: Optional[float] = None, ask: Optional[float] = None,
                 bid_sizes: Optional[list] = None, ask_sizes: Optional[list] = None
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

        # --- selectivity gate (opt-in) --------------------------------------
        # Classify the event by its early-move magnitude; when enabled, stand
        # down on 'small' events. The bucket is always reported for audit.
        early_move_bps = self._early_move_bps(st, df)
        impact_bucket = self._impact_bucket(rule.asset_class, early_move_bps)
        if self.selectivity_enabled and impact_bucket == "small":
            return {"status": "HOLD", "symbol": symbol, "event": st.event_name,
                    "reason": "selectivity_stand_down_small_impact",
                    "early_move_bps": early_move_bps, "impact_bucket": impact_bucket,
                    "pre_signal": signal}

        vol_ok, vol_reason = self._volume_confirmed(rule, df)
        if not vol_ok:
            return {"status": "HOLD", "symbol": symbol, "reason": vol_reason,
                    "pre_signal": signal}

        mkt_ok, mkt_reason = self._market_quality_ok(
            rule, bid, ask, signal["entry_price"])
        if not mkt_ok:
            return {"status": "HOLD", "symbol": symbol, "reason": mkt_reason,
                    "pre_signal": signal}

        # --- fakeout (false-breakout) gate (opt-in) -------------------------
        # The breakout passed price/volume/spread; now require the order book to
        # actually back the direction. OBI is always reported for audit. When
        # enabled and the book contradicts the breakout, reject as a fakeout.
        # No-op when OBI is unavailable (no Level-2 sizes) or the filter is off.
        obi = _order_book_imbalance(bid_sizes, ask_sizes) if _SELECTIVITY_OK else None
        fakeout, fakeout_reason = (False, "fakeout_filter_disabled")
        if self.fakeout_filter_enabled:
            if obi is None and self.fakeout_require_book:
                return {"status": "HOLD", "symbol": symbol, "event": st.event_name,
                        "reason": "fakeout_book_required_but_unavailable",
                        "obi": None, "pre_signal": signal,
                        "fakeout_filter_enabled": True,
                        "fakeout_require_book": True}
            cfg = _FakeoutConfig(min_obi_abs=rule.min_obi_abs) if rule.min_obi_abs is not None else _FakeoutConfig()
            fakeout, fakeout_reason = _is_breakout_fakeout(signal.get("direction", ""), obi, cfg)
            if fakeout:
                return {"status": "REJECT", "symbol": symbol, "event": st.event_name,
                        "reason": fakeout_reason, "obi": obi, "pre_signal": signal,
                        "fakeout_filter_enabled": True}

        # 关键：不在此处关闭事件。标记 pending，等待调用方成交确认后 mark_filled()。
        st.confirmed_pending = True
        return {**signal, "symbol": symbol, "event": st.event_name,
                "atr_reason": atr_reason, "volume_reason": vol_reason,
                "market_reason": mkt_reason, "risk_fraction": rule.risk_fraction,
                "asset_class": rule.asset_class, "tick_size": rule.tick_size,
                "early_move_bps": early_move_bps, "impact_bucket": impact_bucket,
                "selectivity_enabled": self.selectivity_enabled,
                "obi": obi, "fakeout_filter_enabled": self.fakeout_filter_enabled,
                "fakeout_require_book": self.fakeout_require_book,
                "fakeout_reason": fakeout_reason,
                "requires_fill_confirmation": True}
