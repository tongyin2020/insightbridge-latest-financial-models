from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_system.config import AgentConfig
from agent_system.precision_sniping.position_risk_balancer import PositionRiskBalancer
from agent_system.precision_sniping.regime_interlock import CrossAssetInterlock
from agent_system.state import BotSnapshot


class ExecutionBridge:
    """把 Agent 共识转换为现有 5-bot 路由可识别的信号。

    - 默认只生成 pending orders 文件，不连接 IBKR。
    - 只有 `execution_enabled=True` 且 `observe_only=False` 时，才尝试用 `SignalRouter` 发单。
    """

    def __init__(self, config: AgentConfig) -> None:
        self.cfg = config
        self.orders_dir = config.trace_dir / "orders"
        self.orders_dir.mkdir(parents=True, exist_ok=True)

    def _to_signal(self, action: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": action.get("bot_id", "unknown"),
            "symbol": action.get("symbol") or (self.cfg.bot_symbols.get(action.get("bot_id", ""), [None]) or [None])[0],
            "direction": action.get("direction", "HOLD"),
            "quantity": action.get("suggested_size", 1),
            "order_type": "market",
            "confidence": action.get("confidence", 0.0),
            "reason": action.get("reason", {}),
            "agent_trace_id": action.get("trace_id", ""),
        }

    def stage_orders(self, recommendation: dict[str, Any], trace_id: str = "") -> list[dict[str, Any]]:
        signals = [self._to_signal(a) for a in recommendation.get("actions", []) if a.get("direction") in ("BUY", "SELL")]
        for s in signals:
            s["agent_trace_id"] = trace_id
            s["ts"] = datetime.now(timezone.utc).isoformat()
        return signals

    def persist(self, signals: list[dict[str, Any]]) -> Path:
        path = self.orders_dir / "pending_orders.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            for s in signals:
                fh.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")
        return path

    async def _live_route(self, signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "ibkr_connector",
                self.cfg.base_dir / "02_StockIndex_IBKR_ES_NQ" / "ibkr_connector.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            connector = module.IBKRConnector()
            connected = await connector.connect()
            if not connected:
                return [{"status": "error", "reason": "ibkr_connection_failed"} for _ in signals]
            router = module.SignalRouter(connector)
            for sig in signals:
                result = await router.process_signal(sig)
                result["agent_trace_id"] = sig.get("agent_trace_id")
                results.append(result)
            await connector.disconnect()
        except Exception as exc:
            for sig in signals:
                results.append({"status": "error", "reason": str(exc), "signal": sig})
        return results

    def execute(
        self,
        recommendation: dict[str, Any],
        trace_id: str = "",
        bot_snapshots: dict[str, BotSnapshot] | None = None,
    ) -> dict[str, Any]:
        actions = recommendation.get("actions", [])

        # Optional Precision Sniping layer: cross-asset interlock + secondary scaling
        precision_note = "precision_sniping_disabled"
        if self.cfg.precision_sniping_enabled and bot_snapshots:
            interlock = CrossAssetInterlock(self.cfg).evaluate(bot_snapshots)
            if interlock.score < interlock.threshold:
                return {
                    "status": "filtered_by_precision_sniping",
                    "interlock": interlock.__dict__,
                    "staged": 0,
                    "routed": 0,
                    "signals": [],
                }
            actions = PositionRiskBalancer(interlock.secondary_scale).scale(interlock.primary_bot, actions)
            precision_note = f"interlock_score={interlock.score:.3f}, regime={interlock.regime_type}"

        signals = self.stage_orders({"actions": actions}, trace_id)
        if not signals:
            return {"status": "no_action", "staged": 0, "routed": 0, "precision": precision_note}

        persist_path = self.persist(signals)

        live = self.cfg.execution_enabled and not self.cfg.observe_only
        routed: list[dict[str, Any]] = []
        if live:
            routed = asyncio.run(self._live_route(signals))

        return {
            "status": "staged" if not live else "routed",
            "live": live,
            "precision": precision_note,
            "staged": len(signals),
            "routed": len(routed),
            "signals": signals,
            "results": routed,
            "persist_path": str(persist_path),
        }
