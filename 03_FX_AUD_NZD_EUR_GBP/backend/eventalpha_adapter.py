"""
EventAlpha Phase-1/2 adapter for the FX model.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict
import uuid

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

FX_IMPORT_ERROR = None
try:
    from event_engine import EventEngine
    from market_data import MarketDataService
    from signal_engine import SignalEngine
    FX_IMPORT_OK = True
except Exception as exc:
    FX_IMPORT_OK = False
    FX_IMPORT_ERROR = str(exc)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("FX EventAlpha adapter should be called from sync orchestration.")


class FXEventAlphaAdapter:
    def __init__(self) -> None:
        self._market_data = MarketDataService() if FX_IMPORT_OK else None
        self._event_engine = EventEngine() if FX_IMPORT_OK else None
        self._signal_engine = SignalEngine(self._market_data) if FX_IMPORT_OK else None
        self._positions: Dict[str, Dict[str, Any]] = {}

    def get_market_state(self, pair: str = "AUD/USD") -> Dict[str, Any]:
        if FX_IMPORT_OK:
            result = _run_async(self._market_data.poll_once(pair))
            if result is None:
                result = {"pair": pair, "mid": 0.63 if "AUD" in pair else 0.57, "spread_pips": 1.5, "indicators": {}}
            indicators = result.get("indicators", {})
            event_state = self._event_engine.get_event_state()
            signal = _run_async(
                self._signal_engine.generate_signal(
                    pair=pair,
                    indicators=indicators,
                    direction_permission="BOTH",
                    event_state=event_state,
                    override_mode="NORMAL",
                )
            )
        else:
            result = {"pair": pair, "mid": 0.63 if "AUD" in pair else 0.57, "spread_pips": 1.8, "indicators": {"atr": 0.0012}}
            indicators = result["indicators"]
            event_state = {
                "state": "NORMAL",
                "event_level": None,
                "event_title": "",
                "remaining_seconds": 0.0,
                "confirmed_direction": {},
                "timestamp": _utc_now(),
                "fallback_reason": FX_IMPORT_ERROR,
            }
            signal = type(
                "FallbackSignal",
                (),
                {
                    "direction": "BUY",
                    "confidence": 61.0,
                    "regime": "TREND",
                    "reason": f"fallback_fx_adapter:{FX_IMPORT_ERROR}",
                    "to_dict": lambda self=None: {
                        "pair": pair,
                        "direction": "BUY",
                        "confidence": 61.0,
                        "regime": "TREND",
                        "reason": f"fallback_fx_adapter:{FX_IMPORT_ERROR}",
                        "timestamp": _utc_now(),
                    },
                },
            )()
        spread_pips = float(result.get("spread_pips", 1.5))
        market_state = {
            "adapter": "fx_eventalpha_phase2",
            "symbol": pair,
            "timestamp": _utc_now(),
            "market_state": {
                "price": float(result.get("mid", result.get("close", 0.0))),
                "event_state": event_state,
                "signal": signal.to_dict(),
                "indicators": {k: v for k, v in indicators.items() if not str(k).startswith("_")},
                "raw_result": result,
                "eventalpha_market_state": {
                    "asset": "fx",
                    "symbol": pair,
                    "price": float(result.get("mid", result.get("close", 0.0))),
                    "spread_bps": spread_pips,
                    "volatility_z": min(float(indicators.get("atr") or 0.0) * 1000, 5.0),
                    "momentum_score": 0.50 + ((float(signal.confidence) / 100.0) - 0.5) * 0.8 if signal.direction != "WAIT" else 0.50,
                    "reversal_score": max(0.0, 1.0 - (float(signal.confidence) / 100.0)),
                    "liquidity_score": max(0.20, min(0.95, 1.0 - spread_pips / 10.0)),
                    "cross_asset_alignment": 0.62 if signal.direction != "WAIT" else 0.48,
                    "news_alignment": 0.58 if event_state.get("state") in ("POST_EVENT", "NORMAL") else 0.46,
                    "orderbook_pressure": 0.55,
                    "trend_persistence": 0.58 if signal.regime == "TREND" else 0.48,
                    "execution_quality": max(0.20, min(0.95, 1.0 - spread_pips / 8.0)),
                    "breakout_quality": 0.60 if signal.regime == "TREND" else 0.45,
                    "raw": {
                        "pair": pair,
                        "direction": signal.direction,
                        "regime": signal.regime,
                        "reason": signal.reason,
                        "import_mode": "native" if FX_IMPORT_OK else "fallback",
                    },
                },
            },
            "eventalpha_ready": True,
        }
        return market_state

    def execute_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        market_state = decision.get("market_state", {})
        signal = market_state.get("signal", {})
        direction = signal.get("direction", "WAIT")
        if direction == "WAIT":
            return {
                "adapter": "fx_eventalpha_phase2",
                "timestamp": _utc_now(),
                "status": "blocked",
                "reason": "FX signal engine produced WAIT",
            }
        position_id = f"fx_pos_{uuid.uuid4().hex[:10]}"
        position = {
            "position_id": position_id,
            "symbol": decision.get("symbol") or market_state.get("symbol", "AUD/USD"),
            "side": direction,
            "status": "paper_open",
            "entry_reference": market_state.get("price"),
            "confidence": signal.get("confidence", 0.0),
            "created_at": _utc_now(),
        }
        self._positions[position_id] = position
        return {
            "adapter": "fx_eventalpha_phase2",
            "timestamp": _utc_now(),
            "status": "accepted",
            "position_id": position_id,
            "execution_plan": position,
        }

    def manage_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        pnl_pips = float(position.get("pnl_pips", 0.0))
        event_state = self._event_engine.get_event_state()
        action = "hold"
        if event_state.get("state") in ("PRE_EVENT", "COOLDOWN"):
            action = "reduce_or_exit_event_risk"
        elif pnl_pips <= -15:
            action = "exit"
        elif pnl_pips <= -8:
            action = "warning"
        elif pnl_pips >= 20:
            action = "protect_profit"
        return {
            "adapter": "fx_eventalpha_phase2",
            "timestamp": _utc_now(),
            "position_action": action,
            "event_state": event_state,
            "pnl_pips": pnl_pips,
        }


adapter = FXEventAlphaAdapter()


def get_market_state(**kwargs: Any) -> Dict[str, Any]:
    return adapter.get_market_state(**kwargs)


def execute_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.execute_decision(decision)


def manage_position(position: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.manage_position(position)
