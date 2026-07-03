"""Impact-scaled waiting/exit windows: derive per-asset windows *per impact bucket*
(small / mid / big) so the model can shrink the wait and extend the hold on the
decisive events, and stand down on the noise ones.

Why this exists: the P&L backtest (backtest_pnl.py) showed the edge is entirely in
selectivity -- trading every event is flat/negative; gating on decisive moves turns
crypto/FX positive. The impact study (impact_buckets.py) showed big events barely
whipsaw and trend 3-4x longer. This module turns those two facts into a concrete,
per-bucket parameter table using the SAME mapping as the main recalibration
proposal:

    min_wait  = max(washout_p50, venue floor)     rounded 5s
    max_wait  = max(time_to_peak_p50, min_wait+30) rounded 15s
    time_stop = trend_lifetime_p75 (censored@1800 -> 1800) rounded 30s

The bucket is chosen at entry from the market's own early reaction magnitude (an
executable, real-time proxy for the surprise -- actual minus consensus is exactly
what the first move prices in), NOT from a forecast feed. This file emits both the
per-bucket windows and the |move| thresholds that separate the buckets.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import reports_dir
from .event_study import HORIZON_S

ASSET_SOURCES = {
    "CRYPTO": ["crypto_event_measurements_BTCUSDT_*.csv"],
    "FX":     ["jforex_event_measurements_EURUSD_*.csv", "jforex_event_measurements_USDJPY_*.csv"],
    "OIL":    ["ibkr_event_measurements_WTIUSD_*.csv", "fxoil_event_measurements_BCOUSD_*.csv"],
}
MIN_WAIT_FLOOR = {"CRYPTO": 5, "FX": 30, "OIL": 60}
BUCKETS = ["small", "mid", "big"]


def _latest(pattern: str) -> Path | None:
    files = sorted(glob.glob(str(reports_dir() / pattern)))
    return Path(files[-1]) if files else None


def _load(patterns: list[str]) -> pd.DataFrame:
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


def _round_to(x: float, base: int) -> int:
    return int(base * round(float(x) / base))


def _window(df: pd.DataFrame, floor: int) -> dict:
    wash = float(np.nanmedian(df["washout_s"]))
    peak = float(np.nanmedian(df["time_to_peak_s"]))
    life = df["trend_lifetime_s"].dropna()
    life_p75 = float(life.quantile(0.75)) if len(life) else 0.0
    min_wait = _round_to(max(wash, floor), 5)
    max_wait = _round_to(max(peak, min_wait + 30), 15)
    stop = HORIZON_S if life_p75 >= 0.95 * HORIZON_S else _round_to(max(life_p75, max_wait + 60), 30)
    return {"min_wait": min_wait, "max_wait": max_wait, "time_stop": stop}


def build() -> dict:
    out: dict = {"assets": {}}
    for asset, patterns in ASSET_SOURCES.items():
        df = _load(patterns)
        if df.empty or len(df) < 6:
            continue
        # tercile edges on |move| -- also the live entry thresholds
        q = df["abs_move_bps"].quantile([1 / 3, 2 / 3]).round(1).tolist()
        df["bucket"] = pd.qcut(df["abs_move_bps"], 3, labels=BUCKETS)
        floor = MIN_WAIT_FLOOR[asset]
        rec = {"move_bps_edges": {"small<": q[0], "mid<": q[1], "big>=": q[1]},
               "by_bucket": {}}
        for b in BUCKETS:
            g = df[df["bucket"] == b]
            if g.empty:
                continue
            w = _window(g, floor)
            rec["by_bucket"][b] = {"n": int(len(g)),
                                   "move_bps_med": round(float(g["abs_move_bps"].median()), 1),
                                   **w}
        out["assets"][asset] = rec
    return out


def _to_markdown(prop: dict) -> str:
    lines = ["# Impact-scaled windows (per-bucket, live-ready parameters)", "",
             "Bucket chosen at entry from the observed early-move magnitude (bps).",
             "Small = stand down / size down; big = commit fast, hold long.", ""]
    for asset, rec in prop["assets"].items():
        e = rec["move_bps_edges"]
        lines.append(f"## {asset}  (bucket by |move|: small < {e['small<']} bps, "
                     f"mid < {e['mid<']} bps, big >= {e['big>=']} bps)")
        lines.append("")
        lines.append("| bucket | n | move bps | min_wait | max_wait | time_stop |")
        lines.append("|---|--:|--:|--:|--:|--:|")
        for b in BUCKETS:
            r = rec["by_bucket"].get(b)
            if r:
                lines.append(f"| {b} | {r['n']} | {r['move_bps_med']} | "
                             f"{r['min_wait']} | {r['max_wait']} | {r['time_stop']} |")
        lines.append("")
    return "\n".join(lines)


def run() -> dict:
    prop = build()
    md = _to_markdown(prop)
    print(md)
    (reports_dir() / "IMPACT_SCALED_WINDOWS.md").write_text(md)
    (reports_dir() / "impact_scaled_windows.json").write_text(json.dumps(prop, indent=2))
    print(f"Saved: {reports_dir() / 'IMPACT_SCALED_WINDOWS.md'}")
    return prop


if __name__ == "__main__":
    run()
