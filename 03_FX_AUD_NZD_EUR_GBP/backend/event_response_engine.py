"""
Event Response Engine - 事件响应引擎
从固定30秒等待升级为基于市场结构的5阶段状态机

状态流:
IDLE → EVENT_DETECTED → IMPULSE_PHASE → LIQUIDITY_REBUILD → DIRECTION_CONFIRM → READY/INVALID

不同品种配置:
- AUD/USD: max_wait=90s, 需要二次推动确认
- NZD/USD: max_wait=90s, 更严格的阈值
"""
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("fx_main")

# ─── Per-Pair Configuration ────────────────────────────────────────────────────

PAIR_CONFIG = {
    "AUD/USD": {
        "impulse_vol_threshold": 1.8,     # vol_ratio 触发 impulse
        "spread_restore_threshold": 1.3,  # spread_ratio 恢复阈值
        "vol_calm_threshold": 1.8,        # 流动性恢复波动率阈值
        "confirm_break": True,            # 需要二次突破确认
        "require_second_push": True,      # 需要第二波同方向推动
        "max_wait_seconds": 90,           # 最大等待时间
        "min_impulse_pips": 3.0,          # 最小冲击幅度 (pips)
    },
    "NZD/USD": {
        "impulse_vol_threshold": 1.5,     # NZD 更严格
        "spread_restore_threshold": 1.2,
        "vol_calm_threshold": 1.5,
        "confirm_break": True,
        "require_second_push": True,
        "max_wait_seconds": 90,
        "min_impulse_pips": 2.5,
    },
}


@dataclass
class MarketSnapshot:
    """实时市场快照 - 由 MarketDataService 每次 poll 后更新"""
    pair: str
    price: float
    bid: float = 0.0
    ask: float = 0.0
    spread_pips: float = 0.0
    vol_1m: float = 0.0          # 1分钟实现波动率
    vol_5m: float = 0.0          # 5分钟实现波动率
    vol_ratio: float = 1.0       # vol_1m / vol_5m (>1 = 波动加速)
    spread_ratio: float = 1.0    # 当前spread / 基线spread
    tick_rate_10s: int = 0       # 10秒内tick数
    trend_score_5m: float = 0.0  # 5分钟方向强度 (-1 to 1)
    ts: float = 0.0


@dataclass
class EventResponseState:
    """事件响应引擎的完整状态"""
    state: str = "IDLE"
    pair: str = ""
    event_level: str = ""
    event_title: str = ""
    start_time: float = 0.0
    impulse_high: float = 0.0
    impulse_low: float = 0.0
    impulse_direction: str = ""   # "UP" or "DOWN"
    confirmed_direction: str = ""  # "BUY" / "SELL" / ""
    confidence: float = 0.0
    elapsed_seconds: float = 0.0
    max_wait_seconds: float = 90.0
    reason: str = ""
    reason_codes: list = field(default_factory=list)


class EventResponseEngine:
    """
    事件响应引擎 - 替代固定30秒等待
    核心思想: 等待的不是"时间"，而是"市场结构完成重定价"
    """

    STATES = ("IDLE", "EVENT_DETECTED", "IMPULSE_PHASE",
              "LIQUIDITY_REBUILD", "DIRECTION_CONFIRM", "READY", "INVALID")

    def __init__(self, pair: str):
        self.pair = pair
        self.config = PAIR_CONFIG.get(pair, PAIR_CONFIG["AUD/USD"])
        self.state = "IDLE"
        self.start_time: float = 0.0
        self.impulse_high: float = 0.0
        self.impulse_low: float = 0.0
        self.impulse_mid: float = 0.0
        self.impulse_direction: str = ""
        self.confirmed_direction: str = ""
        self.confidence: float = 0.0
        self.reason: str = ""
        self.reason_codes: list[str] = []
        self._pre_event_price: float = 0.0
        self._liquidity_rebuild_start: float = 0.0
        self._peak_vol_ratio: float = 0.0

    def on_event_detected(self, snapshot: MarketSnapshot, event_level: str = "A", title: str = "") -> EventResponseState:
        """事件触发 - 开始结构化等待"""
        self.state = "EVENT_DETECTED"
        self.start_time = time.time()
        self._pre_event_price = snapshot.price
        self.impulse_high = snapshot.price
        self.impulse_low = snapshot.price
        self.impulse_mid = snapshot.price
        self.impulse_direction = ""
        self.confirmed_direction = ""
        self.confidence = 0.0
        self.reason = f"Event detected: {title}"
        self.reason_codes = ["EVENT_DETECTED"]
        self._peak_vol_ratio = snapshot.vol_ratio
        self._liquidity_rebuild_start = 0.0
        logger.info(f"[EventEngine:{self.pair}] Event detected: {title} (level={event_level})")
        return self.get_state(event_level, title)

    def update(self, snapshot: MarketSnapshot) -> EventResponseState:
        """每次行情更新时调用 - 推进状态机"""
        if self.state == "IDLE" or self.state in ("READY", "INVALID"):
            return self.get_state()

        elapsed = time.time() - self.start_time

        # 超时检查
        if elapsed > self.config["max_wait_seconds"]:
            self.state = "INVALID"
            self.reason = f"Timeout: {elapsed:.0f}s > {self.config['max_wait_seconds']}s"
            self.reason_codes = ["TIMEOUT"]
            logger.info(f"[EventEngine:{self.pair}] INVALID - timeout")
            return self.get_state()

        # 更新 impulse 范围
        if snapshot.price > self.impulse_high:
            self.impulse_high = snapshot.price
        if snapshot.price < self.impulse_low:
            self.impulse_low = snapshot.price
        if snapshot.vol_ratio > self._peak_vol_ratio:
            self._peak_vol_ratio = snapshot.vol_ratio

        # 状态转移
        if self.state == "EVENT_DETECTED":
            self._evaluate_impulse(snapshot, elapsed)

        elif self.state == "IMPULSE_PHASE":
            self._evaluate_liquidity_rebuild(snapshot, elapsed)

        elif self.state == "LIQUIDITY_REBUILD":
            self._evaluate_direction_confirm(snapshot, elapsed)

        elif self.state == "DIRECTION_CONFIRM":
            self._evaluate_ready(snapshot, elapsed)

        return self.get_state()

    def _evaluate_impulse(self, snap: MarketSnapshot, elapsed: float):
        """EVENT_DETECTED → IMPULSE_PHASE: 检测第一波冲击"""
        impulse_range_pips = (self.impulse_high - self.impulse_low) * 10000
        is_impulse = (
            snap.vol_ratio >= self.config["impulse_vol_threshold"]
            or impulse_range_pips >= self.config["min_impulse_pips"]
        )

        if is_impulse:
            # 判断冲击方向
            if snap.price > self._pre_event_price:
                self.impulse_direction = "UP"
            elif snap.price < self._pre_event_price:
                self.impulse_direction = "DOWN"
            else:
                self.impulse_direction = "NEUTRAL"

            self.impulse_mid = (self.impulse_high + self.impulse_low) / 2
            self.state = "IMPULSE_PHASE"
            self.reason = f"Impulse detected: {self.impulse_direction}, range={impulse_range_pips:.1f}pips"
            self.reason_codes = ["IMPULSE_DETECTED", f"DIR_{self.impulse_direction}"]
            logger.info(f"[EventEngine:{self.pair}] IMPULSE: dir={self.impulse_direction}, range={impulse_range_pips:.1f}pips")

        # 超过15秒还没有冲击 → 可能是低影响事件
        elif elapsed > 15:
            self.state = "INVALID"
            self.reason = "No significant impulse within 15s"
            self.reason_codes = ["NO_IMPULSE"]

    def _evaluate_liquidity_rebuild(self, snap: MarketSnapshot, elapsed: float):
        """IMPULSE_PHASE → LIQUIDITY_REBUILD: 流动性恢复"""
        spread_restored = snap.spread_ratio < self.config["spread_restore_threshold"]
        vol_calming = snap.vol_ratio < self.config["vol_calm_threshold"]

        if spread_restored and vol_calming:
            self._liquidity_rebuild_start = time.time()
            self.state = "LIQUIDITY_REBUILD"
            self.reason = f"Liquidity rebuilding: spread_ratio={snap.spread_ratio:.2f}, vol_ratio={snap.vol_ratio:.2f}"
            self.reason_codes = ["LIQUIDITY_REBUILD", "SPREAD_RESTORED", "VOL_CALMING"]
            logger.info(f"[EventEngine:{self.pair}] LIQUIDITY_REBUILD: spread={snap.spread_ratio:.2f}")

    def _evaluate_direction_confirm(self, snap: MarketSnapshot, elapsed: float):
        """LIQUIDITY_REBUILD → DIRECTION_CONFIRM: 方向确认"""
        # 等至少3秒让流动性稳定
        if time.time() - self._liquidity_rebuild_start < 3:
            return

        # 检查第二波推动
        if self.config["require_second_push"]:
            if snap.price > self.impulse_high and snap.vol_ratio > 1.2:
                self.confirmed_direction = "BUY"
                self.state = "DIRECTION_CONFIRM"
                pips = (snap.price - self._pre_event_price) * 10000
                self.confidence = min(abs(pips) * 8, 95)
                self.reason = f"Second push UP confirmed: +{pips:.1f}pips"
                self.reason_codes = ["SECOND_PUSH_UP", "DIRECTION_BUY"]
                logger.info(f"[EventEngine:{self.pair}] DIRECTION_CONFIRM: BUY, conf={self.confidence:.0f}")

            elif snap.price < self.impulse_low and snap.vol_ratio > 1.2:
                self.confirmed_direction = "SELL"
                self.state = "DIRECTION_CONFIRM"
                pips = (self._pre_event_price - snap.price) * 10000
                self.confidence = min(abs(pips) * 8, 95)
                self.reason = f"Second push DOWN confirmed: -{pips:.1f}pips"
                self.reason_codes = ["SECOND_PUSH_DOWN", "DIRECTION_SELL"]
                logger.info(f"[EventEngine:{self.pair}] DIRECTION_CONFIRM: SELL, conf={self.confidence:.0f}")

            # 价格回到冲击区间中部 → 不确定
            elif abs(snap.price - self.impulse_mid) < (self.impulse_high - self.impulse_low) * 0.2:
                rebuild_elapsed = time.time() - self._liquidity_rebuild_start
                if rebuild_elapsed > 20:
                    self.state = "INVALID"
                    self.reason = "Price returned to mid-impulse, no clear direction"
                    self.reason_codes = ["NO_CLEAR_DIRECTION"]
        else:
            # 不需要二次推动，直接用冲击方向
            if self.impulse_direction == "UP":
                self.confirmed_direction = "BUY"
            elif self.impulse_direction == "DOWN":
                self.confirmed_direction = "SELL"
            else:
                self.state = "INVALID"
                self.reason = "Neutral impulse"
                self.reason_codes = ["NEUTRAL_IMPULSE"]
                return
            self.state = "DIRECTION_CONFIRM"
            self.confidence = min(self._peak_vol_ratio * 30, 85)

    def _evaluate_ready(self, snap: MarketSnapshot, elapsed: float):
        """DIRECTION_CONFIRM → READY: 最终确认"""
        # 方向不变 → READY
        if self.confirmed_direction == "BUY" and snap.price >= self.impulse_high * 0.9999:
            self.state = "READY"
            self.reason = f"READY: {self.confirmed_direction} confirmed"
            self.reason_codes.append("READY")
            logger.info(f"[EventEngine:{self.pair}] READY: {self.confirmed_direction}")
        elif self.confirmed_direction == "SELL" and snap.price <= self.impulse_low * 1.0001:
            self.state = "READY"
            self.reason = f"READY: {self.confirmed_direction} confirmed"
            self.reason_codes.append("READY")
            logger.info(f"[EventEngine:{self.pair}] READY: {self.confirmed_direction}")
        else:
            # 方向反转 → INVALID
            if self.confirmed_direction == "BUY" and snap.price < self.impulse_mid:
                self.state = "INVALID"
                self.reason = "Direction reversal after confirmation"
                self.reason_codes = ["DIRECTION_REVERSAL"]
            elif self.confirmed_direction == "SELL" and snap.price > self.impulse_mid:
                self.state = "INVALID"
                self.reason = "Direction reversal after confirmation"
                self.reason_codes = ["DIRECTION_REVERSAL"]

    def reset(self):
        """重置引擎"""
        self.state = "IDLE"
        self.start_time = 0.0
        self.impulse_high = 0.0
        self.impulse_low = 0.0
        self.impulse_mid = 0.0
        self.impulse_direction = ""
        self.confirmed_direction = ""
        self.confidence = 0.0
        self.reason = ""
        self.reason_codes = []
        self._pre_event_price = 0.0
        self._peak_vol_ratio = 0.0

    def get_state(self, event_level: str = "", event_title: str = "") -> EventResponseState:
        elapsed = time.time() - self.start_time if self.start_time > 0 else 0
        return EventResponseState(
            state=self.state,
            pair=self.pair,
            event_level=event_level,
            event_title=event_title,
            start_time=self.start_time,
            impulse_high=round(self.impulse_high, 5),
            impulse_low=round(self.impulse_low, 5),
            impulse_direction=self.impulse_direction,
            confirmed_direction=self.confirmed_direction,
            confidence=round(self.confidence, 1),
            elapsed_seconds=round(elapsed, 1),
            max_wait_seconds=self.config["max_wait_seconds"],
            reason=self.reason,
            reason_codes=list(self.reason_codes),
        )


class EventResponseManager:
    """管理所有品种的事件响应引擎"""

    def __init__(self, pairs: list[str]):
        self.engines: dict[str, EventResponseEngine] = {
            pair: EventResponseEngine(pair) for pair in pairs
        }

    def on_event(self, snapshot: MarketSnapshot, event_level: str = "A", title: str = "") -> dict:
        """触发事件 - 所有品种同时进入状态机"""
        results = {}
        for pair, engine in self.engines.items():
            s = MarketSnapshot(pair=pair, price=snapshot.price, spread_pips=snapshot.spread_pips,
                               vol_ratio=snapshot.vol_ratio, spread_ratio=snapshot.spread_ratio)
            results[pair] = engine.on_event_detected(s, event_level, title)
        return results

    def update(self, pair: str, snapshot: MarketSnapshot) -> EventResponseState:
        """行情更新 - 推进对应品种的状态机"""
        if pair in self.engines:
            return self.engines[pair].update(snapshot)
        return EventResponseState()

    def get_all_states(self) -> dict:
        """获取所有品种的引擎状态"""
        return {pair: engine.get_state().__dict__ for pair, engine in self.engines.items()}

    def reset_all(self):
        for engine in self.engines.values():
            engine.reset()

    def reset(self, pair: str):
        if pair in self.engines:
            self.engines[pair].reset()
