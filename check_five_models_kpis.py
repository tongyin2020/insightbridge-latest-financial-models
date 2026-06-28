#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


BASE = Path(__file__).resolve().parent
LABEL = "com.insightbridge.five-models.paper"
RUNTIME_DIR = BASE / "reports" / "runtime"
HEARTBEAT = RUNTIME_DIR / "heartbeat.json"
CONTINUOUS_LOG = RUNTIME_DIR / "continuous.log"
STDOUT_LOG = RUNTIME_DIR / "launchd_stdout.log"
STDERR_LOG = RUNTIME_DIR / "launchd_stderr.log"
DATA_DB = BASE / "data.db"
REPORT_DIR = BASE / "reports" / "five_models_runtime_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL_GROUPS = {
    "FX": ["EURUSD", "USDJPY"],
    "INDEX": ["MES", "MNQ"],
    "TREASURY": ["ZT", "ZN", "SR3"],
    "CRYPTO": ["BTC"],
    "OIL": ["CL"],
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "N/A"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt_age(dt: datetime | None) -> str:
    if dt is None:
        return "N/A"
    delta = (now_utc() - dt.astimezone(timezone.utc)).total_seconds()
    if delta < 60:
        return "<1m"
    if delta < 3600:
        return f"{delta/60:.1f}m"
    if delta < 86400:
        return f"{delta/3600:.1f}h"
    return f"{delta/86400:.1f}d"


def fmt_num(value, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}"


def launchd_running() -> tuple[bool, int | None]:
    proc = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, None
    text = proc.stdout
    pid = None
    if "state = running" not in text:
        return False, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("pid ="):
            try:
                pid = int(line.split("=", 1)[1].strip())
            except Exception:
                pid = None
    return True, pid


def heartbeat() -> dict:
    if not HEARTBEAT.exists():
        return {}
    try:
        return json.loads(HEARTBEAT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def runtime_log_stats() -> dict:
    stats = {
        "first_seen": None,
        "last_seen": None,
        "total_evaluations": 0,
        "holds": 0,
        "buy_signals": 0,
        "sell_signals": 0,
        "halts": 0,
        "reconnects": 0,
        "orders_ready": 0,
        "symbol_counts": Counter(),
        "reason_counts": Counter(),
        "last_eval_by_symbol": {},
        "last_reason_by_symbol": {},
    }
    if not CONTINUOUS_LOG.exists():
        return stats

    for raw in CONTINUOUS_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        ts_text = row.get("ts")
        ts = None
        if ts_text:
            try:
                ts = datetime.fromisoformat(ts_text)
            except Exception:
                ts = None
        if ts is not None:
            if stats["first_seen"] is None or ts < stats["first_seen"]:
                stats["first_seen"] = ts
            if stats["last_seen"] is None or ts > stats["last_seen"]:
                stats["last_seen"] = ts

        stage = row.get("stage")
        if stage == "evaluate":
            stats["total_evaluations"] += 1
            symbol = str(row.get("symbol", "")).upper()
            status = str(row.get("status", "")).upper()
            reason = str(row.get("reason", ""))
            if symbol:
                stats["symbol_counts"][symbol] += 1
                if ts is not None:
                    stats["last_eval_by_symbol"][symbol] = ts
                if reason:
                    stats["last_reason_by_symbol"][symbol] = reason
            if status == "HOLD":
                stats["holds"] += 1
            elif status == "BUY":
                stats["buy_signals"] += 1
            elif status == "SELL":
                stats["sell_signals"] += 1
            if reason:
                stats["reason_counts"][reason] += 1
        elif stage == "HALT":
            stats["halts"] += 1
        elif stage == "reconnected":
            stats["reconnects"] += 1
        elif stage == "order_intent":
            stats["orders_ready"] += 1
    return stats


def classify_runtime_phase(log_stats: dict) -> tuple[str, str]:
    if log_stats["buy_signals"] > 0 or log_stats["sell_signals"] > 0 or log_stats["orders_ready"] > 0:
        return "ACTIVE_SIGNALING", "system is producing actionable trade signals"
    if log_stats["reason_counts"]:
        top_reason, _ = log_stats["reason_counts"].most_common(1)[0]
        if top_reason == "no_active_event":
            return "WAITING_FOR_MACRO_EVENT", "healthy idle state; models are scanning normally and waiting for a configured event"
    return "MONITORING", "runtime is alive and monitoring inputs"


def journal_stats() -> dict:
    out = {
        "closed_trades": 0,
        "open_trades": 0,
        "total_pnl_abs": 0.0,
        "win_rate": None,
        "avg_r": None,
        "per_symbol": {},
    }
    if not DATA_DB.exists():
        return out

    conn = sqlite3.connect(DATA_DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS closed_trades,
              AVG(CASE WHEN r_multiple > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
              AVG(r_multiple) AS avg_r,
              SUM(COALESCE(pnl_abs, 0.0)) AS total_pnl_abs
            FROM trades
            WHERE status='CLOSED'
            """
        ).fetchone()
        if row:
            out["closed_trades"] = int(row["closed_trades"] or 0)
            out["win_rate"] = float(row["win_rate"]) if row["win_rate"] is not None else None
            out["avg_r"] = float(row["avg_r"]) if row["avg_r"] is not None else None
            out["total_pnl_abs"] = float(row["total_pnl_abs"] or 0.0)

        row = conn.execute("SELECT COUNT(*) AS open_trades FROM trades WHERE status='OPEN'").fetchone()
        out["open_trades"] = int(row["open_trades"] or 0) if row else 0

        for row in conn.execute(
            """
            SELECT symbol,
                   SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END) AS closed_trades,
                   SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) AS open_trades,
                   AVG(CASE WHEN status='CLOSED' THEN r_multiple END) AS avg_r,
                   AVG(CASE WHEN status='CLOSED' AND r_multiple > 0 THEN 1.0
                            WHEN status='CLOSED' THEN 0.0 END) AS win_rate,
                   SUM(CASE WHEN status='CLOSED' THEN COALESCE(pnl_abs,0.0) ELSE 0.0 END) AS total_pnl_abs
            FROM trades
            GROUP BY symbol
            ORDER BY symbol
            """
        ):
            out["per_symbol"][row["symbol"]] = {
                "closed_trades": int(row["closed_trades"] or 0),
                "open_trades": int(row["open_trades"] or 0),
                "avg_r": float(row["avg_r"]) if row["avg_r"] is not None else None,
                "win_rate": float(row["win_rate"]) if row["win_rate"] is not None else None,
                "total_pnl_abs": float(row["total_pnl_abs"] or 0.0),
            }
    finally:
        conn.close()
    return out


def ibkr_account_snapshot() -> dict:
    try:
        from ib_insync import IB
    except Exception as exc:
        return {"connected": False, "error": f"ib_insync unavailable: {exc}"}

    ib = IB()
    try:
        ib.connect("127.0.0.1", 7497, clientId=98, timeout=8)
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
                    "avgCost": float(getattr(p, "avgCost", 0.0) or 0.0),
                }
            )
        return {"connected": True, "summary": summary, "positions": positions}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def stderr_warning_summary() -> Counter:
    counter: Counter = Counter()
    stderr_path = STDERR_LOG
    if not stderr_path.exists():
        return counter
    for line in stderr_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-300:]:
        if "Error " in line or "[WARN]" in line:
            if "EUR.USD" in line or "symbol='EUR'" in line:
                counter["EURUSD"] += 1
            if "USD.JPY" in line or "symbol='USD'" in line:
                counter["USDJPY"] += 1
            if "symbol='MES'" in line or "MESU6" in line:
                counter["MES"] += 1
            if "symbol='MNQ'" in line or "MNQU6" in line:
                counter["MNQ"] += 1
            if "symbol='ZT'" in line or "ZTM6" in line:
                counter["ZT"] += 1
            if "symbol='ZN'" in line or "ZNU6" in line:
                counter["ZN"] += 1
            if "BTC.USD" in line or "symbol='BTC'" in line:
                counter["BTC"] += 1
            if "symbol='CL'" in line:
                counter["CL"] += 1
            if "symbol='SR3'" in line:
                counter["SR3"] += 1
    return counter


def write_report(lines: list[str]) -> Path:
    ts = now_utc().strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"five_models_kpi_report_{ts}.md"
    latest = REPORT_DIR / "five_models_kpi_report_latest.md"
    text = "\n".join(lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    running, pid = launchd_running()
    hb = heartbeat()
    hb_ts = None
    if hb.get("ts"):
        try:
            hb_ts = datetime.fromisoformat(hb["ts"])
        except Exception:
            hb_ts = None

    log_stats = runtime_log_stats()
    journal = journal_stats()
    account = ibkr_account_snapshot()
    warnings = stderr_warning_summary()

    lines: list[str] = []
    lines.append("InsightBridge Five Models KPI Report")
    lines.append("============================================================")
    lines.append(f"base: {BASE}")
    lines.append(f"generated_at: {fmt_dt(now_utc())}")
    lines.append("------------------------------------------------------------")
    lines.append(f"service_running: {running}")
    lines.append(f"service_pid: {pid if pid else 'none'}")
    lines.append(f"heartbeat_last_seen: {fmt_dt(hb_ts)}")
    lines.append(f"heartbeat_age: {fmt_age(hb_ts)}")
    lines.append(f"heartbeat_halted: {hb.get('status', {}).get('halted', 'N/A')}")
    lines.append(f"configured_symbols: {', '.join(hb.get('status', {}).get('symbols', [])) or 'N/A'}")
    lines.append("------------------------------------------------------------")

    lines.append("Runtime Activity")
    lines.append("------------------------------------------------------------")
    lines.append(f"first_seen_in_log: {fmt_dt(log_stats['first_seen'])}")
    lines.append(f"last_seen_in_log: {fmt_dt(log_stats['last_seen'])}")
    lines.append(f"total_evaluations: {log_stats['total_evaluations']}")
    lines.append(f"holds: {log_stats['holds']}")
    lines.append(f"buy_signals: {log_stats['buy_signals']}")
    lines.append(f"sell_signals: {log_stats['sell_signals']}")
    lines.append(f"orders_ready_for_ibkr: {log_stats['orders_ready']}")
    lines.append(f"reconnects: {log_stats['reconnects']}")
    lines.append(f"halts_logged: {log_stats['halts']}")
    phase, phase_detail = classify_runtime_phase(log_stats)
    lines.append(f"runtime_phase: {phase}")
    lines.append(f"runtime_phase_detail: {phase_detail}")
    if log_stats["reason_counts"]:
        top_reason, top_count = log_stats["reason_counts"].most_common(1)[0]
        lines.append(f"top_runtime_reason: {top_reason} ({top_count})")
    lines.append("------------------------------------------------------------")

    lines.append("IBKR Account Snapshot")
    lines.append("------------------------------------------------------------")
    if account.get("connected"):
        summary = account.get("summary", {})
        lines.append(f"NetLiquidation: {summary.get('NetLiquidation', 'N/A')}")
        lines.append(f"AvailableFunds: {summary.get('AvailableFunds', 'N/A')}")
        lines.append(f"TotalCashValue: {summary.get('TotalCashValue', 'N/A')}")
        lines.append(f"UnrealizedPnL: {summary.get('UnrealizedPnL', 'N/A')}")
        lines.append(f"RealizedPnL: {summary.get('RealizedPnL', 'N/A')}")
        positions = account.get("positions", [])
        lines.append(f"broker_positions: {len(positions)}")
        for pos in positions:
            lines.append(
                f"  - {pos['symbol']}: qty={fmt_num(pos['quantity'], 6)} avgCost={fmt_num(pos['avgCost'], 4)}"
            )
    else:
        lines.append(f"IBKR snapshot unavailable: {account.get('error', 'unknown error')}")
    lines.append("------------------------------------------------------------")

    lines.append("Trade Journal")
    lines.append("------------------------------------------------------------")
    lines.append(f"closed_trades: {journal['closed_trades']}")
    lines.append(f"open_trades: {journal['open_trades']}")
    lines.append(f"total_pnl_abs: {fmt_num(journal['total_pnl_abs'])}")
    lines.append(f"win_rate: {fmt_num(journal['win_rate'] * 100, 2) + '%' if journal['win_rate'] is not None else 'N/A'}")
    lines.append(f"avg_r: {fmt_num(journal['avg_r'], 4) if journal['avg_r'] is not None else 'N/A'}")
    lines.append("------------------------------------------------------------")

    lines.append("Per Symbol Runtime / KPI")
    lines.append("------------------------------------------------------------")
    all_symbols = ["BTC", "EURUSD", "USDJPY", "MES", "MNQ", "CL", "ZT", "ZN", "SR3"]
    for symbol in all_symbols:
        last_eval = log_stats["last_eval_by_symbol"].get(symbol)
        per_j = journal["per_symbol"].get(symbol, {})
        lines.append(f"[{symbol}]")
        lines.append(f"  last_eval: {fmt_dt(last_eval)} | age={fmt_age(last_eval)}")
        lines.append(f"  eval_count: {log_stats['symbol_counts'].get(symbol, 0)}")
        lines.append(f"  last_reason: {log_stats['last_reason_by_symbol'].get(symbol, 'N/A')}")
        lines.append(f"  recent_warning_count: {warnings.get(symbol, 0)}")
        lines.append(f"  closed_trades: {per_j.get('closed_trades', 0)}")
        lines.append(f"  open_trades: {per_j.get('open_trades', 0)}")
        lines.append(f"  total_pnl_abs: {fmt_num(per_j.get('total_pnl_abs', 0.0))}")
        lines.append(
            f"  win_rate: {fmt_num(per_j['win_rate'] * 100, 2) + '%' if per_j.get('win_rate') is not None else 'N/A'}"
        )
        lines.append(f"  avg_r: {fmt_num(per_j['avg_r'], 4) if per_j.get('avg_r') is not None else 'N/A'}")
        lines.append("------------------------------------------------------------")

    lines.append("Model Groups")
    lines.append("------------------------------------------------------------")
    for group, symbols in SYMBOL_GROUPS.items():
        group_eval = sum(log_stats["symbol_counts"].get(s, 0) for s in symbols)
        group_warn = sum(warnings.get(s, 0) for s in symbols)
        group_closed = sum(journal["per_symbol"].get(s, {}).get("closed_trades", 0) for s in symbols)
        group_open = sum(journal["per_symbol"].get(s, {}).get("open_trades", 0) for s in symbols)
        group_pnl = sum(journal["per_symbol"].get(s, {}).get("total_pnl_abs", 0.0) for s in symbols)
        lines.append(f"[{group}] symbols={', '.join(symbols)}")
        lines.append(f"  evaluations: {group_eval}")
        lines.append(f"  warning_count: {group_warn}")
        lines.append(f"  closed_trades: {group_closed}")
        lines.append(f"  open_trades: {group_open}")
        lines.append(f"  total_pnl_abs: {fmt_num(group_pnl)}")
        lines.append("------------------------------------------------------------")

    report_path = write_report(lines)
    print("\n".join(lines))
    print(f"report_file: {report_path}")
    print(f"latest_report: {REPORT_DIR / 'five_models_kpi_report_latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
