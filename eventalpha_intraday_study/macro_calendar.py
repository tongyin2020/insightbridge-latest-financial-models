"""Precise-timestamp macro event calendar for 2024-2026.

The event study needs the exact release instant (T0) in UTC. US releases are
scheduled in US Eastern local time and converted to UTC with correct DST
handling via zoneinfo:

- NFP  (Employment Situation): first Friday of the month, 08:30 ET  -> deterministic
- CPI  (Consumer Price Index): 08:30 ET on curated real release dates
- FOMC (rate decision statement): 14:00 ET on curated real meeting dates

`surprise` (actual - forecast, normalised) is optional; when unknown it is left
as None. Release *timestamps* are what drive the timing measurements; surprise is
only used later as a feature for conditioning trend-lifetime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class MacroEvent:
    event_type: str          # NFP | CPI | FOMC
    t0_utc: datetime         # exact release instant in UTC
    title: str
    surprise: Optional[float] = None   # normalised (actual-forecast); None if unknown


# --- Curated real release dates (US) -----------------------------------------
# FOMC statement dates (14:00 ET). Verified public schedule.
_FOMC_DATES = [
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
]

# CPI release dates (08:30 ET). 2024 verified; 2025 best-effort curated.
_CPI_DATES = [
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10",
    "2024-05-15", "2024-06-12", "2024-07-11", "2024-08-14",
    "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10",
    "2025-05-13", "2025-06-11", "2025-07-15", "2025-08-12",
    "2025-09-11", "2025-11-13", "2025-12-10",
]


def _et_to_utc(d: date, hh: int, mm: int) -> datetime:
    local = datetime.combine(d, time(hh, mm), tzinfo=ET)
    return local.astimezone(UTC)


def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 4:  # 4 = Friday
        d += timedelta(days=1)
    return d


def nfp_events(start_year: int, end_year: int) -> list[MacroEvent]:
    out: list[MacroEvent] = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            d = _first_friday(y, m)
            out.append(MacroEvent("NFP", _et_to_utc(d, 8, 30), f"NFP {y}-{m:02d}"))
    return out


def cpi_events() -> list[MacroEvent]:
    out = []
    for raw in _CPI_DATES:
        d = date.fromisoformat(raw)
        out.append(MacroEvent("CPI", _et_to_utc(d, 8, 30), f"CPI {raw}"))
    return out


def fomc_events() -> list[MacroEvent]:
    out = []
    for raw in _FOMC_DATES:
        d = date.fromisoformat(raw)
        out.append(MacroEvent("FOMC", _et_to_utc(d, 14, 0), f"FOMC {raw}"))
    return out


def build_calendar(start_year: int = 2024, end_year: int = 2026,
                   types: tuple[str, ...] = ("NFP", "CPI", "FOMC")) -> list[MacroEvent]:
    events: list[MacroEvent] = []
    if "NFP" in types:
        events += nfp_events(start_year, end_year)
    if "CPI" in types:
        events += cpi_events()
    if "FOMC" in types:
        events += fomc_events()
    lo = datetime(start_year, 1, 1, tzinfo=UTC)
    hi = datetime(end_year, 12, 31, 23, 59, tzinfo=UTC)
    events = [e for e in events if lo <= e.t0_utc <= hi]
    events.sort(key=lambda e: e.t0_utc)
    return events


if __name__ == "__main__":
    cal = build_calendar(2024, 2025)
    print(f"{len(cal)} events 2024-2025")
    for e in cal[:6]:
        print(f"  {e.event_type:4s} {e.t0_utc.isoformat()}  {e.title}")
    print("  ...")
    for e in cal[-3:]:
        print(f"  {e.event_type:4s} {e.t0_utc.isoformat()}  {e.title}")
