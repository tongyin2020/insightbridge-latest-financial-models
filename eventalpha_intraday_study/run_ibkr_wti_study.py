"""Event study on IBKR-exported WTI (CL) 5-second bars.

Same engine as the JForex/HistData studies, but for the real WTI front-month
CL bars pulled over the logged-in IBKR Gateway (see wti_check/ibkr_wti_export.py).
Runs at bar_seconds=5 (the export granularity) -- far finer than the 1-minute
Brent proxy it replaces.

Usage:
    python -m eventalpha_intraday_study.run_ibkr_wti_study --years 2024,2025
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone

import pandas as pd

from .config import reports_dir
from .data_sources import jforex_ticks as jf
from .event_study import measure_event, summarize
from .macro_calendar import build_calendar


def run(instrument: str, years: list[int], types: tuple[str, ...], bar_seconds: int) -> dict:
    bars = jf.load_ticks(instrument)
    if bars is None:
        raise SystemExit(f"no IBKR bar export for {instrument} "
                         f"(run wti_check/ibkr_wti_export.py on the Mac first)")
    calendar = build_calendar(min(years), max(years), types)
    safe = instrument.replace("/", "").replace(".", "")
    print(f"[ibkr-wti-study] {instrument}: {len(calendar)} events, {len(bars):,} bars")

    measurements = [measure_event(bars, safe, ev.event_type, ev.t0_utc, ev.title,
                                  ev.surprise, bar_seconds=bar_seconds) for ev in calendar]
    per_event = pd.DataFrame([asdict(m) for m in measurements])
    summary = summarize(measurements)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rdir = reports_dir()
    ev_csv = rdir / f"ibkr_event_measurements_{safe}_{stamp}.csv"
    sum_csv = rdir / f"ibkr_event_summary_{safe}_{stamp}.csv"
    per_event.to_csv(ev_csv, index=False)
    summary.to_csv(sum_csv, index=False)

    print("\n=== SUMMARY (seconds; p25 / median / p75) ===")
    if not summary.empty:
        with pd.option_context("display.max_columns", None, "display.width", 220):
            print(summary.to_string(index=False))
    print(f"\nSaved: {ev_csv}\nSaved: {sum_csv}")
    return {"per_event_csv": str(ev_csv), "summary_csv": str(sum_csv),
            "n_ok": int(per_event["ok"].sum()), "n_total": len(per_event)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--instrument", default="WTIUSD")
    p.add_argument("--years", default="2024,2025")
    p.add_argument("--types", default="NFP,CPI,FOMC")
    p.add_argument("--bar-seconds", type=int, default=5)
    a = p.parse_args()
    run(a.instrument, [int(y) for y in a.years.split(",")],
        tuple(t.strip() for t in a.types.split(",")), a.bar_seconds)
