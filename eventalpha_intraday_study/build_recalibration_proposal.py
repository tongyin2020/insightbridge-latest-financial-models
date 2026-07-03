"""Turn the measured event-study distributions into a concrete recalibration
proposal for the LIVE EventAlpha parameters.

Live insertion points (verified in code):
  - eventalpha_core/advanced/waiting_policy_engine.py : BASE_WINDOWS (per event
    type only; currently NOT asset-aware). `waiting_policy(event, state, ...)`
    already receives `state.asset`, so it can be made asset-aware with no call-site
    change.
  - eventalpha_core/advanced/escape_engine.py : the `seconds_in_trade > 1800`
    time-stop and the 0.60 profit-giveback ratio.

Mapping from measured distributions -> parameters:
  min_wait_seconds  ~ washout p50, floored at a per-venue execution minimum
                      (we cannot realistically fire in ~1s on a retail channel, and
                      the floor also protects against the whipsaw p75 tail)
  max_wait_seconds  ~ time_to_peak p50   (must be positioned before the move tops)
  time_stop_seconds ~ trend_lifetime p75 (flatten once the typical trend is spent);
                      when p75 is censored at the measurement horizon we do NOT
                      early-time-stop (keep the legacy 1800s), because the trend
                      routinely outlives the 30-minute window.

Everything here is a proposal written to a report; it does NOT modify live code.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

from .config import reports_dir
from .event_study import HORIZON_S

# newest summary per asset. FX prefers the JForex TICK study over the 1-minute
# HistData study when a tick export is present (falls back to 1-minute otherwise).
ASSET_FILES = {
    "CRYPTO": ["crypto_event_summary_BTCUSDT_*.csv"],
    "FX_EURUSD": ["jforex_event_summary_EURUSD_*.csv", "fxoil_event_summary_EURUSD_*.csv"],
    "FX_USDJPY": ["jforex_event_summary_USDJPY_*.csv", "fxoil_event_summary_USDJPY_*.csv"],
    # oil prefers real WTI 5-second (IBKR) and falls back to 1-minute Brent proxy
    "OIL": ["ibkr_event_summary_WTIUSD_*.csv", "fxoil_event_summary_BCOUSD_*.csv"],
}


def _resolution(name: str) -> str:
    if name.startswith("jforex_") or name.startswith("crypto_"):
        return "tick"
    if name.startswith("ibkr_"):
        return "5-second"
    return "1-minute"


# venue-realistic minimum entry latency (seconds) per asset family
MIN_WAIT_FLOOR = {"CRYPTO": 5, "FX": 30, "OIL": 60}
EVENTS = ["NFP", "CPI", "FOMC"]


def _latest(patterns: list[str]) -> Path | None:
    for pattern in patterns:
        files = sorted(glob.glob(str(reports_dir() / pattern)))
        if files:
            return Path(files[-1])
    return None


def _round_to(x: float, base: int) -> int:
    return int(base * round(float(x) / base))


def _asset_family(asset: str) -> str:
    return "OIL" if asset.startswith("OIL") else ("FX" if asset.startswith("FX") else "CRYPTO")


def build() -> dict:
    proposal: dict = {"assets": {}, "notes": []}
    censored = 0.95 * HORIZON_S
    for asset, pats in ASSET_FILES.items():
        f = _latest(pats)
        if f is None:
            proposal["notes"].append(f"missing summary for {asset}")
            continue
        floor = MIN_WAIT_FLOOR[_asset_family(asset)]
        df = pd.read_csv(f).set_index("event_type")
        per_event = {}
        for et in EVENTS + ["ALL"]:
            if et not in df.index:
                continue
            r = df.loc[et]
            wash_p50 = r.get("washout_s_med")
            wash_p75 = r.get("washout_s_p75")
            peak_p50 = r.get("time_to_peak_s_med")
            life_p75 = r.get("trend_lifetime_s_p75")
            # proposed live values
            min_wait = _round_to(max(wash_p50 or 0, floor), 5)
            max_wait = _round_to(max((peak_p50 or 0), min_wait + 30), 15)
            if (life_p75 or 0) >= censored:
                time_stop = HORIZON_S   # censored: trend outlives the window -> no early stop
            else:
                time_stop = _round_to(max((life_p75 or 0), max_wait + 60), 30)
            per_event[et] = {
                "measured": {
                    "washout_p50": wash_p50, "washout_p75": wash_p75,
                    "time_to_peak_p50": peak_p50, "trend_life_p75": life_p75,
                    "reaction_p50": r.get("reaction_latency_s_med"),
                    "move_bps_p50": r.get("move_bps_med"),
                },
                "proposed": {
                    "min_wait_seconds": min_wait,
                    "max_wait_seconds": max_wait,
                    "time_stop_seconds": time_stop,
                },
            }
        proposal["assets"][asset] = {"source_file": f.name,
                                      "resolution": _resolution(f.name),
                                      "by_event": per_event}
    return proposal


def to_markdown(p: dict) -> str:
    lines = ["# EventAlpha timing recalibration proposal (measured 2024-2025)", ""]
    lines.append("All numbers in seconds unless noted. `measured` = event-study "
                 "percentiles from real intraday data; `proposed` = suggested live value.")
    lines.append("")
    for asset, blk in p["assets"].items():
        lines.append(f"## {asset}  ({blk['resolution']}, `{blk['source_file']}`)")
        lines.append("")
        lines.append("| event | washout p50/p75 | to_peak p50 | trend_life p75 | move bps p50 | -> min_wait | max_wait | time_stop |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for et, d in blk["by_event"].items():
            m, pr = d["measured"], d["proposed"]
            lines.append(f"| {et} | {m['washout_p50']}/{m['washout_p75']} | "
                         f"{m['time_to_peak_p50']} | {m['trend_life_p75']} | {m['move_bps_p50']} | "
                         f"**{pr['min_wait_seconds']}** | **{pr['max_wait_seconds']}** | **{pr['time_stop_seconds']}** |")
        lines.append("")
    if p["notes"]:
        lines.append("## notes")
        lines += [f"- {n}" for n in p["notes"]]
    return "\n".join(lines)


if __name__ == "__main__":
    p = build()
    md = to_markdown(p)
    out_md = reports_dir() / "RECALIBRATION_PROPOSAL.md"
    out_json = reports_dir() / "recalibration_proposal.json"
    out_md.write_text(md)
    out_json.write_text(json.dumps(p, indent=2))
    print(md)
    print(f"\nSaved: {out_md}\nSaved: {out_json}")
