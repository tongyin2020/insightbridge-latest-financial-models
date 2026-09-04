from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from agent_system.precision_sniping.breakout_filter import MicrostructureBreakoutFilter
from agent_system.precision_sniping.kinetic_tracker import KineticInFlightBacktester
from agent_system.precision_sniping.position_risk_balancer import PositionRiskBalancer
from agent_system.precision_sniping.regime_interlock import CrossAssetInterlock, InterlockResult
from agent_system.state import BotSnapshot


class UnifiedExecutionCoordinator:
    """精确狙击统一协调器：入口过滤 + 动能退出 + 2 小时 lockout。"""

    def __init__(self, interlock: CrossAssetInterlock, risk_balancer: PositionRiskBalancer | None = None) -> None:
        self.interlock = interlock
        self.risk_balancer = risk_balancer or PositionRiskBalancer()
        self._filters: dict[str, MicrostructureBreakoutFilter] = {}
        self._trackers: dict[str, KineticInFlightBacktester] = {}
        self._lockout_until: datetime | None = None

    @staticmethod
    def _event_type(regime: str) -> str:
        return "INTERVENTION" if regime == "FX_INTERVENTION" else "GEOPOLITICS" if regime == "OIL_GEOPOL" else "GENERIC"

    def _filter_for(self, action: dict[str, Any], interlock: InterlockResult) -> MicrostructureBreakoutFilter:
        bot_id = action.get("bot_id", "unknown")
        key = f"{bot_id}:{action.get('symbol', 'X')}"
        if key not in self._filters:
            self._filters[key] = MicrostructureBreakoutFilter(
                asset_class=bot_id,
                event_type=self._event_type(interlock.regime_type),
            )
        return self._filters[key]

    def process_tick(
        self,
        snapshots: dict[str, BotSnapshot],
        actions: list[dict[str, Any]],
        prices: dict[str, float],
        l2_books: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if self._lockout_until and now < self._lockout_until:
            return {"status": "LOCKOUT_ACTIVE", "lockout_until": self._lockout_until.isoformat()}

        interlock = self.interlock.evaluate(snapshots)
        if interlock.score < interlock.threshold:
            return {"status": "NO_ACTION", "reason": f"interlock_score {interlock.score:.3f} below {interlock.threshold}"}

        decisions: list[dict[str, Any]] = []
        # Scale secondary bots
        scaled_actions = self.risk_balancer.scale(interlock.primary_bot, actions)

        for action in scaled_actions:
            symbol = action.get("symbol")
            price = prices.get(symbol)
            book = l2_books.get(symbol, {})
            if price is None:
                continue

            filt = self._filter_for(action, interlock)
            state = filt.system_state

            if state == "MONITORING":
                armed = filt.arm(interlock.score)
                if armed:
                    decisions.append({"bot_id": action["bot_id"], "symbol": symbol, "status": "SYSTEM_ARMED", "score": interlock.score})
                else:
                    decisions.append({"bot_id": action["bot_id"], "symbol": symbol, "status": "NO_ACTION"})

            elif state == "ARMED":
                if filt.validate_breakout(price, book):
                    tracker = KineticInFlightBacktester(price, filt.rules.pulse_ttl_minutes)
                    self._trackers[symbol] = tracker
                    decisions.append({
                        "bot_id": action["bot_id"],
                        "symbol": symbol,
                        "status": "ENTER_MARKET",
                        "direction": action.get("direction"),
                        "suggested_size": action.get("suggested_size"),
                    })
                else:
                    decisions.append({"bot_id": action["bot_id"], "symbol": symbol, "status": "WAITING_BREAKOUT"})

            elif state == "IN_TRADE":
                tracker = self._trackers.get(symbol)
                if tracker is None:
                    tracker = KineticInFlightBacktester(price, filt.rules.pulse_ttl_minutes)
                    self._trackers[symbol] = tracker
                tracker.update_telemetry(price)
                exit_signal = tracker.evaluate_exit_criteria()
                if exit_signal in ("EXIT_MOMENTUM", "EXIT_TTL"):
                    filt.system_state = "MONITORING"
                    self._trackers.pop(symbol, None)
                    self._lockout_until = now + timedelta(hours=2)
                    decisions.append({
                        "bot_id": action["bot_id"],
                        "symbol": symbol,
                        "status": "EXIT_MARKET",
                        "exit_reason": exit_signal,
                    })
                else:
                    decisions.append({
                        "bot_id": action["bot_id"],
                        "symbol": symbol,
                        "status": "TRACKING_PULSE",
                        "velocity": None,
                    })

        return {
            "status": "PROCESSED",
            "interlock": interlock.__dict__,
            "decisions": decisions,
        }
