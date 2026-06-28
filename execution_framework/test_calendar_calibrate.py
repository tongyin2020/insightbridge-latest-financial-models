"""
test_calendar_calibrate.py — 离线自检：经济日历自动触发 + 参数校准/过拟合检测。
运行：python3 execution_framework/test_calendar_calibrate.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from economic_calendar import EconomicCalendar
from trade_journal import TradeJournal, TradeRecord
from calibrate_params import calibrate_symbol


def test_calendar():
    cal = EconomicCalendar(enabled_symbols=["MES", "MNQ", "ZN", "EURUSD", "MBT"])
    now = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)
    # 一个 30 秒后的 CPI 事件
    cal.add("CPI", now + timedelta(seconds=30), title="CPI test")
    # MBT 不在 enabled，CPI 的品种列表应已过滤掉它
    ev = cal.events[0]
    assert "MBT" not in ev.symbols, ev.symbols
    assert "MES" in ev.symbols and "EURUSD" in ev.symbols, ev.symbols
    # 还没到点：pop_due 为空
    assert cal.pop_due(now, window_s=120) == []
    # 到点后：触发一次
    due = cal.pop_due(now + timedelta(seconds=40), window_s=120)
    assert len(due) == 1 and due[0].name == "CPI", due
    # 不重复触发
    assert cal.pop_due(now + timedelta(seconds=50), window_s=120) == []
    print("✓ 经济日历到点触发 + 品种过滤(MBT 被剔除) + 不重复:", due[0].symbols)


def test_calendar_generate():
    cal = EconomicCalendar(enabled_symbols=["MES", "MNQ", "ZN", "ZT", "SR3"])
    n = cal.generate_default(days=30,
                             start=datetime(2026, 7, 1, tzinfo=timezone.utc))
    assert n > 0, "未生成任何默认事件"
    names = {e.name for e in cal.events}
    assert "TREASURY_AUCTION" in names, names
    print(f"✓ 默认日历生成 {n} 个事件，类型: {sorted(names)}")


def test_calibration_overfit():
    db = tempfile.mktemp(suffix=".db")
    j = TradeJournal(db)
    rng = np.random.default_rng(3)
    # 造 40 笔交易：样本内偏好、样本外变差 -> 应能算出过拟合比
    for i in range(40):
        entry = 18000 + i
        risk = 10.0
        # 前 28 笔多为盈利，后 12 笔多为亏损（人为制造 IS/OOS 差异）
        if i < 28:
            exit_p = entry + rng.uniform(5, 25)
        else:
            exit_p = entry - rng.uniform(5, 25)
        j.record_open(TradeRecord(client_ref=f"c{i}", symbol="MNQ",
                                  event_name="CPI", direction="LONG",
                                  entry_price=entry, stop_loss=entry - risk,
                                  quantity=1, risk_per_unit=risk,
                                  minutes_after_event=15 + (i % 5)))
        # 给不同 closed_at 以保证排序
        j.record_close(f"c{i}", exit_price=exit_p, exit_reason="test")

    rep = calibrate_symbol(db, "MNQ")
    assert rep["closed_trades"] == 40, rep
    of = rep["overfit"]
    print(f"✓ 校准/过拟合检测: 胜率={of.get('win_rate')} "
          f"IS_Sharpe={of.get('is_sharpe')} OOS_Sharpe={of.get('oos_sharpe')} "
          f"过拟合比={of.get('overfit_ratio')} 过拟合={of.get('is_overfit')} "
          f"评级={of.get('grade')}")
    print(f"  walk-forward: {rep['cooldown_walk_forward'].get('note','')[:40]}...")
    for s in rep["suggestions"]:
        print(f"  - {s}")


def main() -> int:
    test_calendar()
    test_calendar_generate()
    test_calibration_overfit()
    print("\n✅ 日历 + 校准 自检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
