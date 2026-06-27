#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import pstdev
from typing import Any

from dashboard_schema import QuantumRunRecord


PROJECT_BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DEFAULT_RUNS_DIR = PROJECT_BASE / "reports" / "quantum_runs"
DEFAULT_OUTPUT = PROJECT_BASE / "reports" / "quantum_research" / "dashboard_runs.csv"
DEFAULT_SUMMARY = PROJECT_BASE / "reports" / "quantum_research" / "dashboard_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build dashboard-ready CSV from EventAlpha quantum run files.")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY))
    return parser.parse_args()


def exact_objective_value(baseline: dict[str, Any] | None) -> float:
    baseline = baseline or {}
    for key in ("objective", "score"):
        value = baseline.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def infer_asset_class(problem: str, asset_filter: Any, baseline: dict[str, Any], best_solution: dict[str, Any]) -> str:
    if asset_filter:
        return str(asset_filter)
    if problem == "asset_subset_selection":
        selected = best_solution.get("selected") or baseline.get("selected") or baseline.get("selected_assets") or []
        return "+".join(map(str, selected)) if selected else "multi_asset"
    if problem == "risk_tier_allocation":
        allocation = best_solution.get("allocation") or baseline.get("allocation") or {}
        if isinstance(allocation, dict) and allocation:
            return "+".join(sorted(allocation.keys()))
    if problem == "wait_bucket_optimization":
        return str(best_solution.get("asset") or baseline.get("asset") or "single_asset")
    return "unknown"


def infer_run_type(path: Path, payload: dict[str, Any]) -> str:
    mode = ((payload.get("result") or {}).get("mode") or "").strip()
    if mode:
        return mode
    name = path.name.lower()
    if "_ibm_" in name:
        return "ibm"
    if "_local_" in name:
        return "local"
    return "unknown"


def infer_status(payload: dict[str, Any]) -> str:
    result = payload.get("result") or {}
    task_count = int(result.get("task_count") or 0)
    best_task = result.get("best_task") or {}
    if task_count and best_task:
        return "complete"
    return "partial"


def build_record(path: Path) -> QuantumRunRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    problem = str(payload.get("problem") or "")
    result = payload.get("result") or {}
    best_task = result.get("best_task") or {}
    best_run = best_task.get("best_run") or {}
    best_solution = best_run.get("best_sampled_solution") or {}
    baseline = payload.get("baseline_exact") or {}
    exact_obj = exact_objective_value(baseline)
    objective = float(best_solution.get("objective") or 0.0)
    delta = objective - exact_obj
    all_runs = best_task.get("all_runs_top3") or []
    objective_samples = []
    for row in all_runs:
        best = (row or {}).get("best_sampled_solution") or {}
        if isinstance(best.get("objective"), (int, float)):
            objective_samples.append(float(best["objective"]))
    repeated_std = pstdev(objective_samples) if len(objective_samples) >= 2 else 0.0
    return QuantumRunRecord(
        run_type=infer_run_type(path, payload),
        event_type=str(payload.get("event_type") or ""),
        asset_class=infer_asset_class(problem, payload.get("asset_filter"), baseline, best_solution),
        preset="quick" if "quick" in path.name else "default",
        shots=int(best_solution.get("shots") or 0),
        grid_points=int(best_task.get("grid_size") or 0),
        objective=objective,
        exact_objective=exact_obj,
        delta_vs_exact=delta,
        status=infer_status(payload),
        latency_ms=0.0,
        repeated_run_std=round(repeated_std, 6),
        bitstring=str(best_solution.get("bitstring") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        source_file=str(path),
        problem=problem,
        recommendation="match" if math.isclose(delta, 0.0, abs_tol=1e-9) else ("worse" if delta < 0 else "better"),
    )


def main() -> int:
    args = parse_args()
    runs_dir = Path(args.runs_dir).expanduser()
    output = Path(args.output).expanduser()
    summary_output = Path(args.summary_output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)

    records = [build_record(path) for path in sorted(runs_dir.glob("*.json"))]
    fieldnames = list(QuantumRunRecord.__dataclass_fields__.keys())
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_dict())

    by_problem: dict[str, dict[str, Any]] = {}
    for record in records:
        bucket = by_problem.setdefault(
            record.problem,
            {"count": 0, "avg_delta": 0.0, "exact_match_count": 0, "modes": {}},
        )
        bucket["count"] += 1
        bucket["avg_delta"] += record.delta_vs_exact
        if math.isclose(record.delta_vs_exact, 0.0, abs_tol=1e-9):
            bucket["exact_match_count"] += 1
        bucket["modes"][record.run_type] = bucket["modes"].get(record.run_type, 0) + 1
    for bucket in by_problem.values():
        count = max(1, bucket["count"])
        bucket["avg_delta"] = round(bucket["avg_delta"] / count, 6)

    summary = {
        "record_count": len(records),
        "runs_dir": str(runs_dir),
        "output_csv": str(output),
        "by_problem": by_problem,
    }
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Quantum dashboard dataset built")
    print("=" * 60)
    print(f"records: {len(records)}")
    print(f"csv: {output}")
    print(f"summary: {summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
