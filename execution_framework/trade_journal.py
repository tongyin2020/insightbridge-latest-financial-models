"""
trade_journal.py
═══════════════════════════════════════════════════════════════════════════════
成交后真实 P&L 回写学习库（SQLite）。

解决审计发现的问题：原仓库所有 paper 交易都以 pnl_pct=0.0 / exit_price=None 记录，
"自适应学习"实际跑在虚构数据上。本模块记录每笔交易的真实生命周期：
  开仓(entry) -> 平仓(exit) -> 计算真实 R 倍数与 PnL% -> 落库
并提供按品种/事件类型的胜率、平均 R、连亏等统计，供后续参数校准与风控使用。

纯标准库 sqlite3，无外部依赖。数据库文件默认 data.db（便于持久化）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TradeRecord:
    client_ref: str
    symbol: str
    event_name: str
    direction: str                  # LONG / SHORT
    entry_price: float
    stop_loss: float
    quantity: float
    risk_per_unit: float            # |entry - stop|，用于算 R 倍数
    opened_at: str = field(default_factory=_utcnow)
    exit_price: Optional[float] = None
    closed_at: Optional[str] = None
    pnl_abs: Optional[float] = None     # 价格点数 * 数量（未乘合约乘数，由调用方决定）
    pnl_pct: Optional[float] = None     # 相对入场价
    r_multiple: Optional[float] = None  # 盈亏 / 初始风险（核心学习指标）
    exit_reason: str = ""
    status: str = "OPEN"                 # OPEN / CLOSED


class TradeJournal:
    def __init__(self, db_path: str = "data.db"):
        self.db_path = str(Path(db_path))
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=10.0)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    client_ref   TEXT PRIMARY KEY,
                    symbol       TEXT NOT NULL,
                    event_name   TEXT,
                    direction    TEXT,
                    entry_price  REAL,
                    stop_loss    REAL,
                    quantity     REAL,
                    risk_per_unit REAL,
                    opened_at    TEXT,
                    exit_price   REAL,
                    closed_at    TEXT,
                    pnl_abs      REAL,
                    pnl_pct      REAL,
                    r_multiple   REAL,
                    exit_reason  TEXT,
                    status       TEXT
                )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON trades(symbol)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_status ON trades(status)")

    # ── 开仓 ──────────────────────────────────────────────────────────────
    def record_open(self, rec: TradeRecord) -> None:
        with self._lock, self._conn() as c:
            # 幂等：同一 client_ref 不重复插入
            existing = c.execute("SELECT 1 FROM trades WHERE client_ref=?",
                                 (rec.client_ref,)).fetchone()
            if existing:
                return
            c.execute("""
                INSERT INTO trades (client_ref, symbol, event_name, direction,
                    entry_price, stop_loss, quantity, risk_per_unit, opened_at, status)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (rec.client_ref, rec.symbol, rec.event_name, rec.direction,
                 rec.entry_price, rec.stop_loss, rec.quantity, rec.risk_per_unit,
                 rec.opened_at, "OPEN"))

    # ── 平仓：写入真实出场价并计算 R / PnL ─────────────────────────────────
    def record_close(self, client_ref: str, exit_price: float,
                     exit_reason: str = "") -> Optional[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM trades WHERE client_ref=?",
                            (client_ref,)).fetchone()
            if row is None or row["status"] == "CLOSED":
                return None
            entry = float(row["entry_price"])
            qty = float(row["quantity"])
            risk = float(row["risk_per_unit"]) or 1e-9
            direction = row["direction"]
            sign = 1.0 if direction == "LONG" else -1.0

            move = (exit_price - entry) * sign
            pnl_abs = move * qty
            pnl_pct = (move / entry) if entry else 0.0
            r_multiple = move / risk      # 真实 R 倍数（核心学习指标）

            c.execute("""
                UPDATE trades SET exit_price=?, closed_at=?, pnl_abs=?, pnl_pct=?,
                    r_multiple=?, exit_reason=?, status='CLOSED'
                WHERE client_ref=?""",
                (exit_price, _utcnow(), pnl_abs, pnl_pct, r_multiple,
                 exit_reason, client_ref))
            return {"client_ref": client_ref, "pnl_abs": pnl_abs,
                    "pnl_pct": pnl_pct, "r_multiple": r_multiple}

    # ── 统计：供参数校准 / 风控使用 ────────────────────────────────────────
    def stats(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        with self._lock, self._conn() as c:
            q = "SELECT * FROM trades WHERE status='CLOSED'"
            params: tuple = ()
            if symbol:
                q += " AND symbol=?"
                params = (symbol,)
            rows = c.execute(q, params).fetchall()

        n = len(rows)
        if n == 0:
            return {"symbol": symbol or "ALL", "closed_trades": 0,
                    "win_rate": None, "avg_r": None, "total_pnl_abs": 0.0,
                    "max_consec_losses": 0, "note": "无已平仓交易"}

        rs = [float(r["r_multiple"]) for r in rows if r["r_multiple"] is not None]
        wins = [x for x in rs if x > 0]
        total_pnl = sum(float(r["pnl_abs"] or 0.0) for r in rows)

        # 连亏
        max_consec = consec = 0
        for r in sorted(rows, key=lambda x: x["closed_at"] or ""):
            if (r["r_multiple"] or 0) < 0:
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 0

        return {
            "symbol": symbol or "ALL",
            "closed_trades": n,
            "win_rate": round(len(wins) / n, 4),
            "avg_r": round(sum(rs) / len(rs), 4) if rs else None,
            "avg_win_r": round(sum(wins) / len(wins), 4) if wins else None,
            "total_pnl_abs": round(total_pnl, 2),
            "max_consec_losses": max_consec,
        }

    def open_trades(self) -> List[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
            return [dict(r) for r in rows]

    def export_jsonl(self, path: str) -> int:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM trades ORDER BY opened_at").fetchall()
        p = Path(path)
        with p.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(dict(r), ensure_ascii=False) + "\n")
        return len(rows)
