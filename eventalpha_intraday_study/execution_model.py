"""Realistic execution model for the event backtest.

Paper accounts (and the legacy backtest) fill at the mid price with a single flat
cost, which flatters a strategy that trades in the first seconds after a macro
release -- exactly when spreads blow out and you get adversely selected. This
module replaces that with an explicit, auditable fill model so the backtest can
report *net-of-cost* P&L, not just gross.

A fill is degraded by four separate, individually documented effects:

  1. spread      -- you buy the ask / sell the bid. Modelled as ``half_spread_bps``
                    of the mid, widened by ``event_spread_mult`` for the first
                    ``event_spread_secs`` after T0 (releases blow spreads out).
                    For FX/OIL these numbers are *measured* from real Dukascopy
                    bid/ask (see ``measure_real_spreads``); for crypto they are
                    set from venue schedules (documented in the report).
  2. slippage    -- market-impact / queue position, ``slippage_bps`` per side.
  3. commission  -- broker fee, ``commission_bps`` per side (dominant for crypto).
  4. latency     -- the fill lands ``latency_s`` after the signal bar, so you fill
                    at the *later* price on the real path (adverse drift), not the
                    price you decided on.

The gross scenario zeroes all four, reproducing the legacy mid-price fill, so the
gross-vs-net gap is entirely attributable to this model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExecCosts:
    """Per-side execution costs, all in basis points of the mid unless noted."""
    half_spread_bps: float      # normal half bid/ask spread
    event_spread_mult: float    # spread multiplier inside the event window
    event_spread_secs: float    # seconds after T0 the widened spread applies
    slippage_bps: float         # market-impact / queue slippage, per side
    commission_bps: float       # broker commission, per side
    latency_s: float            # fill delay between signal bar and execution

    def spread_bps_at(self, secs_since_t0: float) -> float:
        mult = self.event_spread_mult if secs_since_t0 <= self.event_spread_secs else 1.0
        return self.half_spread_bps * mult


GROSS = ExecCosts(0.0, 1.0, 0.0, 0.0, 0.0, 0.0)

# ── Cost scenarios ───────────────────────────────────────────────────────────
# half_spread / event_mult for FX & OIL are OVERWRITTEN at runtime by the values
# measured from real Dukascopy bid/ask; the seeds below are only fallbacks. The
# slippage / commission / latency parts are not observable from quote data and
# are set from venue schedules (retail non-professional accounts):
#   FX  IDEALPRO : commission ~USD2/100k notional  ~= 0.2 bps/side
#   OIL CFD/fut  : commission ~0.5 bps/side
#   CRYPTO       : IBKR Zerohash 0.12-0.18% or Binance taker 0.05-0.10% -> the
#                  single largest cost; conservative 10 bps, optimistic 4 bps/side
SCENARIOS: Dict[str, Dict[str, ExecCosts]] = {
    "retail_conservative": {
        "FX":     ExecCosts(0.10, 8.0, 60.0, 0.20, 0.20, 0.75),
        "OIL":    ExecCosts(1.00, 5.0, 60.0, 1.00, 0.50, 0.75),
        "CRYPTO": ExecCosts(1.00, 4.0, 60.0, 3.00, 10.0, 1.00),
    },
    "retail_optimistic": {
        "FX":     ExecCosts(0.10, 4.0, 30.0, 0.10, 0.20, 0.40),
        "OIL":    ExecCosts(1.00, 3.0, 30.0, 0.50, 0.50, 0.40),
        "CRYPTO": ExecCosts(1.00, 2.5, 30.0, 1.50, 4.00, 0.50),
    },
}


def fills(secs: np.ndarray, price: np.ndarray, entry_idx: int, exit_idx: int,
          direction: int, costs: ExecCosts) -> dict:
    """Degrade an ideal mid-price round trip into a realistic net result.

    ``secs``/``price`` are the post-event path (seconds since T0, mid price);
    ``entry_idx``/``exit_idx`` index into them; ``direction`` is +1 long / -1 short.
    Returns entry/exit fill prices and net P&L (bps) after spread+slippage+
    commission+latency.
    """
    n = len(price)
    entry_idx = int(np.clip(entry_idx, 0, n - 1))
    exit_idx = int(np.clip(exit_idx, 0, n - 1))

    def _lat(i: int) -> tuple[float, float]:
        # price actually obtained latency_s after the decision bar (adverse drift)
        t_fill = secs[i] + costs.latency_s
        j = int(np.searchsorted(secs, t_fill, side="left"))
        j = min(j, n - 1)
        return float(price[j]), float(secs[j])

    entry_mid, t_entry = _lat(entry_idx)
    exit_mid, t_exit = _lat(exit_idx)

    entry_edge = costs.spread_bps_at(t_entry) + costs.slippage_bps
    exit_edge = costs.spread_bps_at(t_exit) + costs.slippage_bps

    # buy lifts the ask (pay up), sell hits the bid (receive less); closing a long
    # sells, closing a short buys -> both legs are adverse by construction.
    entry_fill = entry_mid * (1.0 + direction * entry_edge / 1e4)
    exit_fill = exit_mid * (1.0 - direction * exit_edge / 1e4)

    gross_bps = (exit_mid / entry_mid - 1.0) * direction * 1e4
    net_bps = ((exit_fill / entry_fill - 1.0) * direction * 1e4
               - 2.0 * costs.commission_bps)
    return {
        "entry_fill": entry_fill, "exit_fill": exit_fill,
        "gross_bps": float(gross_bps), "net_bps": float(net_bps),
        "cost_bps": float(gross_bps - net_bps),
    }


# ── Measure real spreads from Dukascopy bid/ask (FX / OIL) ────────────────────
def _quotes_path(logical: str) -> Path:
    from .config import data_dir
    token = logical.replace("/", "").replace(".", "")
    return data_dir() / "jforex_ticks" / f"ticks_{token}.csv"


def load_quotes(logical: str) -> Optional[pd.DataFrame]:
    """Load raw bid/ask (not just mid) for a Dukascopy instrument."""
    p = _quotes_path(logical)
    if not p.exists() or p.stat().st_size < 50:
        return None
    df = pd.read_csv(p)
    if df.empty:
        return None
    df["Time"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    df["bid"] = df["bid"].astype(float)
    df["ask"] = df["ask"].astype(float)
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    df["spread_bps"] = (df["ask"] - df["bid"]) / df["mid"] * 1e4
    return df[["Time", "bid", "ask", "mid", "spread_bps"]].dropna().sort_values("Time")


def measure_real_spreads(logical: str, event_times, event_secs: float = 60.0,
                         pre_min: float = 10.0) -> Optional[dict]:
    """Measure the true half-spread from real quotes: the normal (pre-event)
    baseline vs the widened window in the first ``event_secs`` after each release.

    Returns half-spread bps (spread/2) and the widening multiplier, i.e. the
    empirical values for ``ExecCosts.half_spread_bps`` / ``event_spread_mult``.
    """
    q = load_quotes(logical)
    if q is None or q.empty:
        return None
    t = q["Time"]                       # tz-aware Series (UTC)
    sp = q["spread_bps"].to_numpy(dtype=float)

    normal, evt = [], []
    for et in event_times:
        et = pd.Timestamp(et)
        if et.tzinfo is None:
            et = et.tz_localize(timezone.utc)
        pre_lo = et - pd.Timedelta(minutes=pre_min)
        ev_hi = et + pd.Timedelta(seconds=event_secs)
        normal.append(sp[((t >= pre_lo) & (t < et)).to_numpy()])
        evt.append(sp[((t >= et) & (t < ev_hi)).to_numpy()])
    normal = np.concatenate(normal) if normal else np.array([])
    evt = np.concatenate(evt) if evt else np.array([])
    if normal.size == 0:
        return None
    base = float(np.median(normal))
    ev_med = float(np.median(evt)) if evt.size else base
    half = base / 2.0
    mult = max(1.0, (ev_med / base) if base > 0 else 1.0)
    return {
        "normal_spread_bps": round(base, 3),
        "event_spread_bps": round(ev_med, 3),
        "half_spread_bps": round(half, 3),
        "event_spread_mult": round(mult, 2),
        "n_normal": int(normal.size), "n_event": int(evt.size),
    }
