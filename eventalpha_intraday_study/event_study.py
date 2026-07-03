"""Core event-study measurement engine.

Given tick data around a macro release T0, measure the four timing parameters the
event-driven strategy needs. All definitions are deliberately explicit and
heuristic-but-defensible; they are documented inline so the numbers can be
audited and tuned.

Working resolution: 1-second bars built from ticks.

Definitions (bars indexed by seconds since T0):
  P0     = last trade price strictly before T0
  sigma  = robust std (MAD*1.4826) of pre-event 1s log-returns  (noise scale)
  D      = dominant direction = sign(P(t0 + settle_min) - P0)

  1. reaction_latency_s : first second whose |P_s/P0 - 1| exceeds
        max(REACT_K * sigma, REACT_FLOOR_BPS/1e4)          -> "market woke up"
  2. washout_s          : last second within [0, WASH_MAX_S] at which
        sign(P_s - P0) != D                                -> whipsaw against the
        eventual direction is over (fake-impulse cleared). If price never goes the
        wrong way, washout_s == reaction_latency_s (clean start).
  3. time_to_peak_s     : seconds from washout end to max-favourable-excursion
        (MFE) in direction D within HORIZON_S.
  4. trend_lifetime_s   : seconds from washout end until, after the peak, price
        gives back GIVEBACK_FRAC of the peak excursion (trend death).
  5. retrace_after_peak_s = trend_lifetime_s - time_to_peak_s  -> how fast it
        unwinds once it tops (drives trailing-stop tightness).

Also recorded: move size in bps (MFE), direction, post-event net signed volume,
and surprise (if the calendar provides it).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

# --- tunable measurement constants -------------------------------------------
PRE_WINDOW_MIN = 10       # minutes of pre-event data used for the noise baseline
HORIZON_S = 1800          # 30 minutes measured after the event
SETTLE_MIN = 5            # dominant direction judged at T0 + this many minutes
REACT_K = 6.0             # reaction threshold = REACT_K * pre-event 1s sigma
REACT_FLOOR_BPS = 2.0     # ...but at least this many bps
WASH_MAX_S = 300          # only look for whipsaw in the first 5 minutes
GIVEBACK_FRAC = 0.5       # trend dies when it gives back this fraction of MFE


@dataclass
class EventMeasurement:
    symbol: str
    event_type: str
    t0_utc: str
    title: str
    surprise: Optional[float]
    direction: int                 # +1 up, -1 down
    move_bps: float                # MFE from washout price, in bps
    reaction_latency_s: Optional[float]
    washout_s: Optional[float]
    time_to_peak_s: Optional[float]
    trend_lifetime_s: Optional[float]
    retrace_after_peak_s: Optional[float]
    net_vol_post: float            # net signed volume over the horizon
    n_ticks: int
    ok: bool
    note: str = ""


def _resample_bars(ticks: pd.DataFrame, t_start, t_end, bar_seconds: int) -> pd.DataFrame:
    sub = ticks[(ticks["Time"] >= t_start) & (ticks["Time"] < t_end)]
    if sub.empty:
        return pd.DataFrame(columns=["Price", "SignedVol"])
    g = sub.set_index("Time").resample(f"{bar_seconds}s")
    bars = pd.DataFrame({
        "Price": g["Price"].last(),
        "SignedVol": g["SignedVol"].sum(),
    })
    bars["Price"] = bars["Price"].ffill()
    bars["SignedVol"] = bars["SignedVol"].fillna(0.0)
    return bars.dropna(subset=["Price"])


def measure_event(ticks: pd.DataFrame, symbol: str, event_type: str, t0,
                  title: str = "", surprise: Optional[float] = None,
                  bar_seconds: int = 1) -> EventMeasurement:
    """Measure timing params. bar_seconds=1 for tick data, 60 for 1-min data."""
    t0 = pd.Timestamp(t0)
    if t0.tzinfo is None:
        t0 = t0.tz_localize("UTC")

    empty = EventMeasurement(symbol, event_type, t0.isoformat(), title, surprise,
                             0, 0.0, None, None, None, None, None, 0.0, 0, False)

    if ticks is None or ticks.empty:
        empty.note = "no_ticks"
        return empty

    pre = _resample_bars(ticks, t0 - timedelta(minutes=PRE_WINDOW_MIN), t0, bar_seconds)
    post = _resample_bars(ticks, t0, t0 + timedelta(seconds=HORIZON_S), bar_seconds)
    min_pre = max(5, (PRE_WINDOW_MIN * 60) // bar_seconds // 2)
    min_post = max(10, HORIZON_S // bar_seconds // 3)
    if len(pre) < min_pre or len(post) < min_post:
        empty.note = f"insufficient_bars pre={len(pre)} post={len(post)}"
        return empty

    p0 = float(pre["Price"].iloc[-1])
    pre_ret = np.log(pre["Price"]).diff().dropna()
    mad = float(np.median(np.abs(pre_ret - np.median(pre_ret)))) if len(pre_ret) else 0.0
    sigma = max(mad * 1.4826, 1e-6)

    secs = ((post.index - t0).total_seconds()).astype(float)
    price = post["Price"].to_numpy(dtype=float)
    signed = post["SignedVol"].to_numpy(dtype=float)
    rel = price / p0 - 1.0

    # dominant direction at settle horizon
    settle_mask = secs <= SETTLE_MIN * 60
    settle_rel = rel[settle_mask]
    D = 1 if (settle_rel[-1] if len(settle_rel) else 0.0) >= 0 else -1

    # 1. reaction latency
    thr = max(REACT_K * sigma, REACT_FLOOR_BPS / 1e4)
    react_idx = np.argmax(np.abs(rel) > thr) if np.any(np.abs(rel) > thr) else None
    reaction_latency_s = float(secs[react_idx]) if react_idx is not None else None

    # 2. washout: last wrong-way second within WASH_MAX_S
    signed_rel = rel * D  # positive when moving in dominant direction
    wash_mask = (secs <= WASH_MAX_S) & (signed_rel < 0)
    if np.any(wash_mask):
        washout_s = float(secs[wash_mask].max())
    else:
        washout_s = reaction_latency_s if reaction_latency_s is not None else 0.0

    # 3/4. peak and trend death, measured from washout price onward
    after = secs >= washout_s
    if not np.any(after):
        empty.note = "no_post_washout"
        return empty
    secs_a = secs[after]
    price_a = price[after]
    base = float(price_a[0])
    exc = (price_a / base - 1.0) * D          # favourable excursion (>=0 good)
    peak_i = int(np.argmax(exc))
    peak_exc = float(exc[peak_i])
    time_to_peak_s = float(secs_a[peak_i] - washout_s)
    move_bps = peak_exc * 1e4

    trend_lifetime_s = None
    retrace_after_peak_s = None
    if peak_exc > 0:
        # after the peak, find first giveback of GIVEBACK_FRAC * peak
        thresh = peak_exc * (1.0 - GIVEBACK_FRAC)
        post_peak = np.arange(peak_i, len(exc))
        died = [j for j in post_peak if exc[j] <= thresh]
        death_s = float(secs_a[died[0]]) if died else float(secs_a[-1])
        trend_lifetime_s = death_s - washout_s
        retrace_after_peak_s = death_s - float(secs_a[peak_i])

    net_vol_post = float(np.nansum(signed))

    return EventMeasurement(
        symbol=symbol, event_type=event_type, t0_utc=t0.isoformat(), title=title,
        surprise=surprise, direction=D, move_bps=round(move_bps, 2),
        reaction_latency_s=reaction_latency_s, washout_s=washout_s,
        time_to_peak_s=time_to_peak_s, trend_lifetime_s=trend_lifetime_s,
        retrace_after_peak_s=retrace_after_peak_s, net_vol_post=round(net_vol_post, 4),
        n_ticks=int(((ticks["Time"] >= t0) & (ticks["Time"] < t0 + timedelta(seconds=HORIZON_S))).sum()),
        ok=True,
    )


def summarize(measurements: list[EventMeasurement]) -> pd.DataFrame:
    rows = [asdict(m) for m in measurements if m.ok]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    metrics = ["reaction_latency_s", "washout_s", "time_to_peak_s",
               "trend_lifetime_s", "retrace_after_peak_s", "move_bps"]
    out = []
    for et, g in df.groupby("event_type"):
        rec = {"event_type": et, "n": len(g)}
        for m in metrics:
            vals = g[m].dropna()
            if len(vals):
                rec[f"{m}_p25"] = round(float(vals.quantile(0.25)), 1)
                rec[f"{m}_med"] = round(float(vals.median()), 1)
                rec[f"{m}_p75"] = round(float(vals.quantile(0.75)), 1)
        out.append(rec)
    # overall
    rec = {"event_type": "ALL", "n": len(df)}
    for m in metrics:
        vals = df[m].dropna()
        if len(vals):
            rec[f"{m}_p25"] = round(float(vals.quantile(0.25)), 1)
            rec[f"{m}_med"] = round(float(vals.median()), 1)
            rec[f"{m}_p75"] = round(float(vals.quantile(0.75)), 1)
    out.append(rec)
    return pd.DataFrame(out)
