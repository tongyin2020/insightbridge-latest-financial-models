"""Read-only calibration workbench.

This module does not send orders, does not modify configuration and does not
issue any network call.  It produces a JSON-serialisable proposal describing
in-sample / out-of-sample metrics for a parameter grid on user-supplied
samples.  Every proposal is advisory only and explicitly awaits human review;
the workbench never writes to a live configuration file.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence


STATUS_PROPOSED = "PROPOSED"
STATUS_REJECTED_INSUFFICIENT_SAMPLE = "REJECTED_INSUFFICIENT_SAMPLE"
STATUS_REJECTED_OVERFIT = "REJECTED_OVERFIT"
STATUS_REJECTED_SIGN_FLIP = "REJECTED_SIGN_FLIP"

MIN_IS_SAMPLES = 30
MIN_OOS_SAMPLES = 15
MAX_IS_OOS_SHARPE_RATIO = 3.0


ScoreFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class SplitResult:
    in_sample: List[Dict[str, Any]]
    out_of_sample: List[Dict[str, Any]]


def _require_iso_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("ts must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("ts must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _sort_samples(samples: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    ordered: List[Dict[str, Any]] = []
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise ValueError("each sample must be a mapping")
        # Copy defensively and validate mandatory fields.
        row = {
            "ts": sample["ts"],
            "return_bps": float(sample["return_bps"]),
            "algo_version": str(sample["algo_version"]),
            "symbol": str(sample["symbol"]),
        }
        _require_iso_utc(row["ts"])
        ordered.append(row)
    ordered.sort(key=lambda r: _require_iso_utc(r["ts"]))
    return ordered


def _split_70_30(samples: Sequence[Mapping[str, Any]]) -> SplitResult:
    n = len(samples)
    if n == 0:
        return SplitResult([], [])
    cut = int(n * 0.7)
    # Guarantee both sides have at least one row when possible so callers can
    # still see the "insufficient sample" rejection rather than a crash.
    if cut == n and n > 1:
        cut = n - 1
    return SplitResult(list(samples[:cut]), list(samples[cut:]))


def _algo_versions(samples: Sequence[Mapping[str, Any]]) -> List[str]:
    seen: List[str] = []
    for row in samples:
        version = str(row.get("algo_version", ""))
        if version and version not in seen:
            seen.append(version)
    return seen


def _sample_window(samples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not samples:
        return {"start_utc": None, "end_utc": None, "count": 0}
    return {
        "start_utc": samples[0]["ts"],
        "end_utc": samples[-1]["ts"],
        "count": len(samples),
    }


def _grid_iter(param_grid: Mapping[str, Sequence[Any]]) -> Iterable[Dict[str, Any]]:
    keys = sorted(str(k) for k in param_grid.keys())
    if not keys:
        yield {}
        return
    indices = [0] * len(keys)
    sizes = [len(param_grid[k]) for k in keys]
    if any(s <= 0 for s in sizes):
        return
    while True:
        yield {k: list(param_grid[k])[indices[i]] for i, k in enumerate(keys)}
        for i in range(len(keys) - 1, -1, -1):
            indices[i] += 1
            if indices[i] < sizes[i]:
                break
            indices[i] = 0
            if i == 0:
                return


def _coerce_score(raw: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("score_fn must return a mapping")
    try:
        mean_bps = float(raw["mean_bps"])
        sharpe = float(raw["sharpe"])
        n = int(raw["n"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"score_fn returned malformed metrics: {exc}") from exc
    if not math.isfinite(mean_bps) or not math.isfinite(sharpe):
        raise ValueError("score_fn metrics must be finite")
    if n < 0:
        raise ValueError("score_fn returned negative sample count")
    return {"mean_bps": mean_bps, "sharpe": sharpe, "n": n}


def _classify(is_metrics: Mapping[str, Any],
              oos_metrics: Mapping[str, Any]) -> str:
    if (int(is_metrics["n"]) < MIN_IS_SAMPLES
            or int(oos_metrics["n"]) < MIN_OOS_SAMPLES):
        return STATUS_REJECTED_INSUFFICIENT_SAMPLE
    is_mean = float(is_metrics["mean_bps"])
    oos_mean = float(oos_metrics["mean_bps"])
    is_sharpe = float(is_metrics["sharpe"])
    oos_sharpe = float(oos_metrics["sharpe"])
    # Sign flip check: mean_bps must be same sign on IS and OOS (both non-zero).
    if is_mean == 0 or oos_mean == 0 or (is_mean * oos_mean) < 0:
        return STATUS_REJECTED_SIGN_FLIP
    if is_sharpe <= 0 or oos_sharpe <= 0:
        return STATUS_REJECTED_OVERFIT
    ratio = abs(is_sharpe / max(oos_sharpe, 1e-9))
    if ratio > MAX_IS_OOS_SHARPE_RATIO:
        return STATUS_REJECTED_OVERFIT
    return STATUS_PROPOSED


def _proposal_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class CalibrationWorkbench:
    """Deterministic IS/OOS grid evaluator with strict overfit gates."""

    is_advisory_only = True
    applies_to_live = False

    def __init__(self) -> None:
        # No state: instantiate cheaply and reuse without mutation.
        pass

    def evaluate(
        self,
        samples: Sequence[Mapping[str, Any]],
        param_grid: Mapping[str, Sequence[Any]],
        score_fn: ScoreFn,
        *,
        algo_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        ordered = _sort_samples(samples)
        if algo_version is None:
            versions = _algo_versions(ordered)
            if len(versions) == 1:
                algo_version = versions[0]
            else:
                algo_version = "MULTI_VERSION" if versions else "UNSPECIFIED"
        split = _split_70_30(ordered)
        best_status = STATUS_REJECTED_INSUFFICIENT_SAMPLE
        best_params: Optional[Dict[str, Any]] = None
        best_is: Dict[str, Any] = {"mean_bps": 0.0, "sharpe": 0.0, "n": 0}
        best_oos: Dict[str, Any] = {"mean_bps": 0.0, "sharpe": 0.0, "n": 0}
        best_score = -math.inf
        for params in _grid_iter(param_grid):
            is_metrics = _coerce_score(score_fn(split.in_sample, params))
            oos_metrics = _coerce_score(score_fn(split.out_of_sample, params))
            status = _classify(is_metrics, oos_metrics)
            score = float(oos_metrics["sharpe"]) if status == STATUS_PROPOSED else -math.inf
            if score > best_score:
                best_score = score
                best_status = status
                best_params = dict(params)
                best_is = dict(is_metrics)
                best_oos = dict(oos_metrics)
            elif best_status != STATUS_PROPOSED and status != STATUS_PROPOSED:
                # Keep first observed rejection reason if no proposal ever wins.
                best_status = best_status if best_status != STATUS_REJECTED_INSUFFICIENT_SAMPLE else status
                best_params = best_params if best_params is not None else dict(params)
                best_is = best_is if best_is["n"] else dict(is_metrics)
                best_oos = best_oos if best_oos["n"] else dict(oos_metrics)
        recommended = best_params if best_status == STATUS_PROPOSED else None
        generated_at = datetime.now(timezone.utc).isoformat()
        digest_payload = {
            "algo_version": algo_version,
            "sample_window": _sample_window(ordered),
            "is_metrics": best_is,
            "oos_metrics": best_oos,
            "recommended_params": recommended,
            "status": best_status,
        }
        proposal_id = _proposal_id(digest_payload)
        return {
            "proposal_id": proposal_id,
            "algo_version": algo_version,
            "generated_at_utc": generated_at,
            "sample_window": _sample_window(ordered),
            "is_metrics": best_is,
            "oos_metrics": best_oos,
            "recommended_params": recommended,
            "status": best_status,
            "approval": {
                "state": "AWAITING_HUMAN_REVIEW",
                "approved_by": None,
                "approved_at_utc": None,
            },
            "is_advisory_only": True,
            "applies_to_live": False,
        }


def write_proposal(proposal: Mapping[str, Any], out_dir: str | Path) -> Path:
    """Atomically write a proposal to ``out_dir/proposals/{proposal_id}.json``.

    Existing files are never overwritten so the on-disk history stays
    immutable.  Callers must confirm the returned path is the new file.
    """
    proposal_id = str(proposal.get("proposal_id", "")).strip()
    if not proposal_id:
        raise ValueError("proposal_id is required")
    base = Path(out_dir) / "proposals"
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"{proposal_id}.json"
    if target.exists():
        return target
    tmp = base / f".{proposal_id}.json.tmp"
    tmp.write_text(json.dumps(proposal, ensure_ascii=False, sort_keys=True,
                              indent=2, default=str),
                   encoding="utf-8")
    os.replace(tmp, target)
    return target
