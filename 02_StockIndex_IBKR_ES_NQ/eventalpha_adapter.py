"""
EventAlpha Phase-1/2 adapter for the current StockIndex branch.

Note:
This branch is still structurally mixed. This adapter provides a clean
paper-trading interface now, without pretending the branch is already a
pure ES/NQ model.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List
import uuid

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from signal_engines import Signal


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IndexEventAlphaAdapter:
    def __init__(self) -> None:
        self._prices: List[float] = [5200.0, 5205.0, 5210.0, 5208.0, 5216.0, 5220.0, 5218.0, 5226.0]
        self._positions: Dict[str, Dict[str, Any]] = {}

    def _synthetic_signal(self) -> Signal:
        last = self._prices[-1]
        prev = self._prices[-2]
        drift = last - prev
        direction = "BUY" if drift >= 0 else "SELL"
        confidence = min(0.86, 0.62 + abs(drift) / 50.0)
        reason = f"synthetic_index_event_proxy drift={drift:.2f}"
        return Signal(
            model="index",
            symbol="ES_PROXY",
            direction=direction,
            order_type="market",
            quantity=1,
            price=None,
            confidence=confidence,
            reason=reason,
        )

    def get_market_state(self) -> Dict[str, Any]:
        signal = self._synthetic_signal()
        price = self._prices[-1]
        market_state = {
            "adapter": "index_eventalpha_phase2",
            "symbol": "ES_PROXY",
            "timestamp": _utc_now(),
            "market_state": {
                "signal": asdict(signal),
                "structural_warning": "Current stock-index branch is still a mixed live-trader shell; this adapter runs paper mode only.",
                "eventalpha_market_state": {
                    "asset": "index",
                    "symbol": "ES_PROXY",
                    "price": price,
                    "spread_bps": 6.0,
                    "volatility_z": 1.4,
                    "momentum_score": signal.confidence,
                    "reversal_score": max(0.10, 1.0 - signal.confidence),
                    "liquidity_score": 0.84,
                    "cross_asset_alignment": 0.64,
                    "news_alignment": 0.55,
                    "orderbook_pressure": 0.57,
                    "trend_persistence": 0.61,
                    "execution_quality": 0.78,
                    "breakout_quality": 0.59,
                    "raw": {"prices": self._prices[-8:]},
                },
            },
            "eventalpha_ready": True,
        }
        return market_state

    def execute_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        market_state = decision.get("market_state", {})
        signal = market_state.get("signal", {})
        if not signal:
            return {
                "adapter": "index_eventalpha_phase2",
                "timestamp": _utc_now(),
                "status": "blocked",
                "reason": "No synthetic index signal available",
            }
        position_id = f"index_pos_{uuid.uuid4().hex[:10]}"
        position = {
            "position_id": position_id,
            "symbol": signal.get("symbol", "ES_PROXY"),
            "side": signal.get("direction", "BUY"),
            "confidence": signal.get("confidence", 0.0),
            "status": "paper_open",
            "created_at": _utc_now(),
        }
        self._positions[position_id] = position
        return {
            "adapter": "index_eventalpha_phase2",
            "timestamp": _utc_now(),
            "status": "accepted",
            "position_id": position_id,
            "execution_plan": position,
        }

    def manage_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        pnl_points = float(position.get("pnl_points", 0.0))
        action = "hold"
        if pnl_points <= -25:
            action = "exit"
        elif pnl_points <= -12:
            action = "reduce"
        elif pnl_points >= 30:
            action = "protect_profit"
        return {
            "adapter": "index_eventalpha_phase2",
            "timestamp": _utc_now(),
            "position_action": action,
            "pnl_points": pnl_points,
        }


adapter = IndexEventAlphaAdapter()


def get_market_state(**kwargs: Any) -> Dict[str, Any]:
    return adapter.get_market_state(**kwargs)


def execute_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.execute_decision(decision)


def manage_position(position: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.manage_position(position)
