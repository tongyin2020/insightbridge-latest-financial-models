"""
EventAlpha Phase-1 adapter for the Oil model.

This file adds the reduced three-interface contract required by the
shared EventAlpha Core while preserving the current trading bot logic.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from event_engine import event_engine
from trading_bot import OpportunityStatus, trading_bot


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_async(coro):
    """Run async code safely from sync adapter functions."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "Oil EventAlpha adapter scan path cannot run inside an active event loop. "
        "Call the bot directly from async code or invoke the adapter from sync orchestration."
    )


class OilEventAlphaAdapter:
    """Thin wrapper that standardizes the Oil model for EventAlpha."""

    def __init__(self) -> None:
        self._last_market_state: Optional[Dict[str, Any]] = None

    def get_market_state(
        self,
        symbol: str = "WTI",
        current_price: float = 72.5,
        signal_score: Optional[Dict[str, Any]] = None,
        execution_gate: Optional[Dict[str, Any]] = None,
        fragility: Optional[Dict[str, Any]] = None,
        risk_control: Optional[Dict[str, Any]] = None,
        regime: str = "normal",
        atr: float = 1.2,
        indicators: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a normalized EventAlpha market-state packet."""
        signal_score = signal_score or {
            "score": 42.0,
            "zone": "balanced_long",
            "components": {"inventory": 18.0, "usd": -4.0, "momentum": 12.0},
        }
        execution_gate = execution_gate or {"gate_status": "OPEN"}
        fragility = fragility or {"score": 22.0}
        risk_control = risk_control or {"can_trade": True, "equity": {"current": 50000}}
        indicators = indicators or {"rsi": 57.0, "ema_spread": 0.8}

        event_state = event_engine.get_state()
        market_state = {
            "adapter": "oil_eventalpha_phase1",
            "symbol": symbol,
            "timestamp": _utc_now(),
            "market_state": {
                "price": current_price,
                "signal_score": signal_score,
                "execution_gate": execution_gate,
                "fragility": fragility,
                "risk_control": risk_control,
                "regime": regime,
                "atr": atr,
                "indicators": indicators,
                "event_state": event_state,
                "bot_status": trading_bot.get_status(),
                "eventalpha_market_state": {
                    "asset": "oil",
                    "symbol": symbol,
                    "price": current_price,
                    "spread_bps": 8.0 if execution_gate.get("gate_status") == "OPEN" else 16.0,
                    "volatility_z": min(float(atr) / 1.5, 5.0),
                    "momentum_score": min(0.95, max(0.05, 0.50 + signal_score.get("score", 0.0) / 200.0)),
                    "reversal_score": min(0.95, max(0.05, fragility.get("score", 0.0) / 100.0)),
                    "liquidity_score": max(0.20, min(0.95, 1.0 - fragility.get("score", 0.0) / 120.0)),
                    "cross_asset_alignment": 0.70 if event_state.get("upcoming_high_impact", 0) == 0 else 0.56,
                    "news_alignment": 0.66 if not event_state.get("halt_trading") else 0.42,
                    "orderbook_pressure": 0.58,
                    "trend_persistence": 0.60 if regime == "normal" else 0.48,
                    "execution_quality": 0.72 if execution_gate.get("gate_status") == "OPEN" else 0.46,
                    "breakout_quality": 0.62 if signal_score.get("score", 0.0) > 0 else 0.50,
                    "raw": {
                        "gate_status": execution_gate.get("gate_status"),
                        "fragility_score": fragility.get("score"),
                        "risk_modifier": event_state.get("risk_modifier"),
                    },
                },
            },
            "eventalpha_ready": True,
        }
        self._last_market_state = market_state
        return market_state

    def execute_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize oil trade decisions into a standard execution result.

        Supported modes:
        - `mode="scan"`: run existing scan_market() and produce opportunity
        - `mode="approve"`: approve a pending opportunity
        - `mode="reject"`: reject a pending opportunity
        - `mode="mark_executed"`: mark an approved opportunity executed
        """
        mode = decision.get("mode", "scan")

        if mode == "scan":
            trading_bot.enabled = True
            market_state = decision.get("market_state") or self._last_market_state
            if not market_state:
                market_state = self.get_market_state()
            payload = market_state.get("market_state", market_state)
            opp = _run_async(
                trading_bot.scan_market(
                    symbol=decision.get("symbol", market_state.get("symbol", "WTI")),
                    current_price=float(payload.get("price", 72.5)),
                    signal_score=payload.get("signal_score", {}),
                    execution_gate=payload.get("execution_gate", {}),
                    fragility=payload.get("fragility", {}),
                    risk_control=payload.get("risk_control", {}),
                    regime=str(payload.get("regime", "normal")),
                    atr=float(payload.get("atr", 1.2)),
                    indicators=payload.get("indicators", {}),
                )
            )
            if opp is None:
                return {
                    "adapter": "oil_eventalpha_phase1",
                    "timestamp": _utc_now(),
                    "status": "blocked",
                    "mode": "scan",
                    "reason": "No opportunity generated under current oil conditions",
                }
            return {
                "adapter": "oil_eventalpha_phase1",
                "timestamp": _utc_now(),
                "status": "accepted",
                "mode": "scan",
                "opportunity": opp.to_dict(),
            }

        opportunity_id = decision.get("opportunity_id")
        if not opportunity_id:
            return {
                "adapter": "oil_eventalpha_phase1",
                "timestamp": _utc_now(),
                "status": "error",
                "mode": mode,
                "reason": "opportunity_id is required",
            }

        if mode == "approve":
            result = trading_bot.approve_opportunity(opportunity_id)
            return {
                "adapter": "oil_eventalpha_phase1",
                "timestamp": _utc_now(),
                "status": "accepted" if result and "error" not in result else "blocked",
                "mode": mode,
                "result": result,
            }
        if mode == "reject":
            result = trading_bot.reject_opportunity(opportunity_id)
            return {
                "adapter": "oil_eventalpha_phase1",
                "timestamp": _utc_now(),
                "status": "accepted" if result and "error" not in result else "blocked",
                "mode": mode,
                "result": result,
            }
        if mode == "mark_executed":
            position_id = decision.get("position_id", f"oil_pos_{opportunity_id}")
            trading_bot.mark_executed(opportunity_id, position_id)
            return {
                "adapter": "oil_eventalpha_phase1",
                "timestamp": _utc_now(),
                "status": "accepted",
                "mode": mode,
                "opportunity_id": opportunity_id,
                "position_id": position_id,
            }

        return {
            "adapter": "oil_eventalpha_phase1",
            "timestamp": _utc_now(),
            "status": "error",
            "mode": mode,
            "reason": "Unsupported mode",
        }

    def manage_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manage an oil position using existing opportunity exit tiers and event state.
        """
        event_state = event_engine.get_state()
        entry_price = float(position.get("entry_price", 0.0))
        current_price = float(position.get("current_price", entry_price))
        direction = str(position.get("direction", "long")).lower()
        stop_loss = float(position.get("stop_loss", entry_price))

        if direction == "long":
            pnl = current_price - entry_price
            stop_distance = entry_price - stop_loss
        else:
            pnl = entry_price - current_price
            stop_distance = stop_loss - entry_price

        action = "hold"
        if event_state.get("halt_trading"):
            action = "reduce_or_hold_flat"
        elif stop_distance > 0 and pnl <= -stop_distance * 1.5:
            action = "disaster_exit"
        elif stop_distance > 0 and pnl <= -stop_distance:
            action = "main_stop_exit"
        elif stop_distance > 0 and pnl <= -stop_distance * 0.7:
            action = "reduce_50"
        elif stop_distance > 0 and pnl <= -stop_distance * 0.5:
            action = "warning"

        return {
            "adapter": "oil_eventalpha_phase1",
            "timestamp": _utc_now(),
            "symbol": position.get("symbol", "WTI"),
            "direction": direction,
            "entry_price": entry_price,
            "current_price": current_price,
            "price_pnl": round(pnl, 4),
            "event_state": event_state,
            "position_action": action,
        }


adapter = OilEventAlphaAdapter()


def get_market_state(**kwargs: Any) -> Dict[str, Any]:
    return adapter.get_market_state(**kwargs)


def execute_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.execute_decision(decision)


def manage_position(position: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.manage_position(position)
