"""
Build a quantum-ready optimization pack from real-history validation outputs.

This converts the latest large-sample validation into abstract optimization tasks
without touching any broker or live finance logic.
"""
from __future__ import annotations

import argparse
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
import sys
if str(BASE / "validation_upgrade") not in sys.path:
    sys.path.insert(0, str(BASE / "validation_upgrade"))

from unified_scoring_engine import YEAR_WEIGHTS, build_unified_validation_bundle, evidence_level
DEFAULT_VALIDATION_DIR = BASE / "reports" / "real_history_validation"
DEFAULT_OUT_DIR = BASE / "reports" / "quantum_tasks"
ASSETS = ["fx", "rates", "crypto", "oil", "index"]
WAIT_BUCKETS = [0, 60, 120, 180, 240, 300]
RISK_TIERS = {"skip": 0.0, "small": 0.5, "normal": 1.0, "heavy": 1.5}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build quantum task pack from real-history validation results.")
    parser.add_argument("--cases-csv", default="", help="Specific validation cases CSV.")
    parser.add_argument("--matrix-csv", default="", help="Specific validation matrix CSV.")
    parser.add_argument("--validation-dir", default=str(DEFAULT_VALIDATION_DIR), help="Directory of validation outputs.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory.")
    parser.add_argument("--top-k", type=int, default=3, help="Target number of selected assets.")
    parser.add_argument("--risk-budget", type=float, default=2.5, help="Abstract total risk budget.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown summary.")
    return parser.parse_args()


def latest_file(folder: Path, pattern: str) -> Path:
    matches = sorted(folder.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matched {pattern} in {folder}")
    return matches[-1]


def load_inputs(args: argparse.Namespace) -> tuple[Path, Path, pd.DataFrame, pd.DataFrame]:
    vdir = Path(args.validation_dir).expanduser()
    cases_path = Path(args.cases_csv).expanduser() if args.cases_csv else latest_file(vdir, "eventalpha_real_history_cases_*.csv")
    matrix_path = Path(args.matrix_csv).expanduser() if args.matrix_csv else latest_file(vdir, "eventalpha_real_history_matrix_*.csv")
    cases = pd.read_csv(cases_path)
    matrix = pd.read_csv(matrix_path)
    return cases_path, matrix_path, cases, matrix


def asset_stat_block(asset_df: pd.DataFrame) -> dict:
    out = {}
    for asset in ASSETS:
        sub = asset_df[asset_df["asset"] == asset].copy()
        if sub.empty:
            out[asset] = {
                "samples": 0,
                "evidence": evidence_level(0),
                "avg_pnl_pct": 0.0,
                "weighted_avg_pnl_pct": 0.0,
                "avg_wait_seconds": 120.0,
                "memory_edge": 0.5,
                "win_rate": 0.0,
                "weighted_win_rate": 0.0,
                "avg_r_multiple": 0.0,
                "signal_strength": 0.5,
            }
            continue
        row = sub.iloc[0]
        out[asset] = {
            "samples": int(row["samples"]),
            "evidence": row["evidence"],
            "avg_pnl_pct": float(row["avg_pnl_pct"]),
            "weighted_avg_pnl_pct": float(row["weighted_avg_pnl_pct"]),
            "avg_wait_seconds": float(row["avg_wait_seconds"]),
            "memory_edge": float(row["avg_confidence"]),
            "win_rate": float(row["win_rate"]),
            "weighted_win_rate": float(row["weighted_win_rate"]),
            "avg_r_multiple": float(row["avg_r_multiple"]),
            "signal_strength": float(row["avg_confidence"]),
        }
    return out


def solve_exact_subset(bundle, top_k: int) -> tuple[dict, dict]:
    linear_scores = bundle.linear_scores
    pair_penalties = bundle.pair_penalties
    champion = bundle.champion_row
    selected = list(champion.get("subset", []))
    bits = [1 if asset in selected else 0 for asset in ASSETS]
    base = sum(linear_scores.get(asset, 0.0) for asset in selected)
    pair = sum(pair_penalties.get(f"{a}|{b}", 0.0) for a, b in itertools.combinations(selected, 2))
    size_penalty = 0.10 * max(0, len(selected) - top_k) ** 2
    best = {
        "bits": bits,
        "selected": selected,
        "objective": round(float(champion.get("objective", 0.0)), 6),
        "base": round(base, 6),
        "pair_penalty": round(pair, 6),
        "size_penalty": round(size_penalty, 6),
        "evidence": asset_stat_block(bundle.asset_stats),
    }
    problem = {
        "problem": "asset_subset_selection",
        "event_type": "multi_event_real_history",
        "qubo_like": {
            "variables": ASSETS,
            "selection_target": top_k,
            "linear_scores": linear_scores,
            "pair_penalties": pair_penalties,
            "cardinality_penalty_lambda": 0.10,
            "year_weights": YEAR_WEIGHTS,
        },
        "best_exact_solution": best,
    }
    return problem, bundle.correlation_map


def solve_wait_problem(cases: pd.DataFrame) -> dict:
    bundle = build_unified_validation_bundle(cases, risk_budget=2.5, top_n=10)
    wait_lookup = {
        row["wait_bucket"]: row for row in bundle.wait_bucket_stats.to_dict(orient="records")
    }
    per_asset = {}
    for asset in ASSETS:
        sub = bundle.asset_stats[bundle.asset_stats["asset"] == asset].copy()
        if len(sub) == 0:
            avg_wait = 120.0
            edge = 0.5
        else:
            avg_wait = float(sub.iloc[0]["avg_wait_seconds"])
            edge = float(sub.iloc[0]["avg_confidence"])
        bucket_scores = []
        for bucket in WAIT_BUCKETS:
            distance = abs(bucket - avg_wait)
            score = 1.0 - min(distance / 300.0, 1.0) + (edge - 0.5) * 0.5
            bucket_scores.append({"wait_seconds": bucket, "score": round(score, 6)})
        best = max(bucket_scores, key=lambda x: x["score"])
        per_asset[asset] = {
            "target_wait_estimate": round(avg_wait, 2),
            "bucket_scores": bucket_scores,
            "best_exact_solution": best,
        }
    return {"problem": "wait_bucket_optimization", "event_type": "multi_event_real_history", "per_asset": per_asset}


def solve_risk_problem(bundle, subset_problem: dict, risk_budget: float) -> dict:
    selected = subset_problem["best_exact_solution"]["selected"]
    top10 = bundle.risk_tier_top10
    best = top10[0] if top10 else {"allocation": {}, "risk_used": 0.0, "objective": 0.0}
    return {
        "problem": "risk_tier_allocation",
        "selected_assets": selected,
        "qubo_like": {
            "selected_assets": selected,
            "tiers": RISK_TIERS,
            "risk_budget": risk_budget,
            "asset_scores": {
                asset: round(bundle.linear_scores.get(asset, 0.0), 6)
                for asset in selected
            },
        },
        "best_exact_solution": best,
    }


def render_markdown(pack: dict) -> str:
    lines = [
        "# EventAlpha Quantum Candidate Pack From Real History",
        "",
        f"- generated_at: {pack['generated_at']}",
        f"- cases_csv: `{pack['cases_csv']}`",
        f"- matrix_csv: `{pack['matrix_csv']}`",
        "",
        "## Why Quantum Matters Here",
        "",
        "- `asset_subset_selection`: This now comes from real historical case-by-asset payoff data, not a toy heuristic.",
        "- `wait_bucket_optimization`: This uses observed wait distributions and confidence structure from the real-history validation run.",
        "- `risk_tier_allocation`: This uses the historically strongest subset and allocates abstract risk tiers under a hard budget.",
        "",
        "## Asset Stats",
        "",
    ]
    for asset, stat in pack["asset_stats"].items():
        lines.append(
            f"- `{asset}`: samples={stat['samples']}, evidence={stat['evidence']}, weighted_avg_pnl_pct={stat['weighted_avg_pnl_pct']:.3f}, weighted_win_rate={stat['weighted_win_rate']*100:.1f}%, avg_wait_seconds={stat['avg_wait_seconds']:.1f}, memory_edge={stat['memory_edge']:.3f}"
        )
    subset = pack["problems"][0]["best_exact_solution"]
    risk = pack["problems"][2]["best_exact_solution"]
    lines.extend(
        [
            "",
            "## Exact Baseline",
            "",
            f"- best subset: {subset['selected']} | objective={subset['objective']}",
            f"- best risk allocation: {json.dumps(risk['allocation'], ensure_ascii=False)} | objective={risk['objective']}",
            "",
            pack["safety_note"],
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    cases_path, matrix_path, cases, matrix = load_inputs(args)
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle = build_unified_validation_bundle(cases, risk_budget=args.risk_budget, top_n=10)
    asset_stats = asset_stat_block(bundle.asset_stats)
    subset_problem, corr_map = solve_exact_subset(bundle, args.top_k)
    wait_problem = solve_wait_problem(cases)
    risk_problem = solve_risk_problem(bundle, subset_problem, args.risk_budget)

    pack = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_base": str(BASE),
        "cases_csv": str(cases_path),
        "matrix_csv": str(matrix_path),
        "event_type": "multi_event_real_history",
        "uncertainties_best_suited_for_quantum": [
            {
                "name": "best_asset_subset",
                "why_quantum_relevant": "This is now based on a real historical payoff matrix across many macro events.",
                "current_gap": "Classical exact search still works at 5 assets, but the workflow is ready for larger baskets and more constraints.",
            },
            {
                "name": "wait_bucket_choice",
                "why_quantum_relevant": "Wait selection is discrete and now grounded in real observed historical validation behavior.",
                "current_gap": "Still approximated with bucket scoring, not global joint optimization.",
            },
            {
                "name": "risk_tier_allocation",
                "why_quantum_relevant": "Cross-asset tier assignment under a budget is a natural constrained combinatorial problem.",
                "current_gap": "Current allocation remains approximate once the basket size expands.",
            },
        ],
        "asset_stats": asset_stats,
        "correlation_map": corr_map,
        "problems": [subset_problem, wait_problem, risk_problem],
        "safety_note": "This pack contains only abstract optimization inputs derived from real historical validation. It places no orders and touches no broker.",
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"eventalpha_quantum_pack_real_history_{stamp}.json"
    md_path = out_dir / f"eventalpha_quantum_pack_real_history_{stamp}.md"
    json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2))
    md_path.write_text(render_markdown(pack))

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(pack).strip())
        print("")
        print(f"Saved JSON: {json_path}")
        print(f"Saved MD: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
