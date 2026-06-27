from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class EventTradeRecord:
    event_id: str
    event_type: str
    asset: str
    symbol: str
    thesis: str
    entry_confidence: float
    seconds_waited: int
    direction: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    mfe_pct: float
    mae_pct: float
    pnl_pct: float
    exit_reason: str
    mistake_tags: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventMemoryDB:
    def __init__(self, path: str = "eventalpha_memory.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS event_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT,
                    event_type TEXT,
                    asset TEXT,
                    symbol TEXT,
                    thesis TEXT,
                    entry_confidence REAL,
                    seconds_waited INTEGER,
                    direction TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    mfe_pct REAL,
                    mae_pct REAL,
                    pnl_pct REAL,
                    exit_reason TEXT,
                    mistake_tags TEXT,
                    created_at TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    asset TEXT,
                    symbol TEXT,
                    memory_edge_delta REAL,
                    wait_seconds_delta INTEGER,
                    risk_multiplier_delta REAL,
                    lessons TEXT,
                    raw_record TEXT,
                    created_at TEXT
                )
                """
            )

    def append(self, record: EventTradeRecord) -> None:
        data = asdict(record)
        keys = ",".join(data.keys())
        qs = ",".join(["?"] * len(data))
        with self._connect() as con:
            con.execute(f"INSERT INTO event_trades ({keys}) VALUES ({qs})", list(data.values()))

    def edge_summary(self, event_type: str, asset: str) -> Dict[str, Any]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT pnl_pct, seconds_waited, entry_confidence FROM event_trades WHERE event_type=? AND asset=?",
                (event_type, asset),
            ).fetchall()
            updates = con.execute(
                "SELECT memory_edge_delta, wait_seconds_delta, risk_multiplier_delta FROM learning_updates WHERE event_type=? AND asset=?",
                (event_type, asset),
            ).fetchall()
        if not rows:
            base_edge = 0.50
            base_wait = None
        else:
            pnls = [r[0] for r in rows]
            waits = [r[1] for r in rows]
            win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
            avg_pnl = sum(pnls) / len(pnls)
            base_edge = max(0.05, min(0.95, 0.50 + (win_rate - 0.50) * 0.50 + avg_pnl * 0.02))
            base_wait = int(sum(waits) / len(waits))
        edge_bias = sum(r[0] for r in updates) if updates else 0.0
        wait_bias = sum(r[1] for r in updates) if updates else 0
        risk_bias = sum(r[2] for r in updates) if updates else 0.0
        memory_edge = max(0.05, min(0.95, base_edge + edge_bias))
        recommended_wait_seconds = None if base_wait is None else max(0, base_wait + wait_bias)
        return {
            "samples": len(rows),
            "learning_updates": len(updates),
            "memory_edge": memory_edge,
            "recommended_wait_seconds": recommended_wait_seconds,
            "risk_multiplier_bias": risk_bias,
        }

    def append_learning_update(
        self,
        *,
        event_type: str,
        asset: str,
        symbol: str,
        memory_edge_delta: float,
        wait_seconds_delta: int,
        risk_multiplier_delta: float,
        lessons: str,
        raw_record: str,
        created_at: str,
    ) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO learning_updates (
                    event_type, asset, symbol, memory_edge_delta, wait_seconds_delta,
                    risk_multiplier_delta, lessons, raw_record, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    asset,
                    symbol,
                    memory_edge_delta,
                    wait_seconds_delta,
                    risk_multiplier_delta,
                    lessons,
                    raw_record,
                    created_at,
                ),
            )
