#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


TOOLS_BASE = Path("/Users/tongyin/Desktop/Anaconda_Local_Tools")
PROJECT_BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
SUBMIT_SCRIPT = TOOLS_BASE / "ibm_quantum_eventalpha_submit.py"
DEFAULT_PACK_DIR = PROJECT_BASE / "reports" / "quantum_tasks"
DEFAULT_OUT_DIR = PROJECT_BASE / "reports" / "quantum_suite_runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-shot EventAlpha quantum suite runner for local review plus optional IBM submission."
    )
    parser.add_argument("--pack", default="", help="Specific pack JSON path.")
    parser.add_argument("--pack-dir", default=str(DEFAULT_PACK_DIR), help="Directory used to find the newest pack when --pack is omitted.")
    parser.add_argument("--shots", type=int, default=128, help="Shots for local runs and IBM submission.")
    parser.add_argument("--grid-points", type=int, default=2, help="Grid points for local runs and IBM submission.")
    parser.add_argument("--wait-asset", default="oil", help="Asset used for wait-bucket review.")
    parser.add_argument("--ibm-problem", default="none", choices=["none", "asset_subset_selection", "wait_bucket_optimization", "risk_tier_allocation"], help="Optionally submit one problem to IBM after the local suite.")
    parser.add_argument("--backend", default="ibm_fez", help="IBM backend when --ibm-problem is enabled.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory for suite outputs.")
    return parser.parse_args()


def find_latest_pack(pack_dir: Path) -> Path:
    packs = sorted(pack_dir.glob("eventalpha_quantum_pack_*.json"))
    if not packs:
        raise FileNotFoundError(f"No quantum task pack found in {pack_dir}")
    return packs[-1]


def run_submit_command(cmd: list[str]) -> dict:
    result = subprocess.run(cmd, capture_output=True, text=True)
    payload = None
    if result.stdout.strip().startswith("{"):
        payload = json.loads(result.stdout)
    return {
        "command": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "payload": payload,
    }


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    args = parse_args()
    pack_path = Path(args.pack).expanduser() if args.pack else find_latest_pack(Path(args.pack_dir).expanduser())
    out_dir = Path(args.out_dir).expanduser() / f"suite_{utc_slug()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    local_specs = [
        ("asset_subset_selection", ""),
        ("wait_bucket_optimization", args.wait_asset),
        ("risk_tier_allocation", ""),
    ]
    local_results = []
    for problem, asset in local_specs:
        cmd = [
            "python3",
            str(SUBMIT_SCRIPT),
            "--pack",
            str(pack_path),
            "--mode",
            "local",
            "--problem",
            problem,
            "--shots",
            str(args.shots),
            "--grid-points",
            str(args.grid_points),
            "--json",
        ]
        if asset:
            cmd.extend(["--asset", asset])
        local_results.append(run_submit_command(cmd))

    ibm_result = None
    if args.ibm_problem != "none":
        cmd = [
            "python3",
            str(SUBMIT_SCRIPT),
            "--pack",
            str(pack_path),
            "--mode",
            "ibm",
            "--submit-only",
            "--problem",
            args.ibm_problem,
            "--shots",
            str(args.shots),
            "--grid-points",
            str(args.grid_points),
            "--backend",
            args.backend,
            "--json",
        ]
        if args.ibm_problem == "wait_bucket_optimization":
            cmd.extend(["--asset", args.wait_asset])
        ibm_result = run_submit_command(cmd)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pack_path": str(pack_path),
        "local_results": local_results,
        "ibm_result": ibm_result,
        "note": "This suite only evaluates abstract optimization tasks for the five financial models. It does not place trades.",
    }
    (out_dir / "suite_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    lines = [
        "# EventAlpha Quantum Suite Summary",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- pack_path: `{pack_path}`",
        "",
        "## Local Problems",
        "",
    ]
    for item in local_results:
        payload = item.get("payload") or {}
        problem = payload.get("problem", "unknown")
        best_task = (payload.get("result") or {}).get("best_task") or {}
        best_run = best_task.get("best_run") or {}
        best_solution = best_run.get("best_sampled_solution") or {}
        lines.extend(
            [
                f"### {problem}",
                "",
                f"- returncode: {item['returncode']}",
                f"- baseline_exact: `{json.dumps(payload.get('baseline_exact'), ensure_ascii=False)}`",
                f"- best_sampled_solution: `{json.dumps(best_solution, ensure_ascii=False)}`",
                "",
            ]
        )
    if ibm_result is not None:
        lines.extend(
            [
                "## IBM Submission",
                "",
                f"- problem: `{args.ibm_problem}`",
                f"- returncode: {ibm_result['returncode']}",
                f"- stderr: `{ibm_result['stderr'].strip()}`",
                "",
            ]
        )
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n")

    print("EventAlpha Quantum Suite Runner")
    print("=" * 60)
    print(f"pack_path: {pack_path}")
    print(f"saved_json: {out_dir / 'suite_summary.json'}")
    print(f"saved_markdown: {out_dir / 'SUMMARY.md'}")
    print(summary["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
