from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd


ASSETS = ["fx", "rates", "crypto", "oil", "index"]

YEAR_WEIGHTS = {
    2025: 1.50,
    2024: 1.30,
    2023: 1.10,
    2022: 1.00,
    2021: 0.85,
    2020: 0.75,
    2019: 0.65,
    2018: 0.55,
}

WAIT_BUCKETS = [
    ("0_3m", 0, 180),
    ("3_5m", 180, 300),
    ("5_10m", 300, 600),
    ("10_15m", 600, 900),
    ("15_30m", 900, 1800),
    ("30m_plus", 1800, 999999),
]

RISK_TIERS = {"skip": 0.0, "small": 0.5, "normal": 1.0, "heavy": 1.5}


@dataclass
class UnifiedValidationBundle:
    normalized_cases: pd.DataFrame
    entry_cases: pd.DataFrame
    matrix_weighted: pd.DataFrame
    asset_stats: pd.DataFrame
    event_stats: pd.DataFrame
    top_subsets: pd.DataFrame
    champion_subset: list[str]
    champion_row: Dict[str, Any]
    wait_bucket_stats: pd.DataFrame
    risk_tier_top10: list[dict]
    sensitivity_analysis: pd.DataFrame
    linear_scores: Dict[str, float]
    pair_penalties: Dict[str, float]
    correlation_map: Dict[str, Dict[str, float]]


def evidence_level(n: int) -> str:
    if n >= 100:
        return "HIGH"
    if n >= 20:
        return "MEDIUM"
    return "LOW"


def weighted_mean(values: Iterable[float], weights: Iterable[float]) -> float:
    values = np.asarray(list(values), dtype=float)
    weights = np.asarray(list(weights), dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if mask.sum() == 0:
        return 0.0
    return float(np.average(values[mask], weights=weights[mask]))


def infer_year(df: pd.DataFrame) -> pd.Series:
    for col in ["year", "event_date", "entry_date", "state_date", "generated_at", "timestamp", "date"]:
        if col in df.columns:
            years = pd.to_datetime(df[col], errors="coerce").dt.year
            if years.notna().any():
                return years
    return pd.Series([2025] * len(df), index=df.index)


def normalize_cases(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "year" not in out.columns:
        out["year"] = infer_year(out)
    out["year"] = pd.to_numeric(out["year"], errors="coerce").fillna(2025).astype(int)
    out["year_weight"] = out["year"].map(YEAR_WEIGHTS).fillna(0.75)

    if "pnl_pct" not in out.columns:
        for c in ["pnl", "return_pct", "payoff", "avg_pnl"]:
            if c in out.columns:
                out["pnl_pct"] = out[c]
                break
    if "pnl_pct" not in out.columns:
        out["pnl_pct"] = 0.0

    if "confidence" not in out.columns:
        for c in ["execution_confidence", "calibrated_confidence", "avg_confidence"]:
            if c in out.columns:
                out["confidence"] = out[c]
                break
    if "confidence" not in out.columns:
        out["confidence"] = 0.5

    if "wait_seconds" not in out.columns:
        out["wait_seconds"] = 0.0
    if "event_type" not in out.columns:
        out["event_type"] = "unknown"
    if "asset" not in out.columns:
        out["asset"] = "unknown"
    if "profitable" not in out.columns:
        out["profitable"] = pd.to_numeric(out["pnl_pct"], errors="coerce").fillna(0.0) > 0

    out["weighted_pnl_pct"] = pd.to_numeric(out["pnl_pct"], errors="coerce").fillna(0.0) * out["year_weight"]
    out["weighted_profitable"] = out["profitable"].astype(float) * out["year_weight"]
    return out


def asset_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for asset, g in df.groupby("asset"):
        n = len(g)
        weights = g["year_weight"]
        pnl = pd.to_numeric(g["pnl_pct"], errors="coerce").fillna(0.0)
        win = (pnl > 0).astype(float)
        rows.append(
            {
                "asset": asset,
                "samples": int(n),
                "evidence": evidence_level(int(n)),
                "avg_pnl_pct": float(pnl.mean()) if n else 0.0,
                "weighted_avg_pnl_pct": weighted_mean(pnl, weights),
                "win_rate": float(win.mean()) if n else 0.0,
                "weighted_win_rate": weighted_mean(win, weights),
                "avg_confidence": float(pd.to_numeric(g["confidence"], errors="coerce").fillna(0.0).mean()) if n else 0.0,
                "avg_wait_seconds": float(pd.to_numeric(g["wait_seconds"], errors="coerce").fillna(0.0).mean()) if n else 0.0,
                "avg_r_multiple": float(pd.to_numeric(g.get("r_multiple", 0.0), errors="coerce").fillna(0.0).mean()) if n else 0.0,
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=["asset", "samples", "evidence", "avg_pnl_pct", "weighted_avg_pnl_pct", "win_rate", "weighted_win_rate", "avg_confidence", "avg_wait_seconds", "avg_r_multiple"])
    return result.sort_values(["weighted_avg_pnl_pct", "weighted_win_rate"], ascending=False).reset_index(drop=True)


def event_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for event_type, g in df.groupby("event_type"):
        n = len(g)
        weights = g["year_weight"]
        pnl = pd.to_numeric(g["pnl_pct"], errors="coerce").fillna(0.0)
        win = (pnl > 0).astype(float)
        rows.append(
            {
                "event_type": event_type,
                "samples": int(n),
                "evidence": evidence_level(int(n)),
                "avg_pnl_pct": float(pnl.mean()) if n else 0.0,
                "weighted_avg_pnl_pct": weighted_mean(pnl, weights),
                "win_rate": float(win.mean()) if n else 0.0,
                "weighted_win_rate": weighted_mean(win, weights),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=["event_type", "samples", "evidence", "avg_pnl_pct", "weighted_avg_pnl_pct", "win_rate", "weighted_win_rate"])
    return result.sort_values(["weighted_avg_pnl_pct", "weighted_win_rate"], ascending=False).reset_index(drop=True)


def build_weighted_matrix(entry_df: pd.DataFrame) -> pd.DataFrame:
    matrix = (
        entry_df.pivot_table(
            index="case_id",
            columns="asset",
            values="weighted_pnl_pct",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reindex(columns=ASSETS, fill_value=0.0)
        .reset_index()
    )
    return matrix


def subset_objective(asset_df: pd.DataFrame, subset: Iterable[str], risk_budget: float = 2.5) -> float:
    selected = asset_df[asset_df["asset"].isin(list(subset))].copy()
    if selected.empty:
        return -999.0

    edge = float(selected["weighted_avg_pnl_pct"].sum())
    win = float(selected["weighted_win_rate"].mean())
    evidence_bonus = float(selected["samples"].clip(upper=100).sum()) / 1000.0
    size_penalty = max(0, len(selected) - 3) * 0.03
    concentration_penalty = 0.0
    subset_list = list(selected["asset"])
    if "crypto" in subset_list:
        concentration_penalty += 0.015
    if "crypto" in subset_list and "index" in subset_list:
        concentration_penalty += 0.01
    risk_penalty = max(0.0, len(selected) - risk_budget) * 0.02
    return float(edge + win * 0.10 + evidence_bonus - size_penalty - concentration_penalty - risk_penalty)


def rank_subsets(asset_df: pd.DataFrame, risk_budget: float = 2.5, top_n: int = 10) -> pd.DataFrame:
    assets = [a for a in asset_df["asset"].tolist() if a in ASSETS]
    rows = []
    for r in range(1, min(5, len(assets)) + 1):
        for subset in itertools.combinations(assets, r):
            rows.append({"subset": list(subset), "size": r, "risk_budget": risk_budget, "objective": subset_objective(asset_df, subset, risk_budget=risk_budget)})
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=["subset", "size", "risk_budget", "objective"])
    return result.sort_values("objective", ascending=False).head(top_n).reset_index(drop=True)


def sensitivity_analysis(asset_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rb in [1.5, 2.0, 2.5, 3.0, 4.0]:
        top = rank_subsets(asset_df, risk_budget=rb, top_n=1)
        if top.empty:
            continue
        row = top.iloc[0].to_dict()
        rows.append({"risk_budget": rb, "best_subset": row["subset"], "objective": row["objective"]})
    return pd.DataFrame(rows)


def wait_bucket_optimization(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, lo, hi in WAIT_BUCKETS:
        g = df[(pd.to_numeric(df["wait_seconds"], errors="coerce").fillna(0.0) >= lo) & (pd.to_numeric(df["wait_seconds"], errors="coerce").fillna(0.0) < hi)]
        if len(g) == 0:
            continue
        pnl = pd.to_numeric(g["pnl_pct"], errors="coerce").fillna(0.0)
        win = (pnl > 0).astype(float)
        rows.append(
            {
                "wait_bucket": name,
                "samples": int(len(g)),
                "evidence": evidence_level(len(g)),
                "weighted_avg_pnl_pct": weighted_mean(pnl, g["year_weight"]),
                "weighted_win_rate": weighted_mean(win, g["year_weight"]),
                "avg_confidence": float(pd.to_numeric(g["confidence"], errors="coerce").fillna(0.0).mean()),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["wait_bucket", "samples", "evidence", "weighted_avg_pnl_pct", "weighted_win_rate", "avg_confidence"])
    return pd.DataFrame(rows).sort_values("weighted_avg_pnl_pct", ascending=False).reset_index(drop=True)


def risk_tier_allocation(asset_df: pd.DataFrame, champion_subset: list[str], risk_budget: float = 2.5) -> list[dict]:
    candidates = []
    subset_df = asset_df[asset_df["asset"].isin(champion_subset)].copy()
    if subset_df.empty:
        return candidates
    for combo in itertools.product(RISK_TIERS.items(), repeat=len(champion_subset)):
        total_weight = sum(weight for _, weight in combo)
        if total_weight > risk_budget:
            continue
        score = 0.0
        allocation = {}
        for asset, (tier, weight) in zip(champion_subset, combo):
            row = subset_df[subset_df["asset"] == asset].iloc[0]
            edge = float(row["weighted_avg_pnl_pct"])
            win = float(row["weighted_win_rate"])
            evidence = min(float(row["samples"]), 100.0) / 100.0
            score += weight * (edge + 0.10 * win + 0.03 * evidence)
            allocation[asset] = {"tier": tier, "weight": weight}
        candidates.append({"allocation": allocation, "objective": float(score), "total_weight": float(total_weight)})
    return sorted(candidates, key=lambda x: x["objective"], reverse=True)[:10]


def build_linear_scores(asset_df: pd.DataFrame) -> Dict[str, float]:
    scores = {}
    for _, row in asset_df.iterrows():
        scores[row["asset"]] = round(float(row["weighted_avg_pnl_pct"]) + float(row["weighted_win_rate"]) * 0.10 + min(float(row["samples"]), 100.0) / 1000.0, 6)
    return {asset: scores.get(asset, 0.0) for asset in ASSETS}


def build_pair_penalties(weighted_matrix: pd.DataFrame) -> tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    frame = weighted_matrix.reindex(columns=ASSETS, fill_value=0.0).fillna(0.0).copy()
    corr = frame.corr().fillna(0.0).abs()
    pair_penalties = {}
    for a, b in itertools.combinations(ASSETS, 2):
        pair_penalties[f"{a}|{b}"] = round(float(corr.loc[a, b]) * 0.35, 6)
    return pair_penalties, corr.to_dict()


def build_unified_validation_bundle(cases_df: pd.DataFrame, risk_budget: float = 2.5, top_n: int = 10) -> UnifiedValidationBundle:
    normalized = normalize_cases(cases_df)
    entry = normalized[normalized["action"].isin(["enter_small", "enter_normal", "enter_heavy"])].copy()
    asset_df = asset_stats(entry)
    event_df = event_stats(entry)
    weighted_matrix = build_weighted_matrix(entry)
    top_subsets = rank_subsets(asset_df, risk_budget=risk_budget, top_n=top_n)
    champion_row = top_subsets.iloc[0].to_dict() if not top_subsets.empty else {"subset": [], "objective": -999.0, "size": 0, "risk_budget": risk_budget}
    champion_subset = list(champion_row.get("subset", []))
    wait_df = wait_bucket_optimization(entry)
    risk_alloc = risk_tier_allocation(asset_df, champion_subset, risk_budget=risk_budget)
    sensitivity = sensitivity_analysis(asset_df)
    linear_scores = build_linear_scores(asset_df)
    pair_penalties, corr_map = build_pair_penalties(weighted_matrix.set_index(weighted_matrix.columns[0]) if "case_id" in weighted_matrix.columns else weighted_matrix)
    return UnifiedValidationBundle(
        normalized_cases=normalized,
        entry_cases=entry,
        matrix_weighted=weighted_matrix,
        asset_stats=asset_df,
        event_stats=event_df,
        top_subsets=top_subsets,
        champion_subset=champion_subset,
        champion_row=champion_row,
        wait_bucket_stats=wait_df,
        risk_tier_top10=risk_alloc,
        sensitivity_analysis=sensitivity,
        linear_scores=linear_scores,
        pair_penalties=pair_penalties,
        correlation_map=corr_map,
    )

