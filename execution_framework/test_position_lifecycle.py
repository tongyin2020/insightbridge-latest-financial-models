"""Offline tests for broker-confirmed lifecycle and hard hold caps."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from position_lifecycle import PositionLifecycleMonitor


def test_hard_cap_is_independent_and_uses_fill_time():
    monitor = PositionLifecycleMonitor({"INDEX": 1800})
    filled = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
    monitor.register_broker_fill(
        "ref-1", "MNQ", "INDEX", "LONG", 2, 18000, filled)
    assert monitor.evaluate(
        "ref-1", filled + timedelta(seconds=1799)).action == "HOLD"
    decision = monitor.evaluate(
        "ref-1", filled + timedelta(seconds=1800))
    assert decision.action == "EXIT"
    assert decision.reason == "hard_hold_cap"


def test_safety_signal_exits_before_cap():
    monitor = PositionLifecycleMonitor({"FX": 2100})
    filled = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
    monitor.register_broker_fill(
        "ref-2", "EURUSD", "FX", "SHORT", 10000, 1.16, filled)
    decision = monitor.evaluate(
        "ref-2", filled + timedelta(minutes=3),
        liquidity_collapse=True)
    assert decision.action == "EXIT"
    assert decision.reason == "liquidity_collapse"


def test_exit_submission_is_not_close():
    monitor = PositionLifecycleMonitor()
    filled = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
    monitor.register_broker_fill(
        "ref-3", "BTC", "CRYPTO_SPOT", "LONG", 0.01, 60000, filled)
    state = monitor.mark_exit_submitted(
        "ref-3", "hard_hold_cap", filled + timedelta(minutes=30))
    assert state.state == "EXIT_SUBMITTED"
    state = monitor.confirm_exit_fill(
        "ref-3", cumulative_exit_quantity=0.006,
        broker_position_quantity=0.004)
    assert state.state == "EXIT_PARTIAL"
    assert abs(state.remaining_quantity - 0.004) < 1e-12
    state = monitor.confirm_exit_fill(
        "ref-3", cumulative_exit_quantity=0.01,
        broker_position_quantity=0.0)
    assert state.state == "CLOSED"


def test_partial_entry_does_not_reset_first_fill_clock():
    monitor = PositionLifecycleMonitor({"INDEX": 60})
    first = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
    monitor.upsert_broker_fill(
        "ref-4", "MNQ", "INDEX", "LONG", 1, 18000, first)
    state = monitor.upsert_broker_fill(
        "ref-4", "MNQ", "INDEX", "LONG", 2, 18001,
        first + timedelta(seconds=30))
    assert state.broker_fill_time == first
    assert state.filled_quantity == 2
    decision = monitor.evaluate(
        "ref-4", first + timedelta(seconds=61))
    assert decision.action == "EXIT"
    assert decision.reason == "hard_hold_cap"


def test_partial_exit_quantity_is_never_resurrected():
    """Regression: after a confirmed partial exit, a later entry-leg fill
    update must NOT push remaining_quantity back up to cumulative filled."""
    monitor = PositionLifecycleMonitor({"INDEX": 3600})
    filled = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
    monitor.register_broker_fill(
        "ref-5", "MNQ", "INDEX", "LONG", 4, 18000, filled)
    monitor.mark_exit_submitted(
        "ref-5", "fakeout_confirmed", filled + timedelta(minutes=5))
    state = monitor.confirm_exit_fill(
        "ref-5", cumulative_exit_quantity=3.0,
        broker_position_quantity=1.0)
    assert state.state == "EXIT_PARTIAL"
    assert abs(state.remaining_quantity - 1.0) < 1e-12
    # 入场腿的迟到回报/重复回报再次 upsert：剩余量必须保持 filled - exited
    state = monitor.upsert_broker_fill(
        "ref-5", "MNQ", "INDEX", "LONG", 4, 18000.5,
        filled + timedelta(minutes=6))
    assert abs(state.remaining_quantity - 1.0) < 1e-12
    # 乱序/陈旧的退出回报（累计值变小）也不允许复活数量
    state = monitor.confirm_exit_fill(
        "ref-5", cumulative_exit_quantity=2.0,
        broker_position_quantity=1.0)
    assert abs(state.remaining_quantity - 1.0) < 1e-12
    state = monitor.confirm_exit_fill(
        "ref-5", cumulative_exit_quantity=4.0,
        broker_position_quantity=0.0)
    assert state.state == "CLOSED"
    assert state.remaining_quantity == 0.0


def test_persistence_survives_process_restart():
    """Position clock must survive a crash: a fresh monitor on the same
    persist_path restores state and the hard-cap clock keeps running."""
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "lifecycle.db")
        filled = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
        monitor = PositionLifecycleMonitor({"INDEX": 1800}, persist_path=db)
        monitor.register_broker_fill(
            "ref-p1", "MNQ", "INDEX", "LONG", 4, 18000, filled)
        monitor.mark_exit_submitted(
            "ref-p1", "fakeout_confirmed", filled + timedelta(minutes=5))
        state = monitor.confirm_exit_fill(
            "ref-p1", cumulative_exit_quantity=3.0,
            broker_position_quantity=1.0)
        assert state.state == "EXIT_PARTIAL"

        # 模拟进程崩溃重启：全新实例从同一个库恢复
        restored = PositionLifecycleMonitor({"INDEX": 1800}, persist_path=db)
        assert "ref-p1" in restored.positions
        pos = restored.positions["ref-p1"]
        # 时钟不丢失：broker_fill_time 与崩溃前完全一致
        assert pos.broker_fill_time == filled
        assert pos.state == "EXIT_PARTIAL"
        assert abs(pos.remaining_quantity - 1.0) < 1e-12
        assert abs(pos.cumulative_exit_quantity - 3.0) < 1e-12
        assert pos.exit_reason == "fakeout_confirmed"
        assert pos.exit_submitted_at == filled + timedelta(minutes=5)
        # 恢复的持仓继续受硬封顶约束：evaluate 的 elapsed 从原始成交时间起算
        decision = restored.evaluate("ref-p1", filled + timedelta(minutes=29))
        assert decision.action == "MONITOR_EXIT"
        assert abs(decision.elapsed_seconds - 29 * 60) < 1e-9


def test_restore_of_open_position_keeps_cap_clock():
    """An OPEN position restored after restart must EXIT at the cap measured
    from the original fill time, not from the restart time."""
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "lifecycle.db")
        filled = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
        monitor = PositionLifecycleMonitor({"INDEX": 1800}, persist_path=db)
        monitor.register_broker_fill(
            "ref-p2", "MNQ", "INDEX", "LONG", 2, 18000, filled)
        # 重启发生在成交后 25 分钟；5 分钟后必须触发 30 分钟硬封顶
        restarted = PositionLifecycleMonitor({"INDEX": 1800}, persist_path=db)
        decision = restarted.evaluate(
            "ref-p2", filled + timedelta(minutes=29, seconds=59))
        assert decision.action == "HOLD"
        decision = restarted.evaluate(
            "ref-p2", filled + timedelta(minutes=30))
        assert decision.action == "EXIT"
        assert decision.reason == "hard_hold_cap"
        # 无 persist_path 时行为不变（纯内存）
        mem_only = PositionLifecycleMonitor({"INDEX": 1800})
        assert mem_only.restore() == 0


def main() -> int:
    test_hard_cap_is_independent_and_uses_fill_time()
    test_safety_signal_exits_before_cap()
    test_exit_submission_is_not_close()
    test_partial_entry_does_not_reset_first_fill_clock()
    test_partial_exit_quantity_is_never_resurrected()
    test_persistence_survives_process_restart()
    test_restore_of_open_position_keeps_cap_clock()
    print("✓ broker-confirmed position lifecycle and hard caps passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
