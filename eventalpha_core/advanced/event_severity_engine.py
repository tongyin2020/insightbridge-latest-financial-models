from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List

from eventalpha_core.schema import EventGrade, EventType, MacroEvent


@dataclass
class SeverityResult:
    grade: EventGrade
    severity_score: float
    tradeable: bool
    reasons: List[str]


def event_severity(event: MacroEvent, forecast_surprise: float = 0.0, market_gap_score: float = 0.0) -> SeverityResult:
    """Turn a macro/news event into a trading priority.

    Score design:
    - scheduled macro surprises need data-surprise + market confirmation;
    - geopolitical/liquidity shocks can be tradeable with less forecast data;
    - regulatory/earnings events only matter if cross-asset impact is visible.
    """
    base = {
        EventType.FOMC: 0.55,
        EventType.CPI: 0.52,
        EventType.NFP: 0.45,
        EventType.TREASURY_AUCTION: 0.38,
        EventType.OPEC: 0.45,
        EventType.EIA_INVENTORY: 0.36,
        EventType.GEOPOLITICAL: 0.50,
        EventType.LIQUIDITY_SHOCK: 0.58,
        EventType.CENTRAL_BANK: 0.48,
        EventType.REGULATORY: 0.35,
        EventType.EARNINGS_SHOCK: 0.30,
        EventType.GDP: 0.30,
        EventType.UNKNOWN: 0.15,
    }.get(event.event_type, 0.20)
    score = base
    score += 0.18 * abs(event.surprise_score)
    score += 0.16 * abs(forecast_surprise)
    score += 0.15 * event.policy_score
    score += 0.18 * event.liquidity_score
    score += 0.20 * event.geopolitical_score
    score += 0.14 * market_gap_score
    score += 0.08 * event.source_confidence
    score = max(0.0, min(1.0, score))
    if score >= 0.88:
        grade = EventGrade.EXTREME
    elif score >= 0.78:
        grade = EventGrade.HIGH_CONVICTION
    elif score >= 0.64:
        grade = EventGrade.TRADE_CANDIDATE
    elif score >= 0.45:
        grade = EventGrade.WATCH
    else:
        grade = EventGrade.IGNORE
    reasons = [
        f"base_event_importance={base:.2f}",
        f"surprise={event.surprise_score:.2f}",
        f"policy={event.policy_score:.2f}",
        f"liquidity={event.liquidity_score:.2f}",
        f"geopolitical={event.geopolitical_score:.2f}",
        f"market_gap={market_gap_score:.2f}",
    ]
    return SeverityResult(grade=grade, severity_score=score, tradeable=grade not in {EventGrade.IGNORE, EventGrade.WATCH}, reasons=reasons)
