"""Opportunity Engine: does this event have a real, still-tradable repricing?

Scores the current 10-30 minute window only; it does not forecast hours/days. The
weights below are the report's starting heuristics and are NOT yet calibrated --
Phase 2 fits them on real-data replay. Reads the live schema (MarketState) fields
directly, falling back to neutral 0.5 when a feature is missing.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OpportunityResult:
    should_consider: bool
    direction: str
    opportunity_score: float
    confidence: float
    reason: str


class OpportunityEngine:
    def __init__(self, min_score: float = 0.62, min_confidence: float = 0.58):
        self.min_score = min_score
        self.min_confidence = min_confidence

    @staticmethod
    def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, float(x)))

    @staticmethod
    def _early_move(state) -> float:
        # prefer the live schema field; fall back to the raw dict the sketch used
        v = getattr(state, "early_move_bps", None)
        if v is None and hasattr(state, "raw") and isinstance(state.raw, dict):
            v = state.raw.get("early_move", 0.0)
        return float(v or 0.0)

    def evaluate(self, state, event=None) -> OpportunityResult:
        momentum = self._clip(getattr(state, "momentum_score", 0.5))
        persistence = self._clip(getattr(state, "trend_persistence", 0.5))
        cross = self._clip(getattr(state, "cross_asset_alignment", 0.5))
        liquidity = self._clip(getattr(state, "liquidity_score", 0.5))
        reversal = self._clip(getattr(state, "reversal_score", 0.5))
        execution = self._clip(getattr(state, "execution_quality", 0.5))
        surprise = self._clip(getattr(event, "surprise_score", 0.0) if event else 0.0)

        raw_move = self._early_move(state)
        direction = "long" if raw_move >= 0 else "short"

        score = self._clip(
            0.28 * momentum + 0.24 * persistence + 0.18 * cross
            + 0.16 * liquidity + 0.08 * execution + 0.06 * surprise
            - 0.22 * reversal
        )
        confidence = self._clip(
            0.55 * score + 0.25 * abs(momentum - 0.5) * 2 + 0.20 * persistence
        )
        ok = score >= self.min_score and confidence >= self.min_confidence
        reason = (
            f"momentum={momentum:.2f}, persistence={persistence:.2f}, cross={cross:.2f}, "
            f"liquidity={liquidity:.2f}, reversal={reversal:.2f}, execution={execution:.2f}, "
            f"surprise={surprise:.2f}, early_move={raw_move:.1f}bps, "
            f"score={score:.2f}, confidence={confidence:.2f}"
        )
        return OpportunityResult(ok, direction, score, confidence, reason)
