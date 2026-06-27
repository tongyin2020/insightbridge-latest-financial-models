from __future__ import annotations

import json
from datetime import datetime, timezone

from .advanced.post_event_learning import TradeReplay, learn_from_replay
from .event_memory import EventMemoryDB, EventTradeRecord
from .schema import AssetClass, EventType


class LearningEngine:
    """Uses event memory to adapt confidence and waiting rules."""

    def __init__(self, memory: EventMemoryDB):
        self.memory = memory

    def memory_edge(self, event_type: EventType, asset: AssetClass) -> float:
        return float(self.memory.edge_summary(event_type.value, asset.value).get("memory_edge", 0.50))

    def memory_wait(self, event_type: EventType, asset: AssetClass) -> int | None:
        return self.memory.edge_summary(event_type.value, asset.value).get("recommended_wait_seconds")

    def risk_multiplier_bias(self, event_type: EventType, asset: AssetClass) -> float:
        return float(self.memory.edge_summary(event_type.value, asset.value).get("risk_multiplier_bias", 0.0))

    def apply_replay_learning(self, replay: TradeReplay) -> dict:
        update = learn_from_replay(replay)
        created_at = datetime.now(timezone.utc).isoformat()
        self.memory.append(
            EventTradeRecord(
                event_id=f"replay_{replay.event_type}_{replay.asset}_{created_at}",
                event_type=replay.event_type,
                asset=replay.asset,
                symbol=replay.symbol,
                thesis="historical_replay_learning",
                entry_confidence=replay.confidence_at_entry,
                seconds_waited=replay.best_wait_seconds_hindsight,
                direction=replay.predicted_direction,
                entry_price=100.0,
                exit_price=100.0 + replay.final_outcome_r,
                mfe_pct=replay.max_favorable_r * 100.0,
                mae_pct=replay.max_adverse_r * 100.0,
                pnl_pct=replay.final_outcome_r * 100.0,
                exit_reason=replay.exit_reason,
                mistake_tags=";".join(update.lessons),
                created_at=created_at,
            )
        )
        self.memory.append_learning_update(
            event_type=replay.event_type,
            asset=replay.asset,
            symbol=replay.symbol,
            memory_edge_delta=update.memory_edge_delta,
            wait_seconds_delta=update.wait_seconds_delta,
            risk_multiplier_delta=update.risk_multiplier_delta,
            lessons=";".join(update.lessons),
            raw_record=json.dumps(update.record, ensure_ascii=False),
            created_at=created_at,
        )
        return {
            "event_type": replay.event_type,
            "asset": replay.asset,
            "symbol": replay.symbol,
            "memory_edge_delta": update.memory_edge_delta,
            "wait_seconds_delta": update.wait_seconds_delta,
            "risk_multiplier_delta": update.risk_multiplier_delta,
            "lessons": update.lessons,
        }
