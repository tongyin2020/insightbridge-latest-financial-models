"""Event study on JForex-exported TICK data (FX/oil precision refresh).

Phase 2 of the FX/oil measurement: same engine as the HistData 1-minute study
but on real ticks (bar_seconds=1), so reaction latency / washout are measured at
full resolution instead of 60s. Run after EventTickExportStrategy.java has written
the per-instrument tick CSVs on the Mac.

Usage:
    python -m eventalpha_intraday_study.run_jforex_study --instrument EUR/USD \
        --years 2024,2025
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


def run(instrument: str, years: list[int], types: tuple[str, ...]) -> dict:
    ticks = jf.load_ticks(instrument)
    if ticks is None:
        raise SystemExit(f"no JForex tick export for {instrument} "
                         f"(run EventTickExportStrategy in JForex4 first)")
    calendar = build_calendar(min(years), max(years), types)
    safe = instrument.replace("/", "").replace(".", "")
    print(f"[jforex-study] {instrument}: {len(calendar)} events, {len(ticks):,} ticks")

    measurements = [measure_event(ticks, safe, ev.event_type, ev.t0_utc, ev.title,
                                  ev.surprise, bar_seconds=1) for ev in calendar]
    per_event = pd.DataFrame([asdict(m) for m in measurements])
    summary = summarize(measurements)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rdir = reports_dir()
    ev_csv = rdir / f"jforex_event_measurements_{safe}_{stamp}.csv"
    sum_csv = rdir / f"jforex_event_summary_{safe}_{stamp}.csv"
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
    p.add_argument("--instrument", default="EUR/USD")
    p.add_argument("--years", default="2024,2025")
    p.add_argument("--types", default="NFP,CPI,FOMC")
    a = p.parse_args()
    run(a.instrument, [int(y) for y in a.years.split(",")],
        tuple(t.strip() for t in a.types.split(",")))
