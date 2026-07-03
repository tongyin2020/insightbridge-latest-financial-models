"""Measured per-asset event timing parameters.

These numbers are NOT guesses. They are measured by the `eventalpha_intraday_study`
package from real 2024-2025 intraday data (63 NFP/CPI/FOMC events per asset):
  - CRYPTO: BTCUSDT tick data (Binance public archive)
  - FX:     EURUSD + USDJPY TICK data (JForex authenticated export), pooled
  - OIL:    real WTI front-month CL 5-second bars (IBKR authenticated Gateway)

Mapping from the event study to these parameters:
  min_wait_seconds  ~ washout p50, floored at a venue-realistic minimum
                      (crypto 5s, FX 30s, oil 60s -- we cannot fire in ~1s on a
                      retail channel, and the floor also covers the whipsaw p75 tail)
  max_wait_seconds  ~ time_to_peak p50 (must be positioned before the move tops)
  time_stop_seconds ~ trend_lifetime p75; when p75 is censored at the 30-min
                      measurement horizon we keep 1800s (no early time-stop).

FX is now real tick (reaction ~1s, not the earlier 1-minute artifact). OIL is now
real WTI 5-second bars pulled over the IBKR Gateway (reaction ~5s, move ~31bps),
replacing the earlier 1-minute Brent proxy. Pre-2024-07 events use the nearest
available CL back-month (IBKR retains only ~2y of expired contracts), which is
fine for event timing (the whole crude curve moves together on macro releases).
RATES and INDEX are not yet measured and intentionally omitted so they fall back
to the legacy windows.

Source report: eventalpha_intraday_study RECALIBRATION_PROPOSAL.md (measured 2026-07).
"""
from __future__ import annotations

from typing import Optional, Tuple

from eventalpha_core.schema import AssetClass, EventType

# (asset, event_type) -> (min_wait_seconds, max_wait_seconds)
MEASURED_WAIT: dict[Tuple[AssetClass, EventType], Tuple[int, int]] = {
    (AssetClass.CRYPTO, EventType.NFP):  (70, 585),
    (AssetClass.CRYPTO, EventType.CPI):  (5, 330),
    (AssetClass.CRYPTO, EventType.FOMC): (45, 165),

    # FX = EURUSD+USDJPY tick, pooled (see RECALIBRATION_PROPOSAL.md)
    (AssetClass.FX, EventType.NFP):  (30, 450),
    (AssetClass.FX, EventType.CPI):  (30, 585),
    (AssetClass.FX, EventType.FOMC): (30, 450),

    # OIL = real WTI (IBKR CL 5-second), see RECALIBRATION_PROPOSAL.md
    (AssetClass.OIL, EventType.NFP):  (60, 630),
    (AssetClass.OIL, EventType.CPI):  (65, 615),
    (AssetClass.OIL, EventType.FOMC): (60, 960),
}

# per-asset fallback window when the specific event type was not measured
MEASURED_WAIT_ASSET_DEFAULT: dict[AssetClass, Tuple[int, int]] = {
    AssetClass.CRYPTO: (15, 420),
    AssetClass.FX: (30, 510),
    AssetClass.OIL: (60, 675),
}

# per-asset time stop (trend_lifetime p75, ALL events).
# FX p75 is censored at the 30-min horizon (trends routinely outlive the window),
# so FX keeps the legacy 1800s -- i.e. do NOT flatten FX early on time alone.
MEASURED_TIME_STOP: dict[AssetClass, int] = {
    AssetClass.CRYPTO: 1530,
    AssetClass.FX: 1800,
    AssetClass.OIL: 1650,
}


def measured_wait_window(asset: AssetClass, event_type: EventType) -> Optional[Tuple[int, int]]:
    """Return measured (min_wait, max_wait) for this asset+event, or a per-asset
    default, or None when the asset was not measured (caller keeps legacy value)."""
    hit = MEASURED_WAIT.get((asset, event_type))
    if hit is not None:
        return hit
    return MEASURED_WAIT_ASSET_DEFAULT.get(asset)


def measured_time_stop(asset: AssetClass, default: int = 1800) -> int:
    """Return measured per-asset time stop (seconds); legacy default if unmeasured."""
    return MEASURED_TIME_STOP.get(asset, default)
