#!/usr/bin/env python3
"""
Seed the economic calendar with known recurring events for AUD/USD and NZD/USD.

Generates the next 3 months of events (2026-03-30 through 2026-06-30) based on
typical scheduling patterns for central bank meetings, employment data, inflation
reports, and other market-moving releases.

Usage:
    python seed_calendar.py          # Run standalone
    from seed_calendar import seed   # Import and call seed()
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Allow imports from the backend directory
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from database import init_db, insert_event, get_db

# ─── Date helpers ────────────────────────────────────────────────────────────

START_DATE = date(2026, 3, 30)
END_DATE = date(2026, 6, 30)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> Optional[date]:
    """
    Return the n-th occurrence of a weekday in a given month.
    weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    n: 1-based (1st, 2nd, 3rd...)
    Returns None if the month doesn't have that many occurrences.
    """
    first_day = date(year, month, 1)
    # Offset to reach the first occurrence of the target weekday
    offset = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + timedelta(days=offset)
    target = first_occurrence + timedelta(weeks=n - 1)
    if target.month != month:
        return None
    return target


def first_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the first occurrence of a weekday in a month."""
    return nth_weekday(year, month, weekday, 1)


def months_in_range():
    """Yield (year, month) tuples from START_DATE through END_DATE."""
    d = START_DATE.replace(day=1)
    while d <= END_DATE:
        yield d.year, d.month
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1)
        else:
            d = d.replace(month=d.month + 1)


def in_range(d: Optional[date]) -> bool:
    """Check if a date falls within our seeding window."""
    return d is not None and START_DATE <= d <= END_DATE


def make_dt(d: date, hour: int = 12, minute: int = 0) -> str:
    """Format a date+time as ISO string for the events table."""
    return datetime(d.year, d.month, d.day, hour, minute).isoformat()


# ─── Event generators ───────────────────────────────────────────────────────

def generate_events() -> list[dict]:
    """
    Build the full list of economic events for the seeding window.
    Returns a list of dicts ready for insert_event().
    """
    events: list[dict] = []

    # ═══════════════════════════════════════════════════════════════════
    # A-LEVEL EVENTS
    # ═══════════════════════════════════════════════════════════════════

    # --- RBA Interest Rate Decision ---
    # First Tuesday of: Feb, Mar, May, Jun, Aug, Sep, Nov, Dec
    rba_months = [2, 3, 5, 6, 8, 9, 11, 12]
    for year, month in months_in_range():
        if month in rba_months:
            d = first_weekday_of_month(year, month, 1)  # Tuesday
            if in_range(d):
                events.append(dict(
                    title="RBA Interest Rate Decision",
                    country="AU",
                    impact="A",
                    dt=make_dt(d, 4, 30),  # 2:30 PM AEST = 04:30 UTC
                    pair_affected="AUD/USD",
                ))

    # --- RBNZ Interest Rate Decision ---
    # Typically: Feb, Apr, May, Jul, Aug, Oct, Nov
    rbnz_months = [2, 4, 5, 7, 8, 10, 11]
    for year, month in months_in_range():
        if month in rbnz_months:
            # RBNZ usually meets on a Wednesday in the last full week
            d = nth_weekday(year, month, 2, 3)  # 3rd Wednesday as approximation
            if in_range(d):
                events.append(dict(
                    title="RBNZ Interest Rate Decision",
                    country="NZ",
                    impact="A",
                    dt=make_dt(d, 1, 0),  # 2:00 PM NZST = 01:00 UTC
                    pair_affected="NZD/USD",
                ))

    # --- US FOMC Decision ---
    # 2026 approximate dates: Jan 28, Mar 18, May 6, Jun 17
    fomc_dates = [
        date(2026, 3, 18),
        date(2026, 5, 6),
        date(2026, 6, 17),
    ]
    for d in fomc_dates:
        if in_range(d):
            events.append(dict(
                title="US FOMC Interest Rate Decision",
                country="US",
                impact="A",
                dt=make_dt(d, 18, 0),  # 2:00 PM ET = 18:00 UTC
                pair_affected="AUD/USD,NZD/USD",
            ))

    # --- Australian CPI (quarterly) ---
    # Released ~late Jan, late Apr, late Jul, late Oct (Wednesday)
    au_cpi_dates = [
        date(2026, 4, 29),  # Q1 2026
    ]
    for d in au_cpi_dates:
        if in_range(d):
            events.append(dict(
                title="Australian CPI (Quarterly)",
                country="AU",
                impact="A",
                dt=make_dt(d, 1, 30),  # 11:30 AM AEST = 01:30 UTC
                pair_affected="AUD/USD",
            ))

    # --- Australian Monthly CPI Indicator ---
    # Released monthly except quarter months, around the 25th-28th
    au_monthly_cpi = [
        date(2026, 3, 31),  # Feb reading
        date(2026, 5, 27),  # Apr reading
        date(2026, 6, 24),  # May reading
    ]
    for d in au_monthly_cpi:
        if in_range(d):
            events.append(dict(
                title="Australian Monthly CPI Indicator",
                country="AU",
                impact="A",
                dt=make_dt(d, 1, 30),
                pair_affected="AUD/USD",
            ))

    # --- NZ CPI (quarterly) ---
    # Released ~mid Jan, mid Apr, mid Jul, mid Oct
    nz_cpi_dates = [
        date(2026, 4, 16),  # Q1 2026
    ]
    for d in nz_cpi_dates:
        if in_range(d):
            events.append(dict(
                title="NZ CPI (Quarterly)",
                country="NZ",
                impact="A",
                dt=make_dt(d, 22, 45),  # 10:45 AM NZST next day -> 22:45 UTC prior
                pair_affected="NZD/USD",
            ))

    # --- US Non-Farm Payrolls ---
    # First Friday of each month
    for year, month in months_in_range():
        d = first_weekday_of_month(year, month, 4)  # Friday
        if in_range(d):
            events.append(dict(
                title="US Non-Farm Payrolls",
                country="US",
                impact="A",
                dt=make_dt(d, 12, 30),  # 8:30 AM ET = 12:30 UTC
                pair_affected="AUD/USD,NZD/USD",
            ))

    # --- Australian Employment Change ---
    # Monthly, typically the 3rd Thursday
    for year, month in months_in_range():
        d = nth_weekday(year, month, 3, 3)  # 3rd Thursday
        if in_range(d):
            events.append(dict(
                title="Australian Employment Change",
                country="AU",
                impact="A",
                dt=make_dt(d, 1, 30),  # 11:30 AM AEST = 01:30 UTC
                pair_affected="AUD/USD",
            ))

    # --- NZ Employment Change (quarterly) ---
    # Released ~early Feb, May, Aug, Nov
    nz_employment_dates = [
        date(2026, 5, 6),  # Q1 2026
    ]
    for d in nz_employment_dates:
        if in_range(d):
            events.append(dict(
                title="NZ Employment Change (Quarterly)",
                country="NZ",
                impact="A",
                dt=make_dt(d, 22, 45),
                pair_affected="NZD/USD",
            ))

    # ═══════════════════════════════════════════════════════════════════
    # B-LEVEL EVENTS
    # ═══════════════════════════════════════════════════════════════════

    # --- China Manufacturing PMI ---
    # 1st of each month (or last day of prior month)
    for year, month in months_in_range():
        d = date(year, month, 1)
        if in_range(d):
            events.append(dict(
                title="China Manufacturing PMI",
                country="CN",
                impact="B",
                dt=make_dt(d, 1, 0),  # 9:00 AM Beijing = 01:00 UTC
                pair_affected="AUD/USD,NZD/USD",
            ))

    # --- China Caixin Manufacturing PMI ---
    # Usually 1st business day of month
    for year, month in months_in_range():
        d = date(year, month, 1)
        # Shift to Monday if weekend
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if in_range(d):
            events.append(dict(
                title="China Caixin Manufacturing PMI",
                country="CN",
                impact="B",
                dt=make_dt(d, 1, 45),
                pair_affected="AUD/USD,NZD/USD",
            ))

    # --- RBA Governor Speech ---
    # Approximate dates - major scheduled speeches
    rba_speeches = [
        date(2026, 4, 8),
        date(2026, 5, 12),
        date(2026, 6, 9),
    ]
    for d in rba_speeches:
        if in_range(d):
            events.append(dict(
                title="RBA Governor Speech",
                country="AU",
                impact="B",
                dt=make_dt(d, 3, 0),
                pair_affected="AUD/USD",
            ))

    # --- US CPI ---
    # Monthly, typically around the 13th
    us_cpi_dates = [
        date(2026, 4, 14),
        date(2026, 5, 13),
        date(2026, 6, 10),
    ]
    for d in us_cpi_dates:
        if in_range(d):
            events.append(dict(
                title="US CPI (Consumer Price Index)",
                country="US",
                impact="B",
                dt=make_dt(d, 12, 30),
                pair_affected="AUD/USD,NZD/USD",
            ))

    # --- US Retail Sales ---
    # Monthly, mid-month
    us_retail_dates = [
        date(2026, 4, 15),
        date(2026, 5, 15),
        date(2026, 6, 16),
    ]
    for d in us_retail_dates:
        if in_range(d):
            events.append(dict(
                title="US Retail Sales",
                country="US",
                impact="B",
                dt=make_dt(d, 12, 30),
                pair_affected="AUD/USD,NZD/USD",
            ))

    # --- Australian Retail Sales ---
    # Monthly, end of month for prior month data
    au_retail_dates = [
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 6, 1),
    ]
    for d in au_retail_dates:
        if in_range(d):
            events.append(dict(
                title="Australian Retail Sales",
                country="AU",
                impact="B",
                dt=make_dt(d, 1, 30),
                pair_affected="AUD/USD",
            ))

    # --- NZ Retail Sales (quarterly) ---
    nz_retail_dates = [
        date(2026, 5, 22),
    ]
    for d in nz_retail_dates:
        if in_range(d):
            events.append(dict(
                title="NZ Retail Sales (Quarterly)",
                country="NZ",
                impact="B",
                dt=make_dt(d, 22, 45),
                pair_affected="NZD/USD",
            ))

    # --- Australian Trade Balance ---
    # Monthly, first week
    for year, month in months_in_range():
        d = nth_weekday(year, month, 3, 1)  # 1st Thursday
        if in_range(d):
            events.append(dict(
                title="Australian Trade Balance",
                country="AU",
                impact="B",
                dt=make_dt(d, 1, 30),
                pair_affected="AUD/USD",
            ))

    # --- NZ Trade Balance ---
    # Monthly, ~last week of month
    nz_trade_dates = [
        date(2026, 3, 30),
        date(2026, 4, 28),
        date(2026, 5, 27),
        date(2026, 6, 25),
    ]
    for d in nz_trade_dates:
        if in_range(d):
            events.append(dict(
                title="NZ Trade Balance",
                country="NZ",
                impact="B",
                dt=make_dt(d, 22, 45),
                pair_affected="NZD/USD",
            ))

    # --- GDT Dairy Auction ---
    # Bi-weekly on Tuesdays (NZ's largest export)
    # Start from first Tuesday in range
    d = START_DATE
    while d.weekday() != 1:  # Find first Tuesday
        d += timedelta(days=1)
    while d <= END_DATE:
        if in_range(d):
            events.append(dict(
                title="GDT Dairy Price Auction",
                country="NZ",
                impact="B",
                dt=make_dt(d, 12, 0),  # Midday UTC
                pair_affected="NZD/USD",
            ))
        d += timedelta(weeks=2)

    # --- US PPI ---
    # Monthly, day before or after CPI
    us_ppi_dates = [
        date(2026, 4, 13),
        date(2026, 5, 14),
        date(2026, 6, 11),
    ]
    for d in us_ppi_dates:
        if in_range(d):
            events.append(dict(
                title="US PPI (Producer Price Index)",
                country="US",
                impact="B",
                dt=make_dt(d, 12, 30),
                pair_affected="AUD/USD,NZD/USD",
            ))

    # ═══════════════════════════════════════════════════════════════════
    # C-LEVEL EVENTS
    # ═══════════════════════════════════════════════════════════════════

    # --- Australian Building Permits ---
    # Monthly, early month
    au_building_dates = [
        date(2026, 4, 7),
        date(2026, 5, 5),
        date(2026, 6, 2),
    ]
    for d in au_building_dates:
        if in_range(d):
            events.append(dict(
                title="Australian Building Permits",
                country="AU",
                impact="C",
                dt=make_dt(d, 1, 30),
                pair_affected="AUD/USD",
            ))

    # --- NZ Building Permits ---
    nz_building_dates = [
        date(2026, 4, 29),
        date(2026, 5, 28),
        date(2026, 6, 29),
    ]
    for d in nz_building_dates:
        if in_range(d):
            events.append(dict(
                title="NZ Building Permits",
                country="NZ",
                impact="C",
                dt=make_dt(d, 22, 45),
                pair_affected="NZD/USD",
            ))

    # --- Westpac Consumer Confidence (AU) ---
    # Monthly, ~2nd Wednesday
    for year, month in months_in_range():
        d = nth_weekday(year, month, 2, 2)  # 2nd Wednesday
        if in_range(d):
            events.append(dict(
                title="Westpac Consumer Confidence",
                country="AU",
                impact="C",
                dt=make_dt(d, 0, 30),
                pair_affected="AUD/USD",
            ))

    # --- ANZ Consumer Confidence (NZ) ---
    # Monthly, end of month
    nz_consumer_dates = [
        date(2026, 3, 30),
        date(2026, 4, 27),
        date(2026, 5, 25),
        date(2026, 6, 29),
    ]
    for d in nz_consumer_dates:
        if in_range(d):
            events.append(dict(
                title="ANZ Consumer Confidence (NZ)",
                country="NZ",
                impact="C",
                dt=make_dt(d, 1, 0),
                pair_affected="NZD/USD",
            ))

    # --- NAB Business Confidence (AU) ---
    # Monthly, ~2nd Tuesday
    for year, month in months_in_range():
        d = nth_weekday(year, month, 1, 2)  # 2nd Tuesday
        if in_range(d):
            events.append(dict(
                title="NAB Business Confidence",
                country="AU",
                impact="C",
                dt=make_dt(d, 1, 30),
                pair_affected="AUD/USD",
            ))

    # --- ANZ Business Confidence (NZ) ---
    # Monthly, last Thursday
    for year, month in months_in_range():
        d = nth_weekday(year, month, 3, 4)  # 4th Thursday (approx last)
        if d is None:
            d = nth_weekday(year, month, 3, 3)
        if in_range(d):
            events.append(dict(
                title="ANZ Business Confidence (NZ)",
                country="NZ",
                impact="C",
                dt=make_dt(d, 1, 0),
                pair_affected="NZD/USD",
            ))

    # --- US Consumer Confidence (Conference Board) ---
    # Monthly, last Tuesday
    for year, month in months_in_range():
        d = nth_weekday(year, month, 1, 4)  # 4th Tuesday (approx last)
        if d is None:
            d = nth_weekday(year, month, 1, 3)
        if in_range(d):
            events.append(dict(
                title="US Consumer Confidence",
                country="US",
                impact="C",
                dt=make_dt(d, 14, 0),
                pair_affected="AUD/USD,NZD/USD",
            ))

    # --- US Michigan Consumer Sentiment ---
    # Mid-month Friday (preliminary) and end-month Friday (final)
    us_michigan_dates = [
        date(2026, 4, 10),
        date(2026, 4, 24),
        date(2026, 5, 15),
        date(2026, 5, 29),
        date(2026, 6, 12),
        date(2026, 6, 26),
    ]
    for d in us_michigan_dates:
        if in_range(d):
            events.append(dict(
                title="US Michigan Consumer Sentiment",
                country="US",
                impact="C",
                dt=make_dt(d, 14, 0),
                pair_affected="AUD/USD,NZD/USD",
            ))

    return events


# ─── Seeding logic ───────────────────────────────────────────────────────────

async def clear_future_events() -> int:
    """Remove existing events from START_DATE forward to avoid duplicates."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM events WHERE datetime >= ?",
            (START_DATE.isoformat(),),
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await db.close()


async def seed() -> int:
    """
    Seed the economic calendar. Returns the number of events inserted.
    Safe to run multiple times (clears future events first).
    """
    await init_db()

    deleted = await clear_future_events()
    if deleted:
        print(f"  Cleared {deleted} existing future events.")

    events = generate_events()

    # Sort by datetime
    events.sort(key=lambda e: e["dt"])

    count = 0
    for ev in events:
        await insert_event(
            title=ev["title"],
            country=ev["country"],
            impact=ev["impact"],
            dt=ev["dt"],
            forecast="",
            previous="",
            pair_affected=ev["pair_affected"],
        )
        count += 1

    return count


async def main():
    """Entry point when run as a standalone script."""
    print()
    print("=" * 60)
    print("  FX Trading System - Economic Calendar Seeder")
    print("=" * 60)
    print()
    print(f"  Seeding window: {START_DATE} to {END_DATE}")
    print()

    count = await seed()

    print()
    print(f"  Successfully seeded {count} economic events.")
    print()

    # Print summary by category
    events = generate_events()
    events.sort(key=lambda e: e["dt"])

    a_count = sum(1 for e in events if e["impact"] == "A")
    b_count = sum(1 for e in events if e["impact"] == "B")
    c_count = sum(1 for e in events if e["impact"] == "C")

    au_count = sum(1 for e in events if e["country"] == "AU")
    nz_count = sum(1 for e in events if e["country"] == "NZ")
    us_count = sum(1 for e in events if e["country"] == "US")
    cn_count = sum(1 for e in events if e["country"] == "CN")

    print("  Breakdown by impact:")
    print(f"    A-level (high):   {a_count}")
    print(f"    B-level (medium): {b_count}")
    print(f"    C-level (low):    {c_count}")
    print()
    print("  Breakdown by country:")
    print(f"    Australia (AU):   {au_count}")
    print(f"    New Zealand (NZ): {nz_count}")
    print(f"    United States:    {us_count}")
    print(f"    China (CN):       {cn_count}")
    print()

    # Show next 10 upcoming events
    print("  Next 10 upcoming events:")
    print("  " + "-" * 56)
    for ev in events[:10]:
        dt_str = ev["dt"][:16].replace("T", " ")
        print(f"    {dt_str}  [{ev['impact']}] {ev['title']}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
