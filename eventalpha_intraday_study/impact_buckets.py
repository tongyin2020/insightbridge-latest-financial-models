"""Condition event timing on impact magnitude.

The strategy is event-driven and "only trades the ~10 big events a year", so what
matters is whether BIG-impact events behave differently from small ones. We bucket
each measured event by |move_bps| into small / mid / big terciles (per asset) and
report the timing distribution per bucket.

NOTE: this uses REALIZED move magnitude as the impact proxy. True surprise
(actual - forecast, known at T0) is the live-usable signal; wiring the economic
actual/forecast values into macro_calendar.MacroEvent.surprise is the follow-up
that makes this conditioning usable at entry time.
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

from .config import reports_dir

ASSET_SOURCES = {
    "CRYPTO": ["crypto_event_measurements_BTCUSDT_*.csv"],
    "FX":     ["jforex_event_measurements_EURUSD_*.csv", "jforex_event_measurements_USDJPY_*.csv"],
    "OIL":    ["ibkr_event_measurements_WTIUSD_*.csv", "fxoil_event_measurements_BCOUSD_*.csv"],
}
COLS = ["washout_s", "time_to_peak_s", "trend_lifetime_s", "retrace_after_peak_s"]


def _latest(pattern: str) -> Path | None:
    files = sorted(glob.glob(str(reports_dir() / pattern)))
    return Path(files[-1]) if files else None


def _load(patterns: list[str]) -> pd.DataFrame:
    # FX pools both majors; OIL prefers the first resolving source (WTI over Brent)
    fx = len(patterns) == 2 and all("jforex_" in p for p in patterns)
    frames = []
    for p in patterns:
        f = _latest(p)
        if f is not None:
            frames.append(pd.read_csv(f))
            if not fx:
                break
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[df["ok"] == True].copy()  # noqa: E712
    df["abs_move_bps"] = df["move_bps"].abs()
    return df


def run() -> pd.DataFrame:
    rows = []
    for asset, patterns in ASSET_SOURCES.items():
        df = _load(patterns)
        if df.empty or len(df) < 6:
            continue
        df["bucket"] = pd.qcut(df["abs_move_bps"], 3, labels=["small", "mid", "big"])
        for b in ["small", "mid", "big"]:
            g = df[df["bucket"] == b]
            if g.empty:
                continue
            row = {"asset": asset, "bucket": b, "n": len(g),
                   "move_bps_med": round(g["abs_move_bps"].median(), 1)}
            for c in COLS:
                row[c + "_med"] = round(float(np.nanmedian(g[c])), 0)
            rows.append(row)
    res = pd.DataFrame(rows)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(res.to_string(index=False))
    return res


if __name__ == "__main__":
    run()
