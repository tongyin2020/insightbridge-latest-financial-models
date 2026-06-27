"""
EventAlpha Phase-1/2 adapter for the Bond / Treasury model.
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

try:
    from models.schemas import StrategyConfig, StrategyType
    from services.market_data import BondAnalyticsService, MarketDataService
    try:
        from services.ai_engine import AITradingEngine
    except Exception:
        AITradingEngine = None
    BOND_IMPORT_OK = True
except Exception:
    AITradingEngine = None
    StrategyConfig = None
    StrategyType = None
    BondAnalyticsService = None
    MarketDataService = None
    BOND_IMPORT_OK = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Bond EventAlpha adapter should be called from sync orchestration.")


class BondEventAlphaAdapter:
    def __init__(self) -> None:
        self._market_data = MarketDataService() if BOND_IMPORT_OK else None
        self._analytics = BondAnalyticsService() if BOND_IMPORT_OK else None
        self._engine = AITradingEngine() if AITradingEngine else None
        self._positions: Dict[str, Dict[str, Any]] = {}

    def get_market_state(self) -> Dict[str, Any]:
        if BOND_IMPORT_OK:
            md = _run_async(self._market_data.get_real_market_data())
            analytics = _run_async(self._analytics.get_bond_analytics())
            strategy = StrategyConfig(strategy_type=StrategyType.AI_HYBRID)
        else:
            md = type(
                "FallbackMarketData",
                (),
                {"model_dump": lambda self=None: {
                    "timestamp": _utc_now(),
                    "wti_price": 74.8,
                    "bond_yield": 4.26,
                    "ispread": 14.93,
                    "risk_score": 28.0,
                    "source": "fallback",
                },
                 "ispread": 14.93,
                 "bond_yield": 4.26,
                 "risk_score": 28.0},
            )()
            analytics = {
                "yield_curve": {"is_inverted": True, "slope_10y_3m": -0.42},
                "risk_metrics": {"vix": 19.8, "dollar_index": 104.2},
                "inflation": {"breakeven_inflation": 2.35, "real_yield": 1.91},
                "signals": {"curve_inversion": "RECESSION_WARNING"},
                "timestamp": _utc_now(),
            }
            strategy = None

        analysis = None
        if self._engine is not None and strategy is not None:
            try:
                analysis = _run_async(self._engine.analyze_market(md, strategy, self._analytics))
            except Exception:
                analysis = None
        if analysis is None:
            action = "SELL_BOND" if md.ispread > 15.0 else "BUY_BOND" if md.ispread < 10.0 else "HOLD"
            analysis = {
                "action": action,
                "confidence": 0.74 if action != "HOLD" else 0.45,
                "reasoning": "Fallback bond EventAlpha analysis",
            }

        risk_metrics = analytics.get("risk_metrics", {})
        inflation = analytics.get("inflation", {})
        yield_curve = analytics.get("yield_curve", {})
        eventalpha_market_state = {
            "asset": "rates",
            "symbol": "ZN",
            "price": md.bond_yield,
            "spread_bps": max(2.0, risk_metrics.get("vix", 18.0) / 2.0),
            "volatility_z": min(md.risk_score / 20.0, 5.0),
            "momentum_score": min(0.95, max(0.05, analysis.get("confidence", 0.5))),
            "reversal_score": 0.35 if "BUY" in analysis.get("action", "") or "SELL" in analysis.get("action", "") else 0.55,
            "liquidity_score": 0.78,
            "cross_asset_alignment": 0.68 if yield_curve.get("is_inverted") else 0.58,
            "news_alignment": 0.62 if analysis.get("action") != "HOLD" else 0.48,
            "orderbook_pressure": 0.52,
            "trend_persistence": 0.56,
            "execution_quality": 0.74,
            "breakout_quality": 0.54,
            "raw": {
                "market_data": md.model_dump(),
                "analysis": analysis,
                "analytics": analytics,
                "breakeven_inflation": inflation.get("breakeven_inflation"),
            },
        }
        return {
            "adapter": "bond_eventalpha_phase2",
            "symbol": "ZN",
            "timestamp": _utc_now(),
            "market_state": {
                "market_data": md.model_dump(),
                "analysis": analysis,
                "analytics": analytics,
                "eventalpha_market_state": eventalpha_market_state,
            },
            "eventalpha_ready": True,
        }

    def execute_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        market_state = decision.get("market_state", {})
        analysis = market_state.get("analysis", {})
        action = analysis.get("action", "HOLD")
        if action == "HOLD":
            return {
                "adapter": "bond_eventalpha_phase2",
                "timestamp": _utc_now(),
                "status": "blocked",
                "reason": "Bond engine returned HOLD",
            }
        position_id = f"bond_pos_{uuid.uuid4().hex[:10]}"
        side = "BUY" if "BUY" in action or "LONG" in action else "SELL"
        position = {
            "position_id": position_id,
            "symbol": "ZN",
            "side": side,
            "status": "paper_open",
            "confidence": analysis.get("confidence", 0.0),
            "reasoning": analysis.get("reasoning", ""),
            "created_at": _utc_now(),
        }
        self._positions[position_id] = position
        return {
            "adapter": "bond_eventalpha_phase2",
            "timestamp": _utc_now(),
            "status": "accepted",
            "position_id": position_id,
            "execution_plan": position,
        }

    def manage_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        pnl_pct = float(position.get("pnl_pct", 0.0))
        action = "hold"
        if pnl_pct <= -1.2:
            action = "exit"
        elif pnl_pct <= -0.6:
            action = "reduce"
        elif pnl_pct >= 1.0:
            action = "protect_profit"
        return {
            "adapter": "bond_eventalpha_phase2",
            "timestamp": _utc_now(),
            "position_action": action,
            "pnl_pct": pnl_pct,
        }


adapter = BondEventAlphaAdapter()


def get_market_state(**kwargs: Any) -> Dict[str, Any]:
    return adapter.get_market_state(**kwargs)


def execute_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.execute_decision(decision)


def manage_position(position: Dict[str, Any]) -> Dict[str, Any]:
    return adapter.manage_position(position)
