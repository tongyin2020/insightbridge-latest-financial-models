"""Broker-confirmed position lifecycle and product-specific hard time caps.

No alpha thresholds live here.  The monitor consumes explicit safety facts from
upstream modules and guarantees that a hard cap cannot be softened by a score.
All initial caps are PAPER-ONLY hypotheses until causal minute-data calibration.

This monitor is the SINGLE SOURCE OF TRUTH for the hard hold cap.  Other exit
engines (e.g. eventalpha_core.advanced.escape_engine) must receive the cap
verdict from here via an explicit ``hard_cap_breached`` flag instead of keeping
their own independent cap clocks, so the two can never drift apart.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


PROVISIONAL_PAPER_CAP_SECONDS = {
    "CRYPTO_SPOT": 30 * 60,
    "CRYPTO_FUT": 30 * 60,
    "FX": 35 * 60,
    "INDEX": 30 * 60,
    "COMMODITY": 35 * 60,
    "TREASURY": 30 * 60,
    "RATES": 30 * 60,
}


@dataclass
class PositionState:
    client_ref: str
    symbol: str
    asset_class: str
    side: str
    filled_quantity: float
    remaining_quantity: float
    entry_price: float
    broker_fill_time: datetime
    state: str = "OPEN"
    exit_reason: str = ""
    exit_submitted_at: Optional[datetime] = None
    cumulative_exit_quantity: float = 0.0


@dataclass(frozen=True)
class ExitDecision:
    action: str
    reason: str
    elapsed_seconds: float
    remaining_quantity: float


class PositionLifecycleMonitor:
    def __init__(self, cap_seconds: Optional[Dict[str, int]] = None,
                 persist_path: Optional[str] = None):
        self.cap_seconds = dict(PROVISIONAL_PAPER_CAP_SECONDS)
        if cap_seconds:
            self.cap_seconds.update(cap_seconds)
        self.positions: Dict[str, PositionState] = {}
        # Optional SQLite persistence: without it the position clock lived only
        # in memory, so a process crash/restart lost every open position's
        # elapsed time and let it outlive the hard hold cap.  With a path set,
        # every state mutation is written through and restored on startup.
        self.persist_path = str(Path(persist_path)) if persist_path else None
        if self.persist_path:
            self._init_db()
            self.restore()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.persist_path, timeout=15.0)
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS position_states (
                    client_ref TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    side TEXT NOT NULL,
                    filled_quantity REAL NOT NULL,
                    remaining_quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    broker_fill_time TEXT NOT NULL,
                    state TEXT NOT NULL,
                    exit_reason TEXT NOT NULL,
                    exit_submitted_at TEXT,
                    cumulative_exit_quantity REAL NOT NULL,
                    updated_epoch REAL NOT NULL
                )""")

    @staticmethod
    def _to_iso(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value is not None else None

    def _persist(self, pos: PositionState) -> None:
        if not self.persist_path:
            return
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO position_states(
                    client_ref, symbol, asset_class, side, filled_quantity,
                    remaining_quantity, entry_price, broker_fill_time, state,
                    exit_reason, exit_submitted_at, cumulative_exit_quantity,
                    updated_epoch)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(client_ref) DO UPDATE SET
                    symbol=excluded.symbol,
                    asset_class=excluded.asset_class,
                    side=excluded.side,
                    filled_quantity=excluded.filled_quantity,
                    remaining_quantity=excluded.remaining_quantity,
                    entry_price=excluded.entry_price,
                    broker_fill_time=excluded.broker_fill_time,
                    state=excluded.state,
                    exit_reason=excluded.exit_reason,
                    exit_submitted_at=excluded.exit_submitted_at,
                    cumulative_exit_quantity=excluded.cumulative_exit_quantity,
                    updated_epoch=excluded.updated_epoch
                """, (pos.client_ref, pos.symbol, pos.asset_class, pos.side,
                      pos.filled_quantity, pos.remaining_quantity,
                      pos.entry_price, self._to_iso(pos.broker_fill_time),
                      pos.state, pos.exit_reason,
                      self._to_iso(pos.exit_submitted_at),
                      pos.cumulative_exit_quantity, time.time()))

    def restore(self) -> int:
        """Reload persisted position states (e.g. after a process restart).

        The broker fill time is preserved verbatim, so the hard-cap clock keeps
        running across the crash instead of restarting from zero.  Returns the
        number of positions restored.
        """
        if not self.persist_path:
            return 0
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM position_states").fetchall()
        restored = 0
        for row in rows:
            submitted_raw = row["exit_submitted_at"]
            self.positions[row["client_ref"]] = PositionState(
                client_ref=row["client_ref"],
                symbol=row["symbol"],
                asset_class=row["asset_class"],
                side=row["side"],
                filled_quantity=float(row["filled_quantity"]),
                remaining_quantity=float(row["remaining_quantity"]),
                entry_price=float(row["entry_price"]),
                broker_fill_time=datetime.fromisoformat(row["broker_fill_time"]),
                state=row["state"],
                exit_reason=row["exit_reason"],
                exit_submitted_at=(datetime.fromisoformat(submitted_raw)
                                   if submitted_raw else None),
                cumulative_exit_quantity=float(row["cumulative_exit_quantity"]))
            restored += 1
        return restored

    def register_broker_fill(self, client_ref: str, symbol: str, asset_class: str,
                             side: str, filled_quantity: float, entry_price: float,
                             fill_time: datetime) -> PositionState:
        if filled_quantity <= 0 or entry_price <= 0:
            raise ValueError("broker-confirmed quantity and entry price must be positive")
        if fill_time.tzinfo is None:
            raise ValueError("fill_time must be timezone-aware")
        if asset_class not in self.cap_seconds:
            raise ValueError(f"no hard cap configured for {asset_class}")
        pos = PositionState(
            client_ref=client_ref, symbol=symbol, asset_class=asset_class,
            side=side, filled_quantity=float(filled_quantity),
            remaining_quantity=float(filled_quantity),
            entry_price=float(entry_price), broker_fill_time=fill_time)
        self.positions[client_ref] = pos
        self._persist(pos)
        return pos

    def upsert_broker_fill(self, client_ref: str, symbol: str, asset_class: str,
                           side: str, cumulative_filled_quantity: float,
                           average_fill_price: float,
                           fill_time: datetime) -> PositionState:
        """Register first fill or update cumulative exposure without resetting time."""
        existing = self.positions.get(client_ref)
        if existing is None:
            return self.register_broker_fill(
                client_ref, symbol, asset_class, side,
                cumulative_filled_quantity, average_fill_price, fill_time)
        cumulative = float(cumulative_filled_quantity)
        if cumulative < existing.filled_quantity:
            raise ValueError("cumulative filled quantity cannot decrease")
        if average_fill_price <= 0:
            raise ValueError("average fill price must be positive")
        existing.filled_quantity = cumulative
        # remaining = filled - already-exited.  Never resurrect quantity that a
        # confirmed partial exit has already closed (the old
        # ``max(remaining, cumulative)`` did exactly that).
        existing.remaining_quantity = max(
            0.0,
            cumulative - existing.cumulative_exit_quantity)
        existing.entry_price = float(average_fill_price)
        self._persist(existing)
        return existing

    def evaluate(self, client_ref: str, now: Optional[datetime] = None,
                 protective_stop_breached: bool = False,
                 account_flatten_required: bool = False,
                 data_stale: bool = False,
                 book_desync: bool = False,
                 fakeout_confirmed: bool = False,
                 reversal_confirmed: bool = False,
                 liquidity_collapse: bool = False) -> ExitDecision:
        pos = self.positions[client_ref]
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        elapsed = max(0.0, (current - pos.broker_fill_time).total_seconds())

        if pos.state == "CLOSED":
            return ExitDecision("NONE", "already_closed", elapsed, 0.0)
        if pos.state in {"EXIT_SUBMITTED", "EXIT_PARTIAL"}:
            return ExitDecision("MONITOR_EXIT", pos.exit_reason, elapsed,
                                pos.remaining_quantity)

        ordered_reasons = (
            (protective_stop_breached, "protective_stop"),
            (account_flatten_required, "account_flatten"),
            (data_stale, "market_data_stale"),
            (book_desync, "book_desync"),
            (fakeout_confirmed, "fakeout_confirmed"),
            (liquidity_collapse, "liquidity_collapse"),
            (reversal_confirmed, "reversal_confirmed"),
        )
        for condition, reason in ordered_reasons:
            if condition:
                return ExitDecision("EXIT", reason, elapsed,
                                    pos.remaining_quantity)

        if elapsed >= self.cap_seconds[pos.asset_class]:
            return ExitDecision("EXIT", "hard_hold_cap", elapsed,
                                pos.remaining_quantity)
        return ExitDecision("HOLD", "within_hard_cap", elapsed,
                            pos.remaining_quantity)

    def mark_exit_submitted(self, client_ref: str, reason: str,
                            submitted_at: datetime) -> PositionState:
        if submitted_at.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")
        pos = self.positions[client_ref]
        if pos.state == "CLOSED":
            raise ValueError("cannot submit an exit for a closed position")
        pos.state = "EXIT_SUBMITTED"
        pos.exit_reason = reason
        pos.exit_submitted_at = submitted_at
        self._persist(pos)
        return pos

    def confirm_exit_fill(self, client_ref: str, cumulative_exit_quantity: float,
                          broker_position_quantity: float) -> PositionState:
        """Close only when broker confirms both full exit and zero position."""
        pos = self.positions[client_ref]
        exited = max(0.0, float(cumulative_exit_quantity))
        # Cumulative exit reports must be monotone; keep the max so a stale
        # or out-of-order broker report cannot resurrect closed quantity.
        pos.cumulative_exit_quantity = max(pos.cumulative_exit_quantity, exited)
        pos.remaining_quantity = max(
            0.0, pos.filled_quantity - pos.cumulative_exit_quantity)
        if pos.remaining_quantity == 0.0 and abs(float(broker_position_quantity)) == 0.0:
            pos.state = "CLOSED"
        else:
            pos.state = "EXIT_PARTIAL"
        self._persist(pos)
        return pos
