from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DEFAULT_PENALTY_JSON = PROJECT_BASE / "reports" / "quantum_research" / "penalty_results.json"


ACTION_WEIGHT = {
    "enter_heavy": 1.00,
    "enter_normal": 0.84,
    "enter_small": 0.68,
    "watch": 0.18,
    "paper_trade": 0.18,
    "ignore": -0.40,
    "reduce": -0.25,
    "exit": -0.50,
}


def load_preferred_assets(path: Path = DEFAULT_PENALTY_JSON) -> dict[str, Any]:
    if not path.exists():
        return {
            "source": str(path),
            "available": False,
            "preferred_assets": [],
            "preferred_case_ids": [],
            "preferred_share": 0.0,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "source": str(path),
            "available": False,
            "preferred_assets": [],
            "preferred_case_ids": [],
            "preferred_share": 0.0,
        }

    subset = str(payload.get("robust_preferred_subset") or "")
    case_ids = [token for token in subset.split("|") if token]
    preferred_assets: list[str] = []
    for case_id in case_ids:
        asset = case_id.split("_", 1)[0].strip()
        if asset and asset not in preferred_assets:
            preferred_assets.append(asset)
    return {
        "source": str(path),
        "available": bool(preferred_assets),
        "preferred_assets": preferred_assets,
        "preferred_case_ids": case_ids,
        "preferred_share": float(payload.get("robust_preferred_share") or 0.0),
    }


def score_decision_candidate(candidate: dict[str, Any], *, preferred_assets: list[str]) -> float:
    decision = candidate.get("decision", {})
    action = str(decision.get("action") or "ignore")
    rank_score = float(candidate.get("rank_score") or 0.0)
    confidence = float(decision.get("execution_confidence") or 0.0)
    raw_score = float(decision.get("raw_score") or 0.0)
    asset = str(candidate.get("asset") or "")
    preferred_bonus = 0.12 if asset in preferred_assets else 0.0
    wait_penalty = min(float(decision.get("wait_seconds") or 0.0) / 2400.0, 0.20)
    return round(
        ACTION_WEIGHT.get(action, -0.30)
        + rank_score * 0.45
        + confidence * 0.40
        + raw_score * 0.08
        + preferred_bonus
        - wait_penalty,
        6,
    )


def select_portfolio_candidates(
    candidates: list[dict[str, Any]],
    *,
    top_n: int,
    preferred_assets: list[str],
) -> dict[str, Any]:
    enriched = []
    for row in candidates:
        score = score_decision_candidate(row, preferred_assets=preferred_assets)
        action = str((row.get("decision") or {}).get("action") or "")
        row_copy = dict(row)
        row_copy["portfolio_score"] = score
        row_copy["preferred_asset"] = str(row.get("asset") or "") in preferred_assets
        row_copy["portfolio_eligible"] = action in {"enter_heavy", "enter_normal", "enter_small", "watch"}
        enriched.append(row_copy)

    eligible = [row for row in enriched if row.get("portfolio_eligible")]
    eligible.sort(key=lambda x: (x["portfolio_score"], x.get("preferred_asset", False)), reverse=True)

    selected = []
    used_assets: set[str] = set()
    overflow = []
    for row in eligible:
        asset = str(row.get("asset") or "")
        if asset in used_assets:
            overflow.append(row)
            continue
        if len(selected) < max(1, top_n):
            selected.append(row)
            used_assets.add(asset)
        else:
            overflow.append(row)
    return {
        "preferred_assets": preferred_assets,
        "selected_assets": [str(row.get("asset") or "") for row in selected],
        "selected_symbols": [str(row.get("symbol") or "") for row in selected],
        "selected_count": len(selected),
        "selected": selected,
        "overflow": overflow[:10],
    }
