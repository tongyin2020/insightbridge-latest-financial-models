"""
WTI Trading Platform - Fragility Engine
Measures market vulnerability based on spread, liquidity, volatility, and microstructure.
Inspired by the FX Trading Dashboard's 脆弱度引擎.
"""
import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class FragilityLevel(str, Enum):
    LOW = "low"          # 0-30: stable, safe to trade
    MODERATE = "moderate" # 30-60: caution, reduce size
    HIGH = "high"        # 60-80: danger, only reduce positions
    EXTREME = "extreme"  # 80-100: halt trading


@dataclass
class FragilityState:
    level: FragilityLevel = FragilityLevel.LOW
    score: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""
    triggers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "level": self.level.value,
            "score": round(self.score, 1),
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "timestamp": self.timestamp,
            "triggers": self.triggers,
        }


class FragilityEngine:
    """
    Multi-factor fragility scoring engine.
    Combines spread behavior, volatility regime, liquidity depth, and anomaly detection.
    """

    def __init__(self):
        self._spread_history: deque = deque(maxlen=100)
        self._vol_history: deque = deque(maxlen=100)
        self._price_changes: deque = deque(maxlen=50)
        self._liquidity_scores: deque = deque(maxlen=50)
        self._state = FragilityState()

        # Thresholds
        self._spread_normal = 0.03  # Normal spread for CL
        self._spread_warning = 0.08
        self._spread_danger = 0.15
        self._vol_baseline = 0.20   # 20% annualized
        self._vol_spike_mult = 2.0
        self._price_spike_atr = 3.0

    def update(
        self,
        current_spread: float,
        current_vol_ratio: float,
        atr: float,
        price_change: float,
        adx: float,
        regime: str,
        bid_ask_depth: float = 1.0,  # Normalized 0-1
    ) -> FragilityState:
        """Update fragility assessment with latest market data"""
        self._spread_history.append(current_spread)
        self._vol_history.append(current_vol_ratio)
        if atr > 0:
            self._price_changes.append(abs(price_change) / atr)

        triggers = []
        components = {}

        # 1. Spread Fragility (0-30 points)
        spread_score = 0
        if current_spread > self._spread_danger:
            spread_score = 30
            triggers.append("点差异常扩大")
        elif current_spread > self._spread_warning:
            spread_score = 20
            triggers.append("点差偏大")
        elif current_spread > self._spread_normal * 2:
            spread_score = 10
        else:
            spread_score = max(0, (current_spread / self._spread_normal - 1) * 10)

        # Spread acceleration: sudden change
        if len(self._spread_history) >= 5:
            recent_avg = sum(list(self._spread_history)[-5:]) / 5
            older_avg = sum(list(self._spread_history)[-20:-5]) / max(1, len(list(self._spread_history)[-20:-5])) if len(self._spread_history) > 5 else recent_avg
            if older_avg > 0 and recent_avg / older_avg > 2.0:
                spread_score = min(30, spread_score + 10)
                triggers.append("点差突变")

        components["spread"] = spread_score

        # 2. Volatility Fragility (0-25 points)
        vol_score = 0
        if current_vol_ratio > self._vol_spike_mult * 2:
            vol_score = 25
            triggers.append("超短波动触发")
        elif current_vol_ratio > self._vol_spike_mult:
            vol_score = 15
            triggers.append("波动加剧")
        else:
            vol_score = max(0, (current_vol_ratio - 1.0) * 12)

        components["volatility"] = vol_score

        # 3. Price Shock Detection (0-20 points)
        shock_score = 0
        if self._price_changes:
            recent_shock = list(self._price_changes)[-1] if self._price_changes else 0
            if recent_shock > self._price_spike_atr:
                shock_score = 20
                triggers.append("价格剧烈波动")
            elif recent_shock > self._price_spike_atr * 0.6:
                shock_score = 12
            else:
                shock_score = max(0, recent_shock / self._price_spike_atr * 10)

        components["price_shock"] = shock_score

        # 4. Liquidity Assessment (0-15 points)
        liq_score = 0
        normalized_depth = min(1.0, max(0, bid_ask_depth))
        if normalized_depth < 0.3:
            liq_score = 15
            triggers.append("深度萎缩")
        elif normalized_depth < 0.6:
            liq_score = 8
        else:
            liq_score = max(0, (1.0 - normalized_depth) * 10)

        components["liquidity"] = liq_score

        # 5. Regime Penalty (0-10 points)
        regime_score = 0
        if regime == "blocked":
            regime_score = 10
            triggers.append("市场冻结")
        elif regime == "event":
            regime_score = 6
            triggers.append("事件模式")
        elif regime == "spike":
            regime_score = 4

        components["regime"] = regime_score

        # Total score
        total = spread_score + vol_score + shock_score + liq_score + regime_score
        total = min(100, max(0, total))

        # Determine level
        if total >= 80:
            level = FragilityLevel.EXTREME
        elif total >= 60:
            level = FragilityLevel.HIGH
        elif total >= 30:
            level = FragilityLevel.MODERATE
        else:
            level = FragilityLevel.LOW

        self._state = FragilityState(
            level=level,
            score=total,
            components=components,
            timestamp=datetime.now(timezone.utc).isoformat(),
            triggers=triggers,
        )

        return self._state

    @property
    def current_state(self) -> FragilityState:
        return self._state

    def should_halt_trading(self) -> bool:
        return self._state.level == FragilityLevel.EXTREME

    def should_reduce_size(self) -> bool:
        return self._state.level in (FragilityLevel.HIGH, FragilityLevel.EXTREME)

    def get_size_multiplier(self) -> float:
        """Returns position size multiplier based on fragility"""
        if self._state.level == FragilityLevel.EXTREME:
            return 0.0
        elif self._state.level == FragilityLevel.HIGH:
            return 0.25
        elif self._state.level == FragilityLevel.MODERATE:
            return 0.6
        return 1.0


# Global instance
fragility_engine = FragilityEngine()
