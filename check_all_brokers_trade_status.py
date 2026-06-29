#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DATA_DB = BASE / "data.db"
DUKASCOPY_ROOT = "http://127.0.0.1:8001"
REPORT_DIR = BASE / "reports" / "broker_trade_status_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt_age(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    seconds = max(0, int((now_utc() - value.astimezone(timezone.utc)).total_seconds()))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}"


def fetch_json(path: str) -> dict | None:
    try:
        with urlopen(DUKASCOPY_ROOT + path, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def load_ibkr_trade_rows() -> list[dict]:
    if not DATA_DB.exists():
        return []
    conn = sqlite3.connect(DATA_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT client_ref, symbol, direction, quantity, entry_price, exit_price,
                   pnl_abs, pnl_pct, opened_at, closed_at, exit_reason, status
            FROM trades
            ORDER BY COALESCE(closed_at, opened_at) DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_ibkr_account() -> dict:
    try:
        from ib_insync import IB
    except Exception as exc:
        return {"connected": False, "error": f"ib_insync unavailable: {exc}"}

    ib = IB()
    try:
        ib.connect("127.0.0.1", 7497, clientId=188, timeout=8)
        summary_rows = ib.accountSummary()
        summary = {}
        for row in summary_rows:
            if row.tag in {"NetLiquidation", "AvailableFunds", "TotalCashValue", "UnrealizedPnL", "RealizedPnL"}:
                summary[row.tag] = row.value

        positions = []
        for p in ib.positions():
            positions.append(
                {
                    "symbol": p.contract.localSymbol or p.contract.symbol,
                    "quantity": float(p.position),
                    "avg_cost": float(getattr(p, "avgCost", 0.0) or 0.0),
                }
            )
        return {"connected": True, "summary": summary, "positions": positions}
    except Exception as exc:
        message = str(exc).strip() or repr(exc)
        return {"connected": False, "error": message}
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def summarize_ibkr() -> list[str]:
    rows = load_ibkr_trade_rows()
    account = load_ibkr_account()
    open_rows = [r for r in rows if (r.get("status") or "").upper() == "OPEN"]
    closed_rows = [r for r in rows if (r.get("status") or "").upper() == "CLOSED"]
    total_pnl = sum(float(r.get("pnl_abs") or 0.0) for r in closed_rows)

    lines = []
    lines.append("[IBKR | Interactive Brokers]")
    if account.get("connected"):
        summary = account.get("summary", {})
        lines.append("connection: LIVE")
        lines.append(f"net_liquidation: {summary.get('NetLiquidation', 'N/A')}")
        lines.append(f"available_funds: {summary.get('AvailableFunds', 'N/A')}")
        lines.append(f"realized_pnl: {summary.get('RealizedPnL', 'N/A')}")
        lines.append(f"unrealized_pnl: {summary.get('UnrealizedPnL', 'N/A')}")
        lines.append(f"broker_open_positions: {len(account.get('positions', []))}")
    else:
        lines.append(f"connection: ATTENTION | {account.get('error', 'unknown error')}")
        lines.append("broker_open_positions: N/A")

    lines.append(f"journal_open_trades: {len(open_rows)}")
    lines.append(f"journal_closed_trades: {len(closed_rows)}")
    lines.append(f"journal_total_closed_pnl_abs: {fmt_num(total_pnl)}")

    if open_rows:
        lines.append("open_trade_details:")
        for row in open_rows[:10]:
            opened = parse_ts(row.get("opened_at"))
            lines.append(
                f"  - {row.get('symbol')} | {row.get('direction')} | qty={fmt_num(row.get('quantity'), 4)} "
                f"| opened={fmt_dt(opened)} | runtime={fmt_age(opened)} | entry={fmt_num(row.get('entry_price'), 5)}"
            )
    else:
        lines.append("open_trade_details: none")

    if closed_rows:
        lines.append("recent_closed_trade_details:")
        for row in closed_rows[:10]:
            opened = parse_ts(row.get("opened_at"))
            closed = parse_ts(row.get("closed_at"))
            duration = "N/A"
            if opened and closed:
                duration = fmt_age(opened + (closed - opened))
                total_sec = int((closed - opened).total_seconds())
                d, rem = divmod(max(0, total_sec), 86400)
                h, rem = divmod(rem, 3600)
                m, s = divmod(rem, 60)
                duration = f"{d}d {h}h {m}m" if d else (f"{h}h {m}m" if h else f"{m}m {s}s")
            lines.append(
                f"  - {row.get('symbol')} | {row.get('direction')} | opened={fmt_dt(opened)} | closed={fmt_dt(closed)} "
                f"| duration={duration} | pnl_abs={fmt_num(row.get('pnl_abs'))} | pnl_pct={fmt_num((row.get('pnl_pct') or 0.0) * 100, 2)}% "
                f"| exit_reason={row.get('exit_reason') or 'N/A'}"
            )
    else:
        lines.append("recent_closed_trade_details: none")

    if account.get("connected") and account.get("positions"):
        lines.append("live_broker_positions:")
        for pos in account["positions"][:10]:
            lines.append(
                f"  - {pos['symbol']} | qty={fmt_num(pos['quantity'], 6)} | avg_cost={fmt_num(pos['avg_cost'], 5)}"
            )
    else:
        lines.append("live_broker_positions: none")

    return lines


def summarize_dukascopy() -> list[str]:
    health = fetch_json("/api/health") or {}
    status = fetch_json("/api/broker/dukascopy/status") or {}
    positions = fetch_json("/api/broker/positions") or {"positions": [], "count": 0}
    trades = fetch_json("/api/trades") or {"trades": [], "count": 0}
    trade_stats = fetch_json("/api/trades/stats") or {}

    open_positions = positions.get("positions", []) or []
    all_trades = trades.get("trades", []) or []
    closed_trades = [t for t in all_trades if (t.get("status") or "").upper() in {"CLOSED", "FLATTENED"}]

    lines = []
    lines.append("[Dukascopy | Swiss FX]")
    lines.append(f"connection: {'LIVE' if status.get('connected') else 'ATTENTION'}")
    lines.append(f"adapter_status: {status.get('status', 'N/A')}")
    lines.append(f"account_id: {status.get('account_id', 'N/A')}")
    lines.append(f"equity: {status.get('equity', 'N/A')}")
    lines.append(f"last_seen: {status.get('last_seen', 'N/A')} | age={fmt_age(parse_ts(status.get('last_seen')))}")
    lines.append(f"configured_pairs: {', '.join(health.get('pairs', [])) or 'N/A'}")
    lines.append(f"open_positions: {positions.get('count', 0)}")
    lines.append(f"closed_trades_in_backend_memory: {trade_stats.get('total_trades', 0)}")
    lines.append(f"closed_total_pnl_pips: {trade_stats.get('total_pnl_pips', 0.0)}")

    if open_positions:
        lines.append("open_position_details:")
        for pos in open_positions[:10]:
            started = parse_ts(pos.get("timestamp"))
            lines.append(
                f"  - {pos.get('pair')} | {pos.get('direction')} | amount={pos.get('amount')} "
                f"| opened={fmt_dt(started)} | runtime={fmt_age(started)} | entry={pos.get('entry_price')} "
                f"| pnl_pips={pos.get('pnl_pips', 'N/A')} | pnl_usd={pos.get('pnl_usd', 'N/A')}"
            )
    else:
        lines.append("open_position_details: none")

    if closed_trades:
        lines.append("recent_closed_trade_details:")
        grouped: dict[str, list[dict]] = {}
        for item in all_trades:
            label = item.get("label") or item.get("pair") or "UNKNOWN"
            grouped.setdefault(label, []).append(item)
        shown = 0
        for label, items in list(grouped.items())[:20]:
            opens = [i for i in items if (i.get("status") or "").upper() not in {"CLOSED", "FLATTENED"}]
            closes = [i for i in items if (i.get("status") or "").upper() in {"CLOSED", "FLATTENED"}]
            if not closes:
                continue
            close_item = sorted(closes, key=lambda x: x.get("timestamp") or "")[-1]
            open_item = sorted(opens, key=lambda x: x.get("timestamp") or "")[0] if opens else None
            open_ts = parse_ts(open_item.get("timestamp")) if open_item else None
            close_ts = parse_ts(close_item.get("timestamp"))
            duration = "N/A"
            if open_ts and close_ts:
                total_sec = int((close_ts - open_ts).total_seconds())
                d, rem = divmod(max(0, total_sec), 86400)
                h, rem = divmod(rem, 3600)
                m, s = divmod(rem, 60)
                duration = f"{d}d {h}h {m}m" if d else (f"{h}h {m}m" if h else f"{m}m {s}s")
            lines.append(
                f"  - {close_item.get('pair')} | {close_item.get('direction')} | opened={fmt_dt(open_ts)} | closed={fmt_dt(close_ts)} "
                f"| duration={duration} | pnl_pips={close_item.get('pnl_pips', 'N/A')} | pnl_usd={close_item.get('pnl_usd', 'N/A')}"
            )
            shown += 1
            if shown >= 10:
                break
    else:
        lines.append("recent_closed_trade_details: none")

    return lines


def write_report(text: str) -> Path:
    ts = now_utc().strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"all_brokers_trade_status_{ts}.md"
    latest = REPORT_DIR / "all_brokers_trade_status_latest.md"
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    lines: list[str] = []
    lines.append("InsightBridge All Brokers Trade Status")
    lines.append("=" * 60)
    lines.append(f"base: {BASE}")
    lines.append(f"generated_at: {fmt_dt(now_utc())}")
    lines.append("-" * 60)
    lines.extend(summarize_ibkr())
    lines.append("-" * 60)
    lines.extend(summarize_dukascopy())
    lines.append("-" * 60)
    lines.append("Interpretation")
    lines.append("-" * 60)
    lines.append("If open_trade_details or open_position_details is none, that broker currently has no real live trade open.")
    lines.append("If recent_closed_trade_details is none, that broker has no recorded completed trade yet in the currently connected journal/backend memory.")
    lines.append("IBKR closed trade truth comes from local SQLite trade journal data.db.")
    lines.append("Dukascopy trade truth comes from the local FX backend memory and broker-position bridge.")

    text = "\n".join(lines) + "\n"
    report_path = write_report(text)
    print(text, end="")
    print(f"report_file: {report_path}")
    print(f"latest_report: {REPORT_DIR / 'all_brokers_trade_status_latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
