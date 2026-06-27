#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
os.environ.setdefault("NUMBA_CACHE_DIR", "/private/tmp/numba_cache")

from braket.aws import AwsQuantumTask

from aws_braket_eventalpha_submit import select_problem
from ibm_quantum_eventalpha_submit import decode_counts, ensure_best_exact_solution, load_pack


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DEFAULT_RUN_DIR = BASE / "reports" / "quantum_runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check AWS Braket EventAlpha submitted tasks and optionally fetch decoded results."
    )
    parser.add_argument("--run-file", default="", help="Specific saved AWS run JSON file.")
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR), help="Directory to search for the newest AWS run JSON.")
    parser.add_argument("--fetch-results", action="store_true", help="If tasks are completed, fetch and decode counts.")
    parser.add_argument("--write-report", action="store_true", help="Write JSON/Markdown comparison reports next to the run file.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser.parse_args()


def find_latest_run(run_dir: Path) -> Path:
    files = list(run_dir.glob("eventalpha_quantum_run_*_aws_*.json"))
    if not files:
        raise FileNotFoundError(f"No AWS EventAlpha quantum run file found in {run_dir}")

    def score(path: Path) -> tuple[int, float]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            has_submitted_tasks = 1 if payload.get("result", {}).get("submitted_tasks") else 0
        except Exception:
            has_submitted_tasks = 0
        return (has_submitted_tasks, path.stat().st_mtime)

    return max(files, key=score)


def build_report(result: dict, problem: dict, run_path: Path) -> tuple[Path, Path]:
    report_json = run_path.with_name(run_path.stem + "_report.json")
    report_md = run_path.with_name(run_path.stem + "_report.md")

    baseline = None
    best_quantum = None
    for row in result.get("tasks", []):
        if baseline is None:
            baseline = row.get("baseline_exact")
        candidate = row.get("best_sampled_solution")
        if candidate is None:
            continue
        if best_quantum is None or float(candidate.get("objective", float("-inf"))) > float(best_quantum.get("objective", float("-inf"))):
            best_quantum = candidate

    delta = None
    if baseline and best_quantum:
        delta = round(float(best_quantum["objective"]) - float(baseline["objective"]), 6)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_file": str(run_path),
        "problem": problem["problem"],
        "baseline_exact": baseline,
        "best_quantum_solution": best_quantum,
        "delta_vs_exact": delta,
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# EventAlpha AWS Quantum Cross-Check",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- run_file: `{run_path}`",
        f"- problem: `{problem['problem']}`",
        "",
        "## Exact Baseline",
        "",
        json.dumps(baseline, ensure_ascii=False, indent=2) if baseline else "N/A",
        "",
        "## Best AWS Quantum Solution",
        "",
        json.dumps(best_quantum, ensure_ascii=False, indent=2) if best_quantum else "N/A",
        "",
        f"## Delta vs Exact",
        "",
        str(delta) if delta is not None else "N/A",
        "",
        "## Recommendation",
        "",
    ]
    if baseline and best_quantum and delta is not None:
        if delta >= 0:
            lines.append("AWS quantum sample matched or exceeded the local exact baseline.")
        else:
            lines.append("AWS quantum sample is below the local exact baseline. Keep the local exact result as decision truth for now.")
    else:
        lines.append("Not enough completed AWS task results yet to compare with the local exact baseline.")
    report_md.write_text("\n".join(lines), encoding="utf-8")
    return report_json, report_md


def main() -> int:
    args = parse_args()
    run_path = Path(args.run_file).expanduser() if args.run_file else find_latest_run(Path(args.run_dir).expanduser())
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    tasks = payload.get("result", {}).get("submitted_tasks", [])
    if not tasks:
        result = {
            "run_file": str(run_path),
            "status": "NO_PENDING_TASKS",
            "message": "This run file does not contain submit-only AWS tasks.",
        }
    else:
        pack = load_pack(Path(payload["pack_path"]))
        problem = select_problem(pack, payload["problem"])
        inspected = []
        for item in tasks:
            task = AwsQuantumTask(item["task_arn"])
            state = task.state()
            row = {
                "task_arn": item["task_arn"],
                "label": item.get("label"),
                "subject": item.get("subject"),
                "params": item["params"],
                "state": state,
                "baseline_exact": ensure_best_exact_solution(problem, subject=item.get("subject")),
            }
            if args.fetch_results and state == "COMPLETED":
                try:
                    task_result = task.result()
                    row["counts"] = dict(task_result.measurement_counts)
                    decoded = decode_counts(task_result.measurement_counts, problem, subject=item.get("subject"))
                    row["best_sampled_solution"] = decoded.get("best_sampled_solution")
                except Exception as exc:
                    row["result_error"] = str(exc)
            inspected.append(row)
        result = {
            "run_file": str(run_path),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "problem": payload["problem"],
            "tasks": inspected,
        }
        if args.write_report:
            report_json, report_md = build_report(result, problem, run_path)
            result["report_json"] = str(report_json)
            result["report_md"] = str(report_md)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("AWS Braket EventAlpha Status")
        print("=" * 60)
        print(f"run_file: {result['run_file']}")
        if result.get("status") == "NO_PENDING_TASKS":
            print(result["message"])
        else:
            for row in result["tasks"]:
                print("-" * 60)
                print(f"task_arn: {row['task_arn']}")
                print(f"label: {row.get('label')}")
                print(f"params: {json.dumps(row['params'], ensure_ascii=False)}")
                print(f"state: {row['state']}")
                if "best_sampled_solution" in row:
                    print(f"best_sampled_solution: {json.dumps(row['best_sampled_solution'], ensure_ascii=False)}")
                if "counts" in row:
                    print(f"counts: {json.dumps(row['counts'], ensure_ascii=False)}")
                if "result_error" in row:
                    print(f"result_error: {row['result_error']}")
            if result.get("report_json"):
                print("-" * 60)
                print(f"report_json: {result['report_json']}")
                print(f"report_md: {result['report_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
