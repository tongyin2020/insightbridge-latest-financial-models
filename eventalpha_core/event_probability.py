from __future__ import annotations

from .schema import EventGrade, MacroEvent, MarketState


BASE_PRIOR = {
    EventGrade.IGNORE: 0.05,
    EventGrade.WATCH: 0.25,
    EventGrade.TRADE_CANDIDATE: 0.55,
    EventGrade.HIGH_CONVICTION: 0.72,
    EventGrade.EXTREME: 0.82,
}


def clamp(x: float, lo: float = 0.0, hi: float = 0.99) -> float:
    return max(lo, min(hi, x))


def bayesian_event_confidence(event: MacroEvent, grade: EventGrade, state: MarketState, memory_edge: float = 0.50) -> float:
    """A transparent Bayesian-style scoring model.

    Not a true posterior unless calibrated with historical data. It is intentionally
    simple and auditable for paper trading and later calibration.
    """
    prior = BASE_PRIOR[grade]
    evidence = (
        0.18 * state.momentum_score
        + 0.18 * state.cross_asset_alignment
        + 0.15 * state.news_alignment
        + 0.12 * state.liquidity_score
        + 0.10 * event.surprise_score
        + 0.10 * event.liquidity_score
        + 0.07 * event.policy_score
        + 0.10 * memory_edge
    )
    penalty = 0.0
    if state.spread_bps > 20:
        penalty += 0.10
    if state.reversal_score > 0.55:
        penalty += 0.14
    if state.volatility_z > 4.0:
        penalty += 0.08
    confidence = 0.45 * prior + 0.55 * evidence - penalty
    return clamp(confidence)
