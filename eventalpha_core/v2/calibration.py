"""Loader for the per-(asset, bucket) EV calibration table.

The table is produced by ``eventalpha_intraday_study.v2_calibration`` from real
2024-2025 net-of-cost replay and shipped next to this module as
``calibration_table.json``:

    {"FX": {"small": {"n": 21, "p_win": 0.52, "avg_win_bps": 9.1,
                       "avg_loss_bps": 7.4, "mean_gross_bps": 1.2}, ...}, ...}

Payoff is fit on GROSS outcomes; the EV engine subtracts the modelled cost.
Loading is best-effort: a missing/corrupt file returns ``None`` and the EV engine
falls back to its heuristic, so this never breaks a caller.
"""
from __future__ import annotations

import json
import os
from typing import Optional

_DEFAULT = os.path.join(os.path.dirname(__file__), "calibration_table.json")
_CACHE: dict = {}


def load_calibration(path: Optional[str] = None) -> Optional[dict]:
    p = path or os.environ.get("EVENTALPHA_V2_CALIBRATION", _DEFAULT)
    if p in _CACHE:
        return _CACHE[p]
    table = None
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        table = data.get("table", data) if isinstance(data, dict) else None
    except (OSError, ValueError):
        table = None
    _CACHE[p] = table
    return table
