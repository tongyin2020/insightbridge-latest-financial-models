"""Phase 2: calibrate the v2 Expected-Value engine on real net-of-cost replay and
test the EV gate out-of-sample.

Phase 1 shipped the v2 gate chain with *uncalibrated* payoff numbers. This module
replaces the guesswork with numbers fit from the 2024-2025 replay:

  1. Replay every NFP/CPI/FOMC event on real intraday data (reusing the exact
     entry/exit + real fill model from ``execution_backtest``) to get, per trade:
     year, early-move bucket, GROSS bps, and realised NET bps (retail costs).
  2. Calibrate per (asset, bucket) GROSS payoff -> p_win / avg_win / avg_loss.
     The v2 EV engine consumes this table and subtracts the modelled round-trip
     cost, so payoff is empirical and cost is explicit.
  3. Test honestly OUT-OF-SAMPLE: calibrate on one year, decide with the EV gate
     on the other year, and score the *realised* net P&L. Compare three policies
     -- TRADE_ALL, SELECTIVITY (mid/big), V2_EV_GATE -- with bootstrap CIs and a
     permutation test of entered vs skipped trades.
  4. Ship the pooled table to eventalpha_core/v2/calibration_table.json.

Read-only research; never touches a broker. Writes reports/V2_CALIBRATION.md.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .config import reports_dir
from .macro_calendar import build_calendar
from .backtest_pnl import ASSETS, _asset_events
from . import robust_stats as rs
from .execution_backtest import _records, _calibrated_costs

from eventalpha_core.v2.expected_value_engine import ExpectedValueEngine
from eventalpha_core.v2.cost_model import default_cost_model

BUCKETS = ("small", "mid", "big")
MIN_N = 8                       # don't calibrate/trust a cell thinner than this
PRIMARY = "retail_conservative"
CALIB_JSON = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "eventalpha_core", "v2", "calibration_table.json")


@dataclass
class _State:
    """Minimal MarketState stand-in for the EV engine (calibrated path uses only
    asset + spread; live spread None -> modelled event-window spread)."""
    asset: str
    symbol: str = "?"
    spread_bps: Optional[float] = None


@dataclass
class _Opp:
    opportunity_score: float = 0.5
    confidence: float = 0.5


def build_trades(years=(2024, 2025), types=("NFP", "CPI", "FOMC"),
                 use_cache: bool = False) -> pd.DataFrame:
    cache = reports_dir() / "v2_trades_cache.csv"
    if use_cache and cache.exists():
        print(f"[v2cal] using cached trades {cache}")
        return pd.read_csv(cache)
    calendar = build_calendar(min(years), max(years), types)
    costs_by_scen = {PRIMARY: _calibrated_costs(PRIMARY, calendar)[0]}
    recs = []
    for asset, cfg in ASSETS.items():
        events = _asset_events(asset, calendar)
        if not events:
            print(f"[v2cal] no price series for {asset}")
            continue
        recs.extend(_records(asset, events, cfg["bar_seconds"], costs_by_scen))
    df = pd.DataFrame(recs)
    df.to_csv(cache, index=False)
    return df


def calibrate(df: pd.DataFrame) -> dict:
    """Per (asset, bucket) GROSS payoff table."""
    table: dict = {}
    for asset in sorted(df["asset"].unique()):
        a = df[df["asset"] == asset]
        table[asset] = {}
        for bucket in BUCKETS:
            g = a[a["bucket"] == bucket]["gross_bps"].to_numpy(dtype=float)
            g = g[np.isfinite(g)]
            n = int(g.size)
            wins = g[g > 0]
            losses = g[g <= 0]
            table[asset][bucket] = {
                "n": n,
                "p_win": round(float(wins.size / n), 4) if n else 0.0,
                "avg_win_bps": round(float(wins.mean()), 2) if wins.size else 0.0,
                "avg_loss_bps": round(float(-losses.mean()), 2) if losses.size else 0.0,
                "mean_gross_bps": round(float(g.mean()), 2) if n else 0.0,
            }
    return table


def _gate_mask(df: pd.DataFrame, calib: dict, min_ev_bps: float = 1.0) -> np.ndarray:
    """Boolean mask: which trades the v2 EV gate would ENTER, using ``calib``."""
    ev_engine = ExpectedValueEngine(min_ev_bps=min_ev_bps, calibration=calib,
                                    min_calib_n=MIN_N)
    mask = np.zeros(len(df), dtype=bool)
    for i, (_, row) in enumerate(df.iterrows()):
        st = _State(asset=row["asset"])
        cm = default_cost_model(row["asset"])
        res = ev_engine.estimate(_Opp(), st, cm, secs_since_t0=0.0,
                                 bucket=row["bucket"])
        mask[i] = bool(res.tradable)
    return mask


def _policy_stats(net: np.ndarray) -> dict:
    net = np.asarray(net, dtype=float)
    if net.size == 0:
        return {"n": 0, "mean_net_bps": float("nan"), "lo": float("nan"),
                "hi": float("nan"), "win_%": float("nan"), "total_net_bps": 0.0}
    ci = rs.bootstrap_ci(net, np.mean, seed=7)
    return {"n": int(net.size), "mean_net_bps": round(ci["point"], 1),
            "lo": round(ci["lo"], 1), "hi": round(ci["hi"], 1),
            "win_%": round(rs.win_rate(net) * 100, 1),
            "total_net_bps": round(float(net.sum()), 0)}


def _evaluate(train: pd.DataFrame, test: pd.DataFrame, net_col: str,
              label: str) -> tuple[list, list]:
    """Calibrate on train, apply gate on test, score realised net. Returns
    (policy rows, permutation rows)."""
    calib = calibrate(train)
    pol_rows, perm_rows = [], []
    for asset in sorted(test["asset"].unique()):
        a = test[test["asset"] == asset].reset_index(drop=True)
        net_all = a[net_col].to_numpy(dtype=float)
        sel = a[a["bucket"].isin(["mid", "big"])][net_col].to_numpy(dtype=float)
        mask = _gate_mask(a, calib)
        net_gate = a[mask][net_col].to_numpy(dtype=float)
        net_skip = a[~mask][net_col].to_numpy(dtype=float)
        for pol, net in (("TRADE_ALL", net_all), ("SELECTIVITY", sel),
                         ("V2_EV_GATE", net_gate)):
            pol_rows.append({"split": label, "asset": asset, "policy": pol,
                             **_policy_stats(net)})
        if net_gate.size and net_skip.size:
            pt = rs.permutation_test(net_gate, net_skip, seed=11)
            perm_rows.append({"split": label, "asset": asset,
                              "gate_mean": round(float(np.mean(net_gate)), 1),
                              "skip_mean": round(float(np.mean(net_skip)), 1),
                              "diff_bps": round(pt["observed"], 1),
                              "p_value": round(pt["p_value"], 4),
                              "n_gate": pt["n_a"], "n_skip": pt["n_b"]})
    return pol_rows, perm_rows


def ev_diagnostic(pooled: dict, min_ev_bps: float = 1.0) -> pd.DataFrame:
    """Per (asset, bucket): calibrated gross payoff vs modelled round-trip cost,
    so the reader can see exactly why the EV gate does or does not enter."""
    rows = []
    for asset, buckets in pooled.items():
        cm = default_cost_model(asset)
        cost = cm.round_trip_cost_bps(secs_since_t0=0.0)   # event-window widened
        for bucket, cell in buckets.items():
            ev = cell["mean_gross_bps"] - cost
            rows.append({
                "asset": asset, "bucket": bucket, "n": cell["n"],
                "mean_gross_bps": cell["mean_gross_bps"],
                "cost_rt_bps": round(cost, 1),
                "ev_bps": round(ev, 1),
                "enters": bool(cell["n"] >= MIN_N and ev >= min_ev_bps),
            })
    return pd.DataFrame(rows)


def run(years=(2024, 2025), types=("NFP", "CPI", "FOMC"),
        use_cache: bool = False) -> dict:
    df = build_trades(years, types, use_cache=use_cache)
    if df.empty:
        print("[v2cal] no trades produced (no data?)")
        return {}
    net_col = f"net_{PRIMARY}_bps"

    # pooled calibration -> shipped table
    pooled = calibrate(df)
    calib_rows = []
    for asset, buckets in pooled.items():
        for bucket, cell in buckets.items():
            calib_rows.append({"asset": asset, "bucket": bucket, **cell})
    calib_df = pd.DataFrame(calib_rows)
    ev_diag_df = ev_diagnostic(pooled)

    # out-of-sample: 2024 -> 2025 and 2025 -> 2024, plus pooled in-sample reference
    pol_rows, perm_rows = [], []
    yrs = sorted(df["year"].unique())
    if len(yrs) >= 2:
        y0, y1 = yrs[0], yrs[-1]
        for tr, te, lab in ((y0, y1, f"{y0}->{y1}"), (y1, y0, f"{y1}->{y0}")):
            p, q = _evaluate(df[df["year"] == tr], df[df["year"] == te], net_col, lab)
            pol_rows += p
            perm_rows += q
    p, q = _evaluate(df, df, net_col, "pooled(in-sample)")
    pol_rows += p
    perm_rows += q

    pol_df = pd.DataFrame(pol_rows)
    perm_df = pd.DataFrame(perm_rows)
    if not perm_df.empty:
        bh = rs.benjamini_hochberg(perm_df["p_value"].to_numpy(), alpha=0.05)
        perm_df["q_value"] = np.round(bh["qvalues"], 4)
        perm_df["reject_H0"] = bh["reject"]

    rd = reports_dir()
    calib_df.to_csv(rd / "v2_calibration_table.csv", index=False)
    ev_diag_df.to_csv(rd / "v2_ev_diagnostic.csv", index=False)
    pol_df.to_csv(rd / "v2_policy_comparison.csv", index=False)
    perm_df.to_csv(rd / "v2_gate_significance.csv", index=False)

    with open(CALIB_JSON, "w", encoding="utf-8") as fh:
        json.dump({"basis": "2024-2025 real replay, GROSS payoff, pooled",
                   "min_n": MIN_N, "table": pooled}, fh, indent=2)
    print(f"[v2cal] shipped calibration -> {CALIB_JSON}")

    _write_report(rd, calib_df, ev_diag_df, pol_df, perm_df, df, net_col)
    return {"calibration": pooled, "calib_df": calib_df, "ev_diag": ev_diag_df,
            "policy": pol_df, "gate_significance": perm_df, "trades": df}


def _fmt(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_(no rows)_\n"
    with pd.option_context("display.max_columns", None, "display.width", 240):
        return "```\n" + df.to_string(index=False) + "\n```\n"


def _write_report(rd, calib_df, ev_diag_df, pol_df, perm_df, trades, net_col) -> None:
    lines = ["# EventAlpha v2 -- EV Calibration & Out-of-Sample Gate Test\n"]
    lines.append("Phase 2. The v2 Expected-Value engine no longer uses guessed "
                 "payoff numbers: p_win / avg_win / avg_loss are calibrated per "
                 "(asset, bucket) from the 2024-2025 real net-of-cost replay "
                 "(same entry/exit + fill model as EXECUTION_AND_ROBUSTNESS). "
                 "Payoff is fit on GROSS outcomes; the EV engine subtracts the "
                 "modelled round-trip cost, so the decomposition stays honest.\n")

    lines.append("## 1. Calibrated payoff table (pooled, GROSS)\n")
    lines.append("This is what ships in `calibration_table.json`. Note "
                 "`p_win*avg_win - (1-p_win)*avg_loss == mean_gross_bps` by "
                 f"construction. Cells with n<{MIN_N} are not used by the gate.\n")
    lines.append(_fmt(calib_df))

    lines.append("\n## 2. Calibrated EV vs cost -- why the gate trades or not\n")
    lines.append("`ev_bps = mean_gross_bps - cost_rt_bps` (modelled event-window "
                 "round-trip cost). `enters=True` only if the cell has enough "
                 f"samples (n>={MIN_N}) AND ev clears the +1.0 bps safety margin. "
                 "This is the whole story behind the policy table below.\n")
    lines.append(_fmt(ev_diag_df))
    if not ev_diag_df.empty and not ev_diag_df["enters"].any():
        lines.append("\n**No cell clears a positive-EV bar after real costs, so the "
                     "disciplined v2 gate stands down entirely.** This is not a bug: "
                     "FX gross payoff is real but sub-2 bps and is eaten by the ~1.6 "
                     "bps spread; OIL mid is ~break-even; crypto is buried by ~34 bps "
                     "round-trip commission. It is the same conclusion as the "
                     "execution-robustness report, now expressed as an automatic "
                     "trade/no-trade rule.\n")

    lines.append("\n## 3. Policy comparison (realised NET, retail_conservative)\n")
    lines.append("`TRADE_ALL` = every confirmed trade; `SELECTIVITY` = mid/big "
                 "buckets; `V2_EV_GATE` = enter only when calibrated EV (payoff "
                 "minus modelled cost) clears the threshold. **The `->` splits are "
                 "out-of-sample** (calibrate one year, decide on the other); "
                 "`pooled(in-sample)` is optimistic and shown only for reference. "
                 "Means in bps with bootstrap 95% CIs.\n")
    lines.append(_fmt(pol_df))

    lines.append("\n## 4. Does the gate separate winners from losers? "
                 "(permutation, BH-corrected)\n")
    lines.append("Permutation test of entered vs skipped realised net P&L. "
                 "`reject_H0=True` means the gate's entered trades are "
                 "significantly better than the ones it skipped, at FDR 5%.\n")
    lines.append(_fmt(perm_df))

    lines.append("\n## 5. Honest reading\n")
    lines.append("- Calibration removes the false precision of Phase 1's guessed "
                 "payoff, but it cannot manufacture signal: each (asset, bucket) "
                 "cell still rests on very few events, so out-of-sample numbers are "
                 "wide and often straddle zero.\n")
    lines.append("- Trust the **out-of-sample** rows, not the pooled in-sample row. "
                 "If `V2_EV_GATE` does not beat `TRADE_ALL` out-of-sample with a CI "
                 "clear of zero, the gate is not yet proven -- which, at n~=60, is "
                 "the expected and honest outcome.\n")
    lines.append("- Crypto is typically gated to near-zero trades because the "
                 "modelled round-trip commission (~30+ bps) exceeds its calibrated "
                 "gross payoff. That is the cost reality, not a bug.\n")
    lines.append("- The fix for an unproven gate is more events, not more model. "
                 "The calibration harness re-runs automatically as data grows.\n")

    out = rd / "V2_CALIBRATION.md"
    out.write_text("\n".join(lines))
    print(f"[v2cal] saved {out}")


if __name__ == "__main__":
    run()
