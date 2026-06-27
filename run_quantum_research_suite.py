#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DEFAULT_OUTPUT_DIR = PROJECT_BASE / "reports" / "quantum_research"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-shot EventAlpha quantum research suite.")
    parser.add_argument("--runs-dir", default=str(PROJECT_BASE / "reports" / "quantum_runs"))
    parser.add_argument("--decisions-input", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--serve-dashboard", action=argparse.BooleanOptionalAction, default=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    dashboard_csv = output_dir / "dashboard_runs.csv"
    dashboard_summary = output_dir / "dashboard_summary.json"
    penalty_csv = output_dir / "penalty_results.csv"
    penalty_json = output_dir / "penalty_results.json"
    penalty_md = output_dir / "penalty_sensitivity_report.md"
    charts_dir = output_dir / "dashboard_charts"

    commands = [
        [
            sys.executable,
            str(PROJECT_BASE / "quantum_research" / "build_dashboard_dataset.py"),
            "--runs-dir",
            args.runs_dir,
            "--output",
            str(dashboard_csv),
            "--summary-output",
            str(dashboard_summary),
        ],
        [
            sys.executable,
            str(PROJECT_BASE / "quantum_research" / "plot_research_views.py"),
            "--csv",
            str(dashboard_csv),
            "--outdir",
            str(charts_dir),
        ],
        [
            sys.executable,
            str(PROJECT_BASE / "quantum_research" / "tune_asset_subset_penalties.py"),
            "--output-json",
            str(penalty_json),
            "--output-csv",
            str(penalty_csv),
        ],
        [
            sys.executable,
            str(PROJECT_BASE / "quantum_research" / "penalty_sensitivity_report.py"),
            "--csv",
            str(penalty_csv),
            "--output-md",
            str(penalty_md),
        ],
    ]

    if args.decisions_input:
        commands[2].extend(["--input", args.decisions_input])

    for cmd in commands:
        subprocess.check_call(cmd, cwd=str(PROJECT_BASE))

    print("EventAlpha Quantum Research Suite")
    print("=" * 60)
    print(f"dashboard_csv: {dashboard_csv}")
    print(f"dashboard_html: {charts_dir / 'index.html'}")
    print(f"penalty_csv: {penalty_csv}")
    print(f"penalty_report: {penalty_md}")

    if args.serve_dashboard:
        subprocess.check_call(
            [
                sys.executable,
                str(PROJECT_BASE / "quantum_research" / "dashboard_app.py"),
                "--csv",
                str(dashboard_csv),
                "--outdir",
                str(charts_dir),
            ],
            cwd=str(PROJECT_BASE),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
