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
    """Estimate net EV. Payoff (p_win / avg_win / avg_loss) is taken from a
    per-(asset, bucket) *calibration* table when one is supplied and the trade's
    bucket has enough real samples; otherwise it falls back to the uncalibrated
    heuristic. Cost is always the modelled round-trip cost. The calibration table
    is fit on GROSS per-event outcomes so subtracting the modelled cost here is
    the clean payoff-minus-cost decomposition (see eventalpha_intraday_study
    v2_calibration)."""

    def __init__(self, min_ev_bps: float = 1.0, calibration: Optional[dict] = None,
                 min_calib_n: int = 8):
        self.min_ev_bps = min_ev_bps
        self.calibration = calibration
        self.min_calib_n = min_calib_n

    @staticmethod
    def _clip(x, lo=0.01, hi=0.99):
        return max(lo, min(hi, float(x)))

    def _calibrated_payoff(self, asset, bucket):
        if not self.calibration or bucket is None:
            return None
        key = getattr(asset, "name", str(asset)).upper()
        cell = (self.calibration.get(key, {}) or {}).get(str(bucket))
        if not cell or int(cell.get("n", 0)) < self.min_calib_n:
            return None
        return (float(cell["p_win"]), float(cell["avg_win_bps"]),
                float(cell["avg_loss_bps"]))

    def estimate(self, opportunity, state, cost_model: Optional[CostModel] = None,
                 secs_since_t0: float = 0.0, bucket: Optional[str] = None
                 ) -> ExpectedValueResult:
        asset = getattr(state, "asset", "FX")
        calib = self._calibrated_payoff(asset, bucket)
        if calib is not None:
            p_win, avg_win, avg_loss = calib
            source = f"calibrated[{bucket}]"
        else:
            score = float(opportunity.opportunity_score)
            confidence = float(opportunity.confidence)
            # HEURISTIC (uncalibrated) — used only when no calibration cell applies
            p_win = self._clip(0.42 + 0.32 * score + 0.18 * confidence)
            volatility_z = float(getattr(state, "volatility_z", 1.0))
            persistence = float(getattr(state, "trend_persistence", 0.5))
            reversal = float(getattr(state, "reversal_score", 0.5))
            avg_win = 8.0 + 10.0 * max(0.0, persistence - 0.5) + 2.0 * max(0.0, volatility_z - 1.0)
            avg_loss = 5.0 + 8.0 * reversal + 2.0 * max(0.0, volatility_z - 1.0)
            source = "heuristic"

        if cost_model is None:
            cost_model = default_cost_model(asset)
        live_spread = getattr(state, "spread_bps", None)
        cost = cost_model.round_trip_cost_bps(secs_since_t0=secs_since_t0,
                                              live_spread_bps=live_spread)

        ev = p_win * avg_win - (1.0 - p_win) * avg_loss - cost
        tradable = ev >= self.min_ev_bps
        reason = (f"{source}: p_win={p_win:.2f}, avg_win={avg_win:.1f}, "
                  f"avg_loss={avg_loss:.1f}, cost_rt={cost:.1f}, ev={ev:.1f}")
        return ExpectedValueResult(tradable, ev, p_win, avg_win, avg_loss, cost, reason)
