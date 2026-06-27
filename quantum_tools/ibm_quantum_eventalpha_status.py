#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

try:
    from ibm_quantum_eventalpha_submit import decode_counts
except Exception:  # pragma: no cover
    decode_counts = None


TOOLS_BASE = Path("/Users/tongyin/Desktop/Anaconda_Local_Tools")
DEFAULT_ENV_FILE = TOOLS_BASE / ".env.ibm_quantum"
DEFAULT_RUN_DIR = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check IBM Quantum EventAlpha submitted jobs and optionally fetch completed results."
    )
    parser.add_argument("--run-file", default="", help="Specific saved quantum run JSON file.")
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR), help="Directory to search for the newest quantum run JSON.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="IBM token env file.")
    parser.add_argument("--fetch-results", action="store_true", help="If jobs are done, fetch and decode counts.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser.parse_args()


def maybe_load_env(path: Path) -> None:
    if load_dotenv is not None and path.exists():
        load_dotenv(path, override=False)


def find_latest_run(run_dir: Path) -> Path:
    files = sorted(run_dir.glob("eventalpha_quantum_run_*.json"))
    if not files:
        raise FileNotFoundError(f"No quantum run file found in {run_dir}")
    return files[-1]


def get_service(env_file: Path):
    maybe_load_env(env_file)
    token = os.getenv("IBM_QUANTUM_TOKEN", "").strip()
    channel = os.getenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform").strip() or "ibm_quantum_platform"
    if channel == "ibm_quantum":
        channel = "ibm_quantum_platform"
    instance = os.getenv("IBM_QUANTUM_INSTANCE", "").strip() or None
    if not token:
        raise RuntimeError("Missing IBM_QUANTUM_TOKEN.")
    from qiskit_ibm_runtime import QiskitRuntimeService
    kwargs = {"channel": channel, "token": token}
    if instance:
        kwargs["instance"] = instance
    return QiskitRuntimeService(**kwargs)


def resolve_problem(payload: dict) -> dict | None:
    pack_path = payload.get("pack_path")
    problem_name = payload.get("problem")
    if not pack_path or not problem_name:
        return None
    try:
        pack = json.loads(Path(pack_path).read_text())
    except Exception:
        return None
    for problem in pack.get("problems", []):
        if problem.get("problem") == problem_name:
            return problem
    return None


def main() -> int:
    args = parse_args()
    run_path = Path(args.run_file).expanduser() if args.run_file else find_latest_run(Path(args.run_dir).expanduser())
    payload = json.loads(run_path.read_text())
    problem = resolve_problem(payload)
    jobs = payload.get("result", {}).get("submitted_jobs", [])
    if not jobs:
        result = {
            "run_file": str(run_path),
            "status": "NO_PENDING_JOBS",
            "message": "This run file does not contain submit-only IBM jobs.",
        }
    else:
        service = get_service(Path(args.env_file).expanduser())
        inspected = []
        for item in jobs:
            job = service.job(item["job_id"])
            status = str(job.status())
            row = {
                "job_id": item["job_id"],
                "params": item["params"],
                "status": status,
            }
            if args.fetch_results and status == "DONE":
                try:
                    pub = job.result()[0]
                    counts = pub.data.c.get_counts() if hasattr(pub.data, "c") else pub.data.meas.get_counts()
                    row["counts"] = counts
                    if problem is not None and decode_counts is not None:
                        decoded = decode_counts(counts, problem, subject=item.get("subject"))
                        row["best_sampled_solution"] = decoded.get("best_sampled_solution")
                except Exception as exc:
                    row["result_error"] = str(exc)
            inspected.append(row)
        result = {
            "run_file": str(run_path),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "jobs": inspected,
        }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("IBM Quantum EventAlpha Status")
        print("=" * 60)
        print(f"run_file: {result['run_file']}")
        if result.get("status") == "NO_PENDING_JOBS":
            print(result["message"])
        else:
            for row in result["jobs"]:
                print("-" * 60)
                print(f"job_id: {row['job_id']}")
                print(f"params: {json.dumps(row['params'], ensure_ascii=False)}")
                print(f"status: {row['status']}")
                if "best_sampled_solution" in row:
                    print(f"best_sampled_solution: {json.dumps(row['best_sampled_solution'], ensure_ascii=False)}")
                if "counts" in row:
                    print(f"counts: {json.dumps(row['counts'], ensure_ascii=False)}")
                if "result_error" in row:
                    print(f"result_error: {row['result_error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
