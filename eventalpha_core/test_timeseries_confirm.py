"""Offline self-check for zero-shot time-series confirmation (no torch needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eventalpha_core.advanced.timeseries_confirm import (
    ForecastResult,
    NaiveDriftForecaster,
    TimeSeriesConfirmConfig,
    build_forecaster,
    right_side_confirmation,
)


class _StubForecaster:
    """Deterministic forecaster that always drifts one way."""

    def __init__(self, up: bool):
        self.backend = "stub"
        self._up = up

    def forecast(self, context, horizon, n_samples):
        last = float(context[-1])
        step = 1.02 if self._up else 0.98
        paths = []
        for _ in range(n_samples):
            price = last
            path = []
            for _ in range(horizon):
                price *= step
                path.append(price)
            paths.append(path)
        return ForecastResult(samples=paths, backend=self.backend)


def test_naive_forecaster_shape_and_determinism():
    ctx = [100.0 + i * 0.1 for i in range(64)]
    f1 = NaiveDriftForecaster(seed=7).forecast(ctx, horizon=5, n_samples=32)
    f2 = NaiveDriftForecaster(seed=7).forecast(ctx, horizon=5, n_samples=32)
    assert len(f1.samples) == 32 and all(len(p) == 5 for p in f1.samples)
    assert f1.samples == f2.samples  # same seed -> reproducible
    assert f1.median_final is not None


def test_confirm_long_when_model_up():
    prices = [100.0 + i * 0.05 for i in range(64)]
    ok, reason, meta = right_side_confirmation(
        prices, "long", _StubForecaster(up=True))
    assert ok is True and "confirm_long" in reason
    assert meta["prob_dir"] == 1.0 and meta["backend"] == "stub"


def test_veto_long_when_model_down():
    prices = [100.0 + i * 0.05 for i in range(64)]
    ok, reason, _ = right_side_confirmation(
        prices, "long", _StubForecaster(up=False))
    assert ok is False and "veto_long" in reason


def test_short_confirm_when_model_down():
    prices = [100.0 - i * 0.05 for i in range(64)]
    ok, reason, _ = right_side_confirmation(
        prices, "short", _StubForecaster(up=False))
    assert ok is True and "confirm_short" in reason


def test_insufficient_history_declines():
    ok, reason, _ = right_side_confirmation(
        [100.0, 100.1, 100.2], "long", _StubForecaster(up=True))
    assert ok is False and reason == "insufficient_history"


def test_forecast_error_degrades():
    class _Boom:
        backend = "boom"

        def forecast(self, *a, **k):
            raise RuntimeError("model exploded")

    ok, reason, meta = right_side_confirmation(
        [100.0 + i for i in range(64)], "long", _Boom())
    assert ok is False and reason == "forecast_unavailable"
    assert "error" in meta


def test_build_forecaster_falls_back_to_naive():
    # torch/chronos almost certainly absent in CI -> must degrade, never raise.
    f = build_forecaster("auto")
    assert hasattr(f, "forecast")
    out = f.forecast([100.0 + i * 0.1 for i in range(32)], 5, 16)
    assert out.backend in ("naive", "chronos")


if __name__ == "__main__":
    test_naive_forecaster_shape_and_determinism()
    test_confirm_long_when_model_up()
    test_veto_long_when_model_down()
    test_short_confirm_when_model_down()
    test_insufficient_history_declines()
    test_forecast_error_degrades()
    test_build_forecaster_falls_back_to_naive()
    print("ALL TIMESERIES-CONFIRM TESTS PASSED")
