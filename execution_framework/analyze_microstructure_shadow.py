"""Step 2 · Phase A — read-only analyzer for the microstructure shadow log.

Summarizes what the observe-only shadow has recorded so far: how much real
order-book data is actually coming through (depth availability / OBI null-rate),
the OBI distribution, and how often each Step-1 gate *would* have fired. This is
**purely descriptive** — it sets no thresholds and makes no calibration decision;
it just lets us watch data quality accumulate and feeds the eventual Phase C
calibration with an honest picture of the sample.

Usage:
    python3 execution_framework/analyze_microstructure_shadow.py \
        [--log reports/runtime/microstructure_shadow.log] [--json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE = Path(__file__).resolve().parent.parent
DEFAULT_LOG = BASE / "reports" / "runtime" / "microstructure_shadow.log"

STAGE = "microstructure_shadow"


def load_records(log_path: Path) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    if not log_path.exists():
        return recs
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("stage") == STAGE:
                recs.append(obj)
    return recs


def _percentile(sorted_vals: List[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0,1]); pure-python, no numpy."""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _rate(count: int, total: int) -> float:
    return (count / total) if total else 0.0


def summarize(recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _bucket(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(rows)
        obis = sorted(r["obi"] for r in rows
                      if isinstance(r.get("obi"), (int, float)))
        depth_rows = sum(1 for r in rows if (r.get("n_bid_levels") or 0) > 0)
        tape_src: Dict[str, int] = {}
        for r in rows:
            tape_src[r.get("tape_source", "none")] = tape_src.get(
                r.get("tape_source", "none"), 0) + 1
        out: Dict[str, Any] = {
            "n": n,
            "depth_available_rate": round(_rate(depth_rows, n), 4),
            "obi_non_null": len(obis),
            "obi_null_rate": round(_rate(n - len(obis), n), 4),
            "would_reject_fakeout_rate": round(_rate(
                sum(1 for r in rows if r.get("would_reject_fakeout")), n), 4),
            "would_flag_cvd_divergence_rate": round(_rate(
                sum(1 for r in rows if r.get("would_flag_cvd_divergence")), n), 4),
            "would_force_exit_liquidity_crash_rate": round(_rate(
                sum(1 for r in rows if r.get("would_force_exit_liquidity_crash")), n), 4),
            "tape_source": tape_src,
        }
        if obis:
            out["obi_stats"] = {
                "min": round(obis[0], 4),
                "p25": round(_percentile(obis, 0.25), 4),
                "median": round(_percentile(obis, 0.50), 4),
                "p75": round(_percentile(obis, 0.75), 4),
                "max": round(obis[-1], 4),
                "mean": round(sum(obis) / len(obis), 4),
            }
        else:
            out["obi_stats"] = None
        return out

    by_symbol: Dict[str, Any] = {}
    symbols = sorted({r.get("symbol", "?") for r in recs})
    for sym in symbols:
        by_symbol[sym] = _bucket([r for r in recs if r.get("symbol") == sym])

    ts = sorted(r["ts"] for r in recs if r.get("ts"))
    return {
        "total_records": len(recs),
        "first_ts": ts[0] if ts else None,
        "last_ts": ts[-1] if ts else None,
        "overall": _bucket(recs),
        "by_symbol": by_symbol,
    }


def _fmt_bucket(name: str, b: Dict[str, Any]) -> str:
    lines = [f"── {name} ── n={b['n']}"]
    lines.append(
        f"   深度可用率(有盘口档位): {b['depth_available_rate']:.1%}  "
        f"OBI 空值率: {b['obi_null_rate']:.1%}  (有效 OBI {b['obi_non_null']} 条)")
    st = b.get("obi_stats")
    if st:
        lines.append(
            f"   OBI 分布: min={st['min']}  p25={st['p25']}  中位={st['median']}"
            f"  p75={st['p75']}  max={st['max']}  均值={st['mean']}")
    lines.append(
        f"   若开门会触发: 假冲击拒单 {b['would_reject_fakeout_rate']:.1%}  "
        f"CVD背离 {b['would_flag_cvd_divergence_rate']:.1%}  "
        f"买盘枯竭急退 {b['would_force_exit_liquidity_crash_rate']:.1%}")
    lines.append(f"   tape 来源: {b['tape_source']}")
    return "\n".join(lines)


def render(summary: Dict[str, Any]) -> str:
    if summary["total_records"] == 0:
        return ("影子日志还没有任何记录。让 launchd 循环(已开影子)多跑一会儿,"
                "或确认 EVENTALPHA_MICROSTRUCTURE_SHADOW=1 已生效。")
    out = [
        f"微结构影子日志汇总  共 {summary['total_records']} 条  "
        f"({summary['first_ts']} → {summary['last_ts']})",
        "",
        _fmt_bucket("全部", summary["overall"]),
        "",
        "按品种:",
    ]
    for sym, b in summary["by_symbol"].items():
        out.append(_fmt_bucket(sym, b))
    out.append("")
    out.append("注: 以上是描述性统计,未设定/未校准任何阈值。Phase C 才会用这些真实分布定阈值。")
    return "\n".join(out)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Read-only summary of the microstructure shadow log")
    p.add_argument("--log", default=str(DEFAULT_LOG))
    p.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    recs = load_records(Path(args.log))
    summary = summarize(recs)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
