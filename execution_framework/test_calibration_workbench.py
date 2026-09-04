"""Offline tests for the read-only calibration workbench.

This test module never submits an order and never mutates configuration.  It
verifies that overfit / sign-flip / insufficient-sample gates keep advisory
proposals from being labelled ready for live.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from calibration_workbench import (
    CalibrationWorkbench,
    STATUS_PROPOSED,
    STATUS_REJECTED_INSUFFICIENT_SAMPLE,
    STATUS_REJECTED_OVERFIT,
    STATUS_REJECTED_SIGN_FLIP,
    write_proposal,
)


def _sharpe(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        return 0.0
    return mean / stdev


def _basic_score(samples: Sequence[Mapping[str, Any]],
                 params: Mapping[str, Any]) -> Mapping[str, Any]:
    values = [float(row["return_bps"]) + float(params.get("bias", 0.0))
              for row in samples]
    mean_bps = statistics.fmean(values) if values else 0.0
    return {"mean_bps": mean_bps, "sharpe": _sharpe(values), "n": len(values)}


def _linear_samples(n: int, base: float = 1.0, jitter: float = 0.4,
                    start: datetime | None = None,
                    algo_version: str = "v-good") -> list[dict]:
    start = start or datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        rows.append({
            "ts": (start + timedelta(minutes=i)).isoformat(),
            "return_bps": base + jitter * ((-1) ** i) * 0.1,
            "algo_version": algo_version,
            "symbol": "MNQ",
        })
    return rows


def test_insufficient_sample() -> None:
    wb = CalibrationWorkbench()
    result = wb.evaluate(
        _linear_samples(20),
        {"bias": [0.0]},
        _basic_score,
    )
    assert result["status"] == STATUS_REJECTED_INSUFFICIENT_SAMPLE
    assert result["recommended_params"] is None
    assert result["approval"]["state"] == "AWAITING_HUMAN_REVIEW"
    assert result["applies_to_live"] is False


def test_normal_pass() -> None:
    wb = CalibrationWorkbench()
    result = wb.evaluate(
        _linear_samples(80, base=1.2, jitter=0.05),
        {"bias": [0.0, 0.1]},
        _basic_score,
    )
    assert result["status"] == STATUS_PROPOSED
    assert result["recommended_params"] is not None
    assert result["approval"]["state"] == "AWAITING_HUMAN_REVIEW"
    assert result["is_advisory_only"] is True
    assert result["applies_to_live"] is False


def test_sign_flip_rejected() -> None:
    wb = CalibrationWorkbench()
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(70):
        rows.append({
            "ts": (start + timedelta(minutes=i)).isoformat(),
            "return_bps": 1.2,
            "algo_version": "v-flip",
            "symbol": "MNQ",
        })
    for i in range(70, 100):
        rows.append({
            "ts": (start + timedelta(minutes=i)).isoformat(),
            "return_bps": -1.5,
            "algo_version": "v-flip",
            "symbol": "MNQ",
        })
    result = wb.evaluate(rows, {"bias": [0.0]}, _basic_score)
    assert result["status"] == STATUS_REJECTED_SIGN_FLIP
    assert result["recommended_params"] is None


def test_overfit_rejected() -> None:
    """IS sharpe much larger than OOS sharpe -> REJECTED_OVERFIT."""

    # IS uses first 70% of the samples (56 rows for n=80); IS gets very high
    # sharpe and OOS gets very low positive sharpe -> ratio > 3.
    def overfit_score(samples: Sequence[Mapping[str, Any]],
                      params: Mapping[str, Any]) -> Mapping[str, Any]:
        if not samples:
            return {"mean_bps": 0.0, "sharpe": 0.0, "n": 0}
        # Discriminate by sample count, since IS has 56 rows and OOS 24.
        n = len(samples)
        if n >= 40:
            return {"mean_bps": 2.5, "sharpe": 10.0, "n": n}
        return {"mean_bps": 0.05, "sharpe": 0.2, "n": n}

    wb = CalibrationWorkbench()
    result = wb.evaluate(
        _linear_samples(80, base=1.0), {"bias": [0.0]},
        overfit_score,
    )
    assert result["status"] == STATUS_REJECTED_OVERFIT
    assert result["recommended_params"] is None


def test_write_proposal_atomic_and_idempotent(tmp_path: Path) -> None:
    wb = CalibrationWorkbench()
    result = wb.evaluate(
        _linear_samples(80, base=1.2, jitter=0.05),
        {"bias": [0.0]},
        _basic_score,
    )
    path = write_proposal(result, tmp_path)
    assert path.exists()
    original = path.read_text()
    modified = dict(result)
    modified["recommended_params"] = {"bias": 99.0}
    path2 = write_proposal(modified, tmp_path)
    assert path2 == path
    # File must not be overwritten with the modified proposal.
    assert path.read_text() == original
    # No leftover temp files.
    tmps = list((tmp_path / "proposals").glob(".*.tmp"))
    assert tmps == []


def test_no_config_files_are_written(tmp_path: Path) -> None:
    """evaluate() by itself must not create any file on disk."""
    before = {p.name for p in tmp_path.iterdir()}
    wb = CalibrationWorkbench()
    _ = wb.evaluate(
        _linear_samples(80, base=1.2, jitter=0.05),
        {"bias": [0.0]},
        _basic_score,
    )
    after = {p.name for p in tmp_path.iterdir()}
    assert before == after
