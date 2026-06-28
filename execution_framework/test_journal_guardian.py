"""
test_journal_guardian.py — 离线自检：学习库 P&L 回写 + 死手开关 + 品种过滤。
运行：python3 execution_framework/test_journal_guardian.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trade_journal import TradeJournal, TradeRecord
from runtime_guardian import RuntimeGuardian, check_heartbeat
from enabled_symbols import filter_enabled, rejected


def test_journal():
    db = tempfile.mktemp(suffix=".db")
    j = TradeJournal(db)
    # 多单：入场 18000，止损 17990（风险 10），出场 18030 -> R = +3
    j.record_open(TradeRecord(client_ref="t1", symbol="MNQ", event_name="CPI",
                              direction="LONG", entry_price=18000, stop_loss=17990,
                              quantity=2, risk_per_unit=10))
    out = j.record_close("t1", exit_price=18030, exit_reason="target")
    assert abs(out["r_multiple"] - 3.0) < 1e-6, out
    assert abs(out["pnl_abs"] - 60.0) < 1e-6, out   # (18030-18000)*2
    # 空单亏损：入场 110，止损 110.5（风险 0.5），出场 110.4 -> R = -0.8
    j.record_open(TradeRecord(client_ref="t2", symbol="ZN", event_name="FOMC",
                              direction="SHORT", entry_price=110, stop_loss=110.5,
                              quantity=1, risk_per_unit=0.5))
    out2 = j.record_close("t2", exit_price=110.4, exit_reason="stop")
    assert out2["r_multiple"] < 0, out2
    # 幂等：重复平仓返回 None
    assert j.record_close("t1", 99999) is None
    stats = j.stats()
    assert stats["closed_trades"] == 2, stats
    assert 0 <= stats["win_rate"] <= 1, stats
    print("✓ 学习库 P&L 回写 + R 倍数 + 统计 正确:", stats)


def test_guardian():
    hb = tempfile.mktemp(suffix=".json")
    fired = {"why": None}
    g = RuntimeGuardian(heartbeat_path=hb, timeout_s=1.0, check_interval_s=0.3,
                        on_dead=lambda why: fired.__setitem__("why", why))
    g.start()
    g.beat({"ok": True})
    chk = check_heartbeat(hb, timeout_s=5.0)
    assert chk["alive"] is True, chk
    print("✓ 心跳写入并被外部巡检识别:", chk["age_s"], "s")
    # 停止心跳，等待死手开关触发
    time.sleep(2.0)
    g.stop()
    assert g.is_dead and fired["why"], "死手开关未触发"
    print("✓ 死手开关触发:", fired["why"])


def test_symbol_filter():
    req = ["MES", "MNQ", "ZT", "ZN", "SR3", "EUR/USD", "USD/JPY", "MBT"]
    enabled = filter_enabled(req)
    rej = rejected(req)
    assert "MBT" not in enabled, enabled
    assert "MBT" in rej, rej
    assert set(enabled) == {"MES", "MNQ", "ZT", "ZN", "SR3", "EURUSD", "USDJPY"}, enabled
    print("✓ 品种过滤正确（MBT 被拒）: 启用", enabled, "| 拒绝", rej)


def test_pipeline_with_journal():
    """回归防护：带 journal_db 初始化 pipeline（run_tws_continuous 的真实路径）。
    曾因缺失 TradeJournal/TradeRecord import 而在此崩溃。"""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from right_side_pipeline import RightSidePipeline
    db = tempfile.mktemp(suffix=".db")
    pipe = RightSidePipeline(ib=None, dry_run=True, equity=50000.0, journal_db=db)
    assert pipe.journal is not None, "journal 未初始化"
    stats = pipe.journal_stats()
    assert stats is not None and stats["closed_trades"] == 0, stats
    print("✓ 带学习库初始化 pipeline 正常（TradeJournal/TradeRecord import 完整）")


def main() -> int:
    test_journal()
    test_guardian()
    test_symbol_filter()
    test_pipeline_with_journal()
    print("\n✅ 全部自检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
