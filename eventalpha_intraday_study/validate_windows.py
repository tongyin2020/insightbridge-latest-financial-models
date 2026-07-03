"""Replay OLD (legacy) vs NEW (measured) waiting windows on the real per-event
measurements, to check the recalibration before it goes live.

For each event we already measured (from real data): washout_s (fake-impulse
duration), time_to_peak_s, trend_lifetime_s. Given a window (min_wait, max_wait)
and a time-stop, we score how well that policy would have behaved:

  entry            = clamp(washout_s, min_wait, max_wait)   # wait >= min, ideally
                     until the whipsaw clears, but no later than max_wait
  safe_entry       = min_wait >= washout_s   (window does NOT open inside the whipsaw)
  before_peak      = entry < time_to_peak_s  (trend still available at entry)
  trend_capture    = clip((trend_lifetime_s - entry)/trend_lifetime_s, 0, 1)
  early_cut_s      = max(0, trend_lifetime_s - time_stop)  # stop fires before trend dies
  overhold_s       = max(0, time_stop - trend_lifetime_s)

Higher safe_entry / before_peak / trend_capture is better; lower early_cut is
better. This is a policy replay on measured distributions, not a tick-level P&L
backtest, but it directly answers "does NEW avoid the fake spike and stop cutting
winners early".
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

from .config import reports_dir
from .event_study import HORIZON_S

# legacy BASE_WINDOWS (eventalpha_core/advanced/waiting_policy_engine.py) + 1800 stop
LEGACY_WINDOWS = {"CPI": (30, 300), "NFP": (60, 600), "FOMC": (300, 1800)}
LEGACY_TIME_STOP = 1800

# measured (eventalpha_core/advanced/measured_timing.py)
MEASURED = {
    "CRYPTO": {"win": {"NFP": (70, 585), "CPI": (5, 330), "FOMC": (45, 165)}, "stop": 1530},
    "FX":     {"win": {"NFP": (30, 450), "CPI": (30, 585), "FOMC": (30, 450)}, "stop": 1800},
    "OIL":    {"win": {"NFP": (60, 630), "CPI": (65, 615), "FOMC": (60, 960)}, "stop": 1650},
}

# per-asset per-event data (prefer FX tick over 1-minute)
ASSET_SOURCES = {
    "CRYPTO": ["crypto_event_measurements_BTCUSDT_*.csv"],
    "FX":     ["jforex_event_measurements_EURUSD_*.csv", "jforex_event_measurements_USDJPY_*.csv"],
    "OIL":    ["ibkr_event_measurements_WTIUSD_*.csv", "fxoil_event_measurements_BCOUSD_*.csv"],
}


def _latest(pattern: str) -> Path | None:
    files = sorted(glob.glob(str(reports_dir() / pattern)))
    return Path(files[-1]) if files else None


def _load_asset(patterns: list[str]) -> pd.DataFrame:
    # FX pools EURUSD+USDJPY (two patterns); OIL/CRYPTO prefer the first pattern
    # that resolves (real WTI over Brent, tick over 1-minute).
    fx = len(patterns) == 2 and all("jforex_" in p for p in patterns)
    frames = []
    for pat in patterns:
        f = _latest(pat)
        if f is not None:
            frames.append(pd.read_csv(f))
            if not fx:
                break
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df[df["ok"] == True].copy()  # noqa: E712


def _score(df: pd.DataFrame, win: dict, time_stop: int) -> dict:
    rows = []
    for _, r in df.iterrows():
        et = r["event_type"]
        if et not in win:
            continue
        lo, hi = win[et]
        w = float(r["washout_s"]); p = float(r["time_to_peak_s"]); L = float(r["trend_lifetime_s"])
        if not np.isfinite(p) or p <= 0 or not np.isfinite(L) or L <= 0:
            continue
        entry = min(max(lo, w), hi)
        rows.append({
            "safe_entry": 1.0 if lo >= w else 0.0,
            "before_peak": 1.0 if entry < p else 0.0,
            "trend_capture": float(np.clip((L - entry) / L, 0, 1)),
            "early_cut_s": max(0.0, L - time_stop),
            "overhold_s": max(0.0, time_stop - L),
        })
    if not rows:
        return {}
    s = pd.DataFrame(rows)
    return {
        "n": len(s),
        "safe_entry_%": round(100 * s["safe_entry"].mean(), 1),
        "before_peak_%": round(100 * s["before_peak"].mean(), 1),
        "trend_capture_med": round(s["trend_capture"].median(), 3),
        "early_cut_s_med": round(s["early_cut_s"].median(), 1),
        "overhold_s_med": round(s["overhold_s"].median(), 1),
    }


def run() -> pd.DataFrame:
    out = []
    for asset, patterns in ASSET_SOURCES.items():
        df = _load_asset(patterns)
        if df.empty:
            print(f"[validate] no data for {asset}")
            continue
        old = _score(df, LEGACY_WINDOWS, LEGACY_TIME_STOP)
        new = _score(df, MEASURED[asset]["win"], MEASURED[asset]["stop"])
        for label, sc in (("OLD", old), ("NEW", new)):
            if sc:
                out.append({"asset": asset, "policy": label, **sc})
    res = pd.DataFrame(out)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(res.to_string(index=False))
    return res


if __name__ == "__main__":
    run()
