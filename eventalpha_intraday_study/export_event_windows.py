"""Emit the macro-event windows the JForex tick exporter should pull.

The event study only needs ticks in a short window around each macro event
(pre-window for the noise baseline + the measured horizon), NOT two years of raw
ticks. This writes one CSV that the JForex strategy reads.

Columns: event_type, t0_iso, t0_ms, win_start_ms, win_end_ms   (epoch ms, UTC)
"""
from __future__ import annotations

import argparse
import csv
from datetime import timedelta

from .config import data_dir
from .event_study import PRE_WINDOW_MIN, HORIZON_S
from .macro_calendar import build_calendar

PAD_PRE_MIN = PRE_WINDOW_MIN + 2      # small extra pad
PAD_POST_S = HORIZON_S + 120


def run(start_year: int, end_year: int, types: tuple[str, ...]) -> str:
    cal = build_calendar(start_year, end_year, types)
    out = data_dir() / "event_windows.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_type", "t0_iso", "t0_ms", "win_start_ms", "win_end_ms"])
        for ev in cal:
            t0 = ev.t0_utc
            start = t0 - timedelta(minutes=PAD_PRE_MIN)
            end = t0 + timedelta(seconds=PAD_POST_S)
            w.writerow([ev.event_type, t0.isoformat(),
                        int(t0.timestamp() * 1000),
                        int(start.timestamp() * 1000),
                        int(end.timestamp() * 1000)])
    print(f"wrote {len(cal)} event windows -> {out}")
    return str(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2024)
    p.add_argument("--end", type=int, default=2026)
    p.add_argument("--types", default="NFP,CPI,FOMC")
    a = p.parse_args()
    run(a.start, a.end, tuple(t.strip() for t in a.types.split(",")))
