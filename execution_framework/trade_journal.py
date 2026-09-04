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
    model_decision: str = ""
    signal_time: Optional[str] = None
    submit_time: Optional[str] = None
    fill_time: Optional[str] = None
    signal_price: Optional[float] = None
    fill_price: Optional[float] = None
    slippage: Optional[float] = None
    minutes_after_event: float = 0.0   # 入场距事件时点的分钟（供冷静期校准）
    multiplier: float = 1.0            # 合约乘数（每点价值）；现货/外汇为 1
    fee_per_side: float = 0.0          # 单边每手费用（佣金+交易所+监管，账户货币）
    opened_at: str = field(default_factory=_utcnow)
    exit_price: Optional[float] = None
    closed_at: Optional[str] = None
    pnl_abs: Optional[float] = None     # 旧语义：价格点数 * 数量（不含乘数/费用）
    pnl_pct: Optional[float] = None     # 相对入场价
    r_multiple: Optional[float] = None  # 毛 R：价格点数盈亏 / 初始风险
    pnl_gross_abs: Optional[float] = None  # 货币口径毛盈亏：点数 * 数量 * 乘数
    fee_total: Optional[float] = None      # 双边总费用：fee_per_side * 数量 * 2
    pnl_net_abs: Optional[float] = None    # 净盈亏 = pnl_gross_abs - fee_total
    r_multiple_net: Optional[float] = None # 净 R：净盈亏 / (初始货币风险 + 双边费用)
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
                    model_decision TEXT,
                    signal_time  TEXT,
                    submit_time  TEXT,
                    fill_time    TEXT,
                    order_status TEXT,
                    entry_price  REAL,
                    signal_price REAL,
                    fill_price   REAL,
                    slippage     REAL,
                    stop_loss    REAL,
                    quantity     REAL,
                    risk_per_unit REAL,
                    minutes_after_event REAL,
                    opened_at    TEXT,
                    exit_price   REAL,
                    closed_at    TEXT,
                    pnl_abs      REAL,
                    pnl_pct      REAL,
                    r_multiple   REAL,
                    exit_reason  TEXT,
                    status       TEXT
                )""")
            for ddl in [
                "ALTER TABLE trades ADD COLUMN model_decision TEXT",
                "ALTER TABLE trades ADD COLUMN signal_time TEXT",
                "ALTER TABLE trades ADD COLUMN submit_time TEXT",
                "ALTER TABLE trades ADD COLUMN fill_time TEXT",
                "ALTER TABLE trades ADD COLUMN order_status TEXT",
                "ALTER TABLE trades ADD COLUMN signal_price REAL",
                "ALTER TABLE trades ADD COLUMN fill_price REAL",
                "ALTER TABLE trades ADD COLUMN slippage REAL",
                "ALTER TABLE trades ADD COLUMN multiplier REAL",
                "ALTER TABLE trades ADD COLUMN fee_per_side REAL",
                "ALTER TABLE trades ADD COLUMN pnl_gross_abs REAL",
                "ALTER TABLE trades ADD COLUMN fee_total REAL",
                "ALTER TABLE trades ADD COLUMN pnl_net_abs REAL",
                "ALTER TABLE trades ADD COLUMN r_multiple_net REAL",
            ]:
                try:
                    c.execute(ddl)
                except sqlite3.OperationalError:
                    pass
            c.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON trades(symbol)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_status ON trades(status)")

    # ── 开仓 ──────────────────────────────────────────────────────────────
    def record_open(self, rec: TradeRecord) -> None:
        if rec.multiplier <= 0:
            raise ValueError("multiplier must be positive")
        if rec.fee_per_side < 0:
            raise ValueError("fee_per_side cannot be negative")
        with self._lock, self._conn() as c:
            # 幂等：同一 client_ref 不重复插入
            existing = c.execute("SELECT 1 FROM trades WHERE client_ref=?",
                                 (rec.client_ref,)).fetchone()
            if existing:
                return
            c.execute("""
                INSERT INTO trades (client_ref, symbol, event_name, direction,
                    model_decision, signal_time, submit_time, fill_time,
                    order_status,
                    entry_price, signal_price, fill_price, slippage,
                    stop_loss, quantity, risk_per_unit,
                    minutes_after_event, multiplier, fee_per_side,
                    opened_at, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec.client_ref, rec.symbol, rec.event_name, rec.direction,
                 rec.model_decision, rec.signal_time, rec.submit_time, rec.fill_time,
                 "SUBMITTED" if rec.submit_time else "SIGNAL",
                 rec.entry_price, rec.signal_price, rec.fill_price, rec.slippage,
                 rec.stop_loss, rec.quantity, rec.risk_per_unit,
                 rec.minutes_after_event, float(rec.multiplier),
                 float(rec.fee_per_side), rec.opened_at, "OPEN"))

    def record_fill(self, client_ref: str, fill_price: float, order_status: str = "FILLED",
                    fill_time: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM trades WHERE client_ref=?", (client_ref,)).fetchone()
            if row is None:
                return None
            signal_price = float(row["signal_price"] if row["signal_price"] is not None else row["entry_price"] or 0.0)
            direction = row["direction"]
            sign = 1.0 if direction == "LONG" else -1.0
            slippage = ((fill_price - signal_price) * sign) if signal_price else 0.0
            c.execute(
                """
                UPDATE trades
                SET fill_price=?, fill_time=?, slippage=?, order_status=?
                WHERE client_ref=?
                """,
                (fill_price, fill_time or _utcnow(), slippage, order_status, client_ref),
            )
            return {
                "client_ref": client_ref,
                "fill_price": fill_price,
                "signal_price": signal_price,
                "slippage": slippage,
                "order_status": order_status,
            }

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
            r_multiple = move / risk      # 毛 R 倍数（价格口径，不含乘数/费用）

            # 货币口径（净 R）：旧行无乘数/费用时按 1.0 / 0.0 退化，
            # 此时 pnl_gross_abs == pnl_abs、r_multiple_net == r_multiple。
            multiplier = float(row["multiplier"]) if row["multiplier"] else 1.0
            fee_per_side = float(row["fee_per_side"]) if row["fee_per_side"] else 0.0
            pnl_gross_abs = move * qty * multiplier
            fee_total = fee_per_side * qty * 2.0   # 开仓 + 平仓两边
            pnl_net_abs = pnl_gross_abs - fee_total
            risk_money = risk * qty * multiplier + fee_total
            r_multiple_net = pnl_net_abs / risk_money

            c.execute("""
                UPDATE trades SET exit_price=?, closed_at=?, pnl_abs=?, pnl_pct=?,
                    r_multiple=?, pnl_gross_abs=?, fee_total=?, pnl_net_abs=?,
                    r_multiple_net=?, exit_reason=?, status='CLOSED'
                WHERE client_ref=?""",
                (exit_price, _utcnow(), pnl_abs, pnl_pct, r_multiple,
                 pnl_gross_abs, fee_total, pnl_net_abs, r_multiple_net,
                 exit_reason, client_ref))
            return {"client_ref": client_ref, "pnl_abs": pnl_abs,
                    "pnl_pct": pnl_pct, "r_multiple": r_multiple,
                    "pnl_gross_abs": pnl_gross_abs, "fee_total": fee_total,
                    "pnl_net_abs": pnl_net_abs, "r_multiple_net": r_multiple_net}

    def get_trade(self, client_ref: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM trades WHERE client_ref=?", (client_ref,)).fetchone()
            return dict(row) if row is not None else None

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
        # 净口径（货币）：乘数/费用已计入；旧数据无净口径时这些字段为 None
        rs_net = [float(r["r_multiple_net"]) for r in rows
                  if r["r_multiple_net"] is not None]
        total_pnl_net = sum(float(r["pnl_net_abs"] or 0.0)
                            for r in rows if r["pnl_net_abs"] is not None)
        total_fees = sum(float(r["fee_total"] or 0.0) for r in rows)

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
            "avg_r_net": round(sum(rs_net) / len(rs_net), 4) if rs_net else None,
            "total_pnl_net_abs": round(total_pnl_net, 2),
            "total_fees": round(total_fees, 2),
            "max_consec_losses": max_consec,
        }

    def open_trades(self) -> List[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
            return [dict(r) for r in rows]

    def current_consecutive_losses(self) -> int:
        """Return the current trailing loss streak, not the historical maximum."""
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT r_multiple FROM trades WHERE status='CLOSED' "
                "ORDER BY closed_at DESC").fetchall()
        streak = 0
        for row in rows:
            value = row["r_multiple"]
            if value is not None and float(value) < 0:
                streak += 1
            else:
                break
        return streak

    def export_jsonl(self, path: str) -> int:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM trades ORDER BY opened_at").fetchall()
        p = Path(path)
        with p.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(dict(r), ensure_ascii=False) + "\n")
        return len(rows)
