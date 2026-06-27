#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Any


DESKTOP = Path("/Users/tongyin/Desktop")
DEFAULT_INPUT = DESKTOP / "Test" / "results"
PROJECT_BASE = DESKTOP / "InsightBridge_Financial_Models_Latest"
DEFAULT_OUTDIR = PROJECT_BASE / "reports" / "quantum_research"


PAIR_CORR = {
    frozenset({"fx", "rates"}): 0.55,
    frozenset({"oil", "index"}): 0.35,
    frozenset({"crypto", "index"}): 0.45,
    frozenset({"fx", "index"}): 0.22,
    frozenset({"fx", "oil"}): 0.10,
    frozenset({"oil", "crypto"}): 0.30,
    frozenset({"rates", "index"}): 0.18,
    frozenset({"rates", "oil"}): 0.20,
    frozenset({"fx", "crypto"}): 0.16,
    frozenset({"rates", "crypto"}): 0.24,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune asset-subset penalties for EventAlpha portfolio selection.")
    parser.add_argument("--input", default="", help="Specific decisions_input_snapshot.json path. If omitted, use latest under Desktop/Test/results.")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTDIR / "penalty_results.json"))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTDIR / "penalty_results.csv"))
    return parser.parse_args()


def find_latest_input() -> Path:
    candidates = sorted(DEFAULT_INPUT.glob("run_*/decisions_input_snapshot.json"))
    if not candidates:
        raise FileNotFoundError("No decisions_input_snapshot.json found under Desktop/Test/results")
    return candidates[-1]


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    review_path = path.with_name("case_reviews.json")
    if review_path.exists():
        reviews = json.loads(review_path.read_text(encoding="utf-8"))
        review_map = {row["case_id"]: row for row in reviews}
        for case in cases:
            extra = review_map.get(case.get("case_id"))
            if extra:
                case.update(
                    {
                        "recommended_action": extra.get("recommended_action"),
                        "recommended_tier": extra.get("recommended_tier"),
                        "priority_score": extra.get("priority_score"),
                        "recommended_wait_bucket": extra.get("recommended_wait_bucket"),
                    }
                )
    return cases


def base_case_score(case: dict[str, Any]) -> float:
    confidence = float(case.get("confidence") or 0.0)
    edge = float(case.get("expected_edge_score") or 0.0)
    pnl = float(case.get("observed_pnl") or 0.0)
    action = str(case.get("recommended_action") or case.get("action") or "watch")
    tier = str(case.get("recommended_tier") or "")
    priority = float(case.get("priority_score") or 0.0)
    should_exit = bool(case.get("should_exit"))
    action_bias = {"enter": 0.16, "watch": -0.05, "exit": -0.30}.get(action, 0.0)
    tier_bias = {"heavy": 0.10, "normal": 0.05, "small": 0.0, "skip": -0.18}.get(tier, 0.0)
    exit_penalty = 0.20 if should_exit else 0.0
    return round(
        0.30 * confidence
        + 0.25 * edge
        + 0.12 * max(pnl, 0.0)
        + 0.33 * priority
        + action_bias
        + tier_bias
        - exit_penalty,
        6,
    )


def inferred_risk_units(case: dict[str, Any]) -> float:
    tier = str(case.get("recommended_tier") or "")
    if tier == "heavy":
        return 1.5
    if tier == "normal":
        return 1.0
    if tier == "small":
        return 0.5
    if tier == "skip":
        return 0.0
    risk_frac = float(case.get("max_risk_fraction") or 0.0)
    action = str(case.get("action") or "")
    if action != "enter":
        return 0.5
    if risk_frac >= 0.001:
        return 1.5
    if risk_frac >= 0.0004:
        return 1.0
    return 0.75


def pair_corr(asset_a: str, asset_b: str) -> float:
    return PAIR_CORR.get(frozenset({asset_a, asset_b}), 0.25)


def subset_score(
    subset: tuple[dict[str, Any], ...],
    *,
    lambda_size: float,
    lambda_corr: float,
    lambda_risk: float,
    lambda_marginal: float,
) -> tuple[float, float, float, float]:
    base_sum = sum(base_case_score(case) for case in subset)
    size_penalty = lambda_size * max(0, len(subset) - 2) * 0.45
    corr_penalty = 0.0
    marginal_penalty = 0.0
    risk_units = 0.0

    for case in subset:
        risk_units += inferred_risk_units(case)
        recommended_action = str(case.get("recommended_action") or case.get("action") or "")
        recommended_tier = str(case.get("recommended_tier") or "")
        if recommended_action != "enter":
            marginal_penalty += lambda_marginal * 0.35
        if recommended_tier == "skip":
            marginal_penalty += lambda_marginal * 0.30
        marginal_penalty += lambda_marginal * max(0.0, 0.65 - float(case.get("confidence") or 0.0)) * 0.6

    for left, right in itertools.combinations(subset, 2):
        corr_penalty += lambda_corr * pair_corr(str(left.get("asset")), str(right.get("asset"))) * 0.1

    risk_penalty = lambda_risk * max(0.0, risk_units - 2.5) * 0.30
    objective = base_sum - size_penalty - corr_penalty - risk_penalty - marginal_penalty
    return round(objective, 6), round(base_sum, 6), round(corr_penalty + size_penalty, 6), round(risk_units, 6)


def all_subsets(cases: list[dict[str, Any]]) -> list[tuple[dict[str, Any], ...]]:
    result = []
    for size in range(1, len(cases) + 1):
        result.extend(itertools.combinations(cases, size))
    return result


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser() if args.input else find_latest_input()
    output_json = Path(args.output_json).expanduser()
    output_csv = Path(args.output_csv).expanduser()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    cases = load_cases(input_path)
    subsets = all_subsets(cases)
    lambda_size_values = [0.0, 0.05, 0.10, 0.15]
    lambda_corr_values = [0.5, 1.0, 1.5]
    lambda_risk_values = [0.5, 1.0, 1.5]
    lambda_marginal_values = [0.0, 0.25, 0.5, 0.75]

    rows = []
    winners = Counter()
    best_overall = None
    best_overall_score = float("-inf")
    for lambda_size in lambda_size_values:
        for lambda_corr in lambda_corr_values:
            for lambda_risk in lambda_risk_values:
                for lambda_marginal in lambda_marginal_values:
                    best = None
                    for subset in subsets:
                        score, base_sum, pair_penalty, risk_units = subset_score(
                            subset,
                            lambda_size=lambda_size,
                            lambda_corr=lambda_corr,
                            lambda_risk=lambda_risk,
                            lambda_marginal=lambda_marginal,
                        )
                        if best is None or score > best["best_score"]:
                            best = {
                                "lambda_size": lambda_size,
                                "lambda_corr": lambda_corr,
                                "lambda_risk": lambda_risk,
                                "lambda_marginal": lambda_marginal,
                                "best_subset": "|".join(case["case_id"] for case in subset),
                                "best_score": round(score, 6),
                                "base_score": base_sum,
                                "pair_penalty": pair_penalty,
                                "risk_used": risk_units,
                                "selected_assets": [case["asset"] for case in subset],
                            }
                    assert best is not None
                    rows.append(best)
                    winners[best["best_subset"]] += 1
                    if best["best_score"] > best_overall_score:
                        best_overall = best
                        best_overall_score = best["best_score"]

    with output_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "lambda_size",
                "lambda_corr",
                "lambda_risk",
                "lambda_marginal",
                "best_subset",
                "best_score",
                "base_score",
                "pair_penalty",
                "risk_used",
                "selected_assets",
            ],
        )
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["selected_assets"] = "|".join(row["selected_assets"])
            writer.writerow(row)

    summary = {
        "input_path": str(input_path),
        "grid_size": len(rows),
        "unique_winner_count": len(winners),
        "winner_frequency": winners.most_common(),
        "robust_preferred_subset": winners.most_common(1)[0][0] if winners else "",
        "robust_preferred_share": 0.0 if not rows else round(winners.most_common(1)[0][1] / len(rows), 4),
        "best_overall": best_overall,
    }
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Penalty tuning complete")
    print("=" * 60)
    print(f"input: {input_path}")
    print(f"rows: {len(rows)}")
    print(f"csv: {output_csv}")
    print(f"json: {output_json}")
    if winners:
        top_subset, top_count = winners.most_common(1)[0]
        print(f"robust_preferred_subset: {top_subset} ({top_count}/{len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
