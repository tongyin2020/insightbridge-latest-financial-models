"""Stage-4 integration test.

This test module never submits an order and never mutates configuration.  It
exercises the read-only end-to-end path:

  EventDataArchive -> seal -> EventReplayer -> cutoff filter
  CalibrationWorkbench -> two algo versions -> PROPOSED / REJECTED_OVERFIT
  Intent ledger with CLOSED, broker-acked intents -> PaperAcceptanceChecker
"""
from __future__ import annotations

import os
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from calibration_workbench import (
    CalibrationWorkbench,
    STATUS_PROPOSED,
    STATUS_REJECTED_OVERFIT,
)
from event_data_archive import EventDataArchive
from event_replayer import EventReplayer
from paper_acceptance import PaperAcceptanceChecker, READY, NOT_READY


def _sharpe(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        return 0.0
    return mean / stdev


def _good_score(samples: Sequence[Mapping[str, Any]],
                params: Mapping[str, Any]) -> Mapping[str, Any]:
    values = [float(r["return_bps"]) for r in samples]
    return {"mean_bps": statistics.fmean(values) if values else 0.0,
            "sharpe": _sharpe(values), "n": len(values)}


def _overfit_score(samples: Sequence[Mapping[str, Any]],
                   params: Mapping[str, Any]) -> Mapping[str, Any]:
    if not samples:
        return {"mean_bps": 0.0, "sharpe": 0.0, "n": 0}
    n = len(samples)
    if n >= 40:
        return {"mean_bps": 3.0, "sharpe": 12.0, "n": n}
    return {"mean_bps": 0.02, "sharpe": 0.1, "n": n}


def _linear_samples(n: int, algo_version: str, start: datetime,
                    base: float = 1.0, jitter: float = 0.03) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append({
            "ts": (start + timedelta(minutes=i)).isoformat(),
            "return_bps": base + jitter * ((-1) ** i),
            "algo_version": algo_version,
            "symbol": "MNQ",
        })
    return rows


def _build_ledger_with_submitted(path: Path, *, start_epoch: float,
                                 end_epoch: float, total: int) -> None:
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
                source TEXT NOT NULL DEFAULT '',
                updated_epoch REAL NOT NULL,
                PRIMARY KEY(venue,product_group))
            """)
        for i in range(total):
            conn.execute("""
                INSERT INTO order_intents(
                    intent_id,account_id,event_year,event_id,symbol,side,
                    strategy_version,state,broker_ack_state,
                    created_epoch,updated_epoch)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """, (f"intent-{i}", "DU-PAPER", 2026, f"evt-{i}",
                      "MNQ", "BUY", "v-e2e", "CLOSED", "ACKED_PAPER",
                      start_epoch, end_epoch))


def test_stage4_end_to_end_paper_ready(tmp_path: Path) -> None:
    # 1. Archive + replayer
    archive_root = tmp_path / "archive"
    archive = EventDataArchive(str(archive_root), source="stage4-integration")
    event_id = "2026-08-15T12Z-CPI"
    t0 = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    archive.open_event(event_id, "CPI", t0, "ES",
                       {"secType": "FUT", "exchange": "CME"})
    for i in range(5):
        archive.append(event_id, "ES", "bars",
                       {"o": 1, "h": 1, "l": 1, "c": 1, "v": 1},
                       observed_at=t0 - timedelta(minutes=5 - i))
    # Add a trade after cutoff to prove filtering works.
    archive.append(event_id, "ES", "trades",
                   {"price": 100.0, "size": 1},
                   observed_at=t0 + timedelta(minutes=2))
    archive.seal_event(event_id, "ES")

    replayer = EventReplayer(str(archive_root))
    view = replayer.load_event(event_id, "ES", cutoff_utc=t0)
    assert len(view.bars()) == 5
    assert view.trades() == [], "cutoff must filter out post-event trades"

    # 2. Calibration: PROPOSED for well-behaved samples, REJECTED_OVERFIT for the other.
    wb = CalibrationWorkbench()
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    good = wb.evaluate(
        _linear_samples(80, "algo-good", start, base=1.2, jitter=0.02),
        {"bias": [0.0]}, _good_score)
    assert good["status"] == STATUS_PROPOSED
    assert good["approval"]["state"] == "AWAITING_HUMAN_REVIEW"
    assert good["applies_to_live"] is False

    bad = wb.evaluate(
        _linear_samples(80, "algo-overfit", start, base=1.0, jitter=0.02),
        {"bias": [0.0]}, _overfit_score)
    assert bad["status"] == STATUS_REJECTED_OVERFIT
    assert bad["recommended_params"] is None

    # 3. Ledger + paper acceptance -> READY_FOR_PAPER_TRIAL
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    _build_ledger_with_submitted(
        ledger,
        start_epoch=cutoff.timestamp() - 20 * 86400,
        end_epoch=cutoff.timestamp() - 3600,
        total=5)
    log_dir = tmp_path / "runtime_log"
    log_dir.mkdir()
    log_file = log_dir / "run.log"
    log_file.write_text("ok", encoding="utf-8")
    os.utime(log_file, (cutoff.timestamp() - 60, cutoff.timestamp() - 60))
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=[event_id])
    report = checker.check()
    assert report["overall"] == READY, report
    assert "READY_FOR_LIVE" not in report["overall"]


def test_stage4_end_to_end_not_ready_when_archive_missing(tmp_path: Path) -> None:
    cutoff = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    ledger = tmp_path / "ledger.db"
    _build_ledger_with_submitted(
        ledger,
        start_epoch=cutoff.timestamp() - 20 * 86400,
        end_epoch=cutoff.timestamp() - 3600,
        total=5)
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    log_dir = tmp_path / "runtime_log"
    log_dir.mkdir()
    log_file = log_dir / "run.log"
    log_file.write_text("ok", encoding="utf-8")
    os.utime(log_file, (cutoff.timestamp() - 60, cutoff.timestamp() - 60))
    checker = PaperAcceptanceChecker(
        ledger, archive_root, log_dir, cutoff_utc=cutoff,
        min_observation_days=10, required_events=["never-sealed-event"])
    report = checker.check()
    assert report["overall"] == NOT_READY
