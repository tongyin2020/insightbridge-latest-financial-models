"""Data-free unit test for the validation-metrics regression gate.

Guards the comparator logic (direction awareness, tolerances, missing keys) so
the "regression tests comparing previous validation metrics" standard is enforced
without shipping the multi-GB tick dataset. The full replay populates real
`current` metrics on the research box/Mac; here we prove the gate catches
regressions and tolerates noise.

Run: python3 eventalpha_intraday_study/test_metrics_regression.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eventalpha_intraday_study.metrics_baseline import MetricSpec, compare_metrics


BASE = {"win_rate": 60.0, "avg_pnl_bps": 40.0, "max_drawdown": 90.0}
SPECS = {
    "win_rate": MetricSpec(higher_is_better=True, abs_tol=2.0),
    "avg_pnl_bps": MetricSpec(higher_is_better=True, rel_tol=0.10),
    "max_drawdown": MetricSpec(higher_is_better=False, abs_tol=5.0),  # lower is better
}


def test_identical_passes():
    assert compare_metrics(BASE, dict(BASE), SPECS) == []
    print("✓ identical metrics -> no regression")


def test_within_tolerance_passes():
    cur = {"win_rate": 58.5, "avg_pnl_bps": 37.0, "max_drawdown": 94.0}
    assert compare_metrics(BASE, cur, SPECS) == [], compare_metrics(BASE, cur, SPECS)
    print("✓ small adverse noise within tolerance -> no regression")


def test_win_rate_drop_flagged():
    cur = {"win_rate": 55.0, "avg_pnl_bps": 40.0, "max_drawdown": 90.0}
    out = compare_metrics(BASE, cur, SPECS)
    assert any("win_rate" in m for m in out), out
    print("✓ win_rate drop beyond tolerance -> flagged")


def test_drawdown_rise_flagged():
    cur = {"win_rate": 60.0, "avg_pnl_bps": 40.0, "max_drawdown": 110.0}
    out = compare_metrics(BASE, cur, SPECS)
    assert any("max_drawdown" in m for m in out), out
    print("✓ drawdown rise beyond tolerance (lower-is-better) -> flagged")


def test_improvement_not_flagged():
    cur = {"win_rate": 70.0, "avg_pnl_bps": 60.0, "max_drawdown": 60.0}
    assert compare_metrics(BASE, cur, SPECS) == []
    print("✓ across-the-board improvement -> no regression")


def test_missing_metric_flagged():
    cur = {"win_rate": 60.0, "avg_pnl_bps": 40.0}
    out = compare_metrics(BASE, cur, SPECS)
    assert any("max_drawdown" in m and "missing" in m for m in out), out
    print("✓ missing metric -> flagged")


def main() -> int:
    test_identical_passes()
    test_within_tolerance_passes()
    test_win_rate_drop_flagged()
    test_drawdown_rise_flagged()
    test_improvement_not_flagged()
    test_missing_metric_flagged()
    print("\n✅ metrics regression gate self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
