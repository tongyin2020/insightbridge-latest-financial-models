"""Measured per-asset event timing parameters.

These numbers are NOT guesses. They are measured by the `eventalpha_intraday_study`
package from real 2024-2025 intraday data (63 NFP/CPI/FOMC events per asset):
  - CRYPTO: BTCUSDT tick data (Binance public archive)
  - FX:     EURUSD 1-minute bars (HistData) as the liquid-major proxy
  - OIL:    Brent (BCOUSD) 1-minute bars (HistData) as the WTI proxy

Mapping from the event study to these parameters:
  min_wait_seconds  ~ washout p50      (do not enter until the fake-impulse clears)
  max_wait_seconds  ~ time_to_peak p50 (must be positioned before the move tops)
  time_stop_seconds ~ trend_lifetime p75 (typical trend is spent by here)

FX/OIL reaction/washout are at 1-minute resolution (a known limitation; a tick
refresh via JForex is planned). Values are rounded. RATES and INDEX are not yet
measured and intentionally omitted so they fall back to the legacy windows.

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

    (AssetClass.FX, EventType.NFP):  (30, 660),
    (AssetClass.FX, EventType.CPI):  (180, 300),
    (AssetClass.FX, EventType.FOMC): (10, 600),

    (AssetClass.OIL, EventType.NFP):  (120, 780),
    (AssetClass.OIL, EventType.CPI):  (180, 420),
    (AssetClass.OIL, EventType.FOMC): (120, 420),
}

# per-asset fallback window when the specific event type was not measured
MEASURED_WAIT_ASSET_DEFAULT: dict[AssetClass, Tuple[int, int]] = {
    AssetClass.CRYPTO: (15, 420),
    AssetClass.FX: (60, 600),
    AssetClass.OIL: (120, 540),
}

# per-asset time stop (trend_lifetime p75, ALL events)
MEASURED_TIME_STOP: dict[AssetClass, int] = {
    AssetClass.CRYPTO: 1530,
    AssetClass.FX: 1560,
    AssetClass.OIL: 1560,
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
