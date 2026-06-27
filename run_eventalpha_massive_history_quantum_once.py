#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
PYTHON_BIN = "/opt/anaconda3/bin/python3"
REAL_HISTORY_RUNNER = BASE / "run_eventalpha_real_history_validation.py"
PACK_BUILDER = BASE / "build_eventalpha_real_history_quantum_pack.py"
QUANTUM_SUITE = Path("/Users/tongyin/Desktop/Anaconda_Local_Tools/run_eventalpha_quantum_suite.py")
QUANTUM_STATUS = Path("/Users/tongyin/Desktop/Anaconda_Local_Tools/ibm_quantum_eventalpha_status.py")
REAL_HISTORY_DIR = BASE / "reports" / "real_history_validation"
PACK_DIR = BASE / "reports" / "quantum_tasks"
QUANTUM_RUNS_DIR = BASE / "reports" / "quantum_runs"
OUT_DIR = BASE / "reports" / "massive_history_quantum_runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-shot runner: real-history validation -> quantum pack -> IBM quantum suite."
    )
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--max-eia-cases", type=int, default=240)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--risk-budget", type=float, default=2.5)
    parser.add_argument("--shots", type=int, default=512)
    parser.add_argument("--grid-points", type=int, default=3)
    parser.add_argument("--wait-asset", default="oil")
    parser.add_argument("--backend", default="ibm_fez")
    parser.add_argument("--poll-interval", type=int, default=20)
    parser.add_argument("--max-polls", type=int, default=12)
    parser.add_argument(
        "--ibm-problem",
        default="asset_subset_selection",
        choices=["asset_subset_selection", "wait_bucket_optimization", "risk_tier_allocation"],
        help="Which problem to send to IBM from the latest real-history pack.",
    )
    return parser.parse_args()


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def latest_file(folder: Path, pattern: str) -> Path:
    matches = sorted(folder.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matched {pattern} in {folder}")
    return matches[-1]


def run_cmd(cmd: list[str]) -> dict:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "command": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def require_success(step: str, payload: dict) -> None:
    if payload["returncode"] != 0:
        raise RuntimeError(
            f"{step} failed with rc={payload['returncode']}\nSTDOUT:\n{payload['stdout']}\nSTDERR:\n{payload['stderr']}"
        )


def fetch_ibm_status(run_file: Path) -> dict:
    status_cmd = [
        PYTHON_BIN,
        str(QUANTUM_STATUS),
        "--run-file",
        str(run_file),
        "--fetch-results",
        "--json",
    ]
    result = subprocess.run(status_cmd, capture_output=True, text=True)
    payload = {
        "command": status_cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    require_success("ibm_status_fetch", payload)
    text = result.stdout
    json_start = text.find("{")
    if json_start == -1:
        raise RuntimeError(f"ibm_status_fetch returned no JSON payload:\n{text}")
    payload["json"] = json.loads(text[json_start:])
    return payload


def summarize_ibm_status(status_json: dict) -> dict:
    jobs = status_json.get("jobs", [])
    done_jobs = [job for job in jobs if job.get("status") == "DONE"]
    best = None
    for job in done_jobs:
        candidate = job.get("best_sampled_solution")
        if not candidate:
            continue
        if best is None or float(candidate.get("objective", float("-inf"))) > float(best.get("objective", float("-inf"))):
            best = candidate
    return {
        "jobs_total": len(jobs),
        "jobs_done": len(done_jobs),
        "all_done": len(jobs) > 0 and len(jobs) == len(done_jobs),
        "best_quantum_solution": best,
    }


def main() -> int:
    args = parse_args()
    run_dir = OUT_DIR / f"run_{utc_slug()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    history_cmd = [
        PYTHON_BIN,
        str(REAL_HISTORY_RUNNER),
        "--start-year",
        str(args.start_year),
        "--end-year",
        str(args.end_year),
        "--top-n",
        str(args.top_n),
        "--max-eia-cases",
        str(args.max_eia_cases),
    ]
    history_result = run_cmd(history_cmd)
    require_success("real_history_validation", history_result)

    pack_cmd = [
        PYTHON_BIN,
        str(PACK_BUILDER),
        "--top-k",
        str(args.top_k),
        "--risk-budget",
        str(args.risk_budget),
    ]
    pack_result = run_cmd(pack_cmd)
    require_success("build_quantum_pack", pack_result)

    latest_cases = latest_file(REAL_HISTORY_DIR, "eventalpha_real_history_cases_*.csv")
    latest_matrix = latest_file(REAL_HISTORY_DIR, "eventalpha_real_history_matrix_*.csv")
    latest_summary_json = latest_file(REAL_HISTORY_DIR, "eventalpha_real_history_summary_*.json")
    latest_pack = latest_file(PACK_DIR, "eventalpha_quantum_pack_real_history_*.json")

    suite_cmd = [
        PYTHON_BIN,
        str(QUANTUM_SUITE),
        "--pack",
        str(latest_pack),
        "--shots",
        str(args.shots),
        "--grid-points",
        str(args.grid_points),
        "--wait-asset",
        args.wait_asset,
        "--ibm-problem",
        args.ibm_problem,
        "--backend",
        args.backend,
    ]
    suite_result = run_cmd(suite_cmd)
    require_success("quantum_suite", suite_result)

    latest_suite_dir = latest_file(BASE / "reports" / "quantum_suite_runs", "suite_*")
    latest_ibm_run = latest_file(QUANTUM_RUNS_DIR, f"eventalpha_quantum_run_{args.ibm_problem}_ibm_*.json")
    ibm_status_payload = fetch_ibm_status(latest_ibm_run)
    ibm_status_summary = summarize_ibm_status(ibm_status_payload["json"])

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_base": str(BASE),
        "parameters": vars(args),
        "real_history_cases_csv": str(latest_cases),
        "real_history_matrix_csv": str(latest_matrix),
        "real_history_summary_json": str(latest_summary_json),
        "quantum_pack_json": str(latest_pack),
        "quantum_suite_dir": str(latest_suite_dir),
        "ibm_run_file": str(latest_ibm_run),
        "steps": {
            "real_history_validation": history_result,
            "build_quantum_pack": pack_result,
            "quantum_suite": suite_result,
            "ibm_status_fetch": ibm_status_payload,
        },
        "ibm_status_summary": ibm_status_summary,
        "note": "This orchestration uses real historical validation and abstract quantum optimization only. It places no trades and touches no broker.",
    }

    summary_json = run_dir / "massive_history_quantum_summary.json"
    summary_md = run_dir / "MASSIVE_HISTORY_QUANTUM_SUMMARY.md"
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    md_lines = [
        "# EventAlpha Massive History + IBM Quantum Run",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- real_history_cases_csv: `{latest_cases}`",
        f"- real_history_matrix_csv: `{latest_matrix}`",
        f"- real_history_summary_json: `{latest_summary_json}`",
        f"- quantum_pack_json: `{latest_pack}`",
        f"- quantum_suite_dir: `{latest_suite_dir}`",
        f"- ibm_run_file: `{latest_ibm_run}`",
        "",
        "## Parameters",
        "",
    ]
    for key, value in vars(args).items():
        md_lines.append(f"- {key}: `{value}`")
    md_lines.extend(
        [
            "",
            "## Step Return Codes",
            "",
            f"- real_history_validation: `{history_result['returncode']}`",
            f"- build_quantum_pack: `{pack_result['returncode']}`",
            f"- quantum_suite: `{suite_result['returncode']}`",
            f"- ibm_status_fetch: `{ibm_status_payload['returncode']}`",
            "",
            "## IBM Result",
            "",
            f"- jobs_done: `{ibm_status_summary['jobs_done']}` / `{ibm_status_summary['jobs_total']}`",
            f"- all_done: `{ibm_status_summary['all_done']}`",
            f"- best_quantum_solution: `{json.dumps(ibm_status_summary['best_quantum_solution'], ensure_ascii=False)}`",
            "",
            "## Note",
            "",
            summary["note"],
            "",
        ]
    )
    summary_md.write_text("\n".join(md_lines))

    print("EventAlpha Massive History + IBM Quantum Runner")
    print("=" * 60)
    print(f"real_history_cases_csv: {latest_cases}")
    print(f"real_history_matrix_csv: {latest_matrix}")
    print(f"real_history_summary_json: {latest_summary_json}")
    print(f"quantum_pack_json: {latest_pack}")
    print(f"quantum_suite_dir: {latest_suite_dir}")
    print(f"ibm_run_file: {latest_ibm_run}")
    print(f"ibm_jobs_done: {ibm_status_summary['jobs_done']}/{ibm_status_summary['jobs_total']}")
    print(f"ibm_all_done: {ibm_status_summary['all_done']}")
    print(f"ibm_best_quantum_solution: {json.dumps(ibm_status_summary['best_quantum_solution'], ensure_ascii=False)}")
    print(f"saved_summary_json: {summary_json}")
    print(f"saved_summary_md: {summary_md}")
    print(summary["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
