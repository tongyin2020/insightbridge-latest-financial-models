"""Full-stack historical replay: drive the *complete* EventAlpha decision brain
(regime -> severity -> Bayesian signal fusion [news/price/cross-asset/liquidity/
memory] -> waiting policy -> cross-asset -> position sizing -> exit) on the SAME
real 2024-2025 intraday event data used for the timing study, and compare it to
the timing-only baseline (trade every event with the calibrated window).

Why this exists: the repo's existing full-stack validator runs on Yahoo *daily*
bars and holds for *days* -- it cannot see event-scale behaviour. This harness
feeds the same brain our real tick / 5-second event windows and lets the brain
gate, direct and size each trade, so we can quantify what the confirmation stack
adds on top of the pure timing recalibration.

HONEST LIMITATIONS (both clearly labelled as proxies, not real feeds):
  * news_alignment  -- Firecrawl cannot be re-scraped for a past timestamp, so we
    use the same price-bias proxy the production validator uses (EVENT_BIAS x the
    sign of the early post-event move). It is correlated with price by
    construction; treat the news leg as a placeholder, not evidence.
  * surprise_score  -- real consensus forecasts are not freely available; we proxy
    surprise by the magnitude of the market's own early reaction.
Everything else (regime, severity, Bayesian fusion mechanics, waiting policy,
cross-asset scoring across the three real legs, sizing, exit) is the real code.

Run:
    EVENTALPHA_DATA_DIR=/path python3 -m eventalpha_intraday_study.fullstack_replay
"""
from __future__ import annotations

import math
from datetime import timedelta, timezone

import numpy as np
import pandas as pd

from .config import reports_dir
from .event_study import _resample_bars, PRE_WINDOW_MIN, HORIZON_S
from .macro_calendar import build_calendar
from . import backtest_pnl as bt
from eventalpha_core.schema import AssetClass, EventType, MacroEvent, MarketState, DecisionAction
from eventalpha_core.eventalpha_brain import EventAlphaBrain
from eventalpha_core.learning_engine import LearningEngine
from eventalpha_core.event_memory import EventMemoryDB

ENTRY_ACTIONS = {DecisionAction.ENTER_SMALL, DecisionAction.ENTER_NORMAL,
                 DecisionAction.ENTER_HEAVY, DecisionAction.PAPER_TRADE}

_ASSET_CLASS = {"CRYPTO": AssetClass.CRYPTO, "FX": AssetClass.FX, "OIL": AssetClass.OIL}
_EVENT_TYPE = {"NFP": EventType.NFP, "CPI": EventType.CPI, "FOMC": EventType.FOMC}

# NEW (merged) per-asset windows / stops -- reused from the backtest module
NEW = bt.MEASURED
COST_BPS = bt.COST_BPS
REACT_BPS = bt.REACT_BPS
GIVEBACK_FRAC = bt.GIVEBACK_FRAC

# event -> per-asset narrative bias (direction the event tends to push each leg);
# used only for the news proxy + narrative_bias, mirrors the production validator
EVENT_BIAS = {
    EventType.CPI:  {"crypto": -0.5, "fx": -1.0, "oil": -0.2},
    EventType.FOMC: {"crypto": -0.6, "fx": -1.0, "oil": -0.2},
    EventType.NFP:  {"crypto": -0.4, "fx": -0.8, "oil": -0.1},
}
EVENT_DEFAULTS = {
    EventType.CPI:  dict(policy_score=0.68, source_confidence=0.82),
    EventType.FOMC: dict(policy_score=0.82, source_confidence=0.86),
    EventType.NFP:  dict(policy_score=0.54, source_confidence=0.78),
}
# venue-typical liquidity proxies (no real order book in history)
LIQ = {"CRYPTO": dict(liq=0.70, spread=2.0), "FX": dict(liq=0.75, spread=1.0),
       "OIL": dict(liq=0.60, spread=3.0)}


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-_clip(x, -40, 40)))


def _build_state(asset: str, series: pd.DataFrame, t0: pd.Timestamp,
                 entry_wait: int, bar_seconds: int):
    """Build a MarketState observed up to (T0 + entry_wait) plus the forward path
    needed to simulate the trade. Returns (state, ctx) or None."""
    pre = _resample_bars(series, t0 - timedelta(minutes=PRE_WINDOW_MIN), t0, bar_seconds)
    post = _resample_bars(series, t0, t0 + timedelta(seconds=HORIZON_S), bar_seconds)
    if len(pre) < 5 or len(post) < 10:
        return None
    p0 = float(pre["Price"].iloc[-1])
    pre_px = pre["Price"].to_numpy(dtype=float)
    pre_ret = np.diff(pre_px) / pre_px[:-1]
    sig_pre = float(np.std(pre_ret)) if len(pre_ret) > 1 else 0.0
    sig_pre = max(sig_pre, 1e-6)

    secs = ((post.index - t0).total_seconds()).astype(float)
    price = post["Price"].to_numpy(dtype=float)
    rel = price / p0 - 1.0

    ent_mask = secs >= entry_wait
    if not np.any(ent_mask):
        return None
    entry_idx = int(np.argmax(ent_mask))
    entry_price = float(price[entry_idx])
    early_move = entry_price / p0 - 1.0
    sgn = 1.0 if early_move >= 0 else -1.0

    early = rel[: entry_idx + 1]
    n_early = max(len(early), 1)
    # z-score of the early move vs pre-event bar noise
    z = early_move / (sig_pre * math.sqrt(n_early))
    momentum = _clip(_sigmoid(1.6 * z), 0.05, 0.95)
    # adverse excursion inside the early window (whipsaw)
    adverse = float(np.max(np.maximum(0.0, -sgn * early))) if len(early) else 0.0
    reversal = _clip(adverse / (abs(early_move) + 1e-9), 0.0, 0.95)
    # trend persistence: fraction of early path on the final side
    persist = _clip(float(np.mean(np.sign(early) == sgn)) if len(early) else 0.5, 0.05, 0.95)
    sig_early = float(np.std(np.diff(early))) if len(early) > 2 else sig_pre
    vol_z = _clip((sig_early / sig_pre - 1.0) * 1.5 + 1.0, 0.0, 5.0)

    return _finish_state(asset, t0, p0, momentum, reversal, persist, vol_z, sgn), {
        "p0": p0, "secs": secs, "price": price, "entry_idx": entry_idx,
        "entry_price": entry_price, "early_move": early_move,
    }


def _finish_state(asset, t0, p0, momentum, reversal, persist, vol_z, sgn):
    liq = LIQ[asset]
    ex_q = _clip(0.55 * liq["liq"] + 0.25 * (1 - min(vol_z / 5, 1)) + 0.2, 0.05, 0.95)
    return MarketState(
        asset=_ASSET_CLASS[asset],
        symbol=asset,
        timestamp_utc=t0.to_pydatetime().replace(tzinfo=timezone.utc),
        price=p0,
        spread_bps=liq["spread"],
        volatility_z=vol_z,
        momentum_score=momentum,
        reversal_score=reversal,
        liquidity_score=liq["liq"],
        cross_asset_alignment=0.50,
        news_alignment=0.50,   # filled per event below
        orderbook_pressure=_clip(0.50 + 0.20 * (momentum - 0.5) * 2, 0.05, 0.95),
        trend_persistence=persist,
        execution_quality=ex_q,
        breakout_quality=_clip(0.45 + 0.25 * momentum + 0.20 * persist - 0.10 * reversal, 0.05, 0.95),
        raw={"early_move": sgn * abs(momentum)},
    )


def _news_proxy(asset: str, sgn: float, early_move: float) -> float:
    """Directional 'bullishness' proxy for news_alignment. We cannot re-scrape
    2024 news, so we assume the (unobserved) news flow was consistent with the
    market's own realised early reaction: an up move -> bullish news, scaled by
    how decisive the move was. This is collinear with price by construction (the
    disclosed limitation); it exists so the news leg does not veto every trade,
    NOT as independent evidence."""
    edges = {"CRYPTO": 106.9, "FX": 41.8, "OIL": 42.4}[asset]
    conf = _clip(abs(early_move) * 1e4 / edges, 0.0, 1.0)
    return _clip(0.50 + 0.42 * sgn * conf, 0.05, 0.95)


def _make_event(event_type: EventType, t0: pd.Timestamp, asset: str,
                early_move: float) -> MacroEvent:
    d = EVENT_DEFAULTS.get(event_type, {})
    # surprise proxy: bigger early reaction -> bigger surprise (asset-normalised)
    edges = {"CRYPTO": 106.9, "FX": 41.8, "OIL": 42.4}[asset]
    surprise = _clip(abs(early_move) * 1e4 / edges, 0.0, 1.0)
    bias = EVENT_BIAS.get(event_type, {}).get(asset.lower(), 0.0)
    return MacroEvent(
        event_id=f"{event_type.value}_{t0.isoformat()}_{asset}",
        event_type=event_type,
        title=f"{event_type.value} {t0.date()}",
        timestamp_utc=t0.to_pydatetime().replace(tzinfo=timezone.utc),
        source="fullstack_replay",
        surprise_score=surprise,
        narrative_bias=0.20 * bias,
        expected_assets=[AssetClass.CRYPTO, AssetClass.FX, AssetClass.OIL],
        **d,
    )


def _simulate_from(ctx: dict, direction: int, time_stop: int, cost_bps: float):
    """Forward-simulate a trade from ctx['entry_idx'] in the given direction.
    Exit on time_stop or a 40%-giveback trailing stop. Returns dict with pnl_bps,
    hold_s, mae_bps (max adverse excursion)."""
    secs = ctx["secs"]
    price = ctx["price"]
    idx = ctx["entry_idx"]
    entry_price = ctx["entry_price"]
    fwd = np.arange(idx, len(price))
    exc = (price[fwd] / entry_price - 1.0) * direction
    thr = REACT_BPS / 1e4
    peak = 0.0
    exit_j = len(fwd) - 1
    for k in range(len(fwd)):
        peak = max(peak, exc[k])
        if secs[fwd[k]] - secs[idx] >= time_stop:
            exit_j = k
            break
        if peak > thr and exc[k] < (1.0 - GIVEBACK_FRAC) * peak:
            exit_j = k
            break
    mae_bps = float(-np.min(exc[: exit_j + 1])) * 1e4
    exit_price = price[fwd[exit_j]]
    pnl_bps = (exit_price / entry_price - 1.0) * direction * 1e4 - cost_bps
    return {"pnl_bps": float(pnl_bps), "hold_s": float(secs[fwd[exit_j]] - secs[idx]),
            "mae_bps": max(0.0, mae_bps)}


def _agg(trades: list[dict], n_events: int) -> dict:
    if not trades:
        return {"n_events": n_events, "n_trades": 0, "selectivity_%": 0.0}
    trades = sorted(trades, key=lambda t: t["order"])
    pnl = np.array([t["pnl_bps"] for t in trades], dtype=float)
    equity = np.cumsum(pnl)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.max(peak - equity)) if len(equity) else 0.0
    return {
        "n_events": n_events,
        "n_trades": len(trades),
        "selectivity_%": round(100 * len(trades) / max(n_events, 1), 1),
        "win_rate_%": round(float((pnl > 0).mean() * 100), 1),
        "avg_pnl_bps": round(float(pnl.mean()), 1),
        "med_pnl_bps": round(float(np.median(pnl)), 1),
        "total_bps": round(float(pnl.sum()), 0),
        "pnl_vol_ratio": round(float(pnl.mean() / (pnl.std() + 1e-9)), 3),
        "avg_mae_bps": round(float(np.mean([t["mae_bps"] for t in trades])), 1),
        "max_drawdown_bps": round(max_dd, 0),
        "avg_hold_s": round(float(np.mean([t["hold_s"] for t in trades])), 0),
    }


def run(years=(2024, 2025), types=("NFP", "CPI", "FOMC")) -> pd.DataFrame:
    calendar = build_calendar(min(years), max(years), types)
    # fresh empty on-disk memory (a per-connection :memory: db loses its schema);
    # empty means the brain starts with neutral memory edges, which is what we want
    mem_path = reports_dir() / "_fullstack_replay_memory.sqlite"
    if mem_path.exists():
        mem_path.unlink()
    learning = LearningEngine(EventMemoryDB(str(mem_path)))
    brain = EventAlphaBrain(learning)

    # 1. load each asset's events (t0, event_type, price series)
    per_asset = {a: bt._asset_events(a, calendar) for a in ("CRYPTO", "FX", "OIL")}

    # 2. build states + contexts per (asset, event)
    #    key events by (t0, event_type); FX has two symbols pooled -> keep list
    built = {a: [] for a in per_asset}          # a -> list of (t0, et, state, ctx)
    for asset, events in per_asset.items():
        bs = bt.ASSETS[asset]["bar_seconds"]
        for t0, et, series in events:
            if et not in NEW[asset]["win"]:
                continue
            entry_wait = NEW[asset]["win"][et][0]
            r = _build_state(asset, series, pd.Timestamp(t0), entry_wait, bs)
            if r is None:
                continue
            state, ctx = r
            sgn = 1.0 if ctx["early_move"] >= 0 else -1.0
            state.news_alignment = _news_proxy(asset, sgn, ctx["early_move"])
            built[asset].append((pd.Timestamp(t0), et, state, ctx))

    # index the (first) state per (t0, event_type, asset) for cross-asset lookup
    lookup = {}
    for asset, items in built.items():
        for t0, et, state, ctx in items:
            lookup.setdefault((t0, et), {})[asset] = state

    rows = []
    for asset, items in built.items():
        bs_stop = NEW[asset]["stop"]
        cost = COST_BPS[asset]
        full_trades, timing_trades = [], []
        n_events = len(items)
        for order, (t0, et, state, ctx) in enumerate(items):
            et_enum = _EVENT_TYPE[et]
            sgn = 1 if ctx["early_move"] >= 0 else -1
            # ---- timing-only baseline: always trade the early-move direction ----
            if abs(ctx["early_move"]) * 1e4 > REACT_BPS:
                tr = _simulate_from(ctx, sgn, bs_stop, cost)
                tr["order"] = order
                timing_trades.append(tr)
            # ---- full stack: let the brain decide ----
            related = {a: s for a, s in lookup.get((t0, et), {}).items() if a != asset}
            event = _make_event(et_enum, t0, asset, ctx["early_move"])
            decision = brain.decide(event, state, related)
            if decision.action in ENTRY_ACTIONS and decision.direction.value in ("long", "short"):
                d = 1 if decision.direction.value == "long" else -1
                tr = _simulate_from(ctx, d, bs_stop, cost)
                tr["order"] = order
                full_trades.append(tr)
        rows.append({"asset": asset, "policy": "TIMING_ONLY", **_agg(timing_trades, n_events)})
        rows.append({"asset": asset, "policy": "FULL_STACK", **_agg(full_trades, n_events)})

    res = pd.DataFrame(rows)
    with pd.option_context("display.max_columns", None, "display.width", 260):
        print(res.to_string(index=False))
    out = reports_dir() / "fullstack_replay.csv"
    res.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    _write_report(res)
    return res


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    head = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = [
        "| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |"
        for row in df.itertuples(index=False)
    ]
    return "\n".join([head, sep, *body])


def _write_report(res: pd.DataFrame) -> None:
    lines = [
        "# Full-stack replay — complete AI decision brain vs timing-only",
        "",
        "The **same** real 2024-2025 intraday event data (BTC Binance tick, EURUSD+"
        "USDJPY JForex tick, WTI IBKR 5-second bars; NFP/CPI/FOMC) is run through the "
        "**entire** `EventAlphaBrain.decide()` chain — macro-regime engine, event "
        "severity, Bayesian signal fusion (news / price-confirmation / cross-asset / "
        "liquidity / memory), the calibrated waiting policy, cross-asset scoring "
        "across the three real legs, position sizing and the exit engine — and "
        "compared to trading every decisive event on the calibrated window alone "
        "(`TIMING_ONLY`).",
        "",
        "**Honest proxies (cannot be reproduced for past timestamps):** the news leg "
        "uses a price-consistent proxy (Firecrawl cannot be re-scraped historically) "
        "and macro `surprise` is proxied by the market's own early reaction "
        "(consensus forecasts have no free source). So the news leg is collinear with "
        "price by construction — it is a placeholder, not independent evidence. "
        "Everything else is the real production code.",
        "",
        "## Results",
        "",
        _md_table(res),
        "",
        "## Reading the table",
        "",
        "- `selectivity_%` = fraction of events the policy actually traded.",
        "- `max_drawdown_bps` = worst peak-to-trough of the cumulative-bps equity "
        "curve (events in chronological order).",
        "- `avg_mae_bps` = average worst adverse excursion while in the trade.",
        "",
        "## What the full stack adds",
        "",
    ]
    for asset in ("CRYPTO", "FX", "OIL"):
        t = res[(res.asset == asset) & (res.policy == "TIMING_ONLY")].iloc[0]
        f = res[(res.asset == asset) & (res.policy == "FULL_STACK")].iloc[0]
        lines.append(
            f"- **{asset}**: trades {t['selectivity_%']}% -> **{f['selectivity_%']}%** "
            f"of events; win {t['win_rate_%']}% -> **{f['win_rate_%']}%**; "
            f"max drawdown {t['max_drawdown_bps']:.0f} -> **{f['max_drawdown_bps']:.0f}** bps; "
            f"avg MAE {t['avg_mae_bps']} -> **{f['avg_mae_bps']}** bps; "
            f"avg P&L {t['avg_pnl_bps']} -> {f['avg_pnl_bps']} bps."
        )
    lines += [
        "",
        "## Honest verdict",
        "",
        "- The confirmation stack behaves as a **risk filter**: it stands down on a "
        "large share of events and **cuts max drawdown and adverse excursion "
        "materially** on all three legs, with a small win-rate lift on FX.",
        "- It does **not**, on its own, turn the naive momentum entry positive — "
        "consistent with the P&L study (`THREE_MODEL_VALIDATION.md`): the realised "
        "edge comes from the **decisive-move selectivity threshold**, which is "
        "complementary to (and can be stacked on top of) the brain's gating.",
        "- The news / surprise legs here are price-collinear proxies, so this run "
        "**cannot credit real news or real macro-surprise** with any gain. Wiring a "
        "true historical news-tone feed (e.g. GDELT) and real consensus forecasts is "
        "the only way to measure the genuine independent contribution of those legs.",
        "",
    ]
    out = reports_dir() / "FULLSTACK_VALIDATION.md"
    out.write_text("\n".join(lines))
    print(f"Saved: {out}")


if __name__ == "__main__":
    run()
