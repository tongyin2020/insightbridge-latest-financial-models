"""Expected Value Engine: convert signal quality into net expected bps.

More useful than a bare long/short call: only trade when estimated net EV after a
*round-trip* cost is positive with a safety margin, and exit if EV collapses.

IMPORTANT (honesty): the p_win / avg_win / avg_loss formulas below are the
report's heuristics, NOT calibrated numbers. They are false precision until
Phase 2 fits them per impact bucket on real-data replay. Costs, however, are
real: they come from ``CostModel.round_trip_cost_bps`` (measured spreads +
venue commission), not the toy ``cost = spread`` in the original sketch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .cost_model import CostModel, default_cost_model


@dataclass
class ExpectedValueResult:
    tradable: bool
    ev_bps: float
    p_win: float
    avg_win_bps: float
    avg_loss_bps: float
    estimated_cost_bps: float
    reason: str


class ExpectedValueEngine:
    def __init__(self, min_ev_bps: float = 1.0):
        self.min_ev_bps = min_ev_bps

    @staticmethod
    def _clip(x, lo=0.01, hi=0.99):
        return max(lo, min(hi, float(x)))

    def estimate(self, opportunity, state, cost_model: Optional[CostModel] = None,
                 secs_since_t0: float = 0.0) -> ExpectedValueResult:
        score = float(opportunity.opportunity_score)
        confidence = float(opportunity.confidence)
        # HEURISTIC (uncalibrated) — replace with fitted per-bucket values in Phase 2
        p_win = self._clip(0.42 + 0.32 * score + 0.18 * confidence)
        volatility_z = float(getattr(state, "volatility_z", 1.0))
        persistence = float(getattr(state, "trend_persistence", 0.5))
        reversal = float(getattr(state, "reversal_score", 0.5))
        avg_win = 8.0 + 10.0 * max(0.0, persistence - 0.5) + 2.0 * max(0.0, volatility_z - 1.0)
        avg_loss = 5.0 + 8.0 * reversal + 2.0 * max(0.0, volatility_z - 1.0)

        if cost_model is None:
            cost_model = default_cost_model(getattr(state, "asset", "FX"))
        live_spread = getattr(state, "spread_bps", None)
        cost = cost_model.round_trip_cost_bps(secs_since_t0=secs_since_t0,
                                              live_spread_bps=live_spread)

        ev = p_win * avg_win - (1.0 - p_win) * avg_loss - cost
        tradable = ev >= self.min_ev_bps
        reason = (f"p_win={p_win:.2f}, avg_win={avg_win:.1f}, avg_loss={avg_loss:.1f}, "
                  f"cost_rt={cost:.1f}, ev={ev:.1f}")
        return ExpectedValueResult(tradable, ev, p_win, avg_win, avg_loss, cost, reason)
