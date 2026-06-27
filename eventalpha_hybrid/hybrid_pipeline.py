from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eventalpha_core import (
    AssetClass,
    EventAlphaBrain,
    EventMemoryDB,
    EventTradeRecord,
    EventType,
    LearningEngine,
    MacroEvent,
    MarketState,
)


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
REPORTS_DIR = BASE / "reports"
QUANTUM_RUNS_DIR = REPORTS_DIR / "quantum_runs"
QUANTUM_TASKS_DIR = REPORTS_DIR / "quantum_tasks"
HYBRID_RUNS_DIR = REPORTS_DIR / "hybrid_runs"

ASSET_MODULE_PATHS = {
    AssetClass.CRYPTO: BASE / "01_Crypto_BTC_ETH_SOL" / "eventalpha_adapter.py",
    AssetClass.OIL: BASE / "04_WTI_Oil_Futures" / "backend" / "eventalpha_adapter.py",
    AssetClass.FX: BASE / "03_FX_AUD_NZD_EUR_GBP" / "backend" / "eventalpha_adapter.py",
    AssetClass.RATES: BASE / "05_Bond_Treasury" / "backend" / "eventalpha_adapter.py",
    AssetClass.INDEX: BASE / "02_StockIndex_IBKR_ES_NQ" / "eventalpha_adapter.py",
}

ASSET_RUNTIME_KWARGS = {
    AssetClass.CRYPTO: {"symbol": "BTC"},
    AssetClass.OIL: {"symbol": "WTI", "current_price": 73.4},
    AssetClass.FX: {"pair": "AUD/USD"},
    AssetClass.RATES: {},
    AssetClass.INDEX: {},
}


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def build_event(event_type: str, title: str) -> MacroEvent:
    et = EventType(event_type)
    default_scores = {
        EventType.CPI: dict(surprise_score=0.72, policy_score=0.68, source_confidence=0.82, narrative_bias=-0.10),
        EventType.FOMC: dict(surprise_score=0.66, policy_score=0.82, source_confidence=0.86, narrative_bias=-0.08),
        EventType.NFP: dict(surprise_score=0.62, policy_score=0.54, source_confidence=0.78, narrative_bias=0.02),
        EventType.OPEC: dict(surprise_score=0.64, geopolitical_score=0.22, source_confidence=0.80, narrative_bias=0.18),
        EventType.EIA_INVENTORY: dict(surprise_score=0.58, source_confidence=0.74, narrative_bias=0.12),
        EventType.GEOPOLITICAL: dict(geopolitical_score=0.84, liquidity_score=0.42, source_confidence=0.78, narrative_bias=0.20),
        EventType.LIQUIDITY_SHOCK: dict(liquidity_score=0.88, source_confidence=0.80, narrative_bias=-0.18),
    }.get(et, dict(source_confidence=0.70, surprise_score=0.40))
    return MacroEvent(
        event_id=f"{et.value}_{_utc_now().strftime('%Y%m%d%H%M%S')}",
        event_type=et,
        title=title,
        source="eventalpha_hybrid_pipeline",
        human_thesis=title,
        expected_assets=[AssetClass.FX, AssetClass.RATES, AssetClass.CRYPTO, AssetClass.OIL, AssetClass.INDEX],
        **default_scores,
    )


def market_state_from_adapter(payload: dict[str, Any]) -> MarketState:
    raw = payload["market_state"]["eventalpha_market_state"]
    return MarketState(
        asset=AssetClass(raw["asset"]),
        symbol=raw["symbol"],
        timestamp_utc=_utc_now(),
        price=float(raw["price"]),
        spread_bps=float(raw["spread_bps"]),
        volatility_z=float(raw["volatility_z"]),
        momentum_score=float(raw["momentum_score"]),
        reversal_score=float(raw["reversal_score"]),
        liquidity_score=float(raw["liquidity_score"]),
        cross_asset_alignment=float(raw["cross_asset_alignment"]),
        news_alignment=float(raw["news_alignment"]),
        orderbook_pressure=float(raw["orderbook_pressure"]),
        trend_persistence=float(raw.get("trend_persistence", 0.5)),
        execution_quality=float(raw.get("execution_quality", 0.5)),
        breakout_quality=float(raw.get("breakout_quality", 0.5)),
        raw=raw.get("raw", {}),
    )


def load_adapters() -> dict[AssetClass, Any]:
    modules: dict[AssetClass, Any] = {}
    for asset, path in ASSET_MODULE_PATHS.items():
        modules[asset] = load_module(f"{asset.value}_adapter_hybrid", path)
    return modules


def collect_states(modules: dict[AssetClass, Any]) -> tuple[dict[AssetClass, dict[str, Any]], dict[AssetClass, MarketState]]:
    adapter_payloads: dict[AssetClass, dict[str, Any]] = {}
    states: dict[AssetClass, MarketState] = {}
    for asset, module in modules.items():
        payload = module.get_market_state(**ASSET_RUNTIME_KWARGS[asset])
        adapter_payloads[asset] = payload
        states[asset] = market_state_from_adapter(payload)
    return adapter_payloads, states


def load_latest_json(pattern: str, base_dir: Path) -> tuple[Path | None, dict[str, Any] | list[Any] | None]:
    files = sorted(base_dir.glob(pattern))
    if not files:
        return None, None
    path = files[-1]
    return path, json.loads(path.read_text(encoding="utf-8"))


def normalize_quantum_subset(pack: dict[str, Any], run_payload: dict[str, Any] | None) -> dict[str, Any]:
    if run_payload and isinstance(run_payload.get("baseline_exact"), dict):
        baseline = run_payload["baseline_exact"]
        return {
            "source": "latest_ibm_asset_subset_baseline",
            "selected_assets": baseline.get("selected", []),
            "objective": float(baseline.get("objective", 0.0)),
            "raw": baseline,
        }
    problem = pack["problems"]["asset_subset_selection"]
    baseline = problem.get("best_exact_solution", {})
    return {
        "source": "latest_pack_exact_subset",
        "selected_assets": baseline.get("selected", []),
        "objective": float(baseline.get("objective", 0.0)),
        "raw": baseline,
    }


def normalize_quantum_waits(pack: dict[str, Any], run_payload: dict[str, Any] | None) -> dict[str, Any]:
    waits: dict[str, int] = {}
    if run_payload and isinstance(run_payload.get("baseline_exact"), list):
        for row in run_payload["baseline_exact"]:
            waits[str(row["asset"])] = int(row["wait_seconds"])
        return {
            "source": "latest_ibm_wait_baseline",
            "waits": waits,
            "raw": run_payload["baseline_exact"],
        }

    per_asset = pack["problems"]["wait_bucket_optimization"]["per_asset"]
    raw_rows = []
    for asset, block in per_asset.items():
        best = block.get("best_exact_solution", {})
        if "wait_seconds" in best:
            waits[str(asset)] = int(best["wait_seconds"])
            raw_rows.append({"asset": asset, **best})
    return {
        "source": "latest_pack_exact_waits",
        "waits": waits,
        "raw": raw_rows,
    }


@dataclass
class GuardrailResult:
    passed: bool
    state_label: str
    signal_strength: str
    reasons: list[str]


def evaluate_guardrails(state: MarketState, confidence: float, risk_fraction: float) -> GuardrailResult:
    reasons: list[str] = []
    if state.spread_bps > 35:
        reasons.append(f"spread_high:{state.spread_bps:.1f}bps")
    if state.liquidity_score < 0.35:
        reasons.append(f"liquidity_low:{state.liquidity_score:.2f}")
    if state.execution_quality < 0.35:
        reasons.append(f"execution_quality_low:{state.execution_quality:.2f}")
    if state.news_alignment < 0.35:
        reasons.append(f"news_alignment_low:{state.news_alignment:.2f}")
    if state.cross_asset_alignment < 0.30:
        reasons.append(f"cross_asset_low:{state.cross_asset_alignment:.2f}")
    if state.reversal_score > 0.72:
        reasons.append(f"reversal_high:{state.reversal_score:.2f}")
    if risk_fraction <= 0:
        reasons.append("risk_fraction_zero")

    if confidence >= 0.86 and not reasons:
        state_label = "STRONG"
    elif confidence >= 0.78 and len(reasons) <= 1:
        state_label = "HEALTHY"
    elif confidence >= 0.70:
        state_label = "CAUTION"
    else:
        state_label = "WATCH"

    if confidence >= 0.88:
        signal_strength = "Very Strong"
    elif confidence >= 0.80:
        signal_strength = "Strong"
    elif confidence >= 0.72:
        signal_strength = "Moderate"
    else:
        signal_strength = "Weak"

    return GuardrailResult(
        passed=not reasons,
        state_label=state_label,
        signal_strength=signal_strength,
        reasons=reasons,
    )


def size_positions(
    selected_rows: list[dict[str, Any]],
    states: dict[AssetClass, MarketState],
    asset_stats: dict[str, Any],
    *,
    total_risk_budget: float,
) -> list[dict[str, Any]]:
    raw_scores: list[float] = []
    for row in selected_rows:
        asset = str(row["asset"])
        decision = row["decision"]
        state = states[AssetClass(asset)]
        stat = asset_stats.get(asset, {})
        confidence = float(decision["execution_confidence"])
        action = str(decision.get("action") or "")
        direction = str(decision.get("direction") or "")
        if action not in {"enter_small", "enter_normal", "enter_heavy"} or direction == "flat":
            row["_sizing_raw_score"] = 0.0
            raw_scores.append(0.0)
            continue
        signal_strength = float(stat.get("signal_strength", stat.get("memory_edge", 0.5)) or 0.5)
        spread_factor = _clip(1.0 - state.spread_bps / 60.0, 0.20, 1.00)
        vol_factor = _clip(1.15 - max(0.0, state.volatility_z - 1.0) * 0.10, 0.35, 1.10)
        liq_factor = _clip(0.60 + state.liquidity_score * 0.60, 0.40, 1.20)
        raw_score = max(0.01, confidence - 0.69) * signal_strength * spread_factor * vol_factor * liq_factor
        row["_sizing_raw_score"] = raw_score
        raw_scores.append(raw_score)

    total_raw = sum(raw_scores) or 1.0
    sized_rows: list[dict[str, Any]] = []
    for row in selected_rows:
        asset = str(row["asset"])
        decision = row["decision"]
        state = states[AssetClass(asset)]
        allocation_share = row["_sizing_raw_score"] / total_raw
        risk_fraction = round(total_risk_budget * allocation_share, 6)
        max_risk_fraction = float(decision.get("max_risk_fraction", 0.0) or 0.0)
        if max_risk_fraction > 0:
            risk_fraction = min(risk_fraction, max_risk_fraction)
        else:
            risk_fraction = 0.0
        guardrails = evaluate_guardrails(state, float(decision["execution_confidence"]), risk_fraction)
        if risk_fraction >= 0.011:
            size_band = "heavy"
        elif risk_fraction >= 0.006:
            size_band = "normal"
        elif risk_fraction > 0:
            size_band = "small"
        else:
            size_band = "skip"

        row = dict(row)
        row["classical_position_sizing"] = {
            "risk_fraction": risk_fraction,
            "portfolio_share": round(allocation_share, 4),
            "size_band": size_band,
        }
        row["guardrails"] = asdict(guardrails)
        row["eligible_for_paper_execution"] = bool(guardrails.passed and risk_fraction > 0)
        row.pop("_sizing_raw_score", None)
        sized_rows.append(row)
    return sized_rows


def append_hybrid_learning(memory_db_path: Path, event: MacroEvent, rows: list[dict[str, Any]], states: dict[AssetClass, MarketState]) -> None:
    db = EventMemoryDB(str(memory_db_path))
    for row in rows:
        if not row.get("eligible_for_paper_execution"):
            continue
        decision = row["decision"]
        asset_enum = AssetClass(str(row["asset"]))
        state = states[asset_enum]
        db.append(
            EventTradeRecord(
                event_id=event.event_id,
                event_type=event.event_type.value,
                asset=str(row["asset"]),
                symbol=str(row["symbol"]),
                thesis=event.title,
                entry_confidence=float(decision["execution_confidence"]),
                seconds_waited=int(decision["wait_seconds"]),
                direction=str(decision["direction"]),
                entry_price=float(state.price),
                exit_price=None,
                mfe_pct=0.0,
                mae_pct=0.0,
                pnl_pct=0.0,
                exit_reason="hybrid_paper_candidate_logged",
            )
        )


def run_hybrid_eventalpha(
    *,
    event_type: str,
    title: str,
    top_n: int = 3,
    confidence_threshold: float = 0.70,
    total_risk_budget: float = 0.02,
    write_learning: bool = True,
) -> dict[str, Any]:
    modules = load_adapters()
    adapter_payloads, states = collect_states(modules)

    memory_path = REPORTS_DIR / "eventalpha_memory.sqlite"
    learning = LearningEngine(EventMemoryDB(str(memory_path)))
    brain = EventAlphaBrain(learning, max_account_risk=total_risk_budget)
    event = build_event(event_type, title)

    ranks = brain.rank_assets_for_event(event, states)
    candidate_rows: list[dict[str, Any]] = []
    for rank in ranks:
        state = states[rank.asset]
        related = {asset.value: s for asset, s in states.items() if asset != rank.asset}
        decision = brain.decide(event, state, related=related)
        candidate_rows.append(
            {
                "asset": rank.asset.value,
                "symbol": rank.symbol,
                "rank_score": rank.score,
                "rank_reasons": rank.reasons,
                "decision": {
                    "action": decision.action.value,
                    "grade": decision.grade.value,
                    "direction": decision.direction.value,
                    "raw_score": decision.raw_score,
                    "calibrated_confidence": decision.calibrated_confidence,
                    "execution_confidence": decision.execution_confidence,
                    "wait_seconds": decision.wait_seconds,
                    "max_risk_fraction": decision.max_risk_fraction,
                    "reasons": decision.reasons,
                    "metadata": decision.metadata,
                },
                "market_state": {
                    "price": state.price,
                    "spread_bps": state.spread_bps,
                    "volatility_z": state.volatility_z,
                    "liquidity_score": state.liquidity_score,
                    "news_alignment": state.news_alignment,
                    "cross_asset_alignment": state.cross_asset_alignment,
                    "reversal_score": state.reversal_score,
                    "execution_quality": state.execution_quality,
                },
            }
        )

    pack_path, pack_payload = load_latest_json("eventalpha_quantum_pack_*.json", QUANTUM_TASKS_DIR)
    subset_run_path, subset_run_payload = load_latest_json("eventalpha_quantum_run_asset_subset_selection_ibm_*.json", QUANTUM_RUNS_DIR)
    wait_run_path, wait_run_payload = load_latest_json("eventalpha_quantum_run_wait_bucket_optimization_ibm_*.json", QUANTUM_RUNS_DIR)
    if not isinstance(pack_payload, dict):
        raise FileNotFoundError("No EventAlpha quantum pack found for hybrid pipeline.")

    quantum_subset = normalize_quantum_subset(pack_payload, subset_run_payload if isinstance(subset_run_payload, dict) else None)
    quantum_waits = normalize_quantum_waits(pack_payload, wait_run_payload if isinstance(wait_run_payload, dict) else None)
    asset_stats = pack_payload.get("asset_stats", {})

    selected_assets = set(quantum_subset["selected_assets"])
    hybrid_pool: list[dict[str, Any]] = []
    blocked_by_confidence: list[dict[str, Any]] = []
    blocked_by_quantum_subset: list[dict[str, Any]] = []

    for row in candidate_rows:
        asset = str(row["asset"])
        decision = row["decision"]
        confidence = float(decision["execution_confidence"])
        row = dict(row)
        row["signal_strength"] = asset_stats.get(asset, {}).get("signal_strength")
        row["quantum_selected"] = asset in selected_assets
        row["quantum_wait_seconds"] = quantum_waits["waits"].get(asset, int(decision["wait_seconds"]))
        row["decision"]["wait_seconds"] = row["quantum_wait_seconds"]
        if asset not in selected_assets:
            blocked_by_quantum_subset.append(row)
            continue
        if confidence < confidence_threshold:
            blocked_by_confidence.append(row)
            continue
        hybrid_pool.append(row)

    hybrid_pool.sort(
        key=lambda row: (
            float(row["decision"]["execution_confidence"]),
            float(row["rank_score"]),
        ),
        reverse=True,
    )
    hybrid_pool = hybrid_pool[: max(1, top_n)]

    sized_rows = size_positions(
        hybrid_pool,
        states,
        asset_stats,
        total_risk_budget=total_risk_budget,
    )

    if write_learning:
        append_hybrid_learning(memory_path, event, sized_rows, states)

    eligible_rows = [row for row in sized_rows if row.get("eligible_for_paper_execution")]
    blocked_rows = [row for row in sized_rows if not row.get("eligible_for_paper_execution")]

    report = {
        "generated_at": _utc_now().isoformat(),
        "mode": "hybrid_quantum_classical_paper",
        "event": {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "title": event.title,
        },
        "runtime_sources": {
            "quantum_pack": str(pack_path) if pack_path else None,
            "subset_run": str(subset_run_path) if subset_run_path else None,
            "wait_run": str(wait_run_path) if wait_run_path else None,
        },
        "hybrid_principle": "Quantum for discovery and timing, Classical for sizing and safety.",
        "quantum_subset": quantum_subset,
        "quantum_waits": quantum_waits,
        "candidate_decisions": candidate_rows,
        "blocked_by_quantum_subset": blocked_by_quantum_subset,
        "blocked_by_confidence": blocked_by_confidence,
        "hybrid_selected": sized_rows,
        "ready_for_paper_execution": eligible_rows,
        "blocked_by_guardrails": blocked_rows,
        "summary": {
            "candidate_count": len(candidate_rows),
            "quantum_selected_count": len(selected_assets),
            "hybrid_pool_count": len(hybrid_pool),
            "ready_count": len(eligible_rows),
            "blocked_subset_count": len(blocked_by_quantum_subset),
            "blocked_confidence_count": len(blocked_by_confidence),
            "blocked_guardrail_count": len(blocked_rows),
            "total_allocated_risk_fraction": round(
                sum(float(row["classical_position_sizing"]["risk_fraction"]) for row in eligible_rows), 6
            ),
        },
        "note": "Paper-only hybrid run. No broker orders were sent.",
    }

    HYBRID_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HYBRID_RUNS_DIR / f"eventalpha_hybrid_{event.event_type.value}_{_utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["saved_to"] = str(out_path)
    return report
