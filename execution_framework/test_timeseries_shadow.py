"""Offline self-check for the zero-shot time-series shadow (no torch needed)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from timeseries_shadow import TimeSeriesShadow


class _StubForecaster:
    backend = "stub"

    def forecast(self, context, horizon, n_samples):
        from eventalpha_core.advanced.timeseries_confirm import ForecastResult
        last = float(context[-1])
        paths = [[last * (1.01 ** (i + 1)) for i in range(horizon)]
                 for _ in range(n_samples)]
        return ForecastResult(samples=paths, backend=self.backend)


def _prices():
    return [100.0 + i * 0.05 for i in range(64)]


def test_disabled_writes_nothing(tmp_path):
    log = tmp_path / "ts.log"
    sh = TimeSeriesShadow(enabled=False, log_path=str(log))
    assert sh.observe("BTC", "long", _prices()) is None
    assert not log.exists()


def test_enabled_records_verdict(tmp_path):
    log = tmp_path / "ts.log"
    sh = TimeSeriesShadow(enabled=True, log_path=str(log),
                          forecaster=_StubForecaster())
    rec = sh.observe("BTC", "long", _prices(), source="bar_close")
    assert rec is not None
    assert rec["stage"] == "timeseries_shadow"
    assert rec["would_confirm"] is True
    assert rec["backend"] == "stub"
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["symbol"] == "BTC" and obj["direction"] == "long"
    assert obj["prob_dir"] == 1.0


def test_bad_input_never_raises(tmp_path):
    log = tmp_path / "ts.log"
    sh = TimeSeriesShadow(enabled=True, log_path=str(log),
                          forecaster=_StubForecaster())
    # too-short history -> declines gracefully, still logs a line, never raises
    rec = sh.observe("BTC", "long", [100.0, 100.1])
    assert rec is not None and rec["would_confirm"] is False


def test_auto_backend_naive_fallback(tmp_path):
    log = tmp_path / "ts.log"
    sh = TimeSeriesShadow(enabled=True, log_path=str(log))  # builds real forecaster
    rec = sh.observe("BTC", "long", _prices())
    assert rec is not None
    assert rec["backend"] in ("naive", "chronos")


if __name__ == "__main__":
    import tempfile

    for fn in (test_disabled_writes_nothing, test_enabled_records_verdict,
               test_bad_input_never_raises, test_auto_backend_naive_fallback):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("ALL TIMESERIES-SHADOW TESTS PASSED")
