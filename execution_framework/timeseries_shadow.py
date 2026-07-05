"""Step 2 · Phase D — observe-only ("shadow") recorder for zero-shot time-series
confirmation.

Mirrors ``MicrostructureShadow``: per scan it feeds recent price history to a
pretrained zero-shot forecaster (Chronos if installed, else a labelled naive
baseline) and records *whether the model WOULD confirm or veto* the signal
direction — **without ever touching orders or the live decision**. This lets us
watch, on the paper feed, whether the time-series check adds edge before it is
ever enforced, and produces the log Phase C will calibrate its thresholds against.

Default OFF. Enable with ``EVENTALPHA_TIMESERIES_SHADOW=1`` (or ``enabled=True``).
Import is fault-tolerant and the heavy model is lazy-loaded: if the core module or
torch/chronos is unavailable the observer degrades to a no-op / naive baseline so
it can never break the live loop.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_TS_OK = True
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from eventalpha_core.advanced.timeseries_confirm import (
        TimeSeriesConfirmConfig,
        build_forecaster,
        right_side_confirmation,
    )
except Exception:                               # noqa: BLE001
    _TS_OK = False
    TimeSeriesConfirmConfig = None
    build_forecaster = None
    right_side_confirmation = None


def _enabled_from_env() -> bool:
    return os.environ.get(
        "EVENTALPHA_TIMESERIES_SHADOW", "").lower() in {"1", "true", "yes", "on"}


class TimeSeriesShadow:
    """Observe-only zero-shot time-series recorder. Never places, modifies, or
    blocks orders; only appends JSONL describing what the model would say."""

    def __init__(self, enabled: Optional[bool] = None,
                 log_path: Optional[str] = None,
                 config: Optional["TimeSeriesConfirmConfig"] = None,
                 backend: str = "auto",
                 forecaster: Optional[Any] = None) -> None:
        if enabled is None:
            enabled = _enabled_from_env()
        self.enabled = bool(enabled) and _TS_OK
        self.ts_ok = _TS_OK
        self.log_path = Path(log_path) if log_path else None
        self.config = config or (TimeSeriesConfirmConfig() if _TS_OK else None)
        self.backend = backend
        self._forecaster = forecaster          # lazily built on first use if None
        self.n_observed = 0

    def _get_forecaster(self):
        if self._forecaster is None and _TS_OK:
            self._forecaster = build_forecaster(self.backend)
        return self._forecaster

    def observe(self, symbol: str, direction: str,
                recent_prices: Optional[List[float]],
                source: str = "bar_close") -> Optional[Dict[str, Any]]:
        """Run the zero-shot confirmation on this scan's price history and log one
        JSONL line. Returns ``None`` (and does nothing) when disabled. Fail-safe:
        any error is swallowed so the live loop is never disturbed."""
        if not self.enabled:
            return None
        try:
            forecaster = self._get_forecaster()
            if forecaster is None:
                return None
            confirm, reason, meta = right_side_confirmation(
                recent_prices or [], direction, forecaster, self.config)
            rec = {
                "stage": "timeseries_shadow",
                "ts": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "direction": direction,
                "source": source,
                "backend": meta.get("backend"),
                "would_confirm": bool(confirm),
                "confirm_reason": reason,
                "prob_dir": meta.get("prob_dir"),
                "expected_move_frac": meta.get("expected_move_frac"),
                "horizon": meta.get("horizon"),
                "n_context": meta.get("n_context"),
                "n_samples": meta.get("n_samples"),
                "n_prices": (len(recent_prices) if recent_prices else 0),
            }
            self.n_observed += 1
            if self.log_path:
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            return rec
        except Exception:                       # noqa: BLE001
            return None
