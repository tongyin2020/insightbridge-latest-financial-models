"""
WTI Trading Platform - Event Engine & Economic Calendar
Tracks geopolitical events, economic data releases, and their impact on oil prices.
Inspired by the FX Trading Dashboard's 事件引擎 and 经济日历.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class EventImpact(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventCategory(str, Enum):
    GEOPOLITICAL = "geopolitical"
    ECONOMIC_DATA = "economic_data"
    CENTRAL_BANK = "central_bank"
    SUPPLY = "supply"
    DEMAND = "demand"
    INVENTORY = "inventory"
    OPEC = "opec"


class EventPhase(str, Enum):
    UPCOMING = "upcoming"       # Before event
    ACTIVE = "active"           # Event window (cooldown)
    POST_EVENT = "post_event"   # After event, observing
    EXPIRED = "expired"         # No longer relevant


@dataclass
class EconomicCalendarEvent:
    id: str
    title: str
    category: EventCategory
    impact: EventImpact
    scheduled_time: str
    description: str = ""
    forecast: str = ""
    previous: str = ""
    actual: str = ""
    phase: EventPhase = EventPhase.UPCOMING
    oil_relevance: str = ""
    direction_bias: str = "neutral"  # bullish / bearish / neutral

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category.value,
            "impact": self.impact.value,
            "scheduled_time": self.scheduled_time,
            "description": self.description,
            "forecast": self.forecast,
            "previous": self.previous,
            "actual": self.actual,
            "phase": self.phase.value,
            "oil_relevance": self.oil_relevance,
            "direction_bias": self.direction_bias,
        }


@dataclass
class EventEngineState:
    active_events: List[EconomicCalendarEvent] = field(default_factory=list)
    cooldown_active: bool = False
    cooldown_reason: str = ""
    cooldown_remaining_sec: int = 0
    halt_trading: bool = False
    risk_modifier: float = 1.0  # 0.0 = no trading, 1.0 = normal


class EventEngine:
    """
    Event-driven trading engine that tracks economic calendar
    and geopolitical events affecting oil markets.
    """

    def __init__(self):
        self._events: List[EconomicCalendarEvent] = []
        self._cooldown_until: Optional[datetime] = None
        self._cooldown_reason = ""
        self._default_cooldown_min = 15
        self._state = EventEngineState()
        self._init_calendar()

    def _init_calendar(self):
        """Initialize with key recurring economic events affecting oil"""
        now = datetime.now(timezone.utc)
        base_events = [
            {
                "id": "eia_inventory",
                "title": "EIA Crude Oil Inventories",
                "category": EventCategory.INVENTORY,
                "impact": EventImpact.HIGH,
                "description": "Weekly US crude oil inventory report. Builds are bearish, draws are bullish for oil.",
                "oil_relevance": "Direct: Inventory changes directly affect WTI supply/demand pricing",
                "schedule_offset_hours": 2,
            },
            {
                "id": "opec_meeting",
                "title": "OPEC+ Monthly Meeting",
                "category": EventCategory.OPEC,
                "impact": EventImpact.HIGH,
                "description": "OPEC+ production quota decisions. Production cuts are bullish, increases are bearish.",
                "oil_relevance": "Direct: Controls global oil supply allocation",
                "schedule_offset_hours": 24,
            },
            {
                "id": "us_cpi",
                "title": "US CPI Data Release",
                "category": EventCategory.ECONOMIC_DATA,
                "impact": EventImpact.HIGH,
                "description": "US Consumer Price Index. Higher CPI = hawkish Fed = stronger USD = bearish oil.",
                "oil_relevance": "Indirect: CPI affects USD strength which inversely impacts oil prices",
                "forecast": "3.2%",
                "previous": "3.1%",
                "schedule_offset_hours": 6,
            },
            {
                "id": "us_nfp",
                "title": "US Non-Farm Payrolls",
                "category": EventCategory.ECONOMIC_DATA,
                "impact": EventImpact.HIGH,
                "description": "US employment data. Strong jobs = hawkish Fed = USD strength.",
                "oil_relevance": "Indirect: Employment strength affects demand outlook and USD",
                "forecast": "185K",
                "previous": "175K",
                "schedule_offset_hours": 12,
            },
            {
                "id": "china_pmi",
                "title": "China Manufacturing PMI",
                "category": EventCategory.DEMAND,
                "impact": EventImpact.MEDIUM,
                "description": "China's manufacturing activity. Above 50 = expansion = bullish oil demand.",
                "oil_relevance": "Direct: China is top oil importer; PMI indicates demand trajectory",
                "forecast": "50.5",
                "previous": "50.2",
                "schedule_offset_hours": 8,
            },
            {
                "id": "fed_decision",
                "title": "Federal Reserve Rate Decision",
                "category": EventCategory.CENTRAL_BANK,
                "impact": EventImpact.HIGH,
                "description": "Fed interest rate decision. Rate hikes strengthen USD, bearish for oil.",
                "oil_relevance": "Indirect: Rate decisions affect USD and global growth outlook",
                "schedule_offset_hours": 18,
            },
            {
                "id": "hormuz_risk",
                "title": "Strait of Hormuz Shipping Risk",
                "category": EventCategory.GEOPOLITICAL,
                "impact": EventImpact.HIGH,
                "description": "Tensions in Persian Gulf shipping lanes. Disruption threats are bullish for oil.",
                "oil_relevance": "Direct: 20% of global oil transits through Hormuz; any disruption = supply shock",
                "schedule_offset_hours": 4,
            },
            {
                "id": "baker_hughes",
                "title": "Baker Hughes Rig Count",
                "category": EventCategory.SUPPLY,
                "impact": EventImpact.MEDIUM,
                "description": "US active oil rig count. Increasing rigs = more future supply = bearish.",
                "oil_relevance": "Direct: Leading indicator of future US oil production capacity",
                "forecast": "482",
                "previous": "479",
                "schedule_offset_hours": 30,
            },
            {
                "id": "mideast_escalation",
                "title": "Middle East Geopolitical Escalation",
                "category": EventCategory.GEOPOLITICAL,
                "impact": EventImpact.HIGH,
                "description": "Military tensions or supply infrastructure attacks in Middle East.",
                "oil_relevance": "Direct: Regional instability threatens oil production and transport",
                "schedule_offset_hours": 10,
            },
            {
                "id": "api_inventory",
                "title": "API Weekly Crude Stock",
                "category": EventCategory.INVENTORY,
                "impact": EventImpact.MEDIUM,
                "description": "API inventory report (precedes EIA). Sets market expectations.",
                "oil_relevance": "Direct: Preview of official EIA data, moves oil prices after hours",
                "schedule_offset_hours": 1,
            },
        ]

        for evt in base_events:
            scheduled = now + timedelta(hours=evt["schedule_offset_hours"])
            self._events.append(EconomicCalendarEvent(
                id=evt["id"],
                title=evt["title"],
                category=evt["category"],
                impact=evt["impact"],
                scheduled_time=scheduled.isoformat(),
                description=evt["description"],
                oil_relevance=evt["oil_relevance"],
                forecast=evt.get("forecast", ""),
                previous=evt.get("previous", ""),
            ))

    def get_calendar(self, hours_ahead: int = 48) -> List[Dict]:
        """Get upcoming events within time window"""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)
        result = []
        for evt in self._events:
            try:
                evt_time = datetime.fromisoformat(evt.scheduled_time)
                if evt_time <= cutoff:
                    # Update phase
                    if evt_time > now + timedelta(minutes=30):
                        evt.phase = EventPhase.UPCOMING
                    elif evt_time > now - timedelta(minutes=5):
                        evt.phase = EventPhase.ACTIVE
                    elif evt_time > now - timedelta(hours=2):
                        evt.phase = EventPhase.POST_EVENT
                    else:
                        evt.phase = EventPhase.EXPIRED
                    result.append(evt.to_dict())
            except (ValueError, TypeError):
                result.append(evt.to_dict())
        result.sort(key=lambda x: x["scheduled_time"])
        return result

    def trigger_event(self, event_id: str, actual_value: str = "", direction: str = "neutral") -> Dict:
        """Simulate an event being released"""
        for evt in self._events:
            if evt.id == event_id:
                evt.actual = actual_value
                evt.direction_bias = direction
                evt.phase = EventPhase.ACTIVE

                # Activate cooldown for high-impact events
                if evt.impact == EventImpact.HIGH:
                    self._cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=self._default_cooldown_min)
                    self._cooldown_reason = f"高影响事件: {evt.title}"

                return {"triggered": True, "event": evt.to_dict(), "cooldown_minutes": self._default_cooldown_min}

        return {"triggered": False, "error": "Event not found"}

    def get_state(self) -> Dict:
        """Get current event engine state"""
        now = datetime.now(timezone.utc)
        cooldown_active = self._cooldown_until is not None and now < self._cooldown_until
        cooldown_remaining = 0
        if cooldown_active and self._cooldown_until:
            cooldown_remaining = int((self._cooldown_until - now).total_seconds())

        upcoming_high = [e for e in self._events
                         if e.impact == EventImpact.HIGH and e.phase == EventPhase.UPCOMING]

        # Risk modifier: reduce during cooldown or pre-event
        risk_modifier = 1.0
        if cooldown_active:
            risk_modifier = 0.0  # No new trades during cooldown
        elif upcoming_high:
            risk_modifier = 0.5  # Reduce size before high-impact events

        return {
            "cooldown_active": cooldown_active,
            "cooldown_reason": self._cooldown_reason if cooldown_active else "",
            "cooldown_remaining_sec": cooldown_remaining,
            "halt_trading": cooldown_active,
            "risk_modifier": risk_modifier,
            "upcoming_high_impact": len(upcoming_high),
            "total_events": len(self._events),
        }


# Global instance
event_engine = EventEngine()
