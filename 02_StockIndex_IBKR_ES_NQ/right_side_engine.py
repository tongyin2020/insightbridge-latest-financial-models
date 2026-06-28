"""
Right-side confirmation filter for live Event/IBKR execution.

This layer is intentionally lightweight:
- waits for the move to prove itself instead of firing on the first impulse
- blocks repeated duplicate entries during a cooldown window
- rejects stale or poor-quality market states
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Tuple


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RightSideDecision:
    allowed: bool
    status: str
    reason: str
    signal_strength: str
    market_health: str
    metrics: dict


class RightSideDecisionEngine:
    def __init__(self) -> None:
        self.cooldowns: Dict[Tuple[str, str], datetime] = {}
        self.symbol_profiles = {
            "BTC": {
                "cooldown_seconds": 900,
                "min_confidence": 0.64,
                "min_breakout_ratio": 0.56,
                "max_range_ratio": 0.050,
            },
            "ETH": {
                "cooldown_seconds": 900,
                "min_confidence": 0.64,
                "min_breakout_ratio": 0.56,
                "max_range_ratio": 0.055,
            },
            "SOL": {
                "cooldown_seconds": 900,
                "min_confidence": 0.66,
                "min_breakout_ratio": 0.58,
                "max_range_ratio": 0.065,
            },
            "AUDUSD": {
                "cooldown_seconds": 600,
                "min_confidence": 0.63,
                "min_breakout_ratio": 0.54,
                "max_range_ratio": 0.010,
            },
            "NZDUSD": {
                "cooldown_seconds": 600,
                "min_confidence": 0.63,
                "min_breakout_ratio": 0.54,
                "max_range_ratio": 0.011,
            },
            "ZN": {
                "cooldown_seconds": 1200,
                "min_confidence": 0.65,
                "min_breakout_ratio": 0.60,
                "max_range_ratio": 0.018,
            },
            "CL": {
                "cooldown_seconds": 1800,
                "min_confidence": 0.68,
                "min_breakout_ratio": 0.62,
                "max_range_ratio": 0.030,
            },
            "MES": {
                "cooldown_seconds": 1200,
                "min_confidence": 0.67,
                "min_breakout_ratio": 0.60,
                "max_range_ratio": 0.022,
            },
        }
        self.max_signal_age_seconds = 300
        self.blocked_statuses = {"competing_session", "subscription_limited", "subscription_error"}

    def _profile(self, symbol: str) -> dict:
        return self.symbol_profiles.get(
            symbol,
            {
                "cooldown_seconds": 900,
                "min_confidence": 0.63,
                "min_breakout_ratio": 0.55,
                "max_range_ratio": 0.035,
            },
        )

    def _parse_detected_at(self, raw: str | None) -> datetime:
        if not raw:
            return _now()
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return _now()

    def _signal_strength(self, confidence: float, min_confidence: float) -> str:
        if confidence >= 0.82:
            return "strong"
        if confidence >= 0.70:
            return "healthy"
        if confidence >= min_confidence:
            return "moderate"
        return "weak"

    def _market_health(self, status: str, range_ratio: float, max_range_ratio: float) -> str:
        if status in self.blocked_statuses:
            return "blocked"
        if range_ratio >= max_range_ratio:
            return "volatile"
        if status == "delayed":
            return "delayed"
        return "healthy"

    def evaluate(self, signal: dict) -> RightSideDecision:
        symbol = str(signal.get("symbol", ""))
        direction = str(signal.get("direction", "")).upper()
        confidence = float(signal.get("confidence", 0.0))
        price = float(signal.get("latest_price") or 0.0)
        high = float(signal.get("high") or price or 0.0)
        low = float(signal.get("low") or price or 0.0)
        status = str(signal.get("market_status", "unknown"))
        detected_at = self._parse_detected_at(signal.get("detected_at"))
        age_seconds = max(0.0, (_now() - detected_at).total_seconds())
        profile = self._profile(symbol)
        min_confidence = float(profile["min_confidence"])
        min_breakout_ratio = float(profile["min_breakout_ratio"])
        max_range_ratio = float(profile["max_range_ratio"])
        cooldown_seconds = int(profile["cooldown_seconds"])

        range_size = max(high - low, 0.0)
        range_ratio = (range_size / price) if price > 0 else 0.0
        if range_size <= 0:
            breakout_ratio = 0.0
        elif direction == "BUY":
            breakout_ratio = (price - low) / range_size
        else:
            breakout_ratio = (high - price) / range_size

        signal_strength = self._signal_strength(confidence, min_confidence)
        market_health = self._market_health(status, range_ratio, max_range_ratio)
        metrics = {
            "age_seconds": round(age_seconds, 2),
            "breakout_ratio": round(breakout_ratio, 4),
            "range_ratio": round(range_ratio, 4),
            "confidence": round(confidence, 4),
            "market_status": status,
            "symbol_profile": profile,
        }

        if price <= 0:
            return RightSideDecision(True, "manual_context", "no_live_price_context", signal_strength, "unknown", metrics)

        if status in self.blocked_statuses:
            return RightSideDecision(False, "blocked", f"market_status={status}", signal_strength, market_health, metrics)
        if age_seconds > self.max_signal_age_seconds:
            return RightSideDecision(False, "stale", f"signal_age={age_seconds:.0f}s", signal_strength, market_health, metrics)
        if confidence < min_confidence:
            return RightSideDecision(False, "weak_signal", f"confidence={confidence:.2f}", signal_strength, market_health, metrics)
        if range_ratio >= max_range_ratio:
            return RightSideDecision(False, "shock_not_settled", f"range_ratio={range_ratio:.3f}", signal_strength, market_health, metrics)
        if breakout_ratio < min_breakout_ratio:
            return RightSideDecision(False, "not_right_side_yet", f"breakout_ratio={breakout_ratio:.2f}", signal_strength, market_health, metrics)

        cooldown_key = (symbol, direction)
        last_fire = self.cooldowns.get(cooldown_key)
        if last_fire is not None:
            elapsed = (_now() - last_fire).total_seconds()
            if elapsed < cooldown_seconds:
                metrics["cooldown_remaining"] = round(cooldown_seconds - elapsed, 1)
                return RightSideDecision(False, "cooldown", f"{cooldown_seconds - elapsed:.0f}s_remaining", signal_strength, market_health, metrics)

        self.cooldowns[cooldown_key] = _now()
        return RightSideDecision(True, "approved", "right_side_confirmed", signal_strength, market_health, metrics)
