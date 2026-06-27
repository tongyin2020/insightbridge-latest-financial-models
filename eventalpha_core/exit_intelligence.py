from __future__ import annotations

from .schema import DecisionAction, Direction, ExitDecision, PositionState


def current_return_pct(p: PositionState) -> float:
    if p.direction == Direction.LONG:
        return (p.current_price - p.entry_price) / p.entry_price * 100
    if p.direction == Direction.SHORT:
        return (p.entry_price - p.current_price) / p.entry_price * 100
    return 0.0


def max_favorable_excursion_pct(p: PositionState) -> float:
    if p.direction == Direction.LONG:
        return (p.max_price_since_entry - p.entry_price) / p.entry_price * 100
    if p.direction == Direction.SHORT:
        return (p.entry_price - p.min_price_since_entry) / p.entry_price * 100
    return 0.0


def decide_exit(p: PositionState) -> ExitDecision:
    pnl = current_return_pct(p)
    mfe = max_favorable_excursion_pct(p)
    giveback = mfe - pnl

    if p.spread_bps > 30:
        return ExitDecision(DecisionAction.EXIT, 98, "spread_explosion")
    if p.news_alignment < 0.38:
        return ExitDecision(DecisionAction.EXIT, 94, "news_thesis_invalidated")
    if p.cross_asset_alignment < 0.38:
        return ExitDecision(DecisionAction.EXIT, 90, "cross_asset_confirmation_broken")
    if p.reversal_score >= 0.68:
        return ExitDecision(DecisionAction.EXIT, 92, "hard_reversal_detected")
    if p.confidence_now < p.confidence_at_entry - 0.22:
        return ExitDecision(DecisionAction.REDUCE, 78, "confidence_decay", reduce_fraction=0.50)
    if mfe > 0 and giveback >= max(0.20, mfe * 0.35):
        return ExitDecision(DecisionAction.REDUCE, 75, "profit_giveback_protection", reduce_fraction=0.50)
    if p.seconds_in_trade > 3600 and pnl <= 0:
        return ExitDecision(DecisionAction.EXIT, 70, "time_stop_no_follow_through")
    return ExitDecision(DecisionAction.WATCH, 20, "hold")
