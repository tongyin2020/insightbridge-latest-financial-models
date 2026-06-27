from __future__ import annotations

from dataclasses import dataclass
from typing import List

from eventalpha_core.schema import EventType, MacroEvent, MarketState


@dataclass
class WaitingPolicy:
    min_wait_seconds: int
    max_wait_seconds: int
    confirmation_checks: List[str]
    reason: str


BASE_WINDOWS = {
    EventType.CPI: (30, 300),
    EventType.NFP: (60, 600),
    EventType.FOMC: (300, 1800),
    EventType.CENTRAL_BANK: (180, 1200),
    EventType.TREASURY_AUCTION: (120, 900),
    EventType.OPEC: (300, 2400),
    EventType.EIA_INVENTORY: (120, 900),
    EventType.GEOPOLITICAL: (180, 3600),
    EventType.LIQUIDITY_SHOCK: (60, 1800),
}


def waiting_policy(event: MacroEvent, state: MarketState, severity_score: float, memory_best_wait: int | None = None) -> WaitingPolicy:
    lo, hi = BASE_WINDOWS.get(event.event_type, (120, 900))
    if memory_best_wait:
        lo = int(0.6 * lo + 0.4 * memory_best_wait)
        hi = max(lo + 60, int(0.6 * hi + 0.4 * memory_best_wait * 2))
    if severity_score >= 0.88 and state.liquidity_score > 0.70:
        lo = max(15, int(lo * 0.65))
    if state.volatility_z > 2.5 or state.spread_bps > 20:
        lo = int(lo * 1.5)
        hi = int(hi * 1.3)
    checks = [
        "price_momentum_still_aligned_after_min_wait",
        "spread_not_widening",
        "no_major_news_contradiction",
        "cross_asset_confirmation_still_above_threshold",
        "reversal_score_below_threshold",
    ]
    return WaitingPolicy(lo, hi, checks, f"event_type={event.event_type.value}; severity={severity_score:.2f}; volatility_z={state.volatility_z:.2f}")
