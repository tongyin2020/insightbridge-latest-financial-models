"""
Unified EventAlpha paper runner on top of the five financial model adapters.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from eventalpha_core import (
    AssetClass,
    EventAlphaBrain,
    EventMemoryDB,
    EventTradeRecord,
    EventType,
    LearningEngine,
    MacroEvent,
    MarketState,
    PositionState,
)
from eventalpha_core.telegram_notify import EventAlphaTelegramNotifier


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def market_state_from_adapter(payload: dict) -> MarketState:
    raw = payload["market_state"]["eventalpha_market_state"]
    return MarketState(
        asset=AssetClass(raw["asset"]),
        symbol=raw["symbol"],
        timestamp_utc=datetime.now(timezone.utc),
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
        event_id=f"{et.value}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        event_type=et,
        title=title,
        source="manual_eventalpha_runner",
        human_thesis=title,
        expected_assets=[AssetClass.FX, AssetClass.RATES, AssetClass.CRYPTO, AssetClass.OIL, AssetClass.INDEX],
        **default_scores,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-type", default="cpi")
    parser.add_argument("--title", default="Manual EventAlpha paper event")
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--telegram-alerts", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    modules = {
        AssetClass.CRYPTO: load_module("crypto_adapter", BASE / "01_Crypto_BTC_ETH_SOL" / "eventalpha_adapter.py"),
        AssetClass.OIL: load_module("oil_adapter", BASE / "04_WTI_Oil_Futures" / "backend" / "eventalpha_adapter.py"),
        AssetClass.FX: load_module("fx_adapter", BASE / "03_FX_AUD_NZD_EUR_GBP" / "backend" / "eventalpha_adapter.py"),
        AssetClass.RATES: load_module("bond_adapter", BASE / "05_Bond_Treasury" / "backend" / "eventalpha_adapter.py"),
        AssetClass.INDEX: load_module("index_adapter", BASE / "02_StockIndex_IBKR_ES_NQ" / "eventalpha_adapter.py"),
    }

    adapter_states = {
        AssetClass.CRYPTO: modules[AssetClass.CRYPTO].get_market_state(symbol="BTC"),
        AssetClass.OIL: modules[AssetClass.OIL].get_market_state(symbol="WTI", current_price=73.4),
        AssetClass.FX: modules[AssetClass.FX].get_market_state(pair="AUD/USD"),
        AssetClass.RATES: modules[AssetClass.RATES].get_market_state(),
        AssetClass.INDEX: modules[AssetClass.INDEX].get_market_state(),
    }
    states = {asset: market_state_from_adapter(payload) for asset, payload in adapter_states.items()}

    memory_path = BASE / "reports" / "eventalpha_memory.sqlite"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    learning = LearningEngine(EventMemoryDB(str(memory_path)))
    brain = EventAlphaBrain(learning, max_account_risk=0.02)
    event = build_event(args.event_type, args.title)

    ranks = brain.rank_assets_for_event(event, states)
    selected = ranks[: max(1, args.top_n)]

    decisions = []
    executions = []
    exit_reviews = []
    regime_snapshots = []
    telegram_notifications = []
    telegram_summary = {
        "requested": bool(args.telegram_alerts),
        "configured": False,
        "entry_candidates": 0,
        "sent_count": 0,
        "results": [],
    }
    for rank in selected:
        state = states[rank.asset]
        related = {
            a.value: s for a, s in states.items() if a != rank.asset
        }
        decision = brain.decide(event, state, related=related)
        regime_snapshots.append(
            {
                "asset": rank.asset.value,
                "symbol": rank.symbol,
                "macro_regime": decision.metadata.get("macro_regime"),
                "macro_regime_probabilities": decision.metadata.get("macro_regime_probabilities", {}),
                "macro_regime_explanation": decision.metadata.get("macro_regime_explanation", []),
            }
        )
        decisions.append(
            {
                "asset": rank.asset.value,
                "symbol": rank.symbol,
                "rank_score": rank.score,
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
            }
        )
        if decision.action in {
            decision.action.ENTER_SMALL,
            decision.action.ENTER_NORMAL,
            decision.action.ENTER_HEAVY,
        }:
            capital = 100000.0
            risk_bias = learning.risk_multiplier_bias(event.event_type, rank.asset)
            scaled_capital = capital * max(0.5, min(1.5, 1.0 + risk_bias))
            result = modules[rank.asset].execute_decision(
                {
                    "symbol": rank.symbol,
                    "market_state": adapter_states[rank.asset]["market_state"],
                    "capital": scaled_capital,
                }
            )
            executions.append({"asset": rank.asset.value, "result": result})
            learning.memory.append(
                EventTradeRecord(
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    asset=rank.asset.value,
                    symbol=rank.symbol,
                    thesis=event.title,
                    entry_confidence=decision.execution_confidence,
                    seconds_waited=decision.wait_seconds,
                    direction=decision.direction.value,
                    entry_price=state.price,
                    exit_price=None,
                    mfe_pct=0.0,
                    mae_pct=0.0,
                    pnl_pct=0.0,
                    exit_reason="paper_entry_logged_only",
                )
            )
            position = PositionState(
                asset=rank.asset,
                symbol=rank.symbol,
                direction=decision.direction,
                entry_price=state.price,
                current_price=state.price * (1.0 + 0.004),
                max_price_since_entry=state.price * (1.0 + 0.009),
                min_price_since_entry=state.price * (1.0 - 0.003),
                seconds_in_trade=max(decision.wait_seconds, 900),
                confidence_at_entry=decision.execution_confidence,
                confidence_now=max(0.05, decision.execution_confidence - 0.08),
                spread_bps=state.spread_bps,
                momentum_score=state.momentum_score,
                reversal_score=state.reversal_score,
                cross_asset_alignment=state.cross_asset_alignment,
                news_alignment=state.news_alignment,
                thesis_validity=state.news_alignment,
                market_quality=state.execution_quality,
                momentum_persistence=state.trend_persistence,
                raw={"paper_runner": True},
            )
            exit_signal = brain.assess_exit(
                position,
                mfe_r_multiple=1.2,
                current_r_multiple=0.5,
            )
            adapter_exit = modules[rank.asset].manage_position(
                {
                    "symbol": rank.symbol,
                    "position_id": result.get("position_id"),
                    "direction": decision.direction.value,
                    "side": decision.direction.value,
                    "entry_price": state.price,
                    "current_price": state.price * (1.0 + 0.004),
                    "stop_loss": state.price * (0.992 if decision.direction.value == "long" else 1.008),
                    "pnl_pct": 0.4,
                    "pnl_pips": 9,
                    "pnl_points": 14,
                    "unrealized_pnl": 0.4,
                }
            )
            exit_reviews.append(
                {
                    "asset": rank.asset.value,
                    "symbol": rank.symbol,
                    "brain_exit": {
                        "action": exit_signal.action.value,
                        "urgency": exit_signal.urgency,
                        "reason": exit_signal.reason,
                        "reduce_fraction": exit_signal.reduce_fraction,
                        "metadata": exit_signal.metadata,
                    },
                    "adapter_exit": adapter_exit,
                }
            )

    if args.telegram_alerts:
        notifier = EventAlphaTelegramNotifier(BASE)
        telegram_summary["configured"] = notifier.config.enabled
        telegram_summary["entry_candidates"] = sum(
            1
            for row in decisions
            if row.get("decision", {}).get("action") in {"enter_small", "enter_normal", "enter_heavy"}
        )
        try:
            telegram_notifications = notifier.send_for_entries(
                event_type=event.event_type.value,
                title=event.title,
                decisions=decisions,
            )
            telegram_summary["results"] = telegram_notifications
            telegram_summary["sent_count"] = sum(1 for row in telegram_notifications if row.get("sent"))
        except Exception as exc:
            telegram_notifications = [{"sent": False, "reason": f"error:{exc}"}]
            telegram_summary["results"] = telegram_notifications

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event": {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "title": event.title,
        },
        "macro_regime_snapshots": regime_snapshots,
        "asset_ranking": [
            {
                "asset": r.asset.value,
                "symbol": r.symbol,
                "score": r.score,
                "reasons": r.reasons,
            }
            for r in ranks
        ],
        "selected_decisions": decisions,
        "executions": executions,
        "exit_reviews": exit_reviews,
        "telegram_summary": telegram_summary,
        "telegram_notifications": telegram_notifications,
    }

    out_dir = BASE / "reports" / "eventalpha_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"eventalpha_paper_{event.event_type.value}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        f"\nTelegram status: requested={telegram_summary['requested']} "
        f"configured={telegram_summary['configured']} "
        f"entry_candidates={telegram_summary['entry_candidates']} "
        f"sent_count={telegram_summary['sent_count']}"
    )
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
