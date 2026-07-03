"""Run the intraday event study on crypto (Binance tick data).

Downloads BTC (default) aggTrades for each macro-event day in the calendar,
measures the four timing parameters, and writes per-event + summary CSVs and a
markdown report. Read-only research; no broker interaction.

Usage:
    python -m eventalpha_intraday_study.run_crypto_study --symbol BTCUSDT \
        --start-year 2024 --end-year 2025
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone

import pandas as pd

from .config import reports_dir
from .data_sources import binance_aggtrades as binance
from .event_study import measure_event, summarize
from .macro_calendar import build_calendar


def run(symbol: str, start_year: int, end_year: int, types: tuple[str, ...]) -> dict:
    calendar = build_calendar(start_year, end_year, types)
    print(f"[crypto-study] {symbol}: {len(calendar)} events {start_year}-{end_year} ({','.join(types)})")

    measurements = []
    for i, ev in enumerate(calendar, 1):
        day = ev.t0_utc.date()
        ticks = binance.load_window(symbol, day, pre_days=1, post_days=0)
        m = measure_event(ticks, symbol, ev.event_type, ev.t0_utc, ev.title, ev.surprise)
        measurements.append(m)
        flag = "ok" if m.ok else f"skip:{m.note}"
        print(f"  [{i:3d}/{len(calendar)}] {ev.event_type:4s} {ev.t0_utc.date()} "
              f"dir={m.direction:+d} react={m.reaction_latency_s} wash={m.washout_s} "
              f"peak={m.time_to_peak_s} life={m.trend_lifetime_s} move={m.move_bps}bps [{flag}]")

    per_event = pd.DataFrame([asdict(m) for m in measurements])
    summary = summarize(measurements)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rdir = reports_dir()
    ev_csv = rdir / f"crypto_event_measurements_{symbol}_{stamp}.csv"
    sum_csv = rdir / f"crypto_event_summary_{symbol}_{stamp}.csv"
    per_event.to_csv(ev_csv, index=False)
    summary.to_csv(sum_csv, index=False)

    print("\n=== SUMMARY (seconds; p25 / median / p75) ===")
    if not summary.empty:
        with pd.option_context("display.max_columns", None, "display.width", 200):
            print(summary.to_string(index=False))
    print(f"\nSaved: {ev_csv}\nSaved: {sum_csv}")
    return {"per_event_csv": str(ev_csv), "summary_csv": str(sum_csv),
            "n_ok": int(per_event["ok"].sum()), "n_total": len(per_event)}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--start-year", type=int, default=2024)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--types", default="NFP,CPI,FOMC")
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    run(a.symbol, a.start_year, a.end_year, tuple(t.strip() for t in a.types.split(",")))
