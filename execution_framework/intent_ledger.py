"""Durable account-level intent and execution-authority controls.

This module is deliberately independent from signal generation.  It provides:

* deterministic intent IDs for the same economic decision;
* SQLite uniqueness across processes and restarts;
* an account-level leader lease so one process owns order submission;
* a fencing token on that lease so a paused ex-leader cannot submit after
  another process has taken over (the classic split-brain hole);
* an annual cap on independent traded events, with no minimum quota.

The ledger never submits an order.  Callers must reserve before broker submission,
then advance state only from broker-confirmed facts.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


TERMINAL_INTENT_STATES = {"CANCELLED", "REJECTED", "CLOSED"}
VALID_INTENT_STATES = {
    "RESERVED", "SUBMITTED", "PARTIAL", "FILLED", "EXIT_SUBMITTED",
    "EXIT_PARTIAL", "CANCELLED", "REJECTED", "CLOSED",
}
# Broker acknowledgement is tracked separately from the intent state machine:
# ``state`` follows what we did, ``broker_ack_state`` follows what the broker
# confirmed.  It only carries the PAPER/LIVE channel of the ack, never a
# permission to trade.
VALID_BROKER_ACK_STATES = {
    "PENDING_BROKER_ACK", "ACKED_LIVE", "ACKED_PAPER", "REJECTED",
    "CANCEL_ACKED", "CANCEL_REJECTED",
}

# Explicit state-transition table.  Without it, regressions such as
# FILLED -> SUBMITTED were silently accepted.  Same-state updates are always
# allowed (idempotent broker status replays); terminal states never leave.
# RESERVED may jump straight to PARTIAL/FILLED because a fast IOC fill can
# arrive before (or without) an intermediate Submitted status callback.
INTENT_TRANSITIONS = {
    "RESERVED": {"SUBMITTED", "PARTIAL", "FILLED", "REJECTED", "CANCELLED"},
    "SUBMITTED": {"PARTIAL", "FILLED", "REJECTED", "CANCELLED"},
    "PARTIAL": {"FILLED", "CANCELLED", "CLOSED"},
    "FILLED": {"EXIT_SUBMITTED", "EXIT_PARTIAL", "CLOSED"},
    # Exit leg cancelled while the position is still open -> back to FILLED.
    "EXIT_SUBMITTED": {"EXIT_PARTIAL", "CLOSED", "FILLED"},
    "EXIT_PARTIAL": {"EXIT_SUBMITTED", "CLOSED"},
    "CANCELLED": set(),
    "REJECTED": set(),
    "CLOSED": set(),
}


@dataclass(frozen=True)
class IntentReservation:
    accepted: bool
    intent_id: str
    reason: str
    state: str


@dataclass(frozen=True)
class EventReservation:
    accepted: bool
    event_id: str
    reason: str
    counted_events: int
    annual_limit: int


def deterministic_intent_id(account_id: str, event_id: str, symbol: str,
                            side: str, strategy_version: str) -> str:
    payload = {
        "account_id": account_id.strip(),
        "event_id": event_id.strip(),
        "side": side.strip().upper(),
        "strategy_version": strategy_version.strip(),
        "symbol": symbol.strip().upper().replace("/", ""),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class IntentLedger:
    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path))
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        # Concurrent processes may race the first-time WAL/DDL setup; a locked
        # database during init is transient, so retry briefly instead of
        # crashing a worker that started at the same instant as the leader.
        last_exc: Optional[sqlite3.OperationalError] = None
        for attempt in range(5):
            try:
                self._init_db_once()
                return
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                last_exc = exc
                time.sleep(0.2 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    def _init_db_once(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_leases (
                    account_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    expires_epoch REAL NOT NULL,
                    updated_epoch REAL NOT NULL
                )""")
            # Fencing-token migration for databases created before the column
            # existed (same ALTER-TABLE idiom as trade_journal.py).
            try:
                conn.execute(
                    "ALTER TABLE execution_leases "
                    "ADD COLUMN fencing_epoch INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise  # e.g. locked: let the outer retry handle it
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_budget (
                    account_id TEXT NOT NULL,
                    event_year INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_epoch REAL NOT NULL,
                    updated_epoch REAL NOT NULL,
                    PRIMARY KEY (account_id, event_year, event_id)
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS order_intents (
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
                    updated_epoch REAL NOT NULL,
                    UNIQUE(account_id, event_id, symbol, side, strategy_version)
                )""")
            columns = {
                str(row["name"]) for row in
                conn.execute("PRAGMA table_info(order_intents)").fetchall()
            }
            for name, ddl in (
                ("algo_version", "TEXT NOT NULL DEFAULT 'UNSPECIFIED'"),
                ("operator_id", "TEXT NOT NULL DEFAULT 'SYSTEM_UNSPECIFIED'"),
                ("broker_ack_state",
                 "TEXT NOT NULL DEFAULT 'PENDING_BROKER_ACK'"),
                ("broker_ack_payload", "TEXT"),
            ):
                if name not in columns:
                    conn.execute(
                        f"ALTER TABLE order_intents ADD COLUMN {name} {ddl}")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_intents_state "
                "ON order_intents(account_id, state)")

    def acquire_lease(self, account_id: str, owner_id: str, ttl_s: float = 30.0,
                      now_epoch: Optional[float] = None) -> bool:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        now = time.time() if now_epoch is None else float(now_epoch)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT owner_id, expires_epoch FROM execution_leases WHERE account_id=?",
                (account_id,)).fetchone()
            if row and row["owner_id"] != owner_id and float(row["expires_epoch"]) > now:
                conn.rollback()
                return False
            conn.execute("""
                INSERT INTO execution_leases(
                    account_id, owner_id, expires_epoch, updated_epoch, fencing_epoch)
                VALUES(?,?,?,?,1)
                ON CONFLICT(account_id) DO UPDATE SET
                    owner_id=excluded.owner_id,
                    expires_epoch=excluded.expires_epoch,
                    updated_epoch=excluded.updated_epoch,
                    fencing_epoch=execution_leases.fencing_epoch+1
                """, (account_id, owner_id, now + ttl_s, now))
            conn.commit()
            return True

    def renew_lease(self, account_id: str, owner_id: str, ttl_s: float = 30.0,
                    now_epoch: Optional[float] = None) -> bool:
        now = time.time() if now_epoch is None else float(now_epoch)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("""
                UPDATE execution_leases SET expires_epoch=?, updated_epoch=?
                WHERE account_id=? AND owner_id=? AND expires_epoch>?
                """, (now + ttl_s, now, account_id, owner_id, now))
            conn.commit()
            return cur.rowcount == 1

    def release_lease(self, account_id: str, owner_id: str) -> bool:
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "DELETE FROM execution_leases WHERE account_id=? AND owner_id=?",
                (account_id, owner_id))
            conn.commit()
            return cur.rowcount == 1

    def current_fencing_token(self, account_id: str,
                              owner_id: str) -> Optional[int]:
        """Return the fencing epoch of the lease currently held by owner_id.

        None when this owner does not hold the lease.  Callers should read the
        token once right after a successful ``acquire_lease`` and present it on
        every order submission via ``check_fencing``.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT fencing_epoch FROM execution_leases "
                "WHERE account_id=? AND owner_id=?",
                (account_id, owner_id)).fetchone()
            return int(row["fencing_epoch"]) if row else None

    def check_fencing(self, account_id: str, owner_id: str, epoch: int,
                      now_epoch: Optional[float] = None) -> bool:
        """True only if owner_id still holds an unexpired lease with this epoch.

        The epoch is bumped on every ``acquire_lease`` (renewals keep it), so a
        process that paused past its TTL and woke up after a takeover fails this
        check even if it still believes itself leader.  Runs inside BEGIN
        IMMEDIATE so the read is serialized against concurrent takeovers.
        """
        now = time.time() if now_epoch is None else float(now_epoch)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT owner_id, expires_epoch, fencing_epoch "
                "FROM execution_leases WHERE account_id=?",
                (account_id,)).fetchone()
            conn.commit()
            if row is None:
                return False
            return (row["owner_id"] == owner_id
                    and float(row["expires_epoch"]) > now
                    and int(row["fencing_epoch"]) == int(epoch))

    def reserve_event(self, account_id: str, event_id: str, event_year: int,
                      annual_limit: int = 15,
                      now_epoch: Optional[float] = None) -> EventReservation:
        """Reserve one independent event.

        RESERVED and TRADED events both consume capacity, preventing concurrent
        over-admission.  A caller may release a RESERVED event that never traded.
        """
        if annual_limit < 0:
            raise ValueError("annual_limit cannot be negative")
        now = time.time() if now_epoch is None else float(now_epoch)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("""
                SELECT status FROM event_budget
                WHERE account_id=? AND event_year=? AND event_id=?
                """, (account_id, event_year, event_id)).fetchone()
            if existing:
                count = self._event_count_conn(conn, account_id, event_year)
                conn.commit()
                return EventReservation(True, event_id, "event_already_reserved",
                                        count, annual_limit)
            count = self._event_count_conn(conn, account_id, event_year)
            if count >= annual_limit:
                conn.rollback()
                return EventReservation(False, event_id, "annual_event_limit_reached",
                                        count, annual_limit)
            conn.execute("""
                INSERT INTO event_budget
                    (account_id,event_year,event_id,status,created_epoch,updated_epoch)
                VALUES(?,?,?,'RESERVED',?,?)
                """, (account_id, event_year, event_id, now, now))
            conn.commit()
            return EventReservation(True, event_id, "reserved",
                                    count + 1, annual_limit)

    @staticmethod
    def _event_count_conn(conn: sqlite3.Connection, account_id: str,
                          event_year: int) -> int:
        row = conn.execute("""
            SELECT COUNT(*) AS n FROM event_budget
            WHERE account_id=? AND event_year=? AND status IN ('RESERVED','TRADED')
            """, (account_id, event_year)).fetchone()
        return int(row["n"])

    def mark_event_traded(self, account_id: str, event_id: str,
                          event_year: int, now_epoch: Optional[float] = None) -> bool:
        now = time.time() if now_epoch is None else float(now_epoch)
        with self._conn() as conn:
            cur = conn.execute("""
                UPDATE event_budget SET status='TRADED', updated_epoch=?
                WHERE account_id=? AND event_year=? AND event_id=?
                  AND status IN ('RESERVED','TRADED')
                """, (now, account_id, event_year, event_id))
            return cur.rowcount == 1

    def release_untraded_event(self, account_id: str, event_id: str,
                               event_year: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("""
                DELETE FROM event_budget
                WHERE account_id=? AND event_year=? AND event_id=? AND status='RESERVED'
                """, (account_id, event_year, event_id))
            return cur.rowcount == 1

    def reserve_intent(self, account_id: str, event_id: str, event_year: int,
                       symbol: str, side: str,
                       strategy_version: str,
                       max_intents_per_event: int = 1,
                       now_epoch: Optional[float] = None,
                       operator_id: str = "SYSTEM_UNSPECIFIED",
                       algo_version: Optional[str] = None) -> IntentReservation:
        if max_intents_per_event <= 0:
            raise ValueError("max_intents_per_event must be positive")
        # operator/algo are audit provenance only: they are deliberately not
        # part of the deterministic ID so they cannot bypass deduplication.
        intent_id = deterministic_intent_id(
            account_id, event_id, symbol, side, strategy_version)
        operator_id = str(operator_id or "SYSTEM_UNSPECIFIED")
        algo_version = str(algo_version or strategy_version)
        now = time.time() if now_epoch is None else float(now_epoch)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT state FROM order_intents WHERE intent_id=?", (intent_id,)
            ).fetchone()
            if row:
                conn.commit()
                return IntentReservation(
                    False, intent_id, "duplicate_economic_intent", row["state"])
            active = conn.execute("""
                SELECT COUNT(*) AS n FROM order_intents
                WHERE account_id=? AND event_id=? AND strategy_version=?
                  AND state NOT IN ('REJECTED','CANCELLED')
                """, (account_id, event_id, strategy_version)).fetchone()
            if int(active["n"]) >= max_intents_per_event:
                conn.rollback()
                return IntentReservation(
                    False, intent_id, "event_product_limit_reached", "BLOCKED")
            conn.execute("""
                INSERT INTO order_intents(
                    intent_id,account_id,event_year,event_id,symbol,side,
                    strategy_version,algo_version,operator_id,state,
                    created_epoch,updated_epoch)
                VALUES(?,?,?,?,?,?,?,?,?,'RESERVED',?,?)
                """, (intent_id, account_id, event_year, event_id,
                      symbol.upper().replace("/", ""), side.upper(),
                      strategy_version, algo_version, operator_id, now, now))
            conn.commit()
            return IntentReservation(True, intent_id, "reserved", "RESERVED")

    def advance_intent(self, intent_id: str, new_state: str,
                       broker_order_id: Optional[str] = None,
                       filled_quantity: Optional[float] = None,
                       now_epoch: Optional[float] = None) -> bool:
        if new_state not in VALID_INTENT_STATES:
            raise ValueError(f"invalid intent state: {new_state}")
        now = time.time() if now_epoch is None else float(now_epoch)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT state,filled_quantity FROM order_intents WHERE intent_id=?",
                (intent_id,)).fetchone()
            if row is None:
                conn.rollback()
                return False
            current = row["state"]
            if current in TERMINAL_INTENT_STATES and new_state != current:
                conn.rollback()
                return False
            if (new_state != current
                    and new_state not in INTENT_TRANSITIONS.get(current, set())):
                conn.rollback()
                return False
            quantity = (float(row["filled_quantity"])
                        if filled_quantity is None else float(filled_quantity))
            conn.execute("""
                UPDATE order_intents
                SET state=?, broker_order_id=COALESCE(?,broker_order_id),
                    filled_quantity=?, updated_epoch=?
                WHERE intent_id=?
                """, (new_state, broker_order_id, quantity, now, intent_id))
            conn.commit()
            return True

    def record_broker_ack(self, intent_id: str, ack_state: str,
                          payload_json: Optional[str] = None) -> bool:
        """Record a broker acknowledgement without mutating ``state``.

        ``ack_state`` must be one of :data:`VALID_BROKER_ACK_STATES`; anything
        else raises (fail closed).  ``updated_epoch`` is left untouched so the
        PAPER acceptance checker's hanging-intent logic keys off creation time
        and the state machine only.
        """
        if ack_state not in VALID_BROKER_ACK_STATES:
            raise ValueError(f"invalid broker_ack_state: {ack_state}")
        if payload_json is not None and not isinstance(payload_json, str):
            raise ValueError("payload_json must be a JSON string or None")
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE order_intents SET broker_ack_state=?,"
                " broker_ack_payload=COALESCE(?,broker_ack_payload)"
                " WHERE intent_id=?",
                (ack_state, payload_json, intent_id))
            conn.commit()
            return cur.rowcount == 1

    def get_intent(self, intent_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM order_intents WHERE intent_id=?", (intent_id,)
            ).fetchone()
            return dict(row) if row else None

    def event_status(self, account_id: str, event_id: str,
                     event_year: int) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT status FROM event_budget
                WHERE account_id=? AND event_year=? AND event_id=?
                """, (account_id, event_year, event_id)).fetchone()
            return str(row["status"]) if row else None
