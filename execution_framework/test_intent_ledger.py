"""Offline tests for cross-process intent uniqueness and annual event caps."""
from __future__ import annotations

import multiprocessing as mp
import sqlite3
import tempfile
from pathlib import Path

from intent_ledger import IntentLedger, deterministic_intent_id


def _reserve_same_intent(db_path: str, queue) -> None:
    ledger = IntentLedger(db_path)
    row = ledger.reserve_intent(
        "DU-PAPER", "2026-08-27T14:00Z:FOMC", 2026,
        "MNQ", "BUY", "eventalpha-v3")
    queue.put(row.accepted)


def test_deterministic_intent_id():
    a = deterministic_intent_id(
        "DU-PAPER", "evt", "EUR/USD", "buy", "v3")
    b = deterministic_intent_id(
        "DU-PAPER", "evt", "EURUSD", "BUY", "v3")
    assert a == b


def test_cross_process_uniqueness():
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "safety.db")
        queue = mp.Queue()
        workers = [mp.Process(target=_reserve_same_intent, args=(db, queue))
                   for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
            assert worker.exitcode == 0
        accepted = [queue.get(timeout=2) for _ in workers]
        assert sum(bool(x) for x in accepted) == 1, accepted


def test_leader_lease_and_expiry():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        assert ledger.acquire_lease("DU-PAPER", "runner-a", ttl_s=10, now_epoch=100)
        assert not ledger.acquire_lease("DU-PAPER", "runner-b", ttl_s=10, now_epoch=105)
        assert ledger.acquire_lease("DU-PAPER", "runner-b", ttl_s=10, now_epoch=111)
        assert not ledger.renew_lease("DU-PAPER", "runner-a", ttl_s=10, now_epoch=112)


def test_annual_cap_has_no_forced_minimum():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        for n in range(2):
            row = ledger.reserve_event(
                "DU-PAPER", f"event-{n}", 2026, annual_limit=2, now_epoch=100 + n)
            assert row.accepted
        blocked = ledger.reserve_event(
            "DU-PAPER", "event-2", 2026, annual_limit=2, now_epoch=103)
        assert not blocked.accepted
        assert blocked.reason == "annual_event_limit_reached"
        assert ledger.release_untraded_event("DU-PAPER", "event-1", 2026)
        admitted = ledger.reserve_event(
            "DU-PAPER", "event-2", 2026, annual_limit=2, now_epoch=104)
        assert admitted.accepted


def test_one_product_per_event_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        first = ledger.reserve_intent(
            "DU-PAPER", "fomc-1", 2026, "ZN", "BUY", "v3")
        second = ledger.reserve_intent(
            "DU-PAPER", "fomc-1", 2026, "MNQ", "SELL", "v3")
        assert first.accepted
        assert not second.accepted
        assert second.reason == "event_product_limit_reached"


def test_partial_fill_consumes_event_and_rejection_releases_untraded_event():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        event_id = "fomc-partial"
        assert ledger.reserve_event(
            "DU-PAPER", event_id, 2026, annual_limit=1).accepted
        intent = ledger.reserve_intent(
            "DU-PAPER", event_id, 2026, "MNQ", "BUY", "v3")
        assert intent.accepted
        assert ledger.advance_intent(
            intent.intent_id, "PARTIAL", broker_order_id="123",
            filled_quantity=1.0)
        assert ledger.mark_event_traded("DU-PAPER", event_id, 2026)
        assert ledger.event_status("DU-PAPER", event_id, 2026) == "TRADED"
        assert not ledger.release_untraded_event(
            "DU-PAPER", event_id, 2026)

        other = IntentLedger(str(Path(tmp) / "other.db"))
        rejected_event = "ecb-rejected"
        assert other.reserve_event(
            "DU-PAPER", rejected_event, 2026, annual_limit=1).accepted
        rejected = other.reserve_intent(
            "DU-PAPER", rejected_event, 2026, "EURUSD", "SELL", "v3")
        assert rejected.accepted
        assert other.advance_intent(rejected.intent_id, "REJECTED")
        assert other.release_untraded_event(
            "DU-PAPER", rejected_event, 2026)
        assert other.event_status(
            "DU-PAPER", rejected_event, 2026) is None


def test_fencing_token_blocks_stale_leader():
    """Fencing token: a paused ex-leader must fail check_fencing after another
    process takes over the lease, and renewals must not change the token."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        # runner-a 取得租约，token = 1
        assert ledger.acquire_lease("DU-PAPER", "runner-a", ttl_s=10, now_epoch=100)
        token_a = ledger.current_fencing_token("DU-PAPER", "runner-a")
        assert token_a == 1
        # 租约有效期内校验通过；renew 不改变 token
        assert ledger.check_fencing("DU-PAPER", "runner-a", token_a, now_epoch=105)
        assert ledger.renew_lease("DU-PAPER", "runner-a", ttl_s=10, now_epoch=105)
        assert ledger.current_fencing_token("DU-PAPER", "runner-a") == token_a
        assert ledger.check_fencing("DU-PAPER", "runner-a", token_a, now_epoch=114)
        # runner-a 停顿超过 TTL（105+10=115 到期），runner-b 于 116 接管
        assert ledger.acquire_lease("DU-PAPER", "runner-b", ttl_s=10, now_epoch=116)
        token_b = ledger.current_fencing_token("DU-PAPER", "runner-b")
        assert token_b == token_a + 1
        # runner-a 苏醒：旧 token 失配（owner 也不符），下单必须被拒绝
        assert not ledger.check_fencing("DU-PAPER", "runner-a", token_a, now_epoch=117)
        # runner-b 持新 token 正常下单
        assert ledger.check_fencing("DU-PAPER", "runner-b", token_b, now_epoch=117)
        # runner-b 用 runner-a 的旧 epoch 也不行（防 token 猜测/混用）
        assert not ledger.check_fencing("DU-PAPER", "runner-b", token_a, now_epoch=117)
        # 接管者租约过期后同样被拒
        assert not ledger.check_fencing("DU-PAPER", "runner-b", token_b, now_epoch=127)
        # 无租约账户 / 未持租约的 owner 查询返回 None / False
        assert ledger.current_fencing_token("DU-OTHER", "runner-a") is None
        assert ledger.current_fencing_token("DU-PAPER", "runner-a") is None
        assert not ledger.check_fencing("DU-OTHER", "runner-a", 1, now_epoch=100)


def test_fencing_column_migration_on_old_database():
    """Databases created before the fencing_epoch column must be upgraded
    in place via ALTER TABLE, with existing leases keeping epoch 0 semantics."""
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "safety.db")
        conn = sqlite3.connect(db)
        conn.execute("""
            CREATE TABLE execution_leases (
                account_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                expires_epoch REAL NOT NULL,
                updated_epoch REAL NOT NULL
            )""")
        conn.execute(
            "INSERT INTO execution_leases VALUES(?,?,?,?)",
            ("DU-PAPER", "legacy-runner", 50.0, 40.0))
        conn.commit()
        conn.close()
        # 新代码打开旧库：迁移列存在，旧租约过期后可被接管且 token 从 0 递增
        ledger = IntentLedger(db)
        assert ledger.acquire_lease("DU-PAPER", "runner-a", ttl_s=10, now_epoch=100)
        assert ledger.current_fencing_token("DU-PAPER", "runner-a") == 1
        assert ledger.check_fencing("DU-PAPER", "runner-a", 1, now_epoch=105)


def test_state_transition_table():
    """advance_intent enforces an explicit transition table:
    regressions such as FILLED -> SUBMITTED are rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        intent = ledger.reserve_intent(
            "DU-PAPER", "fomc-transitions", 2026, "MNQ", "BUY", "v3")
        assert intent.accepted
        iid = intent.intent_id
        # 非法：RESERVED -> EXIT_SUBMITTED（未下单不能直接进入退出）
        assert not ledger.advance_intent(iid, "EXIT_SUBMITTED")
        # 合法主链：RESERVED -> SUBMITTED -> PARTIAL -> FILLED
        assert ledger.advance_intent(iid, "SUBMITTED")
        # 幂等：同状态重复回报允许（券商状态重放）
        assert ledger.advance_intent(iid, "SUBMITTED")
        assert ledger.advance_intent(iid, "PARTIAL", filled_quantity=1.0)
        # 非法倒退：PARTIAL -> RESERVED
        assert not ledger.advance_intent(iid, "RESERVED")
        assert ledger.advance_intent(iid, "FILLED", filled_quantity=2.0)
        # 非法倒退：FILLED -> SUBMITTED
        assert not ledger.advance_intent(iid, "SUBMITTED")
        assert ledger.get_intent(iid)["state"] == "FILLED"
        # 退出链：FILLED -> EXIT_SUBMITTED -> EXIT_PARTIAL -> CLOSED
        assert ledger.advance_intent(iid, "EXIT_SUBMITTED")
        # 退出腿被撤销、仓位仍在 -> 允许回到 FILLED
        assert ledger.advance_intent(iid, "FILLED")
        assert ledger.advance_intent(iid, "EXIT_SUBMITTED")
        assert ledger.advance_intent(iid, "EXIT_PARTIAL")
        assert ledger.advance_intent(iid, "CLOSED")
        # 终态不可离开
        assert not ledger.advance_intent(iid, "SUBMITTED")
        assert ledger.advance_intent(iid, "CLOSED")  # 同状态幂等允许


def test_operator_and_algo_provenance_do_not_change_intent_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        first = ledger.reserve_intent(
            "DU-PAPER", "prov-evt", 2026, "MNQ", "BUY", "v4",
            operator_id="ops-42")
        assert first.accepted
        row = ledger.get_intent(first.intent_id)
        assert row["operator_id"] == "ops-42"
        assert row["algo_version"] == "v4"
        again = ledger.reserve_intent(
            "DU-PAPER", "prov-evt", 2026, "MNQ", "BUY", "v4",
            operator_id="someone-else")
        assert not again.accepted
        assert again.intent_id == first.intent_id
        assert again.reason == "duplicate_economic_intent"


def test_broker_ack_default_is_pending_and_valid_updates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        reservation = ledger.reserve_intent(
            "DU-PAPER", "broker-ack-evt", 2026, "MNQ", "BUY", "v-ack",
            now_epoch=1000.0)
        assert reservation.accepted
        row = ledger.get_intent(reservation.intent_id)
        assert row["broker_ack_state"] == "PENDING_BROKER_ACK"
        assert row["broker_ack_payload"] is None
        assert ledger.record_broker_ack(
            reservation.intent_id, "ACKED_PAPER",
            payload_json='{"broker_order_id":"BX-1"}')
        after = ledger.get_intent(reservation.intent_id)
        assert after["broker_ack_state"] == "ACKED_PAPER"
        assert after["broker_ack_payload"] == '{"broker_order_id":"BX-1"}'
        assert after["state"] == row["state"], \
            "record_broker_ack must not mutate state"
        assert after["updated_epoch"] == 1000.0, \
            "record_broker_ack must not touch updated_epoch"
        assert not ledger.record_broker_ack("missing-intent", "ACKED_PAPER")


def test_broker_ack_rejects_unknown_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ledger = IntentLedger(str(Path(tmp) / "safety.db"))
        reservation = ledger.reserve_intent(
            "DU-PAPER", "bad-ack-evt", 2026, "MNQ", "BUY", "v-ack")
        try:
            ledger.record_broker_ack(reservation.intent_id, "NOT_A_REAL_STATE")
        except ValueError:
            pass
        else:
            raise AssertionError("unknown broker_ack_state must raise")


def test_broker_ack_columns_migrate_old_schema() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "old.db")
        with sqlite3.connect(db) as conn:
            conn.execute("""
                CREATE TABLE order_intents (
                    intent_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    event_year INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    state TEXT NOT NULL,
                    broker_order_id TEXT,
                    filled_quantity REAL NOT NULL DEFAULT 0,
                    created_epoch REAL NOT NULL,
                    updated_epoch REAL NOT NULL,
                    UNIQUE(account_id,event_id,symbol,side,strategy_version)
                )""")
        ledger = IntentLedger(db)
        reservation = ledger.reserve_intent(
            "DU-PAPER", "migrate-ack", 2026, "MNQ", "BUY", "v-ack")
        assert reservation.accepted
        row = ledger.get_intent(reservation.intent_id)
        assert row["broker_ack_state"] == "PENDING_BROKER_ACK"
        assert row["operator_id"] == "SYSTEM_UNSPECIFIED"
        assert row["algo_version"] == "v-ack"


def main() -> int:
    test_deterministic_intent_id()
    test_cross_process_uniqueness()
    test_leader_lease_and_expiry()
    test_annual_cap_has_no_forced_minimum()
    test_one_product_per_event_by_default()
    test_partial_fill_consumes_event_and_rejection_releases_untraded_event()
    test_fencing_token_blocks_stale_leader()
    test_fencing_column_migration_on_old_database()
    test_state_transition_table()
    test_operator_and_algo_provenance_do_not_change_intent_id()
    test_broker_ack_default_is_pending_and_valid_updates()
    test_broker_ack_rejects_unknown_state()
    test_broker_ack_columns_migrate_old_schema()
    print("✓ durable intent ledger, leader lease and annual event cap passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
