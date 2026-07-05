"""Step 2 · Phase A — observe-only ("shadow") recorder for the Step-1
microstructure gates, wired against a real IB Gateway feed.

Mirrors ``v2_telemetry_shadow``: per scan it takes the Level-2 sizes + tape that
``DepthCollector`` produced and records *what the Step-1 gates WOULD decide*
(OBI fakeout verdict, CVD top divergence, near-side liquidity crash) — **without
ever touching orders or the live decision**. This lets us watch, on the paper
feed, whether ``obi`` / ``fakeout_reason`` / ``cvd_divergence`` /
``liquidity_crash`` look sane before any gate is ever enforced, and it doubles as
the self-recording that Phase C will calibrate the (still unvalidated) thresholds
against.

Default OFF. Enable with ``EVENTALPHA_MICROSTRUCTURE_SHADOW=1`` (or ``enabled=True``).
Import is fault-tolerant: if the Step-1 primitives are unavailable the observer
degrades to a no-op so it can never break the live loop.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_MS_OK = True
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from eventalpha_core.advanced.microstructure import (
        CapitalSafetyExitConfig,
        FakeoutConfig,
        cumulative_volume_delta,
        cvd_top_divergence,
        is_breakout_fakeout,
        near_side_liquidity_crash,
        order_book_imbalance,
    )
except Exception:                           # noqa: BLE001
    _MS_OK = False
    CapitalSafetyExitConfig = None
    FakeoutConfig = None
    cumulative_volume_delta = None
    cvd_top_divergence = None
    is_breakout_fakeout = None
    near_side_liquidity_crash = None
    order_book_imbalance = None


def _enabled_from_env() -> bool:
    return os.environ.get(
        "EVENTALPHA_MICROSTRUCTURE_SHADOW", "").lower() in {"1", "true", "yes", "on"}


class MicrostructureShadow:
    """Observe-only microstructure recorder. Never places, modifies, or blocks
    orders; only appends JSONL describing what the Step-1 gates would say."""

    def __init__(self, enabled: Optional[bool] = None,
                 log_path: Optional[str] = None,
                 fakeout_config: Optional["FakeoutConfig"] = None,
                 exit_config: Optional["CapitalSafetyExitConfig"] = None) -> None:
        if enabled is None:
            enabled = _enabled_from_env()
        self.enabled = bool(enabled) and _MS_OK
        self.ms_ok = _MS_OK
        self.log_path = Path(log_path) if log_path else None
        self.fakeout_config = fakeout_config or (FakeoutConfig() if _MS_OK else None)
        self.exit_config = exit_config or (CapitalSafetyExitConfig() if _MS_OK else None)
        self.n_observed = 0

    def observe(self, symbol: str, direction: str,
                bid_sizes: Optional[List[float]], ask_sizes: Optional[List[float]],
                recent_prices: Optional[List[float]] = None,
                recent_volumes: Optional[List[float]] = None,
                near_side_size_series: Optional[List[float]] = None,
                cvd_series: Optional[List[float]] = None,
                tape_source: str = "none") -> Optional[Dict[str, Any]]:
        """Run every Step-1 gate on this scan's microstructure inputs and log one
        JSONL line. Returns ``None`` (and does nothing) when disabled. Fail-safe:
        any error is swallowed so the live loop is never disturbed."""
        if not self.enabled:
            return None
        try:
            obi = order_book_imbalance(bid_sizes, ask_sizes,
                                       levels=self.fakeout_config.levels)
            fakeout, fakeout_reason = is_breakout_fakeout(
                direction, obi, self.fakeout_config)

            cvd = cvd_series
            if cvd is None and recent_prices and recent_volumes:
                cvd = cumulative_volume_delta(recent_prices, recent_volumes)
            divergent, divergence_reason = (False, "cvd_unavailable")
            if recent_prices and cvd:
                divergent, divergence_reason = cvd_top_divergence(
                    recent_prices, cvd, direction,
                    lookback=self.exit_config.cvd_divergence_lookback)

            crash, crash_reason = near_side_liquidity_crash(
                near_side_size_series or [],
                lookback=self.exit_config.bid_crash_lookback,
                drop_ratio=self.exit_config.bid_crash_drop_ratio)

            rec = {
                "stage": "microstructure_shadow",
                "ts": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "direction": direction,
                "tape_source": tape_source,
                "obi": (round(obi, 4) if obi is not None else None),
                "would_reject_fakeout": bool(fakeout),
                "fakeout_reason": fakeout_reason,
                "would_flag_cvd_divergence": bool(divergent),
                "cvd_divergence_reason": divergence_reason,
                "would_force_exit_liquidity_crash": bool(crash),
                "liquidity_crash_reason": crash_reason,
                "n_bid_levels": (len(bid_sizes) if bid_sizes else 0),
                "n_ask_levels": (len(ask_sizes) if ask_sizes else 0),
                "n_tape": (len(recent_prices) if recent_prices else 0),
                "n_near_side_hist": (len(near_side_size_series)
                                     if near_side_size_series else 0),
            }
            self.n_observed += 1
            if self.log_path:
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            return rec
        except Exception:                   # noqa: BLE001
            return None
