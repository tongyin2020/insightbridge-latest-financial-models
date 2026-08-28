"""shadow_calibration.py — 影子数据校准流水线

读取四个影子日志（timeseries / microstructure / news / v2_telemetry），
产出三样东西：
  1. 覆盖率审计：每个品种多少条、时间跨度、关键字段非空率
  2. 阈值建议：timeseries 确认概率门槛（join 真实后续行情算命中率，
     含置换检验负对照）；microstructure OBI 门槛（数据够才算）
  3. 数据缺口清单：哪些参数因为数据不足【不能】校准，缺什么

纪律：
  - 只产出建议，绝不自动改写 DEFAULT_RULES / FakeoutConfig —— 阈值上线
    必须人工审阅报告后手动改。
  - 样本不足（默认 <30 条）一律标 insufficient，不外推。
  - 置换检验不过（信号与噪声不可区分）的门槛标 no_edge，不建议采用。

用法：
  python3 shadow_calibration.py                      # 只做分布/覆盖率审计
  python3 shadow_calibration.py --fetch-outcomes 5   # 近 5 天条目 join IBKR 历史行情
  python3 shadow_calibration.py --fetch-outcomes 5 --max-entries 200
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

BASE = Path(__file__).resolve().parent
DEFAULT_RUNTIME = BASE.parent / "reports" / "runtime"

MIN_SAMPLES_DEFAULT = 30
PERMUTATIONS = 200


# ── 日志加载 ────────────────────────────────────────────────────────────────
def load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # 容忍半行/损坏行
    return rows


def _ts(row: dict) -> Optional[datetime]:
    raw = row.get("ts")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


# ── 覆盖率审计 ──────────────────────────────────────────────────────────────
def coverage(rows: List[dict], key_fields: List[str]) -> Dict[str, dict]:
    """按品种统计：条数、时间跨度、关键字段非空率。"""
    out: Dict[str, dict] = {}
    by_sym: Dict[str, List[dict]] = {}
    for r in rows:
        by_sym.setdefault(r.get("symbol", "?"), []).append(r)
    for sym, rs in sorted(by_sym.items()):
        stamps = [t for t in (_ts(r) for r in rs) if t]
        entry = {
            "rows": len(rs),
            "first": min(stamps).isoformat() if stamps else None,
            "last": max(stamps).isoformat() if stamps else None,
        }
        for k in key_fields:
            non_null = sum(1 for r in rs if r.get(k) is not None)
            entry[f"{k}_nonnull"] = round(non_null / len(rs), 3) if rs else 0.0
        out[sym] = entry
    return out


# ── 结果对齐（outcome join）─────────────────────────────────────────────────
@dataclass
class Outcome:
    ts: datetime
    symbol: str
    direction: str
    prob_dir: float
    realized_move: float          # 方向调整后收益（正=模型方向对）
    hit: bool


def join_outcomes(rows: List[dict],
                  bar_close: Callable[[str, datetime, int], Optional[float]],
                  horizon_key: str = "horizon") -> List[Outcome]:
    """对每条 timeseries 影子记录，取 ts 之后 horizon 根 1m 线的收盘，
    算方向调整后的实际收益。bar_close(symbol, ts, horizon_bars) -> 收盘价或 None。
    """
    out = []
    for r in rows:
        t, sym = _ts(r), r.get("symbol")
        prob = r.get("prob_dir")
        direction = r.get("direction", "long")
        horizon = r.get(horizon_key) or 5
        if not (t and sym and prob is not None):
            continue
        c1 = bar_close(sym, t, int(horizon))
        c0 = bar_close(sym, t, 0)
        if not c0 or not c1 or c0 <= 0:
            continue
        raw = (c1 - c0) / c0
        move = raw if direction == "long" else -raw
        out.append(Outcome(ts=t, symbol=sym, direction=direction,
                           prob_dir=float(prob),
                           realized_move=move, hit=move > 0))
    return out


# ── 阈值推荐 + 置换检验 ─────────────────────────────────────────────────────
@dataclass
class ThresholdRec:
    symbol: str
    n: int
    baseline_hit: float
    best_threshold: Optional[float] = None
    best_hit: Optional[float] = None
    best_n: int = 0
    perm_p95: Optional[float] = None
    status: str = "insufficient"   # insufficient | no_edge | recommended
    note: str = ""


def recommend_threshold(outcomes: List[Outcome], symbol: str,
                        min_samples: int = MIN_SAMPLES_DEFAULT,
                        permutations: int = PERMUTATIONS,
                        seed: int = 42) -> ThresholdRec:
    """在 prob_dir ≥ t 的子集上找命中率最高的 t；用置换检验判断该命中率
    是否显著高于'概率与结果无关'的噪声基线。"""
    oc = [o for o in outcomes if o.symbol == symbol]
    rec = ThresholdRec(symbol=symbol, n=len(oc),
                       baseline_hit=round(sum(o.hit for o in oc) / len(oc), 3) if oc else 0.0)
    if len(oc) < min_samples:
        rec.note = f"样本 {len(oc)} < {min_samples}，不外推"
        return rec

    grid = [round(0.50 + 0.05 * i, 2) for i in range(10)]   # 0.50..0.95
    best_t, best_hit, best_n = None, -1.0, 0
    for t in grid:
        sub = [o for o in oc if o.prob_dir >= t]
        if len(sub) < min_samples:
            continue
        hr = sum(o.hit for o in sub) / len(sub)
        if hr > best_hit:
            best_t, best_hit, best_n = t, hr, len(sub)
    if best_t is None:
        rec.note = "没有任何门槛档位的子集样本达标"
        return rec

    # 置换检验：打乱 prob_dir 标签，重算最优命中率的经验分布
    rng = random.Random(seed)
    hits = [o.hit for o in oc]
    probs = [o.prob_dir for o in oc]
    perm_best = []
    for _ in range(permutations):
        rng.shuffle(probs)
        b = -1.0
        for t in grid:
            sub = [h for h, p in zip(hits, probs) if p >= t]
            if len(sub) < min_samples:
                continue
            b = max(b, sum(sub) / len(sub))
        perm_best.append(b)
    perm_best.sort()
    p95 = perm_best[int(0.95 * (len(perm_best) - 1))] if perm_best else 1.0

    rec.best_threshold = best_t
    rec.best_hit = round(best_hit, 3)
    rec.best_n = best_n
    rec.perm_p95 = round(p95, 3)
    if best_hit > p95:
        rec.status = "recommended"
        rec.note = (f"prob_dir ≥ {best_t} 时命中率 {best_hit:.1%}（n={best_n}），"
                    f"超过置换检验 95 分位 {p95:.1%}，信号与噪声可区分")
    else:
        rec.status = "no_edge"
        rec.note = (f"最优命中率 {best_hit:.1%} 未超过置换检验 95 分位 {p95:.1%}，"
                    f"现有数据下该阈值与噪声不可区分，不建议采用")
    return rec


# ── microstructure / OBI 分析 ───────────────────────────────────────────────
def obi_analysis(rows: List[dict], min_samples: int = MIN_SAMPLES_DEFAULT) -> Dict[str, dict]:
    """OBI 字段可用率与假突破否决率。OBI 大多来自深度行情——没有订阅时
    全为 null，此时只能标 insufficient（如报告所见）。"""
    out: Dict[str, dict] = {}
    by_sym: Dict[str, List[dict]] = {}
    for r in rows:
        by_sym.setdefault(r.get("symbol", "?"), []).append(r)
    for sym, rs in sorted(by_sym.items()):
        obis = [abs(r["obi"]) for r in rs if r.get("obi") is not None]
        rejects = sum(1 for r in rs if r.get("would_reject_fakeout"))
        entry = {
            "rows": len(rs),
            "obi_available": len(obis),
            "fakeout_would_reject_rate": round(rejects / len(rs), 3) if rs else 0.0,
            "status": "insufficient",
            "note": "",
        }
        if len(obis) >= min_samples:
            obis.sort()
            entry["obi_p50"] = round(obis[len(obis) // 2], 4)
            entry["obi_p90"] = round(obis[int(0.9 * (len(obis) - 1))], 4)
            entry["status"] = "measurable"
            entry["note"] = "OBI 分布可测；门槛需结合结果对齐后定，当前仅给分布"
        else:
            entry["note"] = (f"OBI 非空仅 {len(obis)} 条（需 ≥{min_samples}）。"
                             f"多数因无深度行情订阅（obi_unavailable），"
                             f"该参数暂不可校准")
        out[sym] = entry
    return out


# ── IBKR 历史行情取数（可选）────────────────────────────────────────────────
def make_ibkr_bar_fetcher(port: int = 4002, client_id: int = 77):
    """返回 bar_close(symbol, ts, horizon_bars)：ts 之后第 horizon 根 1m 线收盘。
    horizon=0 返回 ts 当时（或之前最近）的收盘。"""
    from ib_insync import IB, Forex, Future
    from ibkr_contract_resolver import FX_SPECS, FUT_SPECS, CRYPTO_SPECS
    from collections import defaultdict

    ib = IB()
    ib.connect("127.0.0.1", port, clientId=client_id, timeout=10)
    cache: Dict[str, list] = defaultdict(list)   # symbol -> [(dt, close)] 已排序

    def _contract(sym: str):
        if sym in FX_SPECS:
            s = FX_SPECS[sym]
            return Forex(f"{s['symbol']}{s['currency']}", exchange=s["exchange"]), "MIDPOINT"
        if sym in FUT_SPECS:
            s = FUT_SPECS[sym]
            tpl = Future(symbol=s["symbol"], exchange=s["exchange"],
                         currency=s["currency"],
                         tradingClass=s.get("tradingClass", ""))
            # 裸模板无法取历史（错误 321），先锁近月 conId
            details = ib.reqContractDetails(tpl)
            if not details:
                raise ValueError(f"{sym} 无可用合约")
            today = datetime.now(timezone.utc).strftime("%Y%m%d")
            dated = sorted(
                (cd.contract for cd in details
                 if (cd.contract.lastTradeDateOrContractMonth or "")[:8] >= today
                 or len(cd.contract.lastTradeDateOrContractMonth or "") == 6),
                key=lambda c: c.lastTradeDateOrContractMonth)
            return (dated[0] if dated else details[0].contract), "TRADES"
        if sym in CRYPTO_SPECS:
            from ib_insync import Crypto
            s = CRYPTO_SPECS[sym]
            return Crypto(s["symbol"], s["currency"], exchange=s["exchange"]), "TRADES"
        raise ValueError(f"未知品种 {sym}")

    def _ensure(sym: str):
        if sym in cache:
            return
        contract, what = _contract(sym)
        bars = ib.reqHistoricalData(
            contract, endDateTime="", durationStr="5 D",
            barSizeSetting="1 min", whatToShow=what, useRTH=False)
        cache[sym] = [(b.date if b.date.tzinfo else b.date.replace(tzinfo=timezone.utc),
                       float(b.close)) for b in bars]

    def bar_close(sym: str, ts: datetime, horizon: int) -> Optional[float]:
        try:
            _ensure(sym)
        except Exception:
            return None
        series = cache[sym]
        base = None
        for i, (dt, c) in enumerate(series):
            if dt <= ts:
                base = i
            else:
                break
        if base is None:
            return None
        idx = min(base + horizon, len(series) - 1)
        return series[idx][1]

    return bar_close


# ── 报告输出 ────────────────────────────────────────────────────────────────
def write_reports(out_dir: Path, cov_ts: dict, cov_ms: dict, news_rows: int,
                  recs: List[ThresholdRec], obi: dict, fetched: bool) -> tuple:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    md_path = out_dir / f"shadow_calibration_{stamp}.md"
    js_path = out_dir / f"shadow_calibration_{stamp}.json"

    lines = [
        f"# 影子数据校准报告（{stamp}）",
        "",
        f"- timeseries 影子条目覆盖率 / microstructure 覆盖率 / news 条目数: {news_rows}",
        f"- 结果对齐（IBKR 历史行情 join）: {'已执行' if fetched else '未执行（仅分布审计）'}",
        "",
        "## 一、timeseries 确认阈值建议",
        "",
        "| 品种 | 样本 | 无条件命中率 | 建议阈值 | 阈值命中率 | 子集n | 置换p95 | 结论 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in recs:
        lines.append(
            f"| {r.symbol} | {r.n} | {r.baseline_hit:.1%} | "
            f"{r.best_threshold if r.best_threshold is not None else '—'} | "
            f"{(f'{r.best_hit:.1%}' if r.best_hit is not None else '—')} | "
            f"{r.best_n or '—'} | "
            f"{(f'{r.perm_p95:.1%}' if r.perm_p95 is not None else '—')} | "
            f"**{r.status}** {r.note} |")
    lines += ["", "## 二、microstructure / OBI 可校准性", "",
              "| 品种 | 条目 | OBI 可用 | 假突破否决率 | 结论 |",
              "|---|---|---|---|---|"]
    for sym, e in obi.items():
        lines.append(f"| {sym} | {e['rows']} | {e['obi_available']} | "
                     f"{e['fakeout_would_reject_rate']:.1%} | **{e['status']}** {e['note']} |")
    lines += ["", "## 三、纪律",
              "",
              "- 本报告只给建议；阈值上线须人工改 DEFAULT_RULES / FakeoutConfig 并补回归。",
              "- `insufficient` = 样本不足不外推；`no_edge` = 置换检验不过，不采用。",
              "- OBI 校准备注：需要深度行情订阅，否则obi_unavailable。"]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fetched_outcomes": fetched,
        "coverage_timeseries": cov_ts,
        "coverage_microstructure": cov_ms,
        "news_rows": news_rows,
        "threshold_recommendations": [r.__dict__ for r in recs],
        "obi_analysis": obi,
    }
    js_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return md_path, js_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME))
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--fetch-outcomes", type=int, default=0, metavar="DAYS",
                    help="join 近 N 天条目的 IBKR 历史 1m 行情（0=只审计分布）")
    ap.add_argument("--max-entries", type=int, default=500)
    ap.add_argument("--min-samples", type=int, default=MIN_SAMPLES_DEFAULT)
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=77)
    args = ap.parse_args()

    rt = Path(args.runtime_dir)
    out_dir = Path(args.out_dir) if args.out_dir else rt
    out_dir.mkdir(parents=True, exist_ok=True)

    ts_rows = load_jsonl(rt / "timeseries_shadow.log")
    ms_rows = load_jsonl(rt / "microstructure_shadow.log")
    news_rows = load_jsonl(rt / "news_shadow.log")
    print(f"加载: timeseries={len(ts_rows)} microstructure={len(ms_rows)} news={len(news_rows)}")

    cov_ts = coverage(ts_rows, ["prob_dir", "expected_move_frac"])
    cov_ms = coverage(ms_rows, ["obi"])
    obi = obi_analysis(ms_rows, args.min_samples)

    recs: List[ThresholdRec] = []
    fetched = False
    if args.fetch_outcomes > 0 and ts_rows:
        cutoff = datetime.now(timezone.utc).timestamp() - args.fetch_outcomes * 86400
        recent = [r for r in ts_rows
                  if (_ts(r) and _ts(r).timestamp() >= cutoff)][:args.max_entries]
        print(f"结果对齐: 近 {args.fetch_outcomes} 天 {len(recent)} 条，连 IBKR 取 1m 行情…")
        fetcher = make_ibkr_bar_fetcher(args.port, args.client_id)
        outcomes = join_outcomes(recent, fetcher)
        print(f"对齐成功 {len(outcomes)} / {len(recent)} 条")
        fetched = True
        symbols = sorted({o.symbol for o in outcomes})
        for sym in symbols:
            rec = recommend_threshold(outcomes, sym, args.min_samples)
            recs.append(rec)
            print(f"  [{sym}] {rec.status}: {rec.note}")
    else:
        symbols = sorted({r.get("symbol", "?") for r in ts_rows})
        for sym in symbols:
            recs.append(ThresholdRec(symbol=sym, n=cov_ts.get(sym, {}).get("rows", 0),
                                     baseline_hit=0.0,
                                     note="未做结果对齐（--fetch-outcomes 0），仅统计分布"))

    md, js = write_reports(out_dir, cov_ts, cov_ms, len(news_rows), recs, obi, fetched)
    print(f"报告: {md}")
    print(f"数据: {js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
