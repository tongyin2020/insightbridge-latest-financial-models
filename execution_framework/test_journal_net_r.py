"""Net-R tests: contract multiplier and round-trip fees must flow into
pnl_net_abs / r_multiple_net, while legacy gross columns keep their meaning.

Regression covered: pnl_abs used to be price-points * quantity with no
multiplier and no fees, so cross-product totals mixed units and every
R multiple was a gross R overstating the true edge.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from trade_journal import TradeJournal, TradeRecord


def _rec(ref: str, symbol: str, direction: str, entry: float, stop: float,
         qty: float, multiplier: float = 1.0, fee_per_side: float = 0.0
         ) -> TradeRecord:
    return TradeRecord(
        client_ref=ref, symbol=symbol, event_name="CPI", direction=direction,
        entry_price=entry, stop_loss=stop, quantity=qty,
        risk_per_unit=abs(entry - stop),
        multiplier=multiplier, fee_per_side=fee_per_side)


def test_long_futures_net_r_accounts_for_multiplier_and_fees():
    with tempfile.TemporaryDirectory() as tmp:
        j = TradeJournal(str(Path(tmp) / "data.db"))
        # ES 风格：乘数 50，单边费用 1.25/手，2 手，风险 0.5 点
        j.record_open(_rec("r1", "ES", "LONG", 100.0, 99.5, 2,
                           multiplier=50.0, fee_per_side=1.25))
        out = j.record_close("r1", exit_price=101.0, exit_reason="hard_hold_cap")
        # 毛：1 点 * 2 手 * 50 = 100；费用 1.25*2*2 = 5；净 95
        assert abs(out["pnl_gross_abs"] - 100.0) < 1e-9
        assert abs(out["fee_total"] - 5.0) < 1e-9
        assert abs(out["pnl_net_abs"] - 95.0) < 1e-9
        # 旧列语义不变：pnl_abs 仍是点数*数量
        assert abs(out["pnl_abs"] - 2.0) < 1e-9
        assert abs(out["r_multiple"] - 2.0) < 1e-9
        # 净 R = 95 / (0.5*2*50 + 5) = 95/55
        assert abs(out["r_multiple_net"] - 95.0 / 55.0) < 1e-9


def test_short_direction_and_loss_net_r():
    with tempfile.TemporaryDirectory() as tmp:
        j = TradeJournal(str(Path(tmp) / "data.db"))
        j.record_open(_rec("r2", "ZN", "SHORT", 110.0, 110.5, 1,
                           multiplier=1000.0, fee_per_side=0.8))
        out = j.record_close("r2", exit_price=110.25, exit_reason="protective_stop")
        # 亏 0.25 点 * 1 * 1000 = -250 毛；费用 1.6；净 -251.6
        assert abs(out["pnl_gross_abs"] - (-250.0)) < 1e-9
        assert abs(out["pnl_net_abs"] - (-251.6)) < 1e-9
        risk_money = 0.5 * 1 * 1000.0 + 1.6
        assert abs(out["r_multiple_net"] - (-251.6 / risk_money)) < 1e-9
        assert out["r_multiple_net"] < out["r_multiple"] < 0  # 费用让亏损更深


def test_defaults_degrade_to_gross():
    with tempfile.TemporaryDirectory() as tmp:
        j = TradeJournal(str(Path(tmp) / "data.db"))
        j.record_open(_rec("r3", "EURUSD", "LONG", 1.10, 1.09, 10000))
        out = j.record_close("r3", exit_price=1.11)
        assert abs(out["pnl_gross_abs"] - out["pnl_abs"]) < 1e-9
        assert abs(out["pnl_net_abs"] - out["pnl_abs"]) < 1e-9
        assert abs(out["r_multiple_net"] - out["r_multiple"]) < 1e-9
        assert out["fee_total"] == 0.0


def test_legacy_database_rows_migrate_and_close():
    """Databases written before the multiplier/fee columns existed must still
    close correctly after the ALTER migration (degraded to gross)."""
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "data.db")
        conn = sqlite3.connect(db)
        conn.execute("""
            CREATE TABLE trades (
                client_ref TEXT PRIMARY KEY, symbol TEXT NOT NULL,
                event_name TEXT, direction TEXT, entry_price REAL,
                stop_loss REAL, quantity REAL, risk_per_unit REAL,
                opened_at TEXT, exit_price REAL, closed_at TEXT,
                pnl_abs REAL, pnl_pct REAL, r_multiple REAL,
                exit_reason TEXT, status TEXT
            )""")
        conn.execute(
            "INSERT INTO trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("legacy-1", "MNQ", "FOMC", "LONG", 18000.0, 17900.0, 1, 100.0,
             "2026-08-27T13:30:00+00:00", None, None, None, None, None,
             "", "OPEN"))
        conn.commit()
        conn.close()
        j = TradeJournal(db)  # 迁移新增列
        out = j.record_close("legacy-1", exit_price=18100.0)
        assert abs(out["r_multiple"] - 1.0) < 1e-9
        assert abs(out["r_multiple_net"] - out["r_multiple"]) < 1e-9
        row = j.get_trade("legacy-1")
        assert row["multiplier"] is None  # 旧行保持 NULL，读取时按 1.0 退化


def test_stats_report_net_aggregates():
    with tempfile.TemporaryDirectory() as tmp:
        j = TradeJournal(str(Path(tmp) / "data.db"))
        j.record_open(_rec("s1", "ES", "LONG", 100.0, 99.5, 2,
                           multiplier=50.0, fee_per_side=1.25))
        j.record_close("s1", exit_price=101.0)
        j.record_open(_rec("s2", "ES", "LONG", 100.0, 99.5, 2,
                           multiplier=50.0, fee_per_side=1.25))
        j.record_close("s2", exit_price=99.5)
        st = j.stats("ES")
        assert st["closed_trades"] == 2
        # 第二笔：move=-0.5 → 毛 -50，费用 5，净 -55
        assert abs(st["total_pnl_net_abs"] - (95.0 - 55.0)) < 1e-6
        assert abs(st["total_fees"] - 10.0) < 1e-9
        assert st["avg_r_net"] is not None
        assert st["avg_r_net"] < st["avg_r"]  # 费用使净均值低于毛均值


def test_invalid_multiplier_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        j = TradeJournal(str(Path(tmp) / "data.db"))
        try:
            j.record_open(_rec("bad", "ES", "LONG", 100.0, 99.5, 1,
                               multiplier=0.0))
        except ValueError:
            pass
        else:
            raise AssertionError("multiplier <= 0 must be rejected")


def main() -> int:
    test_long_futures_net_r_accounts_for_multiplier_and_fees()
    test_short_direction_and_loss_net_r()
    test_defaults_degrade_to_gross()
    test_legacy_database_rows_migrate_and_close()
    test_stats_report_net_aggregates()
    test_invalid_multiplier_rejected()
    print("✓ journal net-R (multiplier + fees) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
