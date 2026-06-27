"""
WTI Trading Platform - Execution Gate & Signal Scoring
Pre-trade confirmation checklist and unified bullish/bearish scoring system.
Inspired by the FX Trading Dashboard's 执行门控 and 综合多空评分.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


@dataclass
class GateCheck:
    name: str
    status: GateStatus
    value: str
    threshold: str
    weight: float = 1.0

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "value": self.value,
            "threshold": self.threshold,
            "weight": self.weight,
        }


class ExecutionGate:
    """
    Pre-trade execution gate.
    All conditions must pass before allowing entry.
    """

    def __init__(self):
        self._spread_max = 0.08       # Max spread in dollars
        self._min_adx = 18.0          # Min trend strength
        self._max_vol_ratio = 3.0     # Max volatility ratio
        self._min_score = 55          # Min signal score to enter

    def evaluate(
        self,
        spread: float,
        adx: float,
        vol_ratio: float,
        signal_score: float,
        fragility_score: float,
        risk_can_trade: bool,
        cooldown_active: bool,
        regime: str,
    ) -> Dict:
        """Evaluate all gate conditions"""
        checks = []

        # 1. Spread check
        checks.append(GateCheck(
            name="点差检查",
            status=GateStatus.PASS if spread <= self._spread_max else GateStatus.FAIL,
            value=f"${spread:.4f}",
            threshold=f"<= ${self._spread_max}",
            weight=1.5,
        ))

        # 2. Trend strength
        checks.append(GateCheck(
            name="趋势强度 (ADX)",
            status=GateStatus.PASS if adx >= self._min_adx else GateStatus.WARN if adx >= self._min_adx * 0.7 else GateStatus.FAIL,
            value=f"{adx:.1f}",
            threshold=f">= {self._min_adx}",
        ))

        # 3. Volatility check
        checks.append(GateCheck(
            name="波动率控制",
            status=GateStatus.PASS if vol_ratio <= self._max_vol_ratio else GateStatus.FAIL,
            value=f"{vol_ratio:.2f}x",
            threshold=f"<= {self._max_vol_ratio}x",
            weight=1.2,
        ))

        # 4. Signal score
        checks.append(GateCheck(
            name="信号强度",
            status=GateStatus.PASS if signal_score >= self._min_score else GateStatus.WARN if signal_score >= self._min_score * 0.8 else GateStatus.FAIL,
            value=f"{signal_score:.0f}/100",
            threshold=f">= {self._min_score}",
            weight=1.5,
        ))

        # 5. Fragility check
        checks.append(GateCheck(
            name="市场脆弱度",
            status=GateStatus.PASS if fragility_score < 60 else GateStatus.WARN if fragility_score < 80 else GateStatus.FAIL,
            value=f"{fragility_score:.0f}/100",
            threshold="< 60",
        ))

        # 6. Risk control
        checks.append(GateCheck(
            name="风控状态",
            status=GateStatus.PASS if risk_can_trade else GateStatus.FAIL,
            value="允许" if risk_can_trade else "禁止",
            threshold="允许交易",
            weight=2.0,
        ))

        # 7. Cooldown
        checks.append(GateCheck(
            name="冷静期",
            status=GateStatus.PASS if not cooldown_active else GateStatus.FAIL,
            value="无" if not cooldown_active else "冷静期中",
            threshold="无冷静期",
            weight=2.0,
        ))

        # 8. Regime
        regime_ok = regime in ("normal", "event")
        checks.append(GateCheck(
            name="市场状态",
            status=GateStatus.PASS if regime == "normal" else GateStatus.WARN if regime == "event" else GateStatus.FAIL,
            value=regime.upper(),
            threshold="NORMAL / EVENT",
        ))

        # Calculate overall gate
        all_pass = all(c.status != GateStatus.FAIL for c in checks)
        has_warnings = any(c.status == GateStatus.WARN for c in checks)
        fail_count = sum(1 for c in checks if c.status == GateStatus.FAIL)

        if all_pass and not has_warnings:
            gate_status = "OPEN"
            gate_message = "确认指标均通过，可按信号方向入场"
        elif all_pass and has_warnings:
            gate_status = "CAUTION"
            gate_message = "有警告条件，建议减小仓位入场"
        elif fail_count <= 1:
            gate_status = "PARTIAL"
            gate_message = "确认条件不足，建议等待更明确的信号"
        else:
            gate_status = "CLOSED"
            gate_message = "确认条件未满足，建议继续观望"

        return {
            "gate_status": gate_status,
            "message": gate_message,
            "can_enter": all_pass,
            "checks": [c.to_dict() for c in checks],
            "pass_count": sum(1 for c in checks if c.status == GateStatus.PASS),
            "warn_count": sum(1 for c in checks if c.status == GateStatus.WARN),
            "fail_count": fail_count,
            "total_checks": len(checks),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class SignalScorer:
    """
    Unified bullish/bearish signal scoring system.
    Combines multiple factors into a -100 to +100 score.
    Positive = bullish, Negative = bearish.
    """

    def __init__(self):
        self._weights = {
            "ema_cross": 20,       # EMA fast vs slow
            "adx_trend": 15,       # Trend strength
            "regime": 15,          # Market regime
            "volatility": 10,      # Vol conditions
            "price_momentum": 15,  # Recent price change
            "rsi": 10,             # RSI levels (if available)
            "spread": 5,           # Spread conditions
            "fragility": 10,       # Market fragility (inverse)
        }

    def calculate_score(
        self,
        ema_fast: float,
        ema_slow: float,
        adx: float,
        regime: str,
        vol_ratio: float,
        recent_price_change_pct: float,
        spread: float,
        fragility_score: float,
        rsi: float = 50.0,
    ) -> Dict:
        """Calculate unified long/short signal score"""
        components = {}
        total = 0.0

        # 1. EMA Cross Signal (-20 to +20)
        if ema_fast > 0 and ema_slow > 0:
            ema_pct = (ema_fast - ema_slow) / ema_slow * 100
            ema_score = max(-20, min(20, ema_pct * 10))
        else:
            ema_score = 0
        components["ema_cross"] = round(ema_score, 1)
        total += ema_score

        # 2. ADX Trend Strength (-15 to +15)
        if adx > 28:
            adx_score = 15 if recent_price_change_pct > 0 else -15
        elif adx > 22:
            adx_score = 8 if recent_price_change_pct > 0 else -8
        else:
            adx_score = 0  # No clear trend
        components["adx_trend"] = round(adx_score, 1)
        total += adx_score

        # 3. Regime Factor (-15 to +15)
        regime_map = {
            "normal": 5,
            "event": 0,
            "spike": -5,
            "blocked": -15,
        }
        regime_score = regime_map.get(regime, 0)
        if regime == "normal" and recent_price_change_pct > 0:
            regime_score = 10
        elif regime == "normal" and recent_price_change_pct < 0:
            regime_score = -5
        components["regime"] = regime_score
        total += regime_score

        # 4. Volatility (-10 to +10)
        if vol_ratio < 0.8:
            vol_score = 5  # Low vol: neutral to slightly bullish
        elif vol_ratio < 1.5:
            vol_score = 0  # Normal
        elif vol_ratio < 2.5:
            vol_score = -5  # Elevated
        else:
            vol_score = -10  # Extreme
        components["volatility"] = vol_score
        total += vol_score

        # 5. Price Momentum (-15 to +15)
        mom_score = max(-15, min(15, recent_price_change_pct * 5))
        components["price_momentum"] = round(mom_score, 1)
        total += mom_score

        # 6. RSI (-10 to +10)
        if rsi > 70:
            rsi_score = -10  # Overbought
        elif rsi > 60:
            rsi_score = -3
        elif rsi < 30:
            rsi_score = 10  # Oversold (bullish)
        elif rsi < 40:
            rsi_score = 3
        else:
            rsi_score = 0
        components["rsi"] = rsi_score
        total += rsi_score

        # 7. Spread (-5 to +5)
        if spread < 0.03:
            spread_score = 5  # Tight spread = good
        elif spread < 0.08:
            spread_score = 0
        else:
            spread_score = -5  # Wide spread = caution
        components["spread"] = spread_score
        total += spread_score

        # 8. Fragility (inverse: -10 to +10)
        if fragility_score < 20:
            frag_score = 10
        elif fragility_score < 40:
            frag_score = 5
        elif fragility_score < 60:
            frag_score = 0
        elif fragility_score < 80:
            frag_score = -5
        else:
            frag_score = -10
        components["fragility"] = frag_score
        total += frag_score

        total = max(-100, min(100, total))

        # Determine direction and zone
        if total > 60:
            direction = "strong_long"
            zone = "做多区"
            zone_color = "emerald"
        elif total > 20:
            direction = "long"
            zone = "偏多"
            zone_color = "green"
        elif total > -20:
            direction = "neutral"
            zone = "观望区 40-60"
            zone_color = "zinc"
        elif total > -60:
            direction = "short"
            zone = "偏空"
            zone_color = "orange"
        else:
            direction = "strong_short"
            zone = "做空区"
            zone_color = "red"

        return {
            "score": round(total, 1),
            "direction": direction,
            "zone": zone,
            "zone_color": zone_color,
            "components": components,
            "bullish_pct": round(max(0, total + 100) / 2, 1),  # 0-100 bullish percentage
            "bearish_pct": round(max(0, 100 - total) / 2, 1),  # 0-100 bearish percentage
            "confidence": round(abs(total) / 100, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Global instances
execution_gate = ExecutionGate()
signal_scorer = SignalScorer()
