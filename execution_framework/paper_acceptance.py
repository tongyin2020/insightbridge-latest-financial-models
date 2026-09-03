"""Read-only PAPER acceptance checker.

This module does not send orders, does not modify configuration and does not
issue any network call.  It inspects an intent ledger, an event archive and a
runtime log directory to decide whether the system is ready for a PAPER trial.
The checker can never emit ``READY_FOR_LIVE``; live authorisation requires an
external, human-signed approval step outside this module.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from event_replayer import verify_manifest
from intent_ledger import TERMINAL_INTENT_STATES


# Same definition of "finished" as the ledger's state machine, plus the US
# spelling that some broker payloads use.  SUBMITTED / PARTIAL / FILLED /
# EXIT_* are open positions or in-flight orders and never count as terminal.
TERMINAL_STATES = set(TERMINAL_INTENT_STATES) | {"CANCELED"}
PENDING_ACK = "PENDING_BROKER_ACK"
READY = "READY_FOR_PAPER_TRIAL"
NOT_READY = "NOT_READY_FOR_PAPER"
# An intent that is still non-terminal this long after creation (as of the
# cutoff) is a hanging intent; a non-RESERVED intent without a broker ack this
# long after creation is a stuck acknowledgement.  Both block PAPER acceptance.
DEFAULT_HANGING_GRACE_S = 24 * 3600.0
DEFAULT_ACK_GRACE_S = 3600.0


def _require_aware(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("cutoff must be a datetime")
    if value.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    return value.astimezone(timezone.utc)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2, default=str),
                   encoding="utf-8")
    os.replace(tmp, path)


class PaperAcceptanceChecker:
    """Fail-closed PAPER acceptance evaluator.

    ``strict`` (default True) treats any UNKNOWN result as blocking.  The
    checker only opens files it is told to; there is no side-effect on the
    ledger, archive or log directory.
    """

    read_only = True
    may_submit_orders = False

    def __init__(
        self,
        intent_ledger_path: str | Path,
        event_archive_root: str | Path,
        runtime_log_dir: str | Path,
        cutoff_utc: datetime,
        min_observation_days: int,
        required_events: Sequence[str],
        *,
        strict: bool = True,
        hanging_grace_s: float = DEFAULT_HANGING_GRACE_S,
        ack_grace_s: float = DEFAULT_ACK_GRACE_S,
    ) -> None:
        self.intent_ledger_path = Path(intent_ledger_path)
        self.event_archive_root = Path(event_archive_root)
        self.runtime_log_dir = Path(runtime_log_dir)
        self.cutoff_utc = _require_aware(cutoff_utc)
        if int(min_observation_days) < 0:
            raise ValueError("min_observation_days must be >= 0")
        self.min_observation_days = int(min_observation_days)
        self.required_events = tuple(str(e) for e in required_events)
        self.strict = bool(strict)
        if float(hanging_grace_s) < 0 or float(ack_grace_s) < 0:
            raise ValueError("grace periods must be >= 0")
        self.hanging_grace_s = float(hanging_grace_s)
        self.ack_grace_s = float(ack_grace_s)

    def check(self) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = [
            self._check_ledger_observation(),
            self._check_event_archive(),
            self._check_runtime_log_freshness(),
            self._check_no_persistent_upstream_block(),
        ]
        overall = READY
        for entry in checks:
            status = entry["status"]
            if status == "FAIL":
                overall = NOT_READY
                break
            if status == "UNKNOWN" and self.strict:
                overall = NOT_READY
                break
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "cutoff_utc": self.cutoff_utc.isoformat(),
            "min_observation_days": self.min_observation_days,
            "required_events": list(self.required_events),
            "strict": self.strict,
            "checks": checks,
            "overall": overall,
            "read_only": True,
            "may_submit_orders": False,
        }

    def write_report(self, path: str | Path) -> Path:
        report = self.check()
        _atomic_write_json(Path(path), report)
        return Path(path)

    # ------------------------------------------------------------------
    # Individual checks

    def _ro_conn(self) -> sqlite3.Connection:
        uri = f"file:{self.intent_ledger_path.resolve()}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=15.0)

    def _check_ledger_observation(self) -> Dict[str, Any]:
        if not self.intent_ledger_path.exists():
            return {"name": "ledger_observation",
                    "status": "FAIL",
                    "evidence": {"reason": "ledger_path_missing",
                                 "path": str(self.intent_ledger_path)}}
        cutoff_epoch = self.cutoff_utc.timestamp()
        hanging_before = cutoff_epoch - self.hanging_grace_s
        ack_before = cutoff_epoch - self.ack_grace_s
        try:
            with self._ro_conn() as conn:
                conn.row_factory = sqlite3.Row
                columns = {
                    str(r["name"]) for r in conn.execute(
                        "PRAGMA table_info(order_intents)").fetchall()
                }
                if not columns:
                    return {"name": "ledger_observation",
                            "status": "FAIL",
                            "evidence": {"reason": "no_order_intents_table"}}
                # Only rows that exist at the cutoff count, and activity after
                # the cutoff is clamped so it cannot inflate the span.
                row = conn.execute(
                    "SELECT MIN(created_epoch) AS start,"
                    " MAX(MIN(updated_epoch, ?)) AS end, COUNT(*) AS total"
                    " FROM order_intents WHERE created_epoch<=?",
                    (cutoff_epoch, cutoff_epoch)
                ).fetchone()
                if row is None or row["total"] == 0:
                    return {"name": "ledger_observation",
                            "status": "UNKNOWN",
                            "evidence": {"reason": "no_intents_before_cutoff"}}
                start_epoch = float(row["start"])
                end_epoch = float(row["end"])
                span_days = (end_epoch - start_epoch) / 86400.0
                terminal = sorted(TERMINAL_STATES)
                marks = ",".join("?" * len(terminal))
                hanging_rows = conn.execute(
                    "SELECT intent_id, state, created_epoch FROM order_intents"
                    f" WHERE state NOT IN ({marks}) AND created_epoch<=?"
                    " ORDER BY created_epoch",
                    (*terminal, hanging_before)
                ).fetchall()
                has_ack_column = "broker_ack_state" in columns
                pending_ack_rows = []
                if has_ack_column:
                    pending_ack_rows = conn.execute(
                        "SELECT intent_id, state, created_epoch FROM order_intents"
                        " WHERE broker_ack_state=? AND state!='RESERVED'"
                        " AND created_epoch<=? ORDER BY created_epoch",
                        (PENDING_ACK, ack_before)
                    ).fetchall()
        except sqlite3.DatabaseError as exc:
            return {"name": "ledger_observation",
                    "status": "FAIL",
                    "evidence": {"reason": "sqlite_error",
                                 "detail": str(exc)}}

        def _describe(rows) -> List[Dict[str, Any]]:
            return [{"intent_id": r["intent_id"], "state": r["state"],
                     "created_utc": datetime.fromtimestamp(
                         float(r["created_epoch"]), tz=timezone.utc).isoformat()}
                    for r in rows[:20]]

        evidence = {
            "start_utc": datetime.fromtimestamp(start_epoch, tz=timezone.utc).isoformat(),
            "end_utc": datetime.fromtimestamp(end_epoch, tz=timezone.utc).isoformat(),
            "observation_days": round(span_days, 3),
            "hanging_intents": len(hanging_rows),
            "pending_broker_ack_intents": len(pending_ack_rows),
            "total_intents_before_cutoff": int(row["total"]),
            "hanging_grace_s": self.hanging_grace_s,
            "ack_grace_s": self.ack_grace_s,
        }
        if span_days < float(self.min_observation_days):
            return {"name": "ledger_observation", "status": "FAIL",
                    "evidence": {**evidence,
                                 "reason": "insufficient_observation_days",
                                 "min_observation_days":
                                     self.min_observation_days}}
        if hanging_rows:
            return {"name": "ledger_observation", "status": "FAIL",
                    "evidence": {**evidence,
                                 "reason": "hanging_intents_before_cutoff",
                                 "hanging": _describe(hanging_rows)}}
        if not has_ack_column:
            return {"name": "ledger_observation", "status": "UNKNOWN",
                    "evidence": {**evidence,
                                 "reason": "no_broker_ack_state_column"}}
        if pending_ack_rows:
            return {"name": "ledger_observation", "status": "FAIL",
                    "evidence": {**evidence,
                                 "reason": "pending_broker_ack_before_cutoff",
                                 "pending_broker_ack":
                                     _describe(pending_ack_rows)}}
        return {"name": "ledger_observation", "status": "PASS",
                "evidence": evidence}

    def _check_event_archive(self) -> Dict[str, Any]:
        if not self.event_archive_root.exists():
            return {"name": "event_archive",
                    "status": "FAIL",
                    "evidence": {"reason": "archive_root_missing",
                                 "path": str(self.event_archive_root)}}
        if not self.required_events:
            return {"name": "event_archive",
                    "status": "UNKNOWN",
                    "evidence": {"reason": "no_required_events_configured"}}
        details: List[Dict[str, Any]] = []
        overall_status = "PASS"
        for event_id in self.required_events:
            event_root = self.event_archive_root / _safe_name(event_id)
            if not event_root.exists():
                details.append({"event_id": event_id,
                                "status": "MISSING"})
                overall_status = "FAIL"
                continue
            symbol_dirs = [p for p in event_root.iterdir() if p.is_dir()]
            if not symbol_dirs:
                details.append({"event_id": event_id,
                                "status": "NO_SYMBOL_DATA"})
                overall_status = "FAIL"
                continue
            for symbol_dir in symbol_dirs:
                report = verify_manifest(symbol_dir)
                details.append({"event_id": event_id,
                                "symbol": symbol_dir.name,
                                "manifest_status": report["status"],
                                "files_checked": report["files_checked"],
                                "mismatches": report["mismatches"]})
                if report["status"] != "OK":
                    overall_status = "FAIL"
        return {"name": "event_archive", "status": overall_status,
                "evidence": {"details": details}}

    def _check_runtime_log_freshness(self) -> Dict[str, Any]:
        if not self.runtime_log_dir.exists():
            return {"name": "runtime_log_freshness",
                    "status": "FAIL",
                    "evidence": {"reason": "runtime_log_dir_missing",
                                 "path": str(self.runtime_log_dir)}}
        latest_mtime: Optional[float] = None
        for path in self.runtime_log_dir.rglob("*"):
            if not path.is_file():
                continue
            m = path.stat().st_mtime
            if latest_mtime is None or m > latest_mtime:
                latest_mtime = m
        if latest_mtime is None:
            return {"name": "runtime_log_freshness",
                    "status": "UNKNOWN",
                    "evidence": {"reason": "no_files_in_runtime_log_dir"}}
        cutoff_epoch = self.cutoff_utc.timestamp()
        evidence = {
            "latest_mtime_utc": datetime.fromtimestamp(
                latest_mtime, tz=timezone.utc).isoformat(),
            "cutoff_utc": self.cutoff_utc.isoformat(),
        }
        if latest_mtime > cutoff_epoch:
            return {"name": "runtime_log_freshness",
                    "status": "FAIL",
                    "evidence": {**evidence,
                                 "reason": "runtime_log_newer_than_cutoff"}}
        return {"name": "runtime_log_freshness", "status": "PASS",
                "evidence": evidence}

    def _check_no_persistent_upstream_block(self) -> Dict[str, Any]:
        """Look for BLOCKED_BY_UPSTREAM rows that never cleared before cutoff."""
        if not self.intent_ledger_path.exists():
            return {"name": "upstream_block_cleared",
                    "status": "UNKNOWN",
                    "evidence": {"reason": "ledger_path_missing"}}
        try:
            with self._ro_conn() as conn:
                conn.row_factory = sqlite3.Row
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='upstream_states'"
                ).fetchone()
                if not exists:
                    return {"name": "upstream_block_cleared",
                            "status": "UNKNOWN",
                            "evidence": {"reason": "no_upstream_states_table"}}
                cutoff_epoch = self.cutoff_utc.timestamp()
                rows = conn.execute(
                    "SELECT venue,product_group,status,reason,updated_epoch"
                    " FROM upstream_states WHERE status='BLOCKED_BY_UPSTREAM'"
                    " AND updated_epoch<=?", (cutoff_epoch,)
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            return {"name": "upstream_block_cleared",
                    "status": "FAIL",
                    "evidence": {"reason": "sqlite_error", "detail": str(exc)}}
        blocked: List[Dict[str, Any]] = []
        for row in rows:
            blocked.append({
                "venue": row["venue"],
                "product_group": row["product_group"],
                "reason": row["reason"],
                "updated_utc": datetime.fromtimestamp(
                    float(row["updated_epoch"]), tz=timezone.utc).isoformat(),
            })
        if blocked:
            return {"name": "upstream_block_cleared",
                    "status": "FAIL",
                    "evidence": {"blocked": blocked}}
        return {"name": "upstream_block_cleared", "status": "PASS",
                "evidence": {"blocked": []}}


def _safe_name(value: str) -> str:
    import re
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return cleaned.strip("._") or "unknown"
