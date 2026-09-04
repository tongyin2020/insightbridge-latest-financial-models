"""Persistent, fail-closed controls for bounded execution autonomy.

The controller is deliberately broker-agnostic.  It can authorize or block a
local action, persist control state, and produce cancellation *intents*, but it
never sends, changes, or cancels an order.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple


SYSTEM_OPERATOR = "SYSTEM_UNSPECIFIED"
ENABLED = "ENABLED"
DISABLED_REQUIRES_MANUAL_RESET = "DISABLED_REQUIRES_MANUAL_RESET"
BLOCKED_BY_UPSTREAM = "BLOCKED_BY_UPSTREAM"
UPSTREAM_CLEAR = "CLEAR"
UPSTREAM_UNKNOWN = "UNKNOWN"
RETRYABLE = "RETRYABLE"
MANUAL_REVIEW = "MANUAL_REVIEW"
FATAL = "FATAL"
REJECTION_CLASSES = {RETRYABLE, MANUAL_REVIEW, FATAL}


@dataclass(frozen=True)
class ControlDecision:
    allowed: bool
    status: str
    reason: str
    details: Dict[str, Any]


@dataclass(frozen=True)
class PreTradeLimits:
    """Explicit local limits.  Values are policy inputs, not calibrated values."""

    max_price_deviation_pct: Optional[float] = None
    max_order_value: Optional[float] = None
    max_quantity: Optional[float] = None
    max_messages: Optional[int] = None

    def missing(self) -> Tuple[str, ...]:
        return tuple(
            name for name, value in asdict(self).items() if value is None
        )


class BoundedAutonomyController:
    """SQLite-backed bounded-autonomy and local pre-trade controller.

    ``throttle_limits`` may use ``(account_id, event_family, strategy_path)``
    tuple keys.  A ``"*"`` component acts as an explicit wildcard.  There is no
    live default: if no matching limit exists, authorization fails closed.
    """

    def __init__(
        self,
        db_path: str,
        *,
        live_mode: bool = True,
        throttle_limits: Optional[Mapping[Any, int]] = None,
        throttle_limit: Optional[int] = None,
        pre_trade_limits: Optional[PreTradeLimits | Mapping[str, Any]] = None,
        audit_log_path: Optional[str] = None,
        algo_version: str = "UNSPECIFIED",
        account_id: Optional[str] = None,
        event_family: Optional[str] = None,
        strategy_path: Optional[str] = None,
        rejection_mapping: Optional[Mapping[str, str]] = None,
        trusted_upstream_sources: Optional[set[str]] = None,
    ) -> None:
        self.db_path = str(Path(db_path))
        self.live_mode = bool(live_mode)
        self.algo_version = str(algo_version or "UNSPECIFIED")
        self.audit_log_path = Path(audit_log_path) if audit_log_path else None
        self.default_scope = (account_id, event_family, strategy_path)
        if trusted_upstream_sources is None:
            self.trusted_upstream_sources: Optional[frozenset[str]] = None
        else:
            cleaned = {str(s).strip() for s in trusted_upstream_sources
                       if str(s).strip()}
            if not cleaned:
                raise ValueError(
                    "trusted_upstream_sources cannot be empty when provided")
            self.trusted_upstream_sources = frozenset(cleaned)
        self.throttle_limits: Dict[Tuple[str, str, str], int] = {}
        for raw_key, raw_value in (throttle_limits or {}).items():
            key = self._normalise_limit_key(raw_key)
            value = int(raw_value)
            if value <= 0:
                raise ValueError("throttle limits must be positive")
            self.throttle_limits[key] = value
        if throttle_limit is not None:
            value = int(throttle_limit)
            if value <= 0:
                raise ValueError("throttle_limit must be positive")
            default_key = tuple(x or "*" for x in self.default_scope)
            self.throttle_limits[default_key] = value
        if isinstance(pre_trade_limits, Mapping):
            pre_trade_limits = PreTradeLimits(**dict(pre_trade_limits))
        self.pre_trade_limits = pre_trade_limits or PreTradeLimits()
        self.rejection_mapping: Dict[str, str] = {}
        for code, category in (rejection_mapping or {}).items():
            self.set_rejection_mapping(code, category)
        self._init_db()

    @staticmethod
    def _normalise_limit_key(raw_key: Any) -> Tuple[str, str, str]:
        if isinstance(raw_key, tuple) and len(raw_key) == 3:
            return tuple(str(x) for x in raw_key)  # type: ignore[return-value]
        if isinstance(raw_key, str):
            parts = raw_key.split("|")
            if len(parts) == 3:
                return tuple(parts)  # type: ignore[return-value]
        raise ValueError("throttle limit key must be a 3-tuple or 'a|b|c'")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS autonomy_counters (
                    account_id TEXT NOT NULL,
                    event_family TEXT NOT NULL,
                    strategy_path TEXT NOT NULL,
                    action_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    updated_epoch REAL NOT NULL,
                    PRIMARY KEY(account_id,event_family,strategy_path)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS upstream_states (
                    venue TEXT NOT NULL,
                    product_group TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    operator_id TEXT NOT NULL,
                    updated_epoch REAL NOT NULL,
                    PRIMARY KEY(venue,product_group)
                )"""
            )
            # Idempotent migration for pre-existing databases without source.
            upstream_columns = {
                str(row["name"]) for row in conn.execute(
                    "PRAGMA table_info(upstream_states)").fetchall()
            }
            if "source" not in upstream_columns:
                conn.execute(
                    "ALTER TABLE upstream_states ADD COLUMN "
                    "source TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS kill_states (
                    account_id TEXT PRIMARY KEY,
                    killed INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    operator_id TEXT NOT NULL,
                    updated_epoch REAL NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS submission_counters (
                    account_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    product_group TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    updated_epoch REAL NOT NULL,
                    PRIMARY KEY(account_id,venue,product_group)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS control_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload_json TEXT NOT NULL,
                    created_epoch REAL NOT NULL
                )"""
            )

    def _limit_for(self, scope: Tuple[str, str, str]) -> Optional[int]:
        if scope in self.throttle_limits:
            return self.throttle_limits[scope]
        account_id, event_family, strategy_path = scope
        candidates = (
            (account_id, event_family, "*"),
            (account_id, "*", strategy_path),
            ("*", event_family, strategy_path),
            (account_id, "*", "*"),
            ("*", event_family, "*"),
            ("*", "*", strategy_path),
            ("*", "*", "*"),
        )
        for key in candidates:
            if key in self.throttle_limits:
                return self.throttle_limits[key]
        return None

    @staticmethod
    def _clean_scope(
        account_id: str, event_family: str, strategy_path: str
    ) -> Tuple[str, str, str]:
        scope = tuple(str(x).strip() for x in (account_id, event_family, strategy_path))
        if not all(scope):
            raise ValueError("account_id, event_family and strategy_path are required")
        return scope  # type: ignore[return-value]

    def authorize_autonomous_action(
        self,
        account_id: str,
        event_family: str,
        strategy_path: str,
        *,
        event_id: Optional[str] = None,
        operator_id: str = SYSTEM_OPERATOR,
    ) -> ControlDecision:
        """Atomically count one admitted action and disable at the configured cap."""
        scope = self._clean_scope(account_id, event_family, strategy_path)
        limit = self._limit_for(scope)
        if limit is None:
            reason = "missing_throttle_limit"
            return ControlDecision(
                not self.live_mode, "CONFIGURATION_MISSING", reason,
                {"scope": scope, "live_mode": self.live_mode},
            )
        now = time.time()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT action_count,status FROM autonomy_counters
                   WHERE account_id=? AND event_family=? AND strategy_path=?""",
                scope,
            ).fetchone()
            count = int(row["action_count"]) if row else 0
            status = str(row["status"]) if row else ENABLED
            if status == DISABLED_REQUIRES_MANUAL_RESET or count >= limit:
                conn.execute(
                    """INSERT INTO autonomy_counters
                       (account_id,event_family,strategy_path,action_count,status,updated_epoch)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(account_id,event_family,strategy_path) DO UPDATE SET
                         status=excluded.status,updated_epoch=excluded.updated_epoch""",
                    (*scope, count, DISABLED_REQUIRES_MANUAL_RESET, now),
                )
                conn.commit()
                return ControlDecision(
                    False, DISABLED_REQUIRES_MANUAL_RESET,
                    "manual_reset_required",
                    {"scope": scope, "action_count": count, "limit": limit},
                )
            count += 1
            status = (
                DISABLED_REQUIRES_MANUAL_RESET if count >= limit else ENABLED
            )
            conn.execute(
                """INSERT INTO autonomy_counters
                   (account_id,event_family,strategy_path,action_count,status,updated_epoch)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(account_id,event_family,strategy_path) DO UPDATE SET
                     action_count=excluded.action_count,status=excluded.status,
                     updated_epoch=excluded.updated_epoch""",
                (*scope, count, status, now),
            )
            conn.commit()
        if status == DISABLED_REQUIRES_MANUAL_RESET:
            self._audit(
                event_id=event_id, operator_id=operator_id,
                changed_by=operator_id, approved_by=None,
                change_nature="AUTONOMY_LIMIT_REACHED",
                details={"scope": scope, "action_count": count, "limit": limit},
            )
        return ControlDecision(
            True, status, "authorized",
            {"scope": scope, "action_count": count, "limit": limit},
        )

    # Compatibility-friendly aliases for callers that prefer record/check names.
    record_autonomous_action = authorize_autonomous_action

    def autonomy_status(
        self, account_id: str, event_family: str, strategy_path: str
    ) -> Dict[str, Any]:
        scope = self._clean_scope(account_id, event_family, strategy_path)
        with self._conn() as conn:
            row = conn.execute(
                """SELECT action_count,status,updated_epoch FROM autonomy_counters
                   WHERE account_id=? AND event_family=? AND strategy_path=?""",
                scope,
            ).fetchone()
        return {
            "account_id": scope[0],
            "event_family": scope[1],
            "strategy_path": scope[2],
            "action_count": int(row["action_count"]) if row else 0,
            "status": str(row["status"]) if row else ENABLED,
            "limit": self._limit_for(scope),
            "updated_epoch": float(row["updated_epoch"]) if row else None,
        }

    def manual_reset(
        self,
        operator_id: str,
        reason: str,
        account_id: Optional[str] = None,
        event_family: Optional[str] = None,
        strategy_path: Optional[str] = None,
        *,
        approved_by: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> bool:
        """Reset one disabled scope; an operator and reason are mandatory."""
        self._require_operator_reason(operator_id, reason)
        values = (
            account_id or self.default_scope[0],
            event_family or self.default_scope[1],
            strategy_path or self.default_scope[2],
        )
        if not all(values):
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT account_id,event_family,strategy_path
                       FROM autonomy_counters WHERE status=?""",
                    (DISABLED_REQUIRES_MANUAL_RESET,),
                ).fetchall()
            if len(rows) != 1:
                raise ValueError("manual_reset requires an unambiguous scope")
            values = tuple(str(rows[0][name]) for name in (
                "account_id", "event_family", "strategy_path"))
        scope = self._clean_scope(*values)  # type: ignore[arg-type]
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """UPDATE autonomy_counters
                   SET action_count=0,status=?,updated_epoch=?
                   WHERE account_id=? AND event_family=? AND strategy_path=?
                     AND status=?""",
                (ENABLED, time.time(), *scope, DISABLED_REQUIRES_MANUAL_RESET),
            )
            conn.commit()
        if cur.rowcount:
            self._audit(
                event_id=event_id, operator_id=operator_id,
                changed_by=operator_id, approved_by=approved_by,
                change_nature="MANUAL_AUTONOMY_RESET",
                details={"scope": scope, "reason": reason},
            )
        return cur.rowcount == 1

    def set_upstream_blocked(
        self,
        venue: str,
        product_group: str,
        reason: str,
        *,
        operator_id: str = SYSTEM_OPERATOR,
        approved_by: Optional[str] = None,
        event_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        if not str(reason).strip():
            raise ValueError("reason is required")
        self._set_upstream(
            venue, product_group, BLOCKED_BY_UPSTREAM, reason, operator_id,
            approved_by=approved_by, event_id=event_id, source=source,
        )

    # Short alias used by some orchestration code.
    block_upstream = set_upstream_blocked

    def clear_upstream(
        self,
        venue: str,
        product_group: str,
        operator_id: str,
        reason: str,
        *,
        approved_by: Optional[str] = None,
        event_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        self._require_operator_reason(operator_id, reason)
        self._set_upstream(
            venue, product_group, UPSTREAM_CLEAR, reason, operator_id,
            approved_by=approved_by, event_id=event_id, source=source,
        )

    def _set_upstream(
        self,
        venue: str,
        product_group: str,
        status: str,
        reason: str,
        operator_id: str,
        *,
        approved_by: Optional[str],
        event_id: Optional[str],
        source: Optional[str] = None,
    ) -> None:
        key = (str(venue).strip().upper(), str(product_group).strip().upper())
        if not all(key):
            raise ValueError("venue and product_group are required")
        source_value = str(source).strip() if source is not None else ""
        if self.trusted_upstream_sources is not None:
            if not source_value:
                raise ValueError(
                    "trusted_upstream_sources configured but no source supplied")
            if source_value not in self.trusted_upstream_sources:
                raise ValueError(
                    f"source not in trusted_upstream_sources: {source_value}")
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO upstream_states
                   (venue,product_group,status,reason,operator_id,source,updated_epoch)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(venue,product_group) DO UPDATE SET
                     status=excluded.status,reason=excluded.reason,
                     operator_id=excluded.operator_id,source=excluded.source,
                     updated_epoch=excluded.updated_epoch""",
                (*key, status, str(reason), str(operator_id),
                 source_value, now),
            )
        self._audit(
            event_id=event_id, operator_id=operator_id,
            changed_by=operator_id, approved_by=approved_by,
            change_nature=(
                "UPSTREAM_BLOCK_SET" if status == BLOCKED_BY_UPSTREAM
                else "UPSTREAM_BLOCK_CLEARED"
            ),
            details={"venue": key[0], "product_group": key[1],
                     "status": status, "reason": reason,
                     "source": source_value},
        )

    def query_upstream(self, venue: str, product_group: str) -> ControlDecision:
        key = (str(venue).strip().upper(), str(product_group).strip().upper())
        if not all(key):
            return ControlDecision(
                False, UPSTREAM_UNKNOWN, "invalid_upstream_key", {"key": key})
        with self._conn() as conn:
            row = conn.execute(
                """SELECT status,reason,operator_id,updated_epoch
                   FROM upstream_states WHERE venue=? AND product_group=?""",
                key,
            ).fetchone()
        if row is None:
            return ControlDecision(
                not self.live_mode, UPSTREAM_UNKNOWN, "unknown_upstream_state",
                {"venue": key[0], "product_group": key[1],
                 "live_mode": self.live_mode},
            )
        status = str(row["status"])
        return ControlDecision(
            status == UPSTREAM_CLEAR,
            status,
            str(row["reason"]),
            {"venue": key[0], "product_group": key[1],
             "updated_epoch": float(row["updated_epoch"])},
        )

    check_upstream = query_upstream

    def engage_kill(
        self,
        account_id: str,
        reason: str,
        *,
        operator_id: str = SYSTEM_OPERATOR,
        approved_by: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        if not str(reason).strip():
            raise ValueError("reason is required")
        self._set_kill(
            account_id, True, reason, operator_id, approved_by, event_id)

    def clear_kill(
        self,
        account_id: str,
        operator_id: str,
        reason: str,
        *,
        approved_by: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        self._require_operator_reason(operator_id, reason)
        self._set_kill(
            account_id, False, reason, operator_id, approved_by, event_id)

    def _set_kill(
        self,
        account_id: str,
        killed: bool,
        reason: str,
        operator_id: str,
        approved_by: Optional[str],
        event_id: Optional[str],
    ) -> None:
        account_id = str(account_id).strip()
        if not account_id:
            raise ValueError("account_id is required")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO kill_states
                   (account_id,killed,reason,operator_id,updated_epoch)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(account_id) DO UPDATE SET
                     killed=excluded.killed,reason=excluded.reason,
                     operator_id=excluded.operator_id,updated_epoch=excluded.updated_epoch""",
                (account_id, int(killed), reason, operator_id, time.time()),
            )
        self._audit(
            event_id=event_id, operator_id=operator_id,
            changed_by=operator_id, approved_by=approved_by,
            change_nature="LOCAL_KILL_ENGAGED" if killed else "LOCAL_KILL_CLEARED",
            details={"account_id": account_id, "reason": reason},
        )

    def kill_status(self, account_id: str) -> Dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT killed,reason,updated_epoch FROM kill_states
                   WHERE account_id=?""", (account_id,)
            ).fetchone()
        return {
            "account_id": account_id,
            "killed": bool(row["killed"]) if row else False,
            "reason": str(row["reason"]) if row else "not_engaged",
            "updated_epoch": float(row["updated_epoch"]) if row else None,
            "exchange_kill_is_not_relied_upon": True,
        }

    def generate_cancel_intents(
        self,
        account_id: str,
        open_orders: Iterable[Mapping[str, Any]],
        *,
        reason: str = "local_kill",
        event_id: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """Return local cancellation intents without importing a broker client."""
        created_at = datetime.now(timezone.utc).isoformat()
        intents = []
        for order in open_orders:
            intents.append({
                "intent_type": "CANCEL_ORDER",
                "account_id": account_id,
                "order_id": order.get("order_id"),
                "client_ref": order.get("client_ref"),
                "symbol": order.get("symbol"),
                "event_id": event_id,
                "reason": reason,
                "created_at": created_at,
                "broker_action_performed": False,
            })
        return intents

    def check_pre_trade(
        self,
        *,
        account_id: str,
        venue: str,
        product_group: str,
        price: float,
        reference_price: float,
        quantity: float,
        multiplier: float = 1.0,
        submitted_messages: int = 0,
        limits: Optional[PreTradeLimits | Mapping[str, Any]] = None,
    ) -> ControlDecision:
        """Apply all four local checks; no order is sent or synthesized."""
        active_limits = limits or self.pre_trade_limits
        if isinstance(active_limits, Mapping):
            active_limits = PreTradeLimits(**dict(active_limits))
        missing = active_limits.missing()
        if missing:
            return ControlDecision(
                not self.live_mode, "CONFIGURATION_MISSING",
                "missing_pre_trade_limits",
                {"missing": missing, "live_mode": self.live_mode},
            )
        upstream = self.query_upstream(venue, product_group)
        if not upstream.allowed:
            return upstream
        kill = self.kill_status(account_id)
        if kill["killed"]:
            return ControlDecision(False, "KILLED", "local_kill_engaged", kill)
        try:
            price = float(price)
            reference_price = float(reference_price)
            quantity = float(quantity)
            multiplier = float(multiplier)
        except (TypeError, ValueError):
            return ControlDecision(False, "INVALID_ORDER", "non_numeric_order", {})
        values = (price, reference_price, quantity, multiplier)
        if not all(math.isfinite(x) and x > 0 for x in values):
            return ControlDecision(
                False, "INVALID_ORDER", "non_positive_or_non_finite_order", {})
        max_deviation = float(active_limits.max_price_deviation_pct)  # type: ignore[arg-type]
        max_value = float(active_limits.max_order_value)  # type: ignore[arg-type]
        max_quantity = float(active_limits.max_quantity)  # type: ignore[arg-type]
        max_messages = int(active_limits.max_messages)  # type: ignore[arg-type]
        if min(max_deviation, max_value, max_quantity, max_messages) <= 0:
            return ControlDecision(
                False, "INVALID_LIMITS", "limits_must_be_positive", {})
        deviation = abs(price - reference_price) / reference_price
        order_value = abs(price * quantity * multiplier)
        with self._conn() as conn:
            row = conn.execute(
                """SELECT message_count FROM submission_counters
                   WHERE account_id=? AND venue=? AND product_group=?""",
                (account_id, venue.upper(), product_group.upper()),
            ).fetchone()
        persisted_messages = int(row["message_count"]) if row else 0
        next_message = persisted_messages + int(submitted_messages) + 1
        details = {
            "price_deviation_pct": deviation,
            "order_value": order_value,
            "quantity": quantity,
            "next_message_count": next_message,
        }
        if deviation > max_deviation:
            return ControlDecision(False, "PRICE_GUARD", "price_guard_exceeded", details)
        if order_value > max_value:
            return ControlDecision(False, "MAX_ORDER_VALUE", "max_order_value_exceeded", details)
        if quantity > max_quantity:
            return ControlDecision(False, "MAX_QUANTITY", "max_quantity_exceeded", details)
        if next_message > max_messages:
            return ControlDecision(False, "MAX_MESSAGES", "max_messages_exceeded", details)
        return ControlDecision(True, "ALLOWED", "pre_trade_checks_passed", details)

    pre_trade_check = check_pre_trade

    def record_submitted_order(
        self, account_id: str, venue: str, product_group: str
    ) -> int:
        """Synchronously add a broker-submitted order to the local message count."""
        key = (account_id, venue.upper(), product_group.upper())
        now = time.time()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO submission_counters
                   (account_id,venue,product_group,message_count,updated_epoch)
                   VALUES(?,?,?,1,?)
                   ON CONFLICT(account_id,venue,product_group) DO UPDATE SET
                     message_count=message_count+1,updated_epoch=excluded.updated_epoch""",
                (*key, now),
            )
            row = conn.execute(
                """SELECT message_count FROM submission_counters
                   WHERE account_id=? AND venue=? AND product_group=?""", key
            ).fetchone()
            conn.commit()
        return int(row["message_count"])

    def reset_message_count(
        self,
        account_id: str,
        venue: str,
        product_group: str,
        operator_id: str,
        reason: str,
    ) -> None:
        self._require_operator_reason(operator_id, reason)
        with self._conn() as conn:
            conn.execute(
                """DELETE FROM submission_counters
                   WHERE account_id=? AND venue=? AND product_group=?""",
                (account_id, venue.upper(), product_group.upper()),
            )
        self._audit(
            event_id=None, operator_id=operator_id, changed_by=operator_id,
            approved_by=None, change_nature="MESSAGE_COUNT_RESET",
            details={"account_id": account_id, "venue": venue.upper(),
                     "product_group": product_group.upper(), "reason": reason},
        )

    def set_rejection_mapping(self, code: str | int, category: str) -> None:
        category = str(category).upper()
        if category not in REJECTION_CLASSES:
            raise ValueError(f"unknown rejection class: {category}")
        self.rejection_mapping[str(code).upper()] = category

    def classify_rejection(self, code: str | int) -> str:
        """Unknown rejection codes are fatal so retry is never implicit."""
        return self.rejection_mapping.get(str(code).upper(), FATAL)

    @staticmethod
    def _require_operator_reason(operator_id: str, reason: str) -> None:
        if not str(operator_id).strip() or operator_id == SYSTEM_OPERATOR:
            raise ValueError("an explicit operator_id is required")
        if not str(reason).strip():
            raise ValueError("reason is required")

    def _audit(
        self,
        *,
        event_id: Optional[str],
        operator_id: Optional[str],
        changed_by: Optional[str],
        approved_by: Optional[str],
        change_nature: str,
        details: Mapping[str, Any],
    ) -> None:
        changed_at = datetime.now(timezone.utc).isoformat()
        safe_operator = str(operator_id or SYSTEM_OPERATOR)
        payload = {
            "algo_version": self.algo_version,
            "event_id": event_id,
            "operator_id": safe_operator,
            "changed_at": changed_at,
            "changed_by": str(changed_by or safe_operator),
            "approved_by": approved_by,
            "change_nature": change_nature,
            "details": dict(details),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO control_audit(payload_json,created_epoch) VALUES(?,?)",
                (raw, time.time()),
            )
        if self.audit_log_path:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_log_path.open("a", encoding="utf-8") as fh:
                fh.write(raw + "\n")
