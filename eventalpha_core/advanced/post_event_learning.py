from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List


@dataclass
class TradeReplay:
    event_type: str
    asset: str
    symbol: str
    predicted_direction: str
    final_outcome_r: float
    max_favorable_r: float
    max_adverse_r: float
    wait_seconds_used: int
    best_wait_seconds_hindsight: int
    exit_reason: str
    confidence_at_entry: float
    confidence_at_exit: float
    false_breakout: bool


@dataclass
class LearningUpdate:
    memory_edge_delta: float
    wait_seconds_delta: int
    risk_multiplier_delta: float
    lessons: List[str]
    record: Dict


def learn_from_replay(r: TradeReplay) -> LearningUpdate:
    lessons: List[str] = []
    edge_delta = 0.0
    risk_delta = 0.0
    wait_delta = int(0.25 * (r.best_wait_seconds_hindsight - r.wait_seconds_used))
    if r.final_outcome_r > 1.0:
        edge_delta += 0.03
        risk_delta += 0.02
        lessons.append("event_asset_pair_has_positive_edge")
    elif r.final_outcome_r < -0.7:
        edge_delta -= 0.05
        risk_delta -= 0.04
        lessons.append("reduce_future_risk_for_similar_event")
    if r.false_breakout:
        wait_delta = max(wait_delta, 60)
        lessons.append("false_breakout_detected_increase_minimum_wait")
    if r.max_favorable_r > 1.5 and r.final_outcome_r < 0.5:
        lessons.append("exit_too_late_strengthen_profit_giveback_rule")
        risk_delta -= 0.02
    if r.confidence_at_entry - r.confidence_at_exit > 0.18:
        lessons.append("confidence_decay_was_predictive_of_exit")
    return LearningUpdate(edge_delta, wait_delta, risk_delta, lessons, asdict(r))
