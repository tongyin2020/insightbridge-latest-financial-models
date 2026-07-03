"""Regression gate for validation metrics.

Engineering standard (Developer Edition spec): "Replay every code change against
the 2024-2025 historical validation dataset before deployment" and "Regression
tests comparing previous validation metrics."

This module holds the committed baseline of the headline, data-derived metrics
and a direction-aware comparator. The workflow on every change:

    1. re-run the study/replay on the 2024-2025 dataset,
    2. collect the same metric keys,
    3. `compare_metrics(BASELINE, current, SPECS)` -> must return [] (no adverse
       move beyond tolerance) or the change is a regression.

The comparator itself is pure and data-free, so a unit test can guard the gate
logic without shipping the multi-GB tick dataset (see test_metrics_regression.py).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping

from .config import reports_dir


@dataclass(frozen=True)
class MetricSpec:
    """How to judge a metric. `higher_is_better` sets the adverse direction; a
    move is a regression only if it is adverse by more than max(abs_tol, base*rel_tol)."""

    higher_is_better: bool = True
    abs_tol: float = 0.0
    rel_tol: float = 0.0


DEFAULT_SPEC = MetricSpec(higher_is_better=True, abs_tol=0.0, rel_tol=0.10)


def compare_metrics(
    baseline: Mapping[str, float],
    current: Mapping[str, float],
    specs: Mapping[str, MetricSpec] | None = None,
    default_spec: MetricSpec = DEFAULT_SPEC,
) -> List[str]:
    """Return a list of human-readable regression messages. Empty list == pass."""
    specs = specs or {}
    problems: List[str] = []
    for key, base_val in baseline.items():
        if key not in current:
            problems.append(f"{key}: missing from current metrics")
            continue
        spec = specs.get(key, default_spec)
        cur = float(current[key])
        allowed = max(spec.abs_tol, abs(base_val) * spec.rel_tol)
        if spec.higher_is_better:
            if cur < base_val - allowed:
                problems.append(
                    f"{key}: regressed {base_val:.4g} -> {cur:.4g} "
                    f"(drop {base_val - cur:.4g} > allowed {allowed:.4g})"
                )
        else:
            if cur > base_val + allowed:
                problems.append(
                    f"{key}: regressed {base_val:.4g} -> {cur:.4g} "
                    f"(rise {cur - base_val:.4g} > allowed {allowed:.4g})"
                )
    return problems


# --- committed baseline ------------------------------------------------------
# Headline metrics from the 2024-2025 validation (see FINAL_VALIDATION_REPORT.md
# and IMPACT_SCALED_WINDOWS.md). trend_capture: fraction of the trend still alive
# at entry under the NEW measured windows (higher is better). scaled_* : the
# impact-selectivity ("SCALED") policy from backtest_pnl.py on real per-event
# paths. These are the numbers a change must not silently break.
BASELINE_PATH = reports_dir() / "metrics_baseline.json"

BASELINE: Dict[str, float] = {
    # trend still alive at entry under the NEW measured windows (FINAL report)
    "trend_capture_crypto": 0.94,
    "trend_capture_fx": 0.95,
    "trend_capture_oil": 0.87,
    # SCALED selectivity policy on real per-event paths (backtest_pnl.py):
    # its value is a quality/risk filter -> higher win-rate on far fewer trades.
    "scaled_win_rate_crypto": 60.9,
    "scaled_win_rate_fx": 65.8,
    "scaled_win_rate_oil": 62.5,
}

# Sensible per-metric tolerances. Trend capture is a stable ratio -> tight;
# win-rate on a small selected subset is noisier -> a few points of slack.
SPECS: Dict[str, MetricSpec] = {
    "trend_capture_crypto": MetricSpec(True, abs_tol=0.03),
    "trend_capture_fx": MetricSpec(True, abs_tol=0.03),
    "trend_capture_oil": MetricSpec(True, abs_tol=0.03),
    "scaled_win_rate_crypto": MetricSpec(True, abs_tol=6.0),
    "scaled_win_rate_fx": MetricSpec(True, abs_tol=6.0),
    "scaled_win_rate_oil": MetricSpec(True, abs_tol=8.0),
}


def scaled_win_rates_from_backtest_csv(path: Path | None = None) -> Dict[str, float]:
    """Map a backtest_pnl.csv (the real-data replay output) onto the baseline's
    `scaled_win_rate_*` keys, so `compare_metrics(load_baseline(), current, SPECS)`
    runs directly after a replay. Import pandas lazily (only needed on the box
    that actually has the dataset)."""
    import pandas as pd

    csv = path or (reports_dir() / "backtest_pnl.csv")
    df = pd.read_csv(csv)
    scaled = df[df["policy"] == "SCALED"]
    out: Dict[str, float] = {}
    for _, r in scaled.iterrows():
        out[f"scaled_win_rate_{str(r['asset']).lower()}"] = float(r["win_rate_%"])
    return out


def load_baseline() -> Dict[str, float]:
    """Load the on-disk baseline if present, else the in-code BASELINE."""
    if BASELINE_PATH.exists():
        return {k: float(v) for k, v in json.loads(BASELINE_PATH.read_text()).items()}
    return dict(BASELINE)


def save_baseline(metrics: Mapping[str, float], path: Path | None = None) -> Path:
    """Persist a metrics snapshot as the new baseline (explicit, human-approved)."""
    p = path or BASELINE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({k: float(v) for k, v in metrics.items()}, indent=2))
    return p
