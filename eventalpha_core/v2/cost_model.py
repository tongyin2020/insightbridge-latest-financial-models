"""Round-trip cost model for the v2 Expected-Value engine.

These numbers mirror the *measured / venue-schedule* costs used in
``eventalpha_intraday_study.execution_model`` (the retail_conservative scenario):
FX half-spread is measured from real Dukascopy bid/ask; crypto commission (IBKR
Zerohash / Binance taker) is the dominant cost. They are duplicated here as small
constants so ``eventalpha_core`` does not import the research package (layering:
research depends on core, never the reverse). Keep the two in sync.

The EV engine must cost a *round trip* (enter + exit), and spreads widen inside
the event window -- both are handled here so the EV number is honest, not the
toy ``cost = spread`` in the original sketch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CostModel:
    """Per-side execution costs, basis points of mid (except latency, seconds)."""
    half_spread_bps: float
    event_spread_mult: float
    event_spread_secs: float
    slippage_bps: float
    commission_bps: float
    latency_s: float

    def round_trip_cost_bps(self, secs_since_t0: float = 0.0,
                            live_spread_bps: Optional[float] = None) -> float:
        """Total enter+exit cost in bps.

        If a live spread is supplied (from the current quote) it overrides the
        modelled spread; otherwise the modelled half-spread is widened by
        ``event_spread_mult`` while inside the event window.
        """
        if live_spread_bps is not None and live_spread_bps > 0:
            half = live_spread_bps / 2.0
        else:
            mult = self.event_spread_mult if secs_since_t0 <= self.event_spread_secs else 1.0
            half = self.half_spread_bps * mult
        per_side = half + self.slippage_bps + self.commission_bps
        return 2.0 * per_side


# mirrors execution_model.SCENARIOS["retail_conservative"] (FX spread measured)
_DEFAULTS = {
    "FX":     CostModel(0.20, 2.1, 60.0, 0.20, 0.20, 0.75),
    "OIL":    CostModel(1.00, 5.0, 60.0, 1.00, 0.50, 0.75),
    "CRYPTO": CostModel(1.00, 4.0, 60.0, 3.00, 10.0, 1.00),
}
_FALLBACK = CostModel(2.00, 3.0, 60.0, 2.00, 2.00, 1.00)


def default_cost_model(asset: str = "FX") -> CostModel:
    """Conservative per-asset cost model. ``asset`` is an AssetClass name or str."""
    key = getattr(asset, "name", str(asset)).upper()
    return _DEFAULTS.get(key, _FALLBACK)
