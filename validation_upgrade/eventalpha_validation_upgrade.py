from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from unified_scoring_engine import YEAR_WEIGHTS, build_unified_validation_bundle


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
OUT = BASE / "reports" / "validation_upgrade"
OUT.mkdir(parents=True, exist_ok=True)


def load_latest_csv(pattern: str) -> Path | None:
    candidates = sorted(BASE.glob(pattern))
    if not candidates:
        return None
    return candidates[-1]


def main() -> None:
    cases_path = load_latest_csv("reports/real_history_validation/eventalpha_real_history_cases_*.csv")
    if cases_path is None:
        raise FileNotFoundError("No real-history cases CSV found.")

    cases_df = pd.read_csv(cases_path)
    bundle = build_unified_validation_bundle(cases_df, risk_budget=2.5, top_n=10)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle.asset_stats.to_csv(OUT / f"weighted_asset_stats_{ts}.csv", index=False)
    bundle.event_stats.to_csv(OUT / f"weighted_event_stats_{ts}.csv", index=False)
    bundle.top_subsets.to_csv(OUT / f"top_asset_subsets_{ts}.csv", index=False)
    bundle.sensitivity_analysis.to_csv(OUT / f"sensitivity_analysis_{ts}.csv", index=False)
    bundle.wait_bucket_stats.to_csv(OUT / f"wait_bucket_optimization_{ts}.csv", index=False)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases_source": str(cases_path),
        "year_weights": YEAR_WEIGHTS,
        "champion_subset": bundle.champion_subset,
        "top_subsets": bundle.top_subsets.to_dict(orient="records"),
        "sensitivity_analysis": bundle.sensitivity_analysis.to_dict(orient="records"),
        "wait_bucket_optimization": bundle.wait_bucket_stats.to_dict(orient="records"),
        "risk_tier_allocation_top10": bundle.risk_tier_top10,
        "asset_stats": bundle.asset_stats.to_dict(orient="records"),
        "event_stats": bundle.event_stats.to_dict(orient="records"),
        "recommendation": {
            "current_champion_basket": bundle.champion_subset,
            "use_recent_year_weighting": True,
            "use_evidence_score": True,
            "next_quantum_task": "wait_bucket_optimization",
            "ibkr_stage": "paper_trading_shadow_or_micro_contract",
        },
    }

    out_json = OUT / f"eventalpha_validation_upgrade_{ts}.json"
    out_md = OUT / f"eventalpha_validation_upgrade_{ts}.md"
    out_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md = []
    md.append("# EventAlpha Validation Upgrade Report\n")
    md.append(f"- generated_at: {report['generated_at']}")
    md.append(f"- source: `{cases_path}`\n")
    md.append("## Executive Recommendation\n")
    md.append(f"- Current champion basket: **{', '.join(bundle.champion_subset)}**")
    md.append("- Apply year weighting immediately.")
    md.append("- Use Evidence Score to prevent small-sample overconfidence.")
    md.append("- Promote AWS Quantum next task from asset subset selection to wait bucket optimization.")
    md.append("- Keep IBKR in paper/shadow or micro-contract mode until execution logs accumulate.\n")
    md.append("## Year Weights\n")
    for y, w in YEAR_WEIGHTS.items():
        md.append(f"- {y}: {w}")
    md.append("\n## Top Asset Subsets\n")
    for _, row in bundle.top_subsets.iterrows():
        md.append(f"- {row['subset']} | objective={row['objective']:.6f}")
    md.append("\n## Sensitivity Analysis\n")
    for _, row in bundle.sensitivity_analysis.iterrows():
        md.append(f"- risk_budget={row['risk_budget']} | best={row['best_subset']} | objective={row['objective']:.6f}")
    md.append("\n## Asset Evidence\n")
    for _, row in bundle.asset_stats.iterrows():
        md.append(
            f"- {row['asset']}: samples={row['samples']} | evidence={row['evidence']} | "
            f"weighted_avg_pnl={row['weighted_avg_pnl_pct']:.4f}% | weighted_win_rate={row['weighted_win_rate']:.2%}"
        )
    md.append("\n## Wait Bucket Optimization\n")
    if len(bundle.wait_bucket_stats) == 0:
        md.append("- Not enough wait_seconds data.")
    else:
        for _, row in bundle.wait_bucket_stats.iterrows():
            md.append(
                f"- {row['wait_bucket']}: samples={row['samples']} | evidence={row['evidence']} | "
                f"weighted_avg_pnl={row['weighted_avg_pnl_pct']:.4f}% | weighted_win_rate={row['weighted_win_rate']:.2%}"
            )
    md.append("\n## Risk Tier Allocation Top 3\n")
    for r in bundle.risk_tier_top10[:3]:
        md.append(f"- objective={r['objective']:.6f} | total_weight={r['total_weight']} | allocation={r['allocation']}")
    out_md.write_text("\n".join(md), encoding="utf-8")

    print("Validation upgrade complete.")
    print(out_json)
    print(out_md)


if __name__ == "__main__":
    main()
