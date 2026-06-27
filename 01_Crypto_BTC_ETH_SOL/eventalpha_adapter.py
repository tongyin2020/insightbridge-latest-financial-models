"""
EventAlpha Phase-1 adapter for the Crypto model.

This file adds the reduced three-interface contract required by the
shared EventAlpha Core without rewriting the existing engines.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, Optional
import uuid

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from engines import (
    event_response_engine,
    execution_gate,
    fragility_engine,
    get_signal_engine,
    regime_engine,
    risk_engine,
)
from models import FeatureSnapshot, GateInput
from websocket_feeds import get_market_feed


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CryptoEventAlphaAdapter:
    """Thin wrapper that standardizes the Crypto model for EventAlpha."""

    def __init__(self) -> None:
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._decision_log: list[Dict[str, Any]] = []

    def get_market_state(
        self,
        symbol: str = "BTC",
        snapshot: Optional[FeatureSnapshot] = None,
        event_flag: bool = False,
        elapsed_seconds: float = 0.0,
        risk_context: Optional[Dict[str, Any]] = None,
        position_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a normalized EventAlpha market-state packet."""
        symbol = symbol.upper()
        risk_context = risk_context or {}
        position_context = position_context or {}

        if snapshot is None:
            snapshot = get_market_feed([symbol]).create_feature_snapshot(symbol)

        regime = regime_engine.evaluate(snapshot)
        event_state = event_response_engine.evaluate(snapshot, elapsed_seconds, event_flag)
        fragility = fragility_engine.evaluate(snapshot)
        signal = get_signal_engine(symbol).generate(snapshot, regime, fragility)

        gate_input = GateInput(
            symbol=symbol,
            ts=snapshot.ts,
            regime=regime,
            event_state=event_state,
            fragility=fragility,
            trade_allowed=bool(signal.side),
            signal_side=signal.side,
            signal_confidence=signal.conviction_score,
            stale_quote=snapshot.stale_quote,
            venue_divergence=snapshot.venue_divergence,
            daily_drawdown_hit=bool(risk_context.get("daily_drawdown_hit", False)),
            deterioration_triggered=bool(risk_context.get("deterioration_triggered", False)),
            cooldown_state=str(risk_context.get("cooldown_state", "READY")),
            risk_multiplier=float(risk_context.get("risk_multiplier", 1.0)),
            position_open=bool(position_context.get("position_open", False)),
            position_side=position_context.get("position_side"),
            position_age_minutes=float(position_context.get("position_age_minutes", 0.0)),
            max_position_age_minutes=float(position_context.get("max_position_age_minutes", 120.0)),
            exchange_incident_flag=snapshot.exchange_incident_flag,
            network_incident_flag=snapshot.network_incident_flag,
        )
        gate_decision = execution_gate.decide(gate_input)
        liquidity_score = max(0.20, min(0.95, 1.0 - snapshot.spread_ratio / 3.0))
        execution_quality = max(0.20, min(0.95, 1.0 - snapshot.venue_divergence / 3.0))
        momentum_score = max(0.05, min(0.95, signal.conviction_score / 100.0))
        breakout_quality = max(0.05, min(0.95, signal.direction_score / 100.0))

        return {
            "adapter": "crypto_eventalpha_phase1",
            "symbol": symbol,
            "timestamp": snapshot.ts,
            "market_state": {
                "snapshot": asdict(snapshot),
                "regime": regime.value,
                "event_state": event_state.value,
                "fragility_state": fragility.value,
                "signal": asdict(signal),
                "gate_input": asdict(gate_input),
                "gate_decision": asdict(gate_decision),
                "eventalpha_market_state": {
                    "asset": "crypto",
                    "symbol": symbol,
                    "price": snapshot.price,
                    "spread_bps": snapshot.spread_ratio * 10.0,
                    "volatility_z": min(abs(snapshot.price_change_24h) / 3.0, 5.0),
                    "momentum_score": momentum_score,
                    "reversal_score": max(0.05, min(0.95, fragility.fragility_score(snapshot) / 100.0 if hasattr(fragility, 'fragility_score') else signal.fragility_score / 100.0)),
                    "liquidity_score": liquidity_score,
                    "cross_asset_alignment": 0.64 if signal.side else 0.48,
                    "news_alignment": 0.55 if event_state.value == "READY" else 0.45,
                    "orderbook_pressure": max(0.05, min(0.95, snapshot.taker_buy_ratio)),
                    "trend_persistence": breakout_quality,
                    "execution_quality": execution_quality,
                    "breakout_quality": breakout_quality,
                    "raw": {
                        "candidate_type": signal.candidate_type,
                        "reason_codes": signal.reason_codes,
                        "gate_action": gate_decision.action.value,
                    },
                },
            },
            "eventalpha_ready": True,
        }

    def execute_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a crypto trade decision into a standard execution result.

        Expected input:
        - `market_state`: output from get_market_state()
        - optional `capital`
        """
        market_state = decision.get("market_state", {})
        symbol = decision.get("symbol") or market_state.get("symbol") or "BTC"
        signal = market_state.get("signal", {})
        gate_decision = market_state.get("gate_decision", {})
        action = gate_decision.get("action", "BLOCK")
        approved_side = gate_decision.get("approved_side")
        size_multiplier = float(gate_decision.get("size_multiplier", 0.0))

        result = {
            "adapter": "crypto_eventalpha_phase1",
            "symbol": symbol,
            "timestamp": _utc_now(),
            "status": "blocked",
            "action": action,
            "approved_side": approved_side,
            "size_multiplier": size_multiplier,
            "reason_codes": gate_decision.get("reason_codes", []),
        }

        if action not in ("ALLOW", "ALLOW_REDUCED") or not approved_side:
            self._decision_log.append(result)
            return result

        position_id = f"crypto_pos_{uuid.uuid4().hex[:10]}"
        capital = float(decision.get("capital", 100000.0))
        notional = capital * max(size_multiplier, 0.1) * 0.05
        position = {
            "position_id": position_id,
            "symbol": symbol,
            "side": approved_side,
            "status": "open",
            "opened_at": _utc_now(),
            "size_multiplier": size_multiplier,
            "notional": round(notional, 2),
            "entry_reference": market_state.get("snapshot", {}).get("price", 0.0),
            "signal_confidence": signal.get("conviction_score", 0.0),
            "reason_codes": result["reason_codes"],
        }
        self._positions[position_id] = position
        result.update({
            "status": "accepted",
            "position_id": position_id,
            "execution_plan": position,
        })
        self._decision_log.append(result)
        return result

    def manage_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate an open position with the existing Crypto risk engine.

        Expected input:
        - `unrealized_pnl`
        - optional `position_id`
        """
        pnl = float(position.get("unrealized_pnl", 0.0))
        risk_action = risk_engine.evaluate_open_position(
            pnl,
            warning=float(position.get("warning", -0.02)),
            reduce=float(position.get("reduce", -0.03)),
            stop=float(position.get("stop", -0.05)),
            catastrophe=float(position.get("catastrophe", -0.10)),
        )
        position_id = position.get("position_id")
        tracked = self._positions.get(position_id, {}).copy() if position_id else {}
        return {
            "adapter": "crypto_eventalpha_phase1",
            "timestamp": _utc_now(),
            "position_id": position_id,
            "symbol": position.get("symbol") or tracked.get("symbol"),
            "side": position.get("side") or tracked.get("side"),
            "unrealized_pnl": pnl,
            "risk_action": risk_action,
            "tracked_position": tracked,
        }


adapter = CryptoEventAlphaAdapter()


def get_market_state(**kwargs: Any) -> Dict[str, Any]:
    return adapter.get_market_state(**kwargs)


def execute_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.execute_decision(decision)


def manage_position(position: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.manage_position(position)
