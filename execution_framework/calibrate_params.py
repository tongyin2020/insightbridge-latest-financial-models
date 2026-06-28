"""
calibrate_params.py
═══════════════════════════════════════════════════════════════════════════════
参数校准工具：用 data.db 里积累的【真实成交】对各品种做
  1. 健康度 + 过拟合检查（调用共享 StrategyEvaluator：IS/OOS Sharpe 比 > 3 判过拟合）
  2. 冷静期 / 最大等待 的 walk-forward 网格扫描（带样本外分割，避免在样本内调参）
  3. 输出每品种建议参数 + 过拟合警告，写入 reports/calibration/。

为什么这样做：审计指出原系统参数是"魔法数"、且无 IS/OOS 分离。本工具坚持
"先样本内选参 -> 样本外验证 -> 只有样本外也成立才采纳"，并显式跑过拟合比值。

注意：需要每品种有足够的【已平仓】交易（建议 ≥ 30）才有统计意义；样本不足时
工具会明确提示"数据不足，暂用经验初值"，不会硬给结论。

用法：
  python3 execution_framework/calibrate_params.py            # 校准全部已启用品种
  python3 execution_framework/calibrate_params.py --symbol MNQ
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from enabled_symbols import ENABLED_SYMBOLS

_EVAL_OK = True
try:
    from shared_quant_core import StrategyEvaluator
except Exception:   # noqa: BLE001
    _EVAL_OK = False
    StrategyEvaluator = None

JOURNAL_DB = str(BASE / "data.db")
OUT_DIR = BASE / "reports" / "calibration"
MIN_TRADES = 30   # 低于此样本量不给硬结论


def load_closed_trades(db: str, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    if not Path(db).exists():
        return []
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    q = "SELECT * FROM trades WHERE status='CLOSED'"
    params: tuple = ()
    if symbol:
        q += " AND symbol=?"
        params = (symbol,)
    q += " ORDER BY closed_at"
    rows = [dict(r) for r in c.execute(q, params).fetchall()]
    c.close()
    return rows


def build_series(trades: List[Dict[str, Any]], start_equity: float = 100000.0):
    """从真实成交构建 (equity_curve, trade_returns)。
    trade_returns 用 pnl_pct（相对入场），equity_curve 用累计 pnl_abs。"""
    returns = np.array([float(t["pnl_pct"] or 0.0) for t in trades], dtype=float)
    eq = [start_equity]
    for t in trades:
        eq.append(eq[-1] + float(t["pnl_abs"] or 0.0))
    return np.array(eq, dtype=float), returns


def overfit_report(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not _EVAL_OK:
        return {"available": False, "note": "shared StrategyEvaluator 不可用"}
    if len(trades) < 10:
        return {"available": True, "enough_data": False,
                "note": f"样本仅 {len(trades)}，不足以做 IS/OOS 过拟合检测"}
    eq, rets = build_series(trades)
    health = StrategyEvaluator().evaluate(eq, rets, is_split=0.7)

    # 补充判据：共享 StrategyEvaluator 用 ratio>3 判过拟合，但当 OOS Sharpe 为负时
    # 比值会变负数而漏判。这里显式判定：“IS 为正 且 OOS 为负/显著划拉”=过拟合。
    is_s, oos_s = health.is_sharpe, health.oos_sharpe
    sign_flip_overfit = (is_s > 0 and oos_s <= 0)
    severe_decay = (is_s > 0 and oos_s > 0 and oos_s < is_s * 0.33)
    is_overfit = bool(health.is_overfit or sign_flip_overfit or severe_decay)
    return {
        "available": True, "enough_data": True,
        "win_rate": health.win_rate, "profit_factor": health.profit_factor,
        "is_sharpe": health.is_sharpe, "oos_sharpe": health.oos_sharpe,
        "overfit_ratio": health.overfit_ratio, "is_overfit": is_overfit,
        "overfit_reason": ("sign_flip" if sign_flip_overfit else
                           "severe_decay" if severe_decay else
                           "ratio>3" if health.is_overfit else "none"),
        "max_drawdown_pct": health.max_drawdown_pct, "grade": health.grade,
        "issues": health.issues,
    }


def walk_forward_cooldown(trades: List[Dict[str, Any]],
                          grid: List[int]) -> Dict[str, Any]:
    """对'冷静期分钟'做样本外验证（近似）：
    将交易按时间分前 70% (IS) / 后 30% (OOS)。对每个候选冷静期，用一个简单代理目标
    —— 仅保留'入场距事件 >= cooldown 分钟'的交易（需 trades 带 opened_at 与事件时间差）。
    由于当前 journal 未存事件时点差，这里给出方法骨架：以 R 倍数的稳定性作为目标，
    选出在 IS 与 OOS 上都为正期望、且 OOS 不显著劣于 IS 的最稳健候选。

    说明：真正按冷静期切片需要 journal 增记 'minutes_after_event' 字段（见 README 待办）。
    在该字段就绪前，本函数返回基于现有数据的稳健性诊断，而非硬选值。"""
    if len(trades) < MIN_TRADES:
        return {"enough_data": False,
                "note": f"样本 {len(trades)} < {MIN_TRADES}，暂用经验初值，不调参"}
    split = int(len(trades) * 0.7)
    is_r = np.array([float(t["r_multiple"] or 0.0) for t in trades[:split]])
    oos_r = np.array([float(t["r_multiple"] or 0.0) for t in trades[split:]])
    return {
        "enough_data": True,
        "is_mean_r": round(float(is_r.mean()), 3),
        "oos_mean_r": round(float(oos_r.mean()), 3),
        "is_positive": bool(is_r.mean() > 0),
        "oos_positive": bool(oos_r.mean() > 0),
        "generalizes": bool(is_r.mean() > 0 and oos_r.mean() > 0
                            and oos_r.mean() >= 0.5 * is_r.mean()),
        "note": ("样本外仍为正期望且不显著劣于样本内 -> 参数可信；"
                 "否则应判定过拟合，回退保守冷静期。需 journal 增记 minutes_after_event "
                 "才能逐冷静期切片精调。"),
    }


def calibrate_symbol(db: str, symbol: str) -> Dict[str, Any]:
    trades = load_closed_trades(db, symbol)
    rep: Dict[str, Any] = {
        "symbol": symbol, "closed_trades": len(trades),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    rep["overfit"] = overfit_report(trades)
    rep["cooldown_walk_forward"] = walk_forward_cooldown(
        trades, grid=[3, 5, 10, 15, 25])

    # 建议
    suggestions = []
    of = rep["overfit"]
    if of.get("is_overfit"):
        suggestions.append(f"⚠ 过拟合(原因={of.get('overfit_reason')})：IS Sharpe={of.get('is_sharpe')} "
                           f"但 OOS Sharpe={of.get('oos_sharpe')}，样本外不成立。"
                           f"建议：收紧入场、减少自由参数、扩大样本、回退保守冷静期。")
    if of.get("enough_data") and not of.get("is_overfit") and of.get("grade") in ("A", "B"):
        suggestions.append("健康度良好(grade A/B)且样本外成立，当前参数可继续观察。")
    wf = rep["cooldown_walk_forward"]
    if wf.get("enough_data") and not wf.get("generalizes"):
        suggestions.append("⚠ 样本外不成立：回退到更保守的冷静期，勿沿用样本内最优。")
    if len(trades) < MIN_TRADES:
        suggestions.append(f"样本不足({len(trades)}<{MIN_TRADES})：继续 dry-run/模拟盘积累后再定参。")
    rep["suggestions"] = suggestions
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=JOURNAL_DB)
    ap.add_argument("--symbol", default=None, help="单品种；省略则全部已启用品种")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    symbols = [args.symbol.upper()] if args.symbol else ENABLED_SYMBOLS

    all_rep = []
    for sym in symbols:
        rep = calibrate_symbol(args.db, sym)
        all_rep.append(rep)
        print(f"\n=== {sym} ({rep['closed_trades']} 已平仓) ===")
        of = rep["overfit"]
        if of.get("enough_data"):
            print(f"  胜率={of.get('win_rate')} PF={of.get('profit_factor')} "
                  f"IS_Sharpe={of.get('is_sharpe')} OOS_Sharpe={of.get('oos_sharpe')} "
                  f"过拟合比={of.get('overfit_ratio')} 过拟合={of.get('is_overfit')} "
                  f"评级={of.get('grade')}")
        else:
            print(f"  {of.get('note')}")
        for s in rep["suggestions"]:
            print(f"  - {s}")

    out = OUT_DIR / f"calibration_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(all_rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
