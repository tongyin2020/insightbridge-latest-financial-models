from __future__ import annotations

from dataclasses import dataclass
from typing import List

from eventalpha_core.schema import DecisionAction, PositionState


@dataclass
class EscapeSignal:
    action: DecisionAction
    urgency: int
    reduce_fraction: float
    score: float
    reasons: List[str]


def escape_decision(pos: PositionState, mfe_r_multiple: float = 0.0, current_r_multiple: float = 0.0) -> EscapeSignal:
    """Sensitive exit engine. Exit should be faster than entry.

    Designed for event trades where original thesis can decay quickly.
    """
    reasons = []
    score = 0.0
    confidence_decay = max(0.0, pos.confidence_at_entry - pos.confidence_now)
    if confidence_decay > 0.12:
        score += 0.25
        reasons.append(f"confidence_decay={confidence_decay:.2f}")
    if pos.news_alignment < 0.42:
        score += 0.25
        reasons.append(f"news_contradiction={pos.news_alignment:.2f}")
    if pos.cross_asset_alignment < 0.42:
        score += 0.22
        reasons.append(f"cross_asset_breakdown={pos.cross_asset_alignment:.2f}")
    if pos.reversal_score > 0.62:
        score += 0.20
        reasons.append(f"reversal_score={pos.reversal_score:.2f}")
    if pos.spread_bps > 30:
        score += 0.18
        reasons.append(f"spread_widening={pos.spread_bps:.1f}bps")
    if mfe_r_multiple > 1.0 and current_r_multiple < 0.60 * mfe_r_multiple:
        score += 0.22
        reasons.append(f"profit_giveback: mfe={mfe_r_multiple:.2f}R now={current_r_multiple:.2f}R")
    if pos.seconds_in_trade > 1800 and pos.momentum_score < 0.52:
        score += 0.12
        reasons.append("time_decay_without_momentum")
    score = min(1.0, score)
    if score >= 0.58:
        return EscapeSignal(DecisionAction.EXIT, 5, 1.0, score, reasons)
    if score >= 0.38:
        return EscapeSignal(DecisionAction.REDUCE, 4, 0.50, score, reasons)
    if score >= 0.22:
        return EscapeSignal(DecisionAction.REDUCE, 3, 0.25, score, reasons)
    return EscapeSignal(DecisionAction.WATCH, 1, 0.0, score, reasons or ["exit_conditions_not_met"])
