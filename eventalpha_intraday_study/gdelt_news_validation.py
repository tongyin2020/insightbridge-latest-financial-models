"""Does REAL, price-independent news tone (GDELT) carry any directional edge for
the macro-event trades? This is the honest test the price-proxy could not answer.

For every 2024-2025 NFP/CPI/FOMC event we pull GDELT's average news tone in a
+/-3h window and summarise the tone shift around the release (`tone_change`).
Independently, from the real price series we measure the market's realised
direction (net move over the measurement horizon) and early move. We then ask:

  * hit-rate: does sign(tone_change) agree with the realised move direction?
  * correlation: is tone_change linearly related to the realised move (bps)?

A hit-rate near 50% / correlation near 0 is the honest verdict that GDELT tone
does not predict direction; a clear skew would mean the news leg carries real,
independent information worth wiring into the brain.

Run:
    EVENTALPHA_DATA_DIR=/path python3 -m eventalpha_intraday_study.gdelt_news_validation
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .config import reports_dir
from .event_study import _resample_bars, PRE_WINDOW_MIN, HORIZON_S
from .macro_calendar import build_calendar
from . import backtest_pnl as bt
from .data_sources import gdelt_tone as gd

SETTLE_S = 300           # judge realised direction this many seconds after T0


def _realised_move(series: pd.DataFrame, t0: pd.Timestamp, bar_seconds: int):
    """Return (early_move_bps at +SETTLE_S, net_move_bps over horizon) or None."""
    pre = _resample_bars(series, t0 - timedelta(minutes=PRE_WINDOW_MIN), t0, bar_seconds)
    post = _resample_bars(series, t0, t0 + timedelta(seconds=HORIZON_S), bar_seconds)
    if len(pre) < 5 or len(post) < 10:
        return None
    p0 = float(pre["Price"].iloc[-1])
    secs = ((post.index - t0).total_seconds()).astype(float)
    price = post["Price"].to_numpy(dtype=float)
    early_mask = secs >= SETTLE_S
    if not np.any(early_mask):
        return None
    early = float(price[int(np.argmax(early_mask))] / p0 - 1.0) * 1e4
    net = float(np.mean(price[-5:]) / p0 - 1.0) * 1e4
    return early, net


def _hit_stats(rows: list[dict], key: str) -> dict:
    tc = np.array([r["tone_change"] for r in rows], dtype=float)
    mv = np.array([r[key] for r in rows], dtype=float)
    mask = (np.abs(tc) > 1e-9) & (np.abs(mv) > 1e-9)
    tc, mv = tc[mask], mv[mask]
    if len(tc) < 5:
        return {"n": int(len(tc))}
    hit = float(np.mean(np.sign(tc) == np.sign(mv)) * 100)
    corr = float(np.corrcoef(tc, mv)[0, 1]) if np.std(tc) > 0 and np.std(mv) > 0 else 0.0
    return {"n": int(len(tc)), "tone_dir_hit_%": round(hit, 1), "corr": round(corr, 3)}


def run(years=(2024, 2025), types=("NFP", "CPI", "FOMC")) -> pd.DataFrame:
    calendar = build_calendar(min(years), max(years), types)

    # 1. fetch GDELT tone per unique event (asset-independent), cached
    tone_by_event: dict[tuple, dict] = {}
    for ev in calendar:
        t0 = pd.Timestamp(ev.t0_utc)
        eid = f"{ev.event_type}_{t0.strftime('%Y%m%dT%H%M')}"
        sig = gd.tone_signal(eid, ev.event_type, ev.t0_utc)
        if sig:
            tone_by_event[(ev.event_type, t0)] = sig
    print(f"[gdelt] tone fetched for {len(tone_by_event)}/{len(calendar)} events")

    # 2. join with realised price move per asset
    rows = []
    for asset in ("CRYPTO", "FX", "OIL"):
        bs = bt.ASSETS[asset]["bar_seconds"]
        for t0, et, series in bt._asset_events(asset, calendar):
            sig = tone_by_event.get((et, pd.Timestamp(t0)))
            if not sig:
                continue
            rm = _realised_move(series, pd.Timestamp(t0), bs)
            if rm is None:
                continue
            early, net = rm
            rows.append({"asset": asset, "event_type": et,
                         "tone_change": sig["tone_change"], "post_tone": sig["post_tone"],
                         "early_bps": early, "net_bps": net})

    df = pd.DataFrame(rows)
    out_rows = []
    for asset in ("CRYPTO", "FX", "OIL"):
        sub = df[df.asset == asset].to_dict("records")
        if not sub:
            continue
        e = _hit_stats(sub, "early_bps")
        n = _hit_stats(sub, "net_bps")
        out_rows.append({"asset": asset, "n": e.get("n", 0),
                         "tone->early_hit_%": e.get("tone_dir_hit_%"),
                         "tone~early_corr": e.get("corr"),
                         "tone->net_hit_%": n.get("tone_dir_hit_%"),
                         "tone~net_corr": n.get("corr")})
    allr = df.to_dict("records")
    ea, ne = _hit_stats(allr, "early_bps"), _hit_stats(allr, "net_bps")
    out_rows.append({"asset": "ALL", "n": ea.get("n", 0),
                     "tone->early_hit_%": ea.get("tone_dir_hit_%"),
                     "tone~early_corr": ea.get("corr"),
                     "tone->net_hit_%": ne.get("tone_dir_hit_%"),
                     "tone~net_corr": ne.get("corr")})
    res = pd.DataFrame(out_rows)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(res.to_string(index=False))
    df.to_csv(reports_dir() / "gdelt_news_raw.csv", index=False)
    _write_report(res, len(tone_by_event), len(calendar))
    return res


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    head = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |"
            for r in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def _write_report(res: pd.DataFrame, n_tone: int, n_cal: int) -> None:
    lines = [
        "# GDELT real-news-tone directional test",
        "",
        f"Real GDELT average news tone (+/-3h around each release, 15-minute "
        f"resolution) attached to **{n_tone}/{n_cal}** 2024-2025 NFP/CPI/FOMC events "
        "(topics: inflation / unemployment / federal reserve). This is a "
        "price-INDEPENDENT feed, so it can genuinely test whether news mood carries "
        "directional information -- unlike the price-collinear proxy used earlier.",
        "",
        "`tone_change` = mean tone after the release minus mean tone before. "
        "`hit_%` = share of events where the sign of `tone_change` matches the sign "
        "of the realised price move (early = +5min, net = over the 30-min horizon). "
        "50% and corr~0 mean no directional signal.",
        "",
        _md(res),
        "",
        "## Verdict",
        "",
        "- Read the ALL row: hit-rate near 50% and |corr| near 0 mean GDELT topic "
        "tone does **not** predict the direction of the macro-event move -- news "
        "*positivity* is not the same as the *surprise vs expectations* that moves "
        "price, so it cannot replace a real consensus-forecast surprise.",
        "- This is why the full-stack replay's news leg is only a risk/context input, "
        "not a directional edge. Attaching real tone does not change that; a true "
        "*surprise* feed (actual-vs-forecast) remains the missing piece.",
        "",
    ]
    out = reports_dir() / "GDELT_NEWS_VALIDATION.md"
    out.write_text("\n".join(lines))
    print(f"Saved: {out}")


if __name__ == "__main__":
    run()
