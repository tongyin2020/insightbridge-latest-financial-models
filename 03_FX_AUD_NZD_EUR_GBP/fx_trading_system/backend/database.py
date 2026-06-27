"""
SQLite database layer using aiosqlite.
Provides all async CRUD operations for the FX trading system.
"""
from __future__ import annotations

import aiosqlite
import json
from datetime import datetime, timezone
from typing import Any, Optional
from config import settings

DB_PATH = settings.database_path

# ─── Schema ────────────────────────────────────────────────────────────────────

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('LONG', 'SHORT')),
    entry_price REAL NOT NULL,
    exit_price REAL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    pnl_pips REAL,
    pnl_usd REAL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'CLOSED', 'CANCELLED')),
    signal_type TEXT CHECK(signal_type IN ('TREND', 'EVENT', 'MANUAL')),
    confidence REAL,
    stop_loss REAL,
    take_profit REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence REAL NOT NULL,
    regime TEXT,
    event_level TEXT,
    approved INTEGER DEFAULT 0,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL DEFAULT 0,
    sma20 REAL,
    sma50 REAL,
    adx REAL,
    atr REAL,
    rsi REAL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    country TEXT NOT NULL,
    impact TEXT CHECK(impact IN ('A', 'B', 'C')),
    datetime TEXT NOT NULL,
    actual TEXT,
    forecast TEXT,
    previous TEXT,
    pair_affected TEXT
);

CREATE TABLE IF NOT EXISTS system_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "aud_usd_direction": "LONG_ONLY",
    "nzd_usd_direction": "LONG_ONLY",
    "override_mode": "NORMAL",
    "max_hold_minutes": "30",
    "stop_loss_pips": "15",
    "take_profit_pips": "25",
    "spread_threshold_pips": "3.0",
    "event_a_cooldown_seconds": "30",
    "event_b_cooldown_seconds": "20",
    "kill_switch": "false",
}

# ─── Indexes ───────────────────────────────────────────────────────────────────

CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_price_history_pair_ts ON price_history(pair, timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_pair_ts ON signals(pair, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_events_datetime ON events(datetime);
CREATE INDEX IF NOT EXISTS idx_system_log_ts ON system_log(timestamp);
"""


# ─── Connection helpers ────────────────────────────────────────────────────────

async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript(CREATE_TABLES_SQL)
        await db.executescript(CREATE_INDEXES_SQL)

        # Insert default settings if they don't exist
        now = datetime.now(timezone.utc).isoformat()
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
        await db.commit()
    finally:
        await db.close()


# ─── Trades ────────────────────────────────────────────────────────────────────

async def insert_trade(
    pair: str,
    direction: str,
    entry_price: float,
    entry_time: str,
    signal_type: str = "TREND",
    confidence: float = 0.0,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    notes: str = "",
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO trades
               (pair, direction, entry_price, entry_time, status, signal_type, confidence, stop_loss, take_profit, notes)
               VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?)""",
            (pair, direction, entry_price, entry_time, signal_type, confidence, stop_loss, take_profit, notes),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def close_trade(
    trade_id: int,
    exit_price: float,
    exit_time: str,
    pnl_pips: float,
    pnl_usd: float,
) -> None:
    db = await get_db()
    try:
        await db.execute(
            """UPDATE trades
               SET exit_price=?, exit_time=?, pnl_pips=?, pnl_usd=?, status='CLOSED'
               WHERE id=?""",
            (exit_price, exit_time, pnl_pips, pnl_usd, trade_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_trades(
    status: Optional[str] = None,
    pair: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    db = await get_db()
    try:
        query = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if pair:
            query += " AND pair = ?"
            params.append(pair)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_open_trades(pair: Optional[str] = None) -> list[dict]:
    return await get_trades(status="OPEN", pair=pair)


# ─── Signals ──────────────────────────────────────────────────────────────────

async def insert_signal(
    pair: str,
    timestamp: str,
    direction: str,
    confidence: float,
    regime: str = "",
    event_level: str = "",
    approved: bool = False,
    reason: str = "",
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO signals
               (pair, timestamp, direction, confidence, regime, event_level, approved, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (pair, timestamp, direction, confidence, regime, event_level, 1 if approved else 0, reason),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_signals(pair: Optional[str] = None, limit: int = 50) -> list[dict]:
    db = await get_db()
    try:
        query = "SELECT * FROM signals"
        params: list[Any] = []
        if pair:
            query += " WHERE pair = ?"
            params.append(pair)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


# ─── Price History ─────────────────────────────────────────────────────────────

async def insert_price(
    pair: str,
    timestamp: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 0.0,
    sma20: Optional[float] = None,
    sma50: Optional[float] = None,
    adx: Optional[float] = None,
    atr: Optional[float] = None,
    rsi: Optional[float] = None,
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO price_history
               (pair, timestamp, open, high, low, close, volume, sma20, sma50, adx, atr, rsi)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pair, timestamp, open_, high, low, close, volume, sma20, sma50, adx, atr, rsi),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_recent_prices(pair: str, limit: int = 100) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM price_history WHERE pair = ? ORDER BY id DESC LIMIT ?",
            (pair, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]  # Return in chronological order
    finally:
        await db.close()


async def get_latest_price(pair: str) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM price_history WHERE pair = ? ORDER BY id DESC LIMIT 1",
            (pair,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ─── Events ───────────────────────────────────────────────────────────────────

async def insert_event(
    title: str,
    country: str,
    impact: str,
    dt: str,
    actual: str = "",
    forecast: str = "",
    previous: str = "",
    pair_affected: str = "",
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO events
               (title, country, impact, datetime, actual, forecast, previous, pair_affected)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, country, impact, dt, actual, forecast, previous, pair_affected),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_upcoming_events(limit: int = 20) -> list[dict]:
    db = await get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "SELECT * FROM events WHERE datetime >= ? ORDER BY datetime ASC LIMIT ?",
            (now, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_all_events(limit: int = 50) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM events ORDER BY datetime DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


# ─── Settings ─────────────────────────────────────────────────────────────────

async def get_setting(key: str) -> Optional[str]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else None
    finally:
        await db.close()


async def set_setting(key: str, value: str) -> None:
    db = await get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, value, now),
        )
        await db.commit()
    finally:
        await db.close()


async def get_all_settings() -> dict[str, str]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value, updated_at FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: {"value": row["value"], "updated_at": row["updated_at"]} for row in rows}
    finally:
        await db.close()


# ─── System Log ───────────────────────────────────────────────────────────────

async def insert_log(level: str, source: str, message: str) -> int:
    db = await get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "INSERT INTO system_log (timestamp, level, source, message) VALUES (?, ?, ?, ?)",
            (now, level, source, message),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_logs(level: Optional[str] = None, source: Optional[str] = None, limit: int = 100) -> list[dict]:
    db = await get_db()
    try:
        query = "SELECT * FROM system_log WHERE 1=1"
        params: list[Any] = []
        if level:
            query += " AND level = ?"
            params.append(level)
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()
