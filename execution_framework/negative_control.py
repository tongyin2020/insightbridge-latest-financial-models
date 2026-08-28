"""Negative-control harness for the post-cooldown breakout edge (R1-2).

The core evidence behind the right-side engine ("information is absorbed
within ~5 minutes") sits in tension with entering on a breakout *after* a
cooldown.  This harness replays sealed event archives (event_data_archive)
through the REAL engine bar-by-bar, then scores the identical entry timing in
BOTH directions.  Per event the paired statistic is

    diff = R_signal - (R_long + R_short) / 2

which is zero in expectation when the engine's direction choice carries no
information — exactly the random-direction null.  A sign-flip permutation
test over the per-event diffs formalises the check; Benjamini-Hochberg is not
needed because there is a single global hypothesis (plus optional per-symbol
breakdowns reported descriptively).

The harness consumes archived observations only; it never invents prices and
never touches a broker.  R is measured against the engine's own stop distance
and the lifecycle hard cap, mirroring production exits.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from event_right_side_engine import AssetRule, RightSideEventEngine, DEFAULT_RULES
from position_lifecycle import PROVISIONAL_PAPER_CAP_SECONDS


# ── 档案读取 ────────────────────────────────────────────────────────────────
def load_event(event_dir: Path) -> Dict[str, Any]:
    """Load one archived event/symbol pair: metadata + sorted bars DataFrame."""
    event_dir = Path(event_dir)
    meta = json.loads((event_dir / "metadata.json").read_text(encoding="utf-8"))
    bars_path = event_dir / "bars.jsonl"
    rows: List[Dict[str, Any]] = []
    if bars_path.exists():
        with bars_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line)["payload"])
    records = []
    for payload in rows:
        stamp = payload.get("bar_time")
        if not stamp:
            continue
        t = datetime.fromisoformat(str(stamp))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        records.append({
            "date": t.astimezone(timezone.utc),
            "open": float(payload["open"]),
            "high": float(payload["high"]),
            "low": float(payload["low"]),
            "close": float(payload["close"]),
            "volume": float(payload.get("volume") or 0.0),
        })
    df = pd.DataFrame(records)
    if not df.empty:
        df = (df.sort_values("date")
                .drop_duplicates(subset="date", keep="last")
                .reset_index(drop=True))
    return {"metadata": meta, "bars": df}


def sealed_event_dirs(root: Path) -> List[Path]:
    """All event/symbol directories that have been sealed (manifest.json)."""
    root = Path(root)
    out = []
    if not root.exists():
        return out
    for event_dir in sorted(root.iterdir()):
        if not event_dir.is_dir():
            continue
        for sym_dir in sorted(event_dir.iterdir()):
            if sym_dir.is_dir() and (sym_dir / "manifest.json").exists():
                out.append(sym_dir)
    return out


# ── 结果模拟（信号腿与反方向腿共用同一时点/同一止损距离）────────────────────
def simulate_outcome(post_entry: pd.DataFrame, entry: float, risk: float,
                     direction: str, entry_time: datetime,
                     cap_seconds: float) -> Dict[str, Any]:
    """R multiple of holding `direction` from `entry` with stop at ±risk.

    Stop is checked bar-by-bar (conservative: stop fills at the stop price);
    the hard cap exits at the bar close, mirroring the lifecycle monitor.
    """
    sign = 1.0 if direction == "LONG" else -1.0
    for _, bar in post_entry.iterrows():
        if direction == "LONG" and float(bar["low"]) <= entry - risk:
            return {"r": -1.0, "exit_reason": "protective_stop"}
        if direction == "SHORT" and float(bar["high"]) >= entry + risk:
            return {"r": -1.0, "exit_reason": "protective_stop"}
        if (bar["date"] - entry_time).total_seconds() >= cap_seconds:
            r = (float(bar["close"]) - entry) * sign / risk
            return {"r": r, "exit_reason": "hard_hold_cap"}
    if len(post_entry) == 0:
        return {"r": 0.0, "exit_reason": "no_bars_after_entry"}
    last_close = float(post_entry["close"].iloc[-1])
    return {"r": (last_close - entry) * sign / risk,
            "exit_reason": "end_of_archive"}


# ── 单事件回放（真实引擎驱动方向选择）──────────────────────────────────────
def replay_event(rule: AssetRule, symbol: str, event_name: str,
                 t0: datetime, df: pd.DataFrame,
                 cap_seconds: Optional[float] = None,
                 event_id: str = "") -> Dict[str, Any]:
    """Drive the real engine over archived bars; score both directions.

    Returns {"entered": 0, ...} when the engine (correctly) never fires —
    non-trades are reported but do not enter the paired statistic.
    """
    if t0.tzinfo is None:
        raise ValueError("t0 must be timezone-aware")
    cap = float(cap_seconds if cap_seconds is not None
                else PROVISIONAL_PAPER_CAP_SECONDS[rule.asset_class])
    pre = df[df["date"] <= t0].reset_index(drop=True)
    post = df[df["date"] > t0].reset_index(drop=True)
    min_pre = rule.atr_period + rule.base_atr_lookback + 2
    if len(pre) < min_pre or len(post) < 3:
        return {"entered": 0, "reason": "insufficient_bars",
                "pre_bars": int(len(pre)), "post_bars": int(len(post))}

    engine = RightSideEventEngine({symbol: rule})
    engine.trigger_event(symbol, event_name, t0, pre,
                         event_id=event_id or f"{event_name}@{t0.isoformat()}")
    tick = float(rule.tick_size)
    for i in range(len(post)):
        now = post["date"].iloc[i].to_pydatetime()
        window = pd.concat([pre, post.iloc[: i + 1]], ignore_index=True)
        close = float(post["close"].iloc[i])
        # 离线无 L1：用 bar 收盘 ± 1 tick 构造窄盘口（在 max_spread_ticks 内）
        signal = engine.evaluate(symbol, now, window,
                                 bid=close - tick, ask=close + tick)
        if signal["status"] not in ("BUY", "SELL"):
            continue
        entry = float(signal["entry_price"])
        stop = float(signal["stop_loss"])
        risk = abs(entry - stop)
        if risk <= 0:
            return {"entered": 0, "reason": "zero_risk_signal"}
        direction = signal["direction"]
        after = post.iloc[i + 1:].reset_index(drop=True)
        r_long = simulate_outcome(after, entry, risk, "LONG", now, cap)
        r_short = simulate_outcome(after, entry, risk, "SHORT", now, cap)
        r_signal = r_long if direction == "LONG" else r_short
        return {
            "entered": 1, "symbol": symbol, "event_name": event_name,
            "event_id": engine.states[symbol].event_id,
            "direction": direction, "entry_time": now.isoformat(),
            "entry_price": entry, "stop_loss": stop,
            "r_signal": r_signal["r"], "r_long": r_long["r"],
            "r_short": r_short["r"], "exit_reason": r_signal["exit_reason"],
            "paired_diff": r_signal["r"] - (r_long["r"] + r_short["r"]) / 2.0,
        }
    return {"entered": 0, "reason": "no_signal_within_window"}


# ── 符号翻转置换检验（单样本，检验方向选择是否携带信息）────────────────────
def permutation_pvalue(diffs: List[float], n_perm: int = 20000,
                       seed: int = 13) -> Dict[str, Any]:
    """Two-sided sign-flip permutation test on per-event paired diffs.

    Under the random-direction null each event's diff is symmetric around 0,
    so flipping signs at random regenerates the null distribution of the mean.
    """
    vals = [float(d) for d in diffs if math.isfinite(float(d))]
    n = len(vals)
    if n == 0:
        return {"n": 0, "observed": None, "p_value": None}
    observed = sum(vals) / n
    rng = random.Random(seed)
    extreme = 0
    abs_obs = abs(observed)
    for _ in range(n_perm):
        total = 0.0
        for v in vals:
            total += v if rng.random() < 0.5 else -v
        if abs(total / n) >= abs_obs - 1e-15:
            extreme += 1
    return {"n": n, "observed": observed,
            "p_value": (extreme + 1) / (n_perm + 1)}


def verdict(observed: Optional[float], p_value: Optional[float],
            alpha: float = 0.05, min_n: int = 8) -> str:
    if observed is None or p_value is None:
        return "no_data"
    if p_value >= alpha:
        return "insufficient_evidence"
    return "edge_supported" if observed > 0 else "edge_challenged"


# ── 全档案扫描 ──────────────────────────────────────────────────────────────
def run(root: Path, rules: Optional[Dict[str, AssetRule]] = None,
        alpha: float = 0.05) -> Dict[str, Any]:
    rules = rules or DEFAULT_RULES
    records, skipped = [], []
    for sym_dir in sealed_event_dirs(root):
        event = load_event(sym_dir)
        meta = event["metadata"]
        df = event["bars"]
        symbol = str(meta.get("symbol", "")).upper()
        rule = rules.get(symbol)
        if rule is None:
            skipped.append({"dir": str(sym_dir), "reason": "no_rule",
                            "symbol": symbol})
            continue
        t0 = datetime.fromisoformat(meta["t0_utc"])
        rec = replay_event(rule, symbol, meta.get("event_name", ""), t0, df,
                           event_id=meta.get("event_id", ""))
        rec["archive_dir"] = str(sym_dir)
        if rec.get("entered"):
            records.append(rec)
        else:
            skipped.append({"dir": str(sym_dir), **{k: rec.get(k) for k in
                            ("entered", "reason")}})
    diffs = [r["paired_diff"] for r in records]
    test = permutation_pvalue(diffs)
    by_symbol: Dict[str, List[float]] = {}
    for r in records:
        by_symbol.setdefault(r["symbol"], []).append(r["paired_diff"])
    return {
        "events_replayed": len(records),
        "events_skipped": skipped,
        "mean_paired_diff": test["observed"],
        "p_value": test["p_value"],
        "verdict": verdict(test["observed"], test["p_value"], alpha),
        "by_symbol_mean_diff": {s: sum(v) / len(v)
                                for s, v in sorted(by_symbol.items())},
        "records": records,
    }


def _main() -> int:
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/event_archive")
    rep = run(root)
    print(f"replayed={rep['events_replayed']} skipped={len(rep['events_skipped'])}")
    print(f"mean paired diff (R): {rep['mean_paired_diff']}")
    print(f"sign-flip p-value:    {rep['p_value']}")
    print(f"verdict:              {rep['verdict']}")
    for sym, m in rep["by_symbol_mean_diff"].items():
        print(f"  {sym}: mean diff {m:+.3f} R")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
