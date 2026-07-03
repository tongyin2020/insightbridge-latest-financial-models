"""Run the intraday event study on FX and Oil (HistData 1-minute bars).

Measured at 1-minute resolution: trend-lifetime and retracement timing are
captured cleanly; reaction latency / washout are to ~60s granularity. Crude oil
uses Brent (BCOUSD) as the free proxy (WTI's HistData token is JS-gated); WTI and
Brent move together at event-reaction timescales.

Usage:
    python -m eventalpha_intraday_study.run_fxoil_study --symbol EURUSD \
        --years 2024,2025
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone

import pandas as pd

from .config import reports_dir
from .data_sources import histdata_m1 as hd
from .event_study import measure_event, summarize
from .macro_calendar import build_calendar

BAR_SECONDS = 60


def run(symbol: str, years: list[int], types: tuple[str, ...]) -> dict:
    bars = hd.load_years(symbol, years)
    if bars is None:
        raise SystemExit(f"no HistData for {symbol} {years}")
    ticks = hd.to_pricevol(bars)
    calendar = build_calendar(min(years), max(years), types)
    print(f"[fxoil-study] {symbol}: {len(calendar)} events {years} ({','.join(types)}), "
          f"{len(bars):,} 1-min bars")

    measurements = []
    for i, ev in enumerate(calendar, 1):
        m = measure_event(ticks, symbol, ev.event_type, ev.t0_utc, ev.title,
                          ev.surprise, bar_seconds=BAR_SECONDS)
        measurements.append(m)
        flag = "ok" if m.ok else f"skip:{m.note}"
        print(f"  [{i:3d}/{len(calendar)}] {ev.event_type:4s} {ev.t0_utc.date()} "
              f"dir={m.direction:+d} react={m.reaction_latency_s} wash={m.washout_s} "
              f"peak={m.time_to_peak_s} life={m.trend_lifetime_s} move={m.move_bps}bps [{flag}]")

    per_event = pd.DataFrame([asdict(m) for m in measurements])
    summary = summarize(measurements)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rdir = reports_dir()
    ev_csv = rdir / f"fxoil_event_measurements_{symbol}_{stamp}.csv"
    sum_csv = rdir / f"fxoil_event_summary_{symbol}_{stamp}.csv"
    per_event.to_csv(ev_csv, index=False)
    summary.to_csv(sum_csv, index=False)

    print("\n=== SUMMARY (seconds; p25 / median / p75) ===")
    if not summary.empty:
        with pd.option_context("display.max_columns", None, "display.width", 220):
            print(summary.to_string(index=False))
    print(f"\nSaved: {ev_csv}\nSaved: {sum_csv}")
    return {"per_event_csv": str(ev_csv), "summary_csv": str(sum_csv),
            "n_ok": int(per_event["ok"].sum()), "n_total": len(per_event)}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--years", default="2024,2025")
    p.add_argument("--types", default="NFP,CPI,FOMC")
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    run(a.symbol, [int(y) for y in a.years.split(",")],
        tuple(t.strip() for t in a.types.split(",")))
