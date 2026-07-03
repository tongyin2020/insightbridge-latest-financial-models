"""Paper-mode P&L backtest: OLD (legacy) vs NEW (measured) parameters, replayed on
the REAL per-event price paths (not on summary stats).

This is the safety gate before the recalibration goes live. Unlike
validate_windows.py (which scores policies on measured landmark distributions),
this reconstructs the actual price series around each event and simulates a full
event trade under each policy, then compares realized P&L.

Trade model (identical for OLD and NEW; only the timing parameters differ, so the
comparison isolates the parameter change):
  * bars      : resample the tick/bar series to `bar_seconds` around T0.
  * p0        : last price strictly before T0.
  * entry     : after `min_wait`, take the first bar in [min_wait, max_wait] whose
                move from p0 exceeds the reaction threshold (2 bps) -> follow that
                direction. If no bar qualifies, NO TRADE (the confirmation never
                fired). Entry price = that bar's price.
  * exit      : the earliest of
                  - time_stop reached,
                  - profit-giveback trailing stop: after a positive peak, price
                    gives back >40% of max-favourable-excursion (mirrors
                    escape_engine's `current < 0.60 * mfe`),
                  - end of the measurement horizon.
  * pnl_bps   : (exit/entry - 1) * dir * 1e4  -  round-trip cost (per asset).

Reported per asset x policy: n_trades, win_rate, avg/median pnl (bps), total,
and a simple pnl/vol ratio.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import reports_dir
from .event_study import _resample_bars, PRE_WINDOW_MIN, HORIZON_S
from .macro_calendar import build_calendar
from .data_sources import binance_aggtrades as binance
from .data_sources import jforex_ticks as jf

REACT_BPS = 2.0          # entry confirmation threshold
GIVEBACK_FRAC = 0.4      # trailing exit: give back this fraction of MFE
# round-trip transaction cost assumption (bps), venue-realistic retail
COST_BPS = {"CRYPTO": 2.0, "FX": 1.0, "OIL": 3.0}

LEGACY_WINDOWS = {"CPI": (30, 300), "NFP": (60, 600), "FOMC": (300, 1800)}
LEGACY_TIME_STOP = 1800
MEASURED = {
    "CRYPTO": {"win": {"NFP": (70, 585), "CPI": (5, 330), "FOMC": (45, 165)}, "stop": 1530},
    "FX":     {"win": {"NFP": (30, 450), "CPI": (30, 585), "FOMC": (30, 450)}, "stop": 1800},
    "OIL":    {"win": {"NFP": (60, 630), "CPI": (65, 615), "FOMC": (60, 960)}, "stop": 1650},
}

# per asset: bar granularity + how to load the price series for one event
ASSETS = {
    "CRYPTO": {"bar_seconds": 1},
    "FX":     {"bar_seconds": 1},
    "OIL":    {"bar_seconds": 5},
}


def _crypto_series(t0: pd.Timestamp) -> pd.DataFrame | None:
    return binance.load_window("BTCUSDT", t0.date(), pre_days=1, post_days=1)


_FX_CACHE: dict[str, pd.DataFrame] = {}


def _fx_series(symbol: str) -> pd.DataFrame | None:
    if symbol not in _FX_CACHE:
        d = jf.load_ticks(symbol)
        _FX_CACHE[symbol] = d if d is not None else pd.DataFrame()
    d = _FX_CACHE[symbol]
    return None if d.empty else d


def _simulate(series: pd.DataFrame, t0: pd.Timestamp, win: tuple[int, int],
              time_stop: int, bar_seconds: int, cost_bps: float,
              entry_bps: float = REACT_BPS) -> dict | None:
    """Return one trade's outcome, or None if there was no data / no entry.

    `entry_bps` is the confirmation threshold: the move from p0 must exceed it
    (by entry time) for the model to commit. Raising it = only take the events
    that have already moved decisively = a proxy for "only trade the big events"
    (executable ex-ante, since the move is observed by entry time)."""
    pre = _resample_bars(series, t0 - timedelta(minutes=PRE_WINDOW_MIN), t0, bar_seconds)
    post = _resample_bars(series, t0, t0 + timedelta(seconds=HORIZON_S), bar_seconds)
    if len(pre) < 5 or len(post) < 10:
        return None
    p0 = float(pre["Price"].iloc[-1])
    secs = ((post.index - t0).total_seconds()).astype(float)
    price = post["Price"].to_numpy(dtype=float)
    rel = price / p0 - 1.0

    min_wait, max_wait = win
    thr = entry_bps / 1e4
    entry_mask = (secs >= min_wait) & (secs <= max_wait) & (np.abs(rel) > thr)
    idx = np.argmax(entry_mask) if np.any(entry_mask) else None
    if idx is None:
        return {"entered": 0, "pnl_bps": 0.0}          # confirmation never fired
    entry_price = price[idx]
    d = 1 if rel[idx] > 0 else -1

    # walk forward from entry to exit
    fwd = np.arange(idx, len(price))
    exc = (price[fwd] / entry_price - 1.0) * d          # favourable excursion
    exit_j = len(fwd) - 1
    peak = 0.0
    for k in range(len(fwd)):
        peak = max(peak, exc[k])
        t_since_entry = secs[fwd[k]] - secs[idx]
        if t_since_entry >= time_stop:
            exit_j = k
            break
        if peak > thr and exc[k] < (1.0 - GIVEBACK_FRAC) * peak:
            exit_j = k
            break
    exit_price = price[fwd[exit_j]]
    pnl_bps = (exit_price / entry_price - 1.0) * d * 1e4 - cost_bps
    return {"entered": 1, "pnl_bps": float(pnl_bps),
            "hold_s": float(secs[fwd[exit_j]] - secs[idx])}


def _asset_events(asset: str, calendar) -> list[tuple[pd.Timestamp, str, pd.DataFrame]]:
    out = []
    if asset == "CRYPTO":
        for ev in calendar:
            s = _crypto_series(pd.Timestamp(ev.t0_utc))
            if s is not None:
                out.append((pd.Timestamp(ev.t0_utc), ev.event_type, s))
    elif asset == "FX":
        for sym in ("EUR/USD", "USD/JPY"):
            s = _fx_series(sym)
            if s is None:
                continue
            for ev in calendar:
                out.append((pd.Timestamp(ev.t0_utc), ev.event_type, s))
    elif asset == "OIL":
        s = jf.load_ticks("WTIUSD")
        if s is not None:
            for ev in calendar:
                out.append((pd.Timestamp(ev.t0_utc), ev.event_type, s))
    return out


def _score(trades: list[dict]) -> dict:
    ent = [t for t in trades if t and t.get("entered")]
    if not ent:
        return {"n_trades": 0}
    pnl = np.array([t["pnl_bps"] for t in ent], dtype=float)
    return {
        "n_trades": len(ent),
        "win_rate_%": round(float((pnl > 0).mean() * 100), 1),
        "avg_pnl_bps": round(float(pnl.mean()), 1),
        "med_pnl_bps": round(float(np.median(pnl)), 1),
        "total_bps": round(float(pnl.sum()), 0),
        "pnl_vol_ratio": round(float(pnl.mean() / (pnl.std() + 1e-9)), 3),
        "avg_hold_s": round(float(np.mean([t["hold_s"] for t in ent])), 0),
    }


def run(years=(2024, 2025), types=("NFP", "CPI", "FOMC"),
        entry_levels=(2.0, 10.0, 20.0, 35.0)) -> pd.DataFrame:
    calendar = build_calendar(min(years), max(years), types)
    rows = []
    for asset, cfg in ASSETS.items():
        bs = cfg["bar_seconds"]
        cost = COST_BPS[asset]
        events = _asset_events(asset, calendar)
        if not events:
            print(f"[backtest] no price series for {asset}")
            continue
        for entry_bps in entry_levels:
            for label, win_map, stop in (
                ("OLD", LEGACY_WINDOWS, LEGACY_TIME_STOP),
                ("NEW", MEASURED[asset]["win"], MEASURED[asset]["stop"]),
            ):
                trades = []
                for t0, et, series in events:
                    if et not in win_map:
                        continue
                    trades.append(_simulate(series, t0, win_map[et], stop, bs, cost,
                                            entry_bps=entry_bps))
                sc = _score(trades)
                if sc.get("n_trades"):
                    rows.append({"asset": asset, "entry_bps": entry_bps,
                                 "policy": label, **sc})
    res = pd.DataFrame(rows)
    with pd.option_context("display.max_columns", None, "display.width", 240):
        print(res.to_string(index=False))
    out = reports_dir() / "backtest_pnl.csv"
    res.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return res


if __name__ == "__main__":
    run()
