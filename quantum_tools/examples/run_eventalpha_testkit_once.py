#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


BASE = Path("/Users/tongyin/Desktop/Test")
DEFAULT_CSV = BASE / "decisions.csv"
DEFAULT_RESULTS = BASE / "results"
IBM_SUBMIT_SCRIPT = Path("/Users/tongyin/Desktop/Anaconda_Local_Tools/ibm_quantum_eventalpha_submit.py")
IBM_STATUS_SCRIPT = Path("/Users/tongyin/Desktop/Anaconda_Local_Tools/ibm_quantum_eventalpha_status.py")

PRESETS = {
    "quick": {"shots": 128, "grid_points": 2},
    "balanced": {"shots": 512, "grid_points": 3},
    "deep": {"shots": 2048, "grid_points": 5},
}

WAIT_BUCKETS = [0, 60, 120, 180, 240, 300, 420, 600]
TIER_WEIGHT = {
    "skip": 0.0,
    "small": 0.5,
    "normal": 1.0,
    "heavy": 1.5,
}
TIER_MULTIPLIER = {
    "skip": 0.0,
    "small": 0.6,
    "normal": 1.0,
    "heavy": 1.35,
}


@dataclass
class DecisionRow:
    case_id: str
    event_type: str
    asset: str
    symbol: str
    action: str
    direction: str
    grade: str
    confidence: float
    wait_seconds: int
    max_risk_fraction: float
    expected_edge_score: float
    observed_pnl: float
    should_exit: bool
    exit_reasons: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-shot EventAlpha test kit runner for CSV decisions plus optional IBM quantum submission."
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Path to decisions.csv.")
    parser.add_argument("--output", default=str(DEFAULT_RESULTS), help="Output root directory.")
    parser.add_argument("--risk-budget", type=float, default=2.5, help="Abstract portfolio risk budget.")
    parser.add_argument("--max-assets", type=int, default=3, help="Maximum number of selected assets.")
    parser.add_argument("--mode", default="local", choices=["local", "ibm-submit", "ibm-suite"], help="Run local analysis only, submit the subset problem, or submit the full subset/wait/risk suite to IBM.")
    parser.add_argument("--backend", default="ibm_fez", help="IBM backend name if --mode ibm-submit.")
    parser.add_argument("--preset", default="balanced", choices=sorted(PRESETS.keys()), help="Quantum parameter preset. quick=fast smoke test, balanced=default formal check, deep=heavier scan.")
    parser.add_argument("--shots", type=int, default=128, help="IBM submission shots if --mode ibm-submit.")
    parser.add_argument("--grid-points", type=int, default=2, help="IBM submission grid size if --mode ibm-submit.")
    parser.add_argument("--auto-wait", action=argparse.BooleanOptionalAction, default=True, help="When submitting to IBM, automatically poll until complete and write a comparison report.")
    parser.add_argument("--poll-interval", type=int, default=20, help="Seconds between IBM status polls when --auto-wait is enabled.")
    parser.add_argument("--max-polls", type=int, default=18, help="Maximum IBM status polls before stopping.")
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fmt_delta(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.6f}"


def render_solution(solution: dict | None) -> list[str]:
    if not solution:
        return ["N/A"]
    return [
        f"selected={solution.get('selected')}",
        f"objective={solution.get('objective')}",
        f"shots={solution.get('shots', 'N/A')}",
        f"bitstring={solution.get('bitstring', 'N/A')}",
    ]


def render_generic_solution(solution: dict | None) -> list[str]:
    if not solution:
        return ["N/A"]
    lines = []
    for key in ["selected", "selected_waits", "chosen_wait_seconds", "allocation", "objective", "shots", "bitstring", "risk_used"]:
        if key in solution:
            lines.append(f"{key}={solution.get(key)}")
    return lines or [json.dumps(solution, ensure_ascii=False)]


def resolve_quantum_params(args: argparse.Namespace) -> tuple[int, int]:
    preset = PRESETS[args.preset]
    shots = args.shots if args.shots != 128 else preset["shots"]
    grid_points = args.grid_points if args.grid_points != 2 else preset["grid_points"]
    return shots, grid_points


def load_rows(csv_path: Path) -> List[DecisionRow]:
    rows: List[DecisionRow] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for item in reader:
            rows.append(
                DecisionRow(
                    case_id=item["case_id"],
                    event_type=item["event_type"],
                    asset=item["asset"],
                    symbol=item["symbol"],
                    action=item["action"],
                    direction=item["direction"],
                    grade=item["grade"],
                    confidence=float(item["confidence"]),
                    wait_seconds=int(float(item["wait_seconds"])),
                    max_risk_fraction=float(item["max_risk_fraction"]),
                    expected_edge_score=float(item["expected_edge_score"]),
                    observed_pnl=float(item["observed_pnl"]),
                    should_exit=str(item["should_exit"]).strip().lower() == "true",
                    exit_reasons=item.get("exit_reasons", "").strip(),
                )
            )
    return rows


def pair_penalty(a: str, b: str) -> float:
    pair = tuple(sorted((a, b)))
    return {
        ("crypto", "index"): 0.10,
        ("fx", "rates"): 0.08,
        ("index", "oil"): 0.12,
        ("crypto", "oil"): 0.05,
        ("fx", "index"): 0.04,
        ("oil", "rates"): 0.03,
    }.get(pair, 0.02)


def row_priority(row: DecisionRow) -> float:
    pnl_term = max(-1.0, min(1.0, row.observed_pnl / 2.0)) * 0.10
    exit_penalty = -0.45 if row.should_exit else 0.0
    action_bonus = 0.08 if row.action == "enter" else -0.04 if row.action == "watch" else 0.0
    grade_bonus = {
        "extreme": 0.12,
        "high_conviction": 0.08,
        "trade_candidate": 0.03,
    }.get(row.grade, 0.0)
    return round(
        row.confidence * 0.55
        + row.expected_edge_score * 0.35
        + pnl_term
        + action_bonus
        + grade_bonus
        + exit_penalty,
        6,
    )


def nearest_wait_bucket(wait_seconds: int) -> int:
    return min(WAIT_BUCKETS, key=lambda x: abs(x - wait_seconds))


def recommended_tier(row: DecisionRow) -> str:
    if row.should_exit:
        return "skip"
    if row.action == "watch" and row.confidence < 0.69:
        return "skip"
    if row.confidence >= 0.72 and row.expected_edge_score >= 0.54:
        return "heavy"
    if row.confidence >= 0.69:
        return "normal"
    if row.confidence >= 0.62:
        return "small"
    return "skip"


def optimize_portfolio(rows: List[DecisionRow], risk_budget: float, max_assets: int) -> dict:
    eligible = [r for r in rows if not r.should_exit and r.action in {"enter", "watch"}]
    best = None
    all_candidates = []
    for mask in range(1 << len(eligible)):
        selected = [eligible[i] for i in range(len(eligible)) if mask & (1 << i)]
        if len(selected) > max_assets:
            continue
        risk_used = sum(TIER_WEIGHT[recommended_tier(r)] for r in selected)
        if risk_used > risk_budget:
            continue
        base = sum(row_priority(r) * TIER_MULTIPLIER[recommended_tier(r)] for r in selected)
        penalty = 0.0
        for i in range(len(selected)):
            for j in range(i + 1, len(selected)):
                penalty += pair_penalty(selected[i].asset, selected[j].asset)
        objective = round(base - penalty, 6)
        candidate = {
            "selected_case_ids": [r.case_id for r in selected],
            "selected_assets": [r.asset for r in selected],
            "risk_used": round(risk_used, 6),
            "objective": objective,
            "base_score": round(base, 6),
            "pair_penalty": round(penalty, 6),
        }
        all_candidates.append(candidate)
        if best is None or candidate["objective"] > best["objective"]:
            best = candidate
    assert best is not None
    return {"best": best, "top5": sorted(all_candidates, key=lambda x: x["objective"], reverse=True)[:5]}


def build_wait_problem(rows: List[DecisionRow]) -> dict:
    per_asset = {}
    by_asset: Dict[str, List[DecisionRow]] = defaultdict(list)
    for row in rows:
        by_asset[row.asset].append(row)
    for asset, asset_rows in sorted(by_asset.items()):
        avg_wait = sum(r.wait_seconds for r in asset_rows) / max(1, len(asset_rows))
        avg_conf = sum(r.confidence for r in asset_rows) / max(1, len(asset_rows))
        avg_edge = sum(r.expected_edge_score for r in asset_rows) / max(1, len(asset_rows))
        scored = []
        for bucket in WAIT_BUCKETS:
            distance = abs(bucket - avg_wait)
            fit = 1.0 - min(distance / 600.0, 1.0)
            confidence_bonus = (avg_conf - 0.5) * 0.35
            edge_bonus = avg_edge * 0.25
            overshoot_penalty = 0.08 if bucket > avg_wait + 180 else 0.0
            score = round(fit + confidence_bonus + edge_bonus - overshoot_penalty, 6)
            scored.append({"wait_seconds": bucket, "score": score})
        best = max(scored, key=lambda x: x["score"])
        per_asset[asset] = {
            "target_wait_estimate": round(avg_wait, 2),
            "bucket_scores": scored,
            "best_exact_solution": best,
        }
    return {
        "problem": "wait_bucket_optimization",
        "event_type": "mixed_uploaded_cases",
        "per_asset": per_asset,
    }


def build_risk_problem(rows: List[DecisionRow], portfolio: dict, risk_budget: float) -> dict:
    row_map = {row.case_id: row for row in rows}
    selected_case_ids = portfolio["best"]["selected_case_ids"]
    selected_assets = []
    asset_scores = {}
    for case_id in selected_case_ids:
        row = row_map.get(case_id)
        if row is None:
            continue
        if row.asset not in selected_assets:
            selected_assets.append(row.asset)
            asset_scores[row.asset] = round(row_priority(row), 6)
    allocation = {}
    risk_used = 0.0
    for case_id in selected_case_ids:
        row = row_map.get(case_id)
        if row is None or row.asset in allocation:
            continue
        tier = recommended_tier(row)
        weight = TIER_WEIGHT[tier]
        allocation[row.asset] = {"tier": tier, "weight": weight}
        risk_used += weight
    objective = round(
        sum(asset_scores.get(asset, 0.0) * allocation[asset]["weight"] for asset in allocation),
        6,
    )
    return {
        "problem": "risk_tier_allocation",
        "selected_assets": selected_assets,
        "qubo_like": {
            "selected_assets": selected_assets,
            "tiers": TIER_WEIGHT,
            "risk_budget": risk_budget,
            "asset_scores": asset_scores,
        },
        "best_exact_solution": {
            "allocation": allocation,
            "risk_used": round(risk_used, 6),
            "objective": objective,
        },
    }


def choose_wait_asset(portfolio: dict, reviews: List[dict]) -> str:
    selected_assets = set(portfolio["best"]["selected_assets"])
    candidates = [row for row in reviews if row["asset"] in selected_assets and row["recommended_action"] != "exit"]
    if not candidates:
        return portfolio["best"]["selected_assets"][0] if portfolio["best"]["selected_assets"] else reviews[0]["asset"]
    candidates.sort(key=lambda x: x["priority_score"], reverse=True)
    return candidates[0]["asset"]


def build_quantum_pack(rows: List[DecisionRow], risk_budget: float, max_assets: int, portfolio: dict) -> dict:
    variables = [r.case_id for r in rows]
    linear_scores = {r.case_id: row_priority(r) for r in rows}
    pair_penalties = {}
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            pair_penalties[f"{a.case_id}|{b.case_id}"] = pair_penalty(a.asset, b.asset)
    best_count = len(portfolio["best"]["selected_case_ids"])
    return {
        "generated_at": _utc_now(),
        "source_csv": str(DEFAULT_CSV),
        "event_type": "mixed_uploaded_cases",
        "uncertainties_best_suited_for_quantum": [
            {
                "name": "best_asset_subset",
                "why_quantum_relevant": "Uploaded cases form a discrete choose-k portfolio selection problem under correlation and risk constraints.",
                "current_gap": "Current case sheet contains strong candidates, but still needs final constrained subset optimization.",
            }
        ],
        "asset_stats": {
            r.case_id: {
                "asset": r.asset,
                "symbol": r.symbol,
                "priority_score": row_priority(r),
                "recommended_wait_bucket": nearest_wait_bucket(r.wait_seconds),
                "recommended_tier": recommended_tier(r),
                "should_exit": r.should_exit,
            }
            for r in rows
        },
        "problems": [
            {
                "problem": "asset_subset_selection",
                "event_type": "mixed_uploaded_cases",
                "best_exact_solution": portfolio["best"],
                "qubo_like": {
                    "variables": variables,
                    "selection_target": best_count,
                    "linear_scores": linear_scores,
                    "pair_penalties": pair_penalties,
                    "cardinality_penalty_lambda": 0.45,
                    "risk_budget": risk_budget,
                },
            },
            build_wait_problem(rows),
            build_risk_problem(rows, portfolio, risk_budget),
        ],
        "safety_note": "This pack is built from uploaded CSV decisions only. It places no orders and touches no broker.",
    }


def build_case_reviews(rows: List[DecisionRow]) -> List[dict]:
    reviews = []
    for row in rows:
        tier = recommended_tier(row)
        recommended_action = "exit" if row.should_exit else "enter" if tier in {"small", "normal", "heavy"} else "watch"
        reviews.append(
            {
                "case_id": row.case_id,
                "event_type": row.event_type,
                "asset": row.asset,
                "symbol": row.symbol,
                "current_action": row.action,
                "recommended_action": recommended_action,
                "recommended_tier": tier,
                "priority_score": row_priority(row),
                "recommended_wait_bucket": nearest_wait_bucket(row.wait_seconds),
                "reason": row.exit_reasons if row.should_exit else f"confidence={row.confidence:.4f}, edge={row.expected_edge_score:.4f}",
            }
        )
    return reviews


def write_outputs(
    out_dir: Path,
    rows: List[DecisionRow],
    reviews: List[dict],
    portfolio: dict,
    quantum_pack: dict,
    ibm_submission: dict | None,
    quantum_report: dict | None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "decisions_input_snapshot.json").write_text(
        json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2)
    )
    (out_dir / "case_reviews.json").write_text(
        json.dumps(reviews, ensure_ascii=False, indent=2)
    )
    (out_dir / "portfolio_optimization.json").write_text(
        json.dumps(portfolio, ensure_ascii=False, indent=2)
    )
    (out_dir / "quantum_pack.json").write_text(
        json.dumps(quantum_pack, ensure_ascii=False, indent=2)
    )
    if ibm_submission is not None:
        (out_dir / "ibm_submission.json").write_text(
            json.dumps(ibm_submission, ensure_ascii=False, indent=2)
        )
    if quantum_report is not None:
        (out_dir / "ibm_quantum_report.json").write_text(
            json.dumps(quantum_report, ensure_ascii=False, indent=2)
        )
        report_lines = [
            "# EventAlpha IBM Quantum Comparison Report",
            "",
            f"- generated_at: {_utc_now()}",
        ]
        if "runs" in quantum_report:
            report_lines.extend(["", "## Suite Results", ""])
            for key, item in quantum_report["runs"].items():
                report_lines.append(f"### {key}")
                report_lines.append("")
                if not item:
                    report_lines.append("- result: N/A")
                    report_lines.append("")
                    continue
                report_lines.extend(
                    [
                        f"- run_file: `{item.get('run_file', '')}`",
                        f"- preset: `{item.get('preset')}`",
                        f"- shots: `{item.get('shots')}`",
                        f"- grid_points: `{item.get('grid_points')}`",
                        f"- jobs_done: `{item.get('jobs_done')}` / `{item.get('jobs_total')}`",
                        f"- status: `{item.get('status')}`",
                        f"- baseline_exact: `{json.dumps(item.get('baseline_exact', item.get('exact_baseline')), ensure_ascii=False)}`",
                    ]
                )
                for line in render_generic_solution(item.get("best_quantum_solution")):
                    report_lines.append(f"- {line}")
                report_lines.append(f"- delta_vs_exact: {fmt_delta(item.get('delta_vs_exact'))}")
                report_lines.append(f"- recommendation: {item.get('recommendation')}")
                report_lines.append("")
        else:
            report_lines.extend(
                [
                    f"- run_file: `{quantum_report.get('run_file', '')}`",
                    f"- preset: `{quantum_report.get('preset')}`",
                    f"- shots: `{quantum_report.get('shots')}`",
                    f"- grid_points: `{quantum_report.get('grid_points')}`",
                    f"- jobs_done: `{quantum_report.get('jobs_done')}` / `{quantum_report.get('jobs_total')}`",
                    f"- status: `{quantum_report.get('status')}`",
                    "",
                    "## Exact Baseline",
                    "",
                    f"- selected_case_ids: {quantum_report.get('exact_baseline', {}).get('selected_case_ids')}",
                    f"- selected_assets: {quantum_report.get('exact_baseline', {}).get('selected_assets')}",
                    f"- objective: {quantum_report.get('exact_baseline', {}).get('objective')}",
                    f"- risk_used: {quantum_report.get('exact_baseline', {}).get('risk_used')}",
                    "",
                    "## Best Quantum Sampled Solution",
                    "",
                ]
            )
            for line in render_solution(quantum_report.get("best_quantum_solution")):
                report_lines.append(f"- {line}")
            report_lines.extend(
                [
                    "",
                    "## Conclusion",
                    "",
                    f"- delta_vs_exact: {fmt_delta(quantum_report.get('delta_vs_exact'))}",
                    f"- recommendation: {quantum_report.get('recommendation')}",
                ]
            )
        (out_dir / "IBM_QUANTUM_COMPARISON.md").write_text("\n".join(report_lines) + "\n")

    with (out_dir / "case_reviews.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "case_id",
            "event_type",
            "asset",
            "symbol",
            "current_action",
            "recommended_action",
            "recommended_tier",
            "priority_score",
            "recommended_wait_bucket",
            "reason",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in reviews:
            writer.writerow(row)

    md_lines = [
        "# EventAlpha Uploaded Test Kit Run",
        "",
        f"- generated_at: {_utc_now()}",
        f"- output_dir: `{out_dir}`",
        "",
        "## What I changed",
        "",
        "- The uploaded folder did not actually contain the executable scripts referenced in the markdown docs.",
        "- I converted the uploaded decisions sheet into a complete one-shot runnable test program.",
        "- The runner now generates case review, exact portfolio optimization, and a ready quantum pack in one go.",
        "",
        "## Best portfolio",
        "",
        f"- selected_case_ids: {portfolio['best']['selected_case_ids']}",
        f"- selected_assets: {portfolio['best']['selected_assets']}",
        f"- objective: {portfolio['best']['objective']}",
        f"- risk_used: {portfolio['best']['risk_used']}",
        "",
        "## Per-case recommendations",
        "",
    ]
    for row in reviews:
        md_lines.append(
            f"- `{row['case_id']}` -> {row['recommended_action']} / {row['recommended_tier']} / wait {row['recommended_wait_bucket']}s"
        )
    if ibm_submission is not None:
        if ibm_submission.get("mode") == "ibm-suite":
            suite_returncodes = {
                key: run.get("returncode") for key, run in ibm_submission.get("runs", {}).items()
            }
            returncode_text = json.dumps(suite_returncodes, ensure_ascii=False)
        else:
            returncode_text = str(ibm_submission.get("returncode"))
        md_lines.extend(
            [
                "",
                "## IBM submission",
                "",
                f"- mode: `{ibm_submission.get('mode', 'unknown')}`",
                f"- returncode: `{returncode_text}`",
            ]
        )
    if quantum_report is not None:
        md_lines.extend(["", "## IBM quantum comparison", ""])
        if "runs" in quantum_report:
            for key, item in quantum_report["runs"].items():
                md_lines.append(f"- {key}: status={item.get('status') if item else 'N/A'} delta={item.get('delta_vs_exact') if item else 'N/A'}")
        else:
            md_lines.extend(
                [
                    f"- run_file: `{quantum_report.get('run_file', '')}`",
                    f"- jobs_done: `{quantum_report.get('jobs_done')}` / `{quantum_report.get('jobs_total')}`",
                    f"- status: `{quantum_report.get('status')}`",
                ]
            )
            best = quantum_report.get("best_quantum_solution")
            if best:
                md_lines.extend(
                    [
                        f"- best_quantum_selected: {best.get('selected')}",
                        f"- best_quantum_objective: {best.get('objective')}",
                        f"- vs_exact_delta: {quantum_report.get('delta_vs_exact')}",
                        f"- recommendation: {quantum_report.get('recommendation')}",
                    ]
                )
    (out_dir / "SUMMARY.md").write_text("\n".join(md_lines) + "\n")


def maybe_submit_ibm_problem(
    quantum_pack_path: Path,
    backend: str,
    shots: int,
    grid_points: int,
    preset: str,
    *,
    problem: str,
    asset: str = "",
) -> dict:
    cmd = [
        "python3",
        str(IBM_SUBMIT_SCRIPT),
        "--mode",
        "ibm",
        "--submit-only",
        "--backend",
        backend,
        "--problem",
        problem,
        "--pack",
        str(quantum_pack_path),
        "--grid-points",
        str(grid_points),
        "--shots",
        str(shots),
    ]
    if asset:
        cmd.extend(["--asset", asset])
    result = subprocess.run(cmd, capture_output=True, text=True)
    run_file = ""
    match = re.search(r"saved:\s+(\S+eventalpha_quantum_run_\S+\.json)", result.stdout)
    if match:
        run_file = match.group(1)
    return {
        "mode": "ibm-submit",
        "preset": preset,
        "problem": problem,
        "asset": asset or None,
        "command": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "run_file": run_file,
        "shots": shots,
        "grid_points": grid_points,
    }


def maybe_submit_ibm(quantum_pack_path: Path, backend: str, shots: int, grid_points: int, preset: str) -> dict:
    return maybe_submit_ibm_problem(
        quantum_pack_path,
        backend,
        shots,
        grid_points,
        preset,
        problem="asset_subset_selection",
    )


def maybe_submit_ibm_suite(
    quantum_pack_path: Path,
    backend: str,
    shots: int,
    grid_points: int,
    preset: str,
    *,
    wait_asset: str,
) -> dict:
    runs = {
        "asset_subset_selection": maybe_submit_ibm_problem(
            quantum_pack_path, backend, shots, grid_points, preset, problem="asset_subset_selection"
        ),
        "wait_bucket_optimization": maybe_submit_ibm_problem(
            quantum_pack_path, backend, shots, grid_points, preset, problem="wait_bucket_optimization", asset=wait_asset
        ),
        "risk_tier_allocation": maybe_submit_ibm_problem(
            quantum_pack_path, backend, shots, grid_points, preset, problem="risk_tier_allocation"
        ),
    }
    return {
        "mode": "ibm-suite",
        "preset": preset,
        "wait_asset": wait_asset,
        "runs": runs,
    }


def fetch_quantum_status(run_file: str) -> dict:
    cmd = [
        "python3",
        str(IBM_STATUS_SCRIPT),
        "--run-file",
        run_file,
        "--fetch-results",
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "IBM status command failed.")
    payload_text = result.stdout.strip()
    json_start = payload_text.find("{")
    if json_start == -1:
        raise RuntimeError("IBM status output did not contain JSON payload.")
    return json.loads(payload_text[json_start:])


def summarize_quantum_report(status_payload: dict, portfolio: dict, run_file: str, preset: str, shots: int, grid_points: int) -> dict:
    jobs = status_payload.get("jobs", [])
    done_jobs = [j for j in jobs if j.get("status") == "DONE"]
    best_quantum = None
    for job in done_jobs:
        candidate = job.get("best_sampled_solution")
        if not candidate:
            continue
        if best_quantum is None or candidate.get("objective", float("-inf")) > best_quantum.get("objective", float("-inf")):
            best_quantum = candidate
    exact = portfolio["best"]
    delta = None
    recommendation = "No completed quantum solution yet."
    if best_quantum is not None:
        delta = round(best_quantum["objective"] - exact["objective"], 6)
        if delta > 0:
            recommendation = "Quantum sampled solution currently beats the local exact baseline. Review carefully before trusting it."
        elif delta == 0:
            recommendation = "Quantum sampled solution matches the local exact baseline."
        else:
            recommendation = "Quantum sampled solution is below the local exact baseline. Keep local exact selection as decision truth for now."
    return {
        "generated_at": _utc_now(),
        "run_file": run_file,
        "preset": preset,
        "shots": shots,
        "grid_points": grid_points,
        "jobs_total": len(jobs),
        "jobs_done": len(done_jobs),
        "status": "complete" if jobs and len(done_jobs) == len(jobs) else "pending",
        "exact_baseline": exact,
        "best_quantum_solution": best_quantum,
        "delta_vs_exact": delta,
        "recommendation": recommendation,
        "raw_status": status_payload,
    }


def summarize_generic_quantum_report(status_payload: dict, run_file: str, preset: str, shots: int, grid_points: int) -> dict:
    jobs = status_payload.get("jobs", [])
    done_jobs = [j for j in jobs if j.get("status") == "DONE"]
    best_quantum = None
    for job in done_jobs:
        candidate = job.get("best_sampled_solution")
        if not candidate:
            continue
        if best_quantum is None or candidate.get("objective", float("-inf")) > best_quantum.get("objective", float("-inf")):
            best_quantum = candidate
    baseline = status_payload.get("baseline_exact")
    if baseline is None:
        try:
            run_payload = json.loads(Path(run_file).read_text())
            baseline = run_payload.get("baseline_exact")
        except Exception:
            baseline = None
    delta = None
    baseline_objective = None
    if isinstance(baseline, dict):
        baseline_objective = baseline.get("objective", baseline.get("score"))
    if best_quantum is not None and isinstance(baseline_objective, (int, float)):
        delta = round(best_quantum["objective"] - baseline_objective, 6)
    recommendation = "No completed quantum solution yet."
    if best_quantum is not None:
        if delta is None:
            recommendation = "Quantum result fetched. Review against the local baseline for this problem."
        elif delta > 0:
            recommendation = "Quantum sampled solution currently beats the local baseline for this problem. Review carefully."
        elif delta == 0:
            recommendation = "Quantum sampled solution matches the local baseline for this problem."
        else:
            recommendation = "Quantum sampled solution is below the local baseline for this problem."
    return {
        "generated_at": _utc_now(),
        "run_file": run_file,
        "preset": preset,
        "shots": shots,
        "grid_points": grid_points,
        "jobs_total": len(jobs),
        "jobs_done": len(done_jobs),
        "status": "complete" if jobs and len(done_jobs) == len(jobs) else "pending",
        "baseline_exact": baseline,
        "best_quantum_solution": best_quantum,
        "delta_vs_exact": delta,
        "recommendation": recommendation,
        "raw_status": status_payload,
    }


def maybe_wait_for_ibm_result(ibm_submission: dict, portfolio: dict, preset: str, shots: int, grid_points: int, poll_interval: int, max_polls: int) -> dict | None:
    run_file = ibm_submission.get("run_file", "")
    if ibm_submission.get("returncode") != 0 or not run_file:
        return None
    latest_status = None
    for _ in range(max_polls):
        latest_status = fetch_quantum_status(run_file)
        jobs = latest_status.get("jobs", [])
        if jobs and all(job.get("status") == "DONE" for job in jobs):
            break
        time.sleep(poll_interval)
    if latest_status is None:
        return None
    return summarize_quantum_report(latest_status, portfolio, run_file, preset, shots, grid_points)


def maybe_wait_for_ibm_suite_results(
    ibm_submission: dict,
    portfolio: dict,
    preset: str,
    shots: int,
    grid_points: int,
    poll_interval: int,
    max_polls: int,
) -> dict:
    suite_reports = {}
    for key, run in ibm_submission.get("runs", {}).items():
        run_file = run.get("run_file", "")
        if run.get("returncode") != 0 or not run_file:
            suite_reports[key] = None
            continue
        latest_status = None
        for _ in range(max_polls):
            latest_status = fetch_quantum_status(run_file)
            jobs = latest_status.get("jobs", [])
            if jobs and all(job.get("status") == "DONE" for job in jobs):
                break
            time.sleep(poll_interval)
        if latest_status is None:
            suite_reports[key] = None
            continue
        if key == "asset_subset_selection":
            suite_reports[key] = summarize_quantum_report(latest_status, portfolio, run_file, preset, shots, grid_points)
        else:
            suite_reports[key] = summarize_generic_quantum_report(latest_status, run_file, preset, shots, grid_points)
    return suite_reports


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv).expanduser()
    output_root = Path(args.output).expanduser()
    run_dir = output_root / f"run_{_slug_time()}"
    shots, grid_points = resolve_quantum_params(args)

    rows = load_rows(csv_path)
    reviews = build_case_reviews(rows)
    portfolio = optimize_portfolio(rows, args.risk_budget, args.max_assets)
    quantum_pack = build_quantum_pack(rows, args.risk_budget, args.max_assets, portfolio)
    wait_asset = choose_wait_asset(portfolio, reviews)

    quantum_pack_path = run_dir / "quantum_pack.json"
    ibm_submission = None
    quantum_report = None
    run_dir.mkdir(parents=True, exist_ok=True)
    quantum_pack_path.write_text(json.dumps(quantum_pack, ensure_ascii=False, indent=2))

    if args.mode == "ibm-submit":
        ibm_submission = maybe_submit_ibm(quantum_pack_path, args.backend, shots, grid_points, args.preset)
        if args.auto_wait and ibm_submission.get("returncode") == 0:
            quantum_report = maybe_wait_for_ibm_result(
                ibm_submission,
                portfolio,
                args.preset,
                shots,
                grid_points,
                args.poll_interval,
                args.max_polls,
            )
    elif args.mode == "ibm-suite":
        ibm_submission = maybe_submit_ibm_suite(
            quantum_pack_path,
            args.backend,
            shots,
            grid_points,
            args.preset,
            wait_asset=wait_asset,
        )
        if args.auto_wait:
            quantum_report = {
                "mode": "ibm-suite",
                "wait_asset": wait_asset,
                "runs": maybe_wait_for_ibm_suite_results(
                    ibm_submission,
                    portfolio,
                    args.preset,
                    shots,
                    grid_points,
                    args.poll_interval,
                    args.max_polls,
                ),
            }

    write_outputs(run_dir, rows, reviews, portfolio, quantum_pack, ibm_submission, quantum_report)

    print("EventAlpha One-Shot Test Runner")
    print("=" * 60)
    print(f"input_csv: {csv_path}")
    print(f"output_dir: {run_dir}")
    print(f"preset: {args.preset} | shots={shots} | grid_points={grid_points}")
    print("-" * 60)
    print(f"best_selected_case_ids: {portfolio['best']['selected_case_ids']}")
    print(f"best_selected_assets: {portfolio['best']['selected_assets']}")
    print(f"objective: {portfolio['best']['objective']}")
    print(f"risk_used: {portfolio['best']['risk_used']}")
    print(f"wait_asset_for_quantum: {wait_asset}")
    print("-" * 60)
    print("generated files:")
    print(f"- {run_dir / 'case_reviews.csv'}")
    print(f"- {run_dir / 'case_reviews.json'}")
    print(f"- {run_dir / 'portfolio_optimization.json'}")
    print(f"- {run_dir / 'quantum_pack.json'}")
    print(f"- {run_dir / 'SUMMARY.md'}")
    if ibm_submission is not None:
        print("-" * 60)
        if ibm_submission.get("mode") == "ibm-suite":
            print("ibm_suite_submissions:")
            for key, run in ibm_submission.get("runs", {}).items():
                print(f"  - {key}: returncode={run.get('returncode')} run_file={run.get('run_file')}")
        else:
            print(f"ibm_submit_returncode: {ibm_submission['returncode']}")
            print("ibm_submit_stdout:")
            print(ibm_submission["stdout"].strip())
            if ibm_submission["stderr"].strip():
                print("ibm_submit_stderr:")
                print(ibm_submission["stderr"].strip())
    if quantum_report is not None:
        print("-" * 60)
        if "runs" in quantum_report:
            print("ibm_suite_results:")
            for key, item in quantum_report["runs"].items():
                if not item:
                    print(f"  - {key}: N/A")
                    continue
                print(f"  - {key}: jobs_done={item['jobs_done']}/{item['jobs_total']} status={item['status']} delta={fmt_delta(item['delta_vs_exact'])}")
        else:
            print(f"ibm_jobs_done: {quantum_report['jobs_done']}/{quantum_report['jobs_total']}")
            print(f"ibm_status: {quantum_report['status']}")
            print("exact_baseline:")
            print(f"  selected_assets={quantum_report['exact_baseline'].get('selected_assets')}")
            print(f"  objective={quantum_report['exact_baseline'].get('objective')}")
            if quantum_report.get("best_quantum_solution"):
                print("best_quantum_solution:")
                print(f"  selected={quantum_report['best_quantum_solution'].get('selected')}")
                print(f"  objective={quantum_report['best_quantum_solution'].get('objective')}")
                print(f"  shots={quantum_report['best_quantum_solution'].get('shots')}")
                print(f"  bitstring={quantum_report['best_quantum_solution'].get('bitstring')}")
                print(f"delta_vs_exact: {fmt_delta(quantum_report['delta_vs_exact'])}")
        print(f"report_file: {run_dir / 'ibm_quantum_report.json'}")
        print(f"markdown_report: {run_dir / 'IBM_QUANTUM_COMPARISON.md'}")
        if "recommendation" in quantum_report:
            print(f"recommendation: {quantum_report['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
