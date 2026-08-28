"""Regression tests for temporal integrity in intraday replay."""
from __future__ import annotations

import numpy as np

from eventalpha_intraday_study.v2_replay import event_window_features


def _path(future):
    observed = [100.0, 100.1, 100.3, 100.2, 100.5]
    prices = observed + list(future)
    return {
        "price": np.asarray(prices, dtype=float),
        "entry_idx": len(observed) - 1,
        "exit_idx": len(prices) - 1,
        "direction": 1,
        "early_bps": 50.0,
    }


def test_decision_features_ignore_everything_after_entry():
    up_future = [101.0, 102.0, 103.0, 104.0]
    crash_future = [99.0, 95.0, 90.0, 80.0]
    a = event_window_features(_path(up_future), "CRYPTO")
    b = event_window_features(_path(crash_future), "CRYPTO")
    assert a == b, (a, b)


def main() -> int:
    test_decision_features_ignore_everything_after_entry()
    print("✓ replay decision features are prefix-invariant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
