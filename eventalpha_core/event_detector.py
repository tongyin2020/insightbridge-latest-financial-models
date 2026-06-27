from __future__ import annotations

import re
from typing import Iterable, List

from .schema import EventGrade, EventType, MacroEvent


KEYWORDS = {
    EventType.CPI: ["cpi", "inflation", "core cpi", "headline cpi"],
    EventType.FOMC: ["fomc", "powell", "fed decision", "dot plot", "federal reserve"],
    EventType.NFP: ["nonfarm", "payroll", "nfp", "unemployment"],
    EventType.TREASURY_AUCTION: ["treasury auction", "tail", "bid-to-cover"],
    EventType.OPEC: ["opec", "production cut", "oil output"],
    EventType.EIA_INVENTORY: ["eia", "crude inventory", "oil inventory"],
    EventType.GEOPOLITICAL: ["war", "missile", "sanction", "invasion", "conflict", "red sea", "middle east"],
    EventType.LIQUIDITY_SHOCK: ["liquidity", "repo", "funding stress", "bank crisis", "credit stress"],
    EventType.REGULATORY: ["sec", "regulation", "ban", "etf approval", "lawsuit"],
    EventType.EARNINGS_SHOCK: ["earnings", "guidance", "mega cap", "profit warning"],
}


def classify_text_event(title: str, body: str = "") -> EventType:
    text = f"{title} {body}".lower()
    for event_type, words in KEYWORDS.items():
        if any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words):
            return event_type
    return EventType.UNKNOWN


def grade_event(event: MacroEvent) -> EventGrade:
    score = (
        0.25 * event.source_confidence
        + 0.25 * event.surprise_score
        + 0.20 * event.geopolitical_score
        + 0.20 * event.liquidity_score
        + 0.10 * event.policy_score
    )
    if event.event_type in {EventType.FOMC, EventType.CPI, EventType.NFP, EventType.GEOPOLITICAL, EventType.OPEC}:
        score += 0.10
    if event.human_thesis:
        score += 0.05
    score = max(0.0, min(1.0, score))
    if score >= 0.88:
        return EventGrade.EXTREME
    if score >= 0.78:
        return EventGrade.HIGH_CONVICTION
    if score >= 0.65:
        return EventGrade.TRADE_CANDIDATE
    if score >= 0.45:
        return EventGrade.WATCH
    return EventGrade.IGNORE


def detect_events_from_headlines(headlines: Iterable[str]) -> List[MacroEvent]:
    events: List[MacroEvent] = []
    for i, h in enumerate(headlines):
        et = classify_text_event(h)
        if et != EventType.UNKNOWN:
            events.append(MacroEvent(event_id=f"headline_{i}", event_type=et, title=h, source_confidence=0.65))
    return events
