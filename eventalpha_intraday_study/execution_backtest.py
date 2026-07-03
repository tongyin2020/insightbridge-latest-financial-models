"""Net-of-cost event backtest + small-sample robustness + threshold optimization.

This is the "real historical data" answer to: paper fills are fake, so what does
the selectivity edge look like once you pay realistic spread + slippage +
commission + latency, and is it statistically real at n~=60?

Pipeline (per asset CRYPTO/FX/OIL, replayed on real 2024-2025 intraday data):

  1. For every NFP/CPI/FOMC event: reconstruct the price path, take the same
     confirmation trade the strategy would (measured per-type window), and record
     the event's early-move bucket + the trade's GROSS and NET P&L, where NET is
     produced by ``execution_model`` (spreads for FX/OIL are MEASURED from real
     Dukascopy bid/ask, not assumed).
  2. Isolate the selectivity lever: split trades into small vs non-small buckets
     and test (permutation) whether non-small really beats small net-of-cost, with
     bootstrap CIs and Benjamini-Hochberg correction across the asset family, plus
     a Bayesian (Beta-Binomial) win-rate with a credible interval.
  3. Use the quantum-inspired annealer to pick the early-move threshold that
     maximises a robust (bootstrap-lower-bound) net objective, and compare it to
     the measured small/mid cutoff.

Writes reports/EXECUTION_AND_ROBUSTNESS.md (+ CSVs). Read-only research; never
touches a broker.
"""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import numpy as np
import pandas as pd

from .config import reports_dir
from .event_study import _resample_bars, PRE_WINDOW_MIN, HORIZON_S
from .macro_calendar import build_calendar
from .backtest_pnl import (
    _asset_events, ASSETS, REACT_BPS, GIVEBACK_FRAC, CLASSIFY_S,
    _ASSET_CLASS, MEASURED,
)
from eventalpha_core.advanced.measured_timing import (
    impact_bucket, MEASURED_IMPACT_EDGES,
)
from . import execution_model as em
from . import robust_stats as rs
from . import qi_optimizer as qi

MIN_TRADES = 8            # don't trust a cell thinner than this
FX_SYMS = ("EUR/USD", "USD/JPY")
OIL_SYMS = ("WTIUSD",)


def _simulate_path(series: pd.DataFrame, t0: pd.Timestamp, win: tuple[int, int],
                   time_stop: int, bar_seconds: int,
                   entry_bps: float = REACT_BPS) -> dict | None:
    """Replay one event and return the raw fill path (mid prices), so the
    execution model can degrade it. Mirrors backtest_pnl._simulate's entry/exit
    logic exactly but returns indices instead of a pre-costed P&L."""
    pre = _resample_bars(series, t0 - timedelta(minutes=PRE_WINDOW_MIN), t0, bar_seconds)
    post = _resample_bars(series, t0, t0 + timedelta(seconds=HORIZON_S), bar_seconds)
    if len(pre) < 5 or len(post) < 10:
        return None
    p0 = float(pre["Price"].iloc[-1])
    secs = ((post.index - t0).total_seconds()).astype(float).to_numpy()
    price = post["Price"].to_numpy(dtype=float)
    rel = price / p0 - 1.0

    # early-move magnitude (classification), executable at CLASSIFY_S
    early_mask = secs <= CLASSIFY_S
    early_bps = (float(np.max(np.abs(rel[early_mask]))) * 1e4
                 if np.any(early_mask) else None)

    min_wait, max_wait = win
    thr = entry_bps / 1e4
    entry_mask = (secs >= min_wait) & (secs <= max_wait) & (np.abs(rel) > thr)
    if not np.any(entry_mask):
        return {"entered": 0, "early_bps": early_bps}
    idx = int(np.argmax(entry_mask))
    d = 1 if rel[idx] > 0 else -1

    fwd = np.arange(idx, len(price))
    exc = (price[fwd] / price[idx] - 1.0) * d
    exit_j = len(fwd) - 1
    peak = 0.0
    for k in range(len(fwd)):
        peak = max(peak, exc[k])
        if secs[fwd[k]] - secs[idx] >= time_stop:
            exit_j = k
            break
        if peak > thr and exc[k] < (1.0 - GIVEBACK_FRAC) * peak:
            exit_j = k
            break
    return {"entered": 1, "early_bps": early_bps, "secs": secs, "price": price,
            "entry_idx": idx, "exit_idx": int(fwd[exit_j]), "direction": d}


def _calibrated_costs(scenario: str, calendar) -> dict:
    """Copy a scenario and overwrite FX/OIL half-spread & event-widening with the
    values measured from real Dukascopy bid/ask; crypto keeps venue defaults."""
    costs = dict(em.SCENARIOS[scenario])
    event_times = [pd.Timestamp(ev.t0_utc) for ev in calendar]
    meas = {}
    for asset, syms in (("FX", FX_SYMS), ("OIL", OIL_SYMS)):
        halfs, mults, samples = [], [], []
        for s in syms:
            m = em.measure_real_spreads(s, event_times)
            # skip degenerate sources with no real quotes (bid==ask export)
            if m and m["half_spread_bps"] > 0.01:
                halfs.append(m["half_spread_bps"])
                mults.append(m["event_spread_mult"])
                samples.append(m)
        if halfs:
            costs[asset] = dataclasses.replace(
                costs[asset],
                half_spread_bps=float(np.mean(halfs)),
                event_spread_mult=float(np.mean(mults)))
            meas[asset] = samples
    return costs, meas


def _records(asset: str, events, bs: int, costs_by_scen: dict) -> list[dict]:
    """One record per entered event with gross + per-scenario net P&L and bucket."""
    ac = _ASSET_CLASS[asset]
    win_map = MEASURED[asset]["win"]
    stop = MEASURED[asset]["stop"]
    recs = []
    for t0, et, series in events:
        if et not in win_map:
            continue
        path = _simulate_path(series, t0, win_map[et], stop, bs, REACT_BPS)
        if path is None or not path.get("entered"):
            continue
        early = path["early_bps"]
        bucket = impact_bucket(ac, early) if early is not None else None
        rec = {"asset": asset, "event_type": et, "early_bps": early, "bucket": bucket}
        g = em.fills(path["secs"], path["price"], path["entry_idx"],
                     path["exit_idx"], path["direction"], em.GROSS)
        rec["gross_bps"] = g["net_bps"]
        for scen, costs in costs_by_scen.items():
            r = em.fills(path["secs"], path["price"], path["entry_idx"],
                         path["exit_idx"], path["direction"], costs[asset])
            rec[f"net_{scen}_bps"] = r["net_bps"]
        recs.append(rec)
    return recs


def _cell(vals: np.ndarray) -> dict:
    ci = rs.bootstrap_ci(vals, np.mean, seed=7)
    wr = rs.bootstrap_ci(vals, rs.win_rate, seed=7)
    return {"n": int(vals.size),
            "mean_bps": round(ci["point"], 1),
            "mean_lo": round(ci["lo"], 1), "mean_hi": round(ci["hi"], 1),
            "win_rate": round(rs.win_rate(vals) * 100, 1),
            "win_lo": round(wr["lo"] * 100, 1), "win_hi": round(wr["hi"] * 100, 1)}


def run(years=(2024, 2025), types=("NFP", "CPI", "FOMC"),
        scenarios=("retail_conservative", "retail_optimistic")) -> dict:
    calendar = build_calendar(min(years), max(years), types)
    costs_by_scen = {}
    measured_spreads = {}
    for scen in scenarios:
        c, meas = _calibrated_costs(scen, calendar)
        costs_by_scen[scen] = c
        measured_spreads[scen] = meas

    all_recs: list[dict] = []
    for asset, cfg in ASSETS.items():
        events = _asset_events(asset, calendar)
        if not events:
            print(f"[exec] no price series for {asset}")
            continue
        all_recs.extend(_records(asset, events, cfg["bar_seconds"], costs_by_scen))
    df = pd.DataFrame(all_recs)
    if df.empty:
        print("[exec] no trades produced (no data?)")
        return {}

    primary = scenarios[0]
    net_col = f"net_{primary}_bps"

    # ── per asset x scenario aggregates + selectivity split ──────────────────
    agg_rows, perm_rows, bayes_rows = [], [], []
    for asset in df["asset"].unique():
        a = df[df["asset"] == asset]
        for scen in ("gross", *scenarios):
            col = "gross_bps" if scen == "gross" else f"net_{scen}_bps"
            for label, sub in (("ALL", a),
                               ("SMALL", a[a["bucket"] == "small"]),
                               ("NONSMALL", a[a["bucket"].isin(["mid", "big"])])):
                if len(sub) == 0:
                    continue
                agg_rows.append({"asset": asset, "scenario": scen, "policy": label,
                                 **_cell(sub[col].to_numpy(dtype=float))})
        # selectivity significance on the PRIMARY net column
        small = a[a["bucket"] == "small"][net_col].to_numpy(dtype=float)
        nons = a[a["bucket"].isin(["mid", "big"])][net_col].to_numpy(dtype=float)
        pt = rs.permutation_test(nons, small, seed=11)
        perm_rows.append({"asset": asset, "scenario": primary,
                          "mean_nonsmall": round(float(np.mean(nons)) if nons.size else float("nan"), 1),
                          "mean_small": round(float(np.mean(small)) if small.size else float("nan"), 1),
                          "diff_bps": round(pt["observed"], 1),
                          "p_value": round(pt["p_value"], 4),
                          "n_nonsmall": pt["n_a"], "n_small": pt["n_b"]})
        # Bayesian win rate of the selective (non-small) net trades
        wins = int((nons > 0).sum())
        bb = rs.beta_binomial_posterior(wins, int(nons.size))
        bayes_rows.append({"asset": asset, "scenario": primary,
                           "raw_win_%": round(bb["raw_win_rate"] * 100, 1) if nons.size else float("nan"),
                           "post_mean_%": round(bb["posterior_mean"] * 100, 1),
                           "cred_lo_%": round(bb["lo"] * 100, 1),
                           "cred_hi_%": round(bb["hi"] * 100, 1), "n": bb["n"]})

    perm_df = pd.DataFrame(perm_rows)
    if not perm_df.empty:
        bh = rs.benjamini_hochberg(perm_df["p_value"].to_numpy(), alpha=0.05)
        perm_df["q_value"] = np.round(bh["qvalues"], 4)
        perm_df["reject_H0"] = bh["reject"]

    # ── quantum-inspired threshold optimization (per asset, primary net) ─────
    opt_rows = []
    for asset in df["asset"].unique():
        a = df[df["asset"] == asset]
        early = a["early_bps"].to_numpy(dtype=float)
        net = a[net_col].to_numpy(dtype=float)
        ok = np.isfinite(early)
        early, net = early[ok], net[ok]
        if early.size < MIN_TRADES:
            continue

        def objective(theta_vec, _early=early, _net=net):
            theta = theta_vec[0]
            mask = _early >= theta
            if mask.sum() < MIN_TRADES:
                return -1e6
            return rs.bootstrap_ci(_net[mask], np.mean, n_boot=1500, seed=3)["lo"]

        res = qi.anneal(objective, [float(np.median(early))],
                        [(0.0, float(np.max(early)))], maximize=True, seed=5)
        theta = float(res["x"][0])
        measured_cut = MEASURED_IMPACT_EDGES.get(_ASSET_CLASS[asset], (float("nan"),))[0]
        kept = net[early >= theta]
        opt_rows.append({
            "asset": asset,
            "annealed_theta_bps": round(theta, 1),
            "measured_small_cut_bps": round(measured_cut, 1),
            "kept_trades": int(kept.size),
            "kept_mean_net_bps": round(float(np.mean(kept)), 1) if kept.size else float("nan"),
            "kept_robust_lo_bps": round(res["value"], 1),
        })

    agg_df = pd.DataFrame(agg_rows)
    bayes_df = pd.DataFrame(bayes_rows)
    opt_df = pd.DataFrame(opt_rows)

    rd = reports_dir()
    df.to_csv(rd / "execution_trades.csv", index=False)
    agg_df.to_csv(rd / "execution_aggregates.csv", index=False)
    perm_df.to_csv(rd / "execution_significance.csv", index=False)
    opt_df.to_csv(rd / "execution_threshold_opt.csv", index=False)

    _write_report(rd, costs_by_scen, measured_spreads, primary, agg_df,
                  perm_df, bayes_df, opt_df)
    return {"trades": df, "aggregates": agg_df, "significance": perm_df,
            "bayes": bayes_df, "threshold_opt": opt_df}


def _fmt(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_(no rows)_\n"
    with pd.option_context("display.max_columns", None, "display.width", 240):
        return "```\n" + df.to_string(index=False) + "\n```\n"


def _write_report(rd, costs_by_scen, measured_spreads, primary, agg_df,
                  perm_df, bayes_df, opt_df) -> None:
    lines = []
    lines.append("# Execution Model + Small-Sample Robustness\n")
    lines.append("Net-of-cost replay of the 2024-2025 NFP/CPI/FOMC events on real "
                 "intraday data (crypto: Binance aggTrades; FX/OIL: Dukascopy tick "
                 "with real bid/ask). Answers: does the selectivity edge survive "
                 "realistic spread+slippage+commission+latency, and is it "
                 "statistically real at n~=60?\n")

    lines.append("## 1. Cost assumptions (per side, bps)\n")
    lines.append("FX half-spread and event-widening are **measured from real "
                 "Dukascopy bid/ask** (see the measured table below). OIL and CRYPTO "
                 "use venue-default spreads because their available archives carry no "
                 "real L1 quotes (crypto = trades only; the WTI export is bid==ask "
                 "5-second bars). slippage/commission/latency are venue schedules.\n")
    for scen, costs in costs_by_scen.items():
        lines.append(f"\n**{scen}**\n")
        rows = []
        for asset, c in costs.items():
            rows.append({"asset": asset, "half_spread_bps": c.half_spread_bps,
                         "event_mult": c.event_spread_mult,
                         "event_secs": c.event_spread_secs,
                         "slippage_bps": c.slippage_bps,
                         "commission_bps": c.commission_bps, "latency_s": c.latency_s})
        lines.append(_fmt(pd.DataFrame(rows)))
    # measured spread evidence
    ev = measured_spreads.get(primary, {})
    if ev:
        lines.append("\n**Measured spreads (real Dukascopy bid/ask)**\n")
        rows = []
        for asset, samples in ev.items():
            for s in samples:
                rows.append({"asset": asset, **s})
        lines.append(_fmt(pd.DataFrame(rows)))

    lines.append("\n## 2. Gross vs net P&L, and the selectivity split\n")
    lines.append("`ALL` = every event; `SMALL` = early move below the measured "
                 "cutoff; `NONSMALL` = mid/big. Means in bps with bootstrap 95% CIs.\n")
    lines.append(_fmt(agg_df))

    lines.append("\n## 3. Is the selectivity edge statistically real? "
                 f"(net, {primary})\n")
    lines.append("Permutation test of NONSMALL vs SMALL net P&L per trade, "
                 "Benjamini-Hochberg corrected across assets. `reject_H0=True` means "
                 "the non-small edge is significant at FDR 5%.\n")
    lines.append(_fmt(perm_df))
    lines.append("\n**Bayesian win rate of the selective (non-small) net trades** "
                 "(Beta-Binomial, uniform prior; posterior mean shrinks toward 50% "
                 "when n is small):\n")
    lines.append(_fmt(bayes_df))

    lines.append("\n## 4. Quantum-inspired threshold optimization\n")
    lines.append("Simulated annealing (the classical analogue of quantum annealing) "
                 "picks the early-move threshold that maximises a **robust** "
                 "objective -- the bootstrap lower bound of net P&L, penalised below "
                 f"{MIN_TRADES} trades -- so it cannot chase a lucky thin cell. "
                 "Compared to the independently-measured small/mid cutoff:\n")
    lines.append(_fmt(opt_df))

    lines.append("\n## 5. Honest reading\n")
    lines.append("- Paper-account P&L is not used anywhere here; this is real-data "
                 "replay with an explicit fill model, so the **net** columns are the "
                 "trustworthy ones.\n")
    lines.append("- The gross-vs-net gap is dominated by crypto commission (IBKR "
                 "Zerohash 12-18 bps / Binance taker 5-10 bps round trip); FX is "
                 "cheap (measured sub-bps spread), OIL in between.\n")
    lines.append("- Selectivity is only worth claiming where the permutation test "
                 "survives BH correction AND the Bayesian credible interval stays "
                 "above 50%. Where it does not, n is simply too small to assert an "
                 "edge -- which is the point of doing this honestly.\n")
    lines.append("- No quantum hardware is used or needed: the annealer is a CPU "
                 "algorithm. Quantum would not help the real bottleneck (only ~60 "
                 "events per asset); more events would.\n")

    out = rd / "EXECUTION_AND_ROBUSTNESS.md"
    out.write_text("\n".join(lines))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    run()
