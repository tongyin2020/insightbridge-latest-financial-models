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


def asset_stat_block(cases: pd.DataFrame) -> dict:
    out = {}
    for asset in ASSETS:
        sub = cases[cases["asset"] == asset].copy()
        entries = sub[sub["action"].isin(["enter_small", "enter_normal", "enter_heavy"])].copy()
        out[asset] = {
            "samples": int(len(entries)),
            "avg_pnl_pct": float(entries["pnl_pct"].mean()) if len(entries) else 0.0,
            "avg_wait_seconds": float(sub["wait_seconds"].mean()) if len(sub) else 120.0,
            "memory_edge": float(sub["execution_confidence"].mean()) if len(sub) else 0.5,
            "win_rate": float(entries["profitable"].mean()) if len(entries) else 0.0,
            "avg_r_multiple": float(entries["r_multiple"].mean()) if len(entries) else 0.0,
            "signal_strength": float(sub["execution_confidence"].mean()) if len(sub) else 0.5,
        }
    return out


def solve_exact_subset(matrix: pd.DataFrame, top_k: int) -> tuple[dict, dict]:
    frame = matrix[ASSETS].fillna(0.0).copy()
    corr = frame.corr().fillna(0.0).abs()
    per_asset_mean = frame.mean(axis=0).to_dict()
    per_asset_win = (frame > 0).mean(axis=0).to_dict()
    linear_scores = {
        asset: round(float(per_asset_mean.get(asset, 0.0)) + float(per_asset_win.get(asset, 0.0)) * 4.0, 6)
        for asset in ASSETS
    }
    pair_penalties = {}
    for a, b in itertools.combinations(ASSETS, 2):
        pair_penalties[f"{a}|{b}"] = round(float(corr.loc[a, b]) * 0.35, 6)

    lam = 0.10
    best = None
    for bits in itertools.product([0, 1], repeat=len(ASSETS)):
        selected = [ASSETS[i] for i, bit in enumerate(bits) if bit]
        base = sum(linear_scores[a] for a in selected)
        pair = sum(pair_penalties[f"{a}|{b}"] for a, b in itertools.combinations(selected, 2))
        size_penalty = lam * (len(selected) - top_k) ** 2
        objective = base - pair - size_penalty
        candidate = {
            "bits": list(bits),
            "selected": selected,
            "objective": round(objective, 6),
            "base": round(base, 6),
            "pair_penalty": round(pair, 6),
            "size_penalty": round(size_penalty, 6),
        }
        if best is None or candidate["objective"] > best["objective"]:
            best = candidate
    assert best is not None
    problem = {
        "problem": "asset_subset_selection",
        "event_type": "multi_event_real_history",
        "qubo_like": {
            "variables": ASSETS,
            "selection_target": top_k,
            "linear_scores": linear_scores,
            "pair_penalties": pair_penalties,
            "cardinality_penalty_lambda": lam,
        },
        "best_exact_solution": best,
    }
    return problem, corr.to_dict()


def solve_wait_problem(cases: pd.DataFrame) -> dict:
    per_asset = {}
    for asset in ASSETS:
        sub = cases[cases["asset"] == asset].copy()
        if len(sub) == 0:
            avg_wait = 120.0
            edge = 0.5
        else:
            avg_wait = float(sub["wait_seconds"].mean())
            edge = float(sub["execution_confidence"].mean())
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


def solve_risk_problem(asset_stats: dict, subset_problem: dict, risk_budget: float) -> dict:
    selected = subset_problem["best_exact_solution"]["selected"]
    best = None
    for combo in itertools.product(RISK_TIERS.items(), repeat=len(selected)):
        risk_used = sum(weight for _, weight in combo)
        if risk_used > risk_budget:
            continue
        allocation = {}
        objective = 0.0
        for asset, (tier_name, weight) in zip(selected, combo):
            stat = asset_stats[asset]
            score = stat["avg_pnl_pct"] + stat["win_rate"] * 5.0 + stat["memory_edge"]
            objective += score * weight
            allocation[asset] = {"tier": tier_name, "weight": weight}
        objective -= max(0.0, risk_budget - risk_used) * 0.1
        candidate = {
            "allocation": allocation,
            "risk_used": round(risk_used, 6),
            "objective": round(objective, 6),
        }
        if best is None or candidate["objective"] > best["objective"]:
            best = candidate
    return {
        "problem": "risk_tier_allocation",
        "selected_assets": selected,
        "qubo_like": {
            "selected_assets": selected,
            "tiers": RISK_TIERS,
            "risk_budget": risk_budget,
            "asset_scores": {
                asset: round(asset_stats[asset]["avg_pnl_pct"] + asset_stats[asset]["win_rate"] * 5.0 + asset_stats[asset]["memory_edge"], 6)
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
            f"- `{asset}`: samples={stat['samples']}, avg_pnl_pct={stat['avg_pnl_pct']:.3f}, win_rate={stat['win_rate']*100:.1f}%, avg_wait_seconds={stat['avg_wait_seconds']:.1f}, memory_edge={stat['memory_edge']:.3f}"
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

    asset_stats = asset_stat_block(cases)
    subset_problem, corr_map = solve_exact_subset(matrix, args.top_k)
    wait_problem = solve_wait_problem(cases)
    risk_problem = solve_risk_problem(asset_stats, subset_problem, args.risk_budget)

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
