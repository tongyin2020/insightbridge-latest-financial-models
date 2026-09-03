"""Offline tests for the read-only PAPER acceptance checker.

This test module never submits an order and never mutates configuration.  It
builds a tmp intent ledger + event archive + runtime log directory and asserts
PASS / FAIL / UNKNOWN branches of the checker.
"""
from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from event_data_archive import EventDataArchive
from paper_acceptance import (
    NOT_READY,
    READY,
    PaperAcceptanceChecker,
)


def _build_ledger(path: Path, *, start_epoch: float, end_epoch: float,
                  hanging: int = 0, total: int = 5,
                  settled_state: str = "CLOSED",
                  ack_state: str = "ACKED_PAPER") -> None:
    with sqlite3.connect(str(path)) as conn:
        conn.execute("""
            CREATE TABLE order_intents (
                intent_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                event_year INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                algo_version TEXT NOT NULL DEFAULT 'UNSPECIFIED',
                operator_id TEXT NOT NULL DEFAULT 'SYSTEM_UNSPECIFIED',
                broker_ack_state TEXT NOT NULL DEFAULT 'PENDING_BROKER_ACK',
                broker_ack_payload TEXT,
                state TEXT NOT NULL,
                broker_order_id TEXT,
                filled_quantity REAL NOT NULL DEFAULT 0,
                created_epoch REAL NOT NULL,
                updated_epoch REAL NOT NULL)
            """)
        conn.execute("""
            CREATE TABLE upstream_states (
                venue TEXT NOT NULL,
                product_group TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                operator_id TEXT NOT NULL,
                updated_epoch REAL NOT NULL,
                PRIMARY KEY(venue,product_group))
            """)
        for i in range(total):
            state = "RESERVED" if i < hanging else settled_state
            conn.execute("""
                INSERT INTO order_intents(
                    intent_id,account_id,event_year,event_id,symbol,side,
                    strategy_version,state,broker_ack_state,
                    created_epoch,updated_epoch)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """, (f"intent-{i}", "DU-PAPER", 2026, f"evt-{i}",
                      "MNQ", "BUY", "v-test", state, ack_state,
                      start_epoch, end_epoch))


def _insert_intent(path: Path, intent_id: str, state: str,
                   created_epoch: float, updated_epoch: float,
                   ack_state: str = "ACKED_PAPER") -> None:
    with sqlite3.connect(str(path)) as conn:
        conn.execute("""
            INSERT INTO order_intents(
                intent_id,account_id,event_year,event_id,symbol,side,
                strategy_version,state,broker_ack_state,
                created_epoch,updated_epoch)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (intent_id, "DU-PAPER", 2026, f"evt-{intent_id}",
                  "MNQ", "BUY", "v-test", state, ack_state,
                  created_epoch, updated_epoch))


def _ledger_check(report: dict) -> dict:
    return [c for c in report["checks"] if c["name"] == "ledger_observation"][0]


def _seed_archive(tmp_path: Path, event_id: str) -> Path:
    root = tmp_path / "archive"
    archive = EventDataArchive(str(root), source="paper-acceptance-test")
    t0 = datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)
    archive.open_event(event_id, "CPI", t0, "ES",
                       {"secType": "FUT", "exchange": "CME"})
    archive.append(event_id, "ES", "bars",
                   {"o": 1, "h": 1, "l": 1, "c": 1, "v": 1},
                   observed_at=t0)
    archive.seal_event(event_id, "ES")
    return root


def _seed_runtime_log(tmp_path: Path, mtime: float) -> Path:
    log_dir = tmp_path / "runtime_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    file = log_dir / "run.log"
    file.write_text("ok", encoding="utf-8")
    os.utime(file, (mtime, mtime))
    return log_dir


def test_pass_path(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end,
                  hanging=0, total=5)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == READY, report
    assert all(c["status"] == "PASS" for c in report["checks"]), report


def test_fail_insufficient_observation_days(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 2 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == NOT_READY
    ledger_check = [c for c in report["checks"]
                    if c["name"] == "ledger_observation"][0]
    assert ledger_check["status"] == "FAIL"
    assert ledger_check["evidence"]["reason"] == "insufficient_observation_days"


def test_fail_hanging_intent(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end,
                  hanging=1, total=5)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == NOT_READY


def test_fail_observation_days_ignore_rows_after_cutoff(tmp_path: Path) -> None:
    """Ledger activity after the cutoff must not inflate the observation span."""
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 2 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    # A row created 30 days after the cutoff, and a pre-cutoff row that was
    # touched 30 days after the cutoff.
    future = cutoff.timestamp() + 30 * 86400
    _insert_intent(ledger, "future", "CLOSED", future, future)
    _insert_intent(ledger, "touched-later", "CLOSED", start, future)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == NOT_READY, report
    ledger_check = _ledger_check(report)
    assert ledger_check["evidence"]["reason"] == "insufficient_observation_days"
    assert ledger_check["evidence"]["observation_days"] <= 2.0
    assert ledger_check["evidence"]["total_intents_before_cutoff"] == 6


def test_fail_non_terminal_submitted_intents(tmp_path: Path) -> None:
    """SUBMITTED / FILLED are not terminal: old ones are hanging intents."""
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    for state in ("SUBMITTED", "FILLED", "EXIT_SUBMITTED", "PARTIAL"):
        path = tmp_path / f"ledger-{state}.db"
        _build_ledger(path, start_epoch=start, end_epoch=end, hanging=0,
                      settled_state=state)
        event_id = "2026-08-01T14Z-CPI"
        archive_root = _seed_archive(tmp_path / state, event_id)
        log_dir = _seed_runtime_log(tmp_path / state,
                                    mtime=cutoff.timestamp() - 60)
        checker = PaperAcceptanceChecker(
            path, archive_root, log_dir, cutoff_utc=cutoff,
            min_observation_days=10, required_events=[event_id])
        report = checker.check()
        assert report["overall"] == NOT_READY, (state, report)
        ledger_check = _ledger_check(report)
        assert ledger_check["evidence"]["reason"] == "hanging_intents_before_cutoff"
        assert ledger_check["evidence"]["hanging_intents"] == 5


def test_recent_open_intent_within_grace_is_not_hanging(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    # Filled 2h before cutoff: an open position inside the 24h grace window.
    _insert_intent(ledger, "recent", "FILLED", cutoff.timestamp() - 7200,
                   cutoff.timestamp() - 7200)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    assert checker.check()["overall"] == READY
    strict_grace = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id],
        hanging_grace_s=3600)
    assert strict_grace.check()["overall"] == NOT_READY


def test_hanging_reserved_detected_even_if_updated_after_cutoff(
        tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    _insert_intent(ledger, "stale-reserved", "RESERVED",
                   cutoff.timestamp() - 5 * 86400,
                   cutoff.timestamp() + 86400)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == NOT_READY
    assert _ledger_check(report)["evidence"]["reason"] == \
        "hanging_intents_before_cutoff"


def test_fail_long_pending_broker_ack(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    _insert_intent(ledger, "never-acked", "CLOSED",
                   cutoff.timestamp() - 2 * 86400,
                   cutoff.timestamp() - 2 * 86400,
                   ack_state="PENDING_BROKER_ACK")
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == NOT_READY
    ledger_check = _ledger_check(report)
    assert ledger_check["evidence"]["reason"] == "pending_broker_ack_before_cutoff"
    assert ledger_check["evidence"]["pending_broker_ack_intents"] == 1


def test_unknown_when_ledger_has_no_broker_ack_column(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    with sqlite3.connect(str(ledger)) as conn:
        conn.execute("ALTER TABLE order_intents DROP COLUMN broker_ack_state")
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == NOT_READY
    ledger_check = _ledger_check(report)
    assert ledger_check["status"] == "UNKNOWN"
    assert ledger_check["evidence"]["reason"] == "no_broker_ack_state_column"


def test_checker_opens_ledger_read_only(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    _build_ledger(ledger, start_epoch=cutoff.timestamp() - 15 * 86400,
                  end_epoch=cutoff.timestamp() - 3600)
    checker = PaperAcceptanceChecker(
        ledger, tmp_path, tmp_path, cutoff_utc=cutoff,
        min_observation_days=10, required_events=["x"])
    with checker._ro_conn() as conn:
        try:
            conn.execute("DELETE FROM order_intents")
        except sqlite3.OperationalError as exc:
            assert "readonly" in str(exc).lower()
        else:
            raise AssertionError("checker connection must be read-only")


def test_fail_missing_required_event(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    archive_root = _seed_archive(tmp_path, "existing-event")
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10,
        required_events=["missing-event"])
    report = checker.check()
    archive_check = [c for c in report["checks"]
                     if c["name"] == "event_archive"][0]
    assert archive_check["status"] == "FAIL"
    assert report["overall"] == NOT_READY


def test_fail_runtime_log_newer_than_cutoff(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() + 3600)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == NOT_READY
    log_check = [c for c in report["checks"]
                 if c["name"] == "runtime_log_freshness"][0]
    assert log_check["status"] == "FAIL"


def test_fail_persistent_upstream_block(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    with sqlite3.connect(str(ledger)) as conn:
        conn.execute(
            "INSERT INTO upstream_states"
            "(venue,product_group,status,reason,operator_id,updated_epoch)"
            "VALUES(?,?,?,?,?,?)",
            ("CME", "INDEX", "BLOCKED_BY_UPSTREAM",
             "venue notice", "feed-gateway",
             cutoff.timestamp() - 3600))
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == NOT_READY
    upstream_check = [c for c in report["checks"]
                      if c["name"] == "upstream_block_cleared"][0]
    assert upstream_check["status"] == "FAIL"


def test_unknown_when_no_intents_in_strict_mode(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    with sqlite3.connect(str(ledger)) as conn:
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
                updated_epoch REAL NOT NULL)
            """)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id], strict=True)
    report = checker.check()
    assert report["overall"] == NOT_READY
    ledger_check = [c for c in report["checks"]
                    if c["name"] == "ledger_observation"][0]
    assert ledger_check["status"] == "UNKNOWN"


def test_write_report_is_atomic(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    start = cutoff.timestamp() - 15 * 86400
    end = cutoff.timestamp() - 3600
    _build_ledger(ledger, start_epoch=start, end_epoch=end, hanging=0)
    event_id = "2026-08-01T14Z-CPI"
    archive_root = _seed_archive(tmp_path, event_id)
    log_dir = _seed_runtime_log(tmp_path, mtime=cutoff.timestamp() - 60)
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    target = tmp_path / "report" / "paper.json"
    checker.write_report(target)
    assert target.exists()
    tmps = list(target.parent.glob(".*.tmp"))
    assert tmps == []
