#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


BASE = Path(__file__).resolve().parent
LABEL = "com.insightbridge.five-models.paper"
PLIST = Path("/Users/tongyin/Library/LaunchAgents/com.insightbridge.five-models.paper.plist")
RUNTIME_DIR = BASE / "reports" / "runtime"
HEARTBEAT = RUNTIME_DIR / "heartbeat.json"
CONTINUOUS_LOG = RUNTIME_DIR / "continuous.log"
STDOUT_LOG = RUNTIME_DIR / "launchd_stdout.log"
STDERR_LOG = RUNTIME_DIR / "launchd_stderr.log"
MANUAL_PID_FILE = RUNTIME_DIR / "five_models_paper_live.pid"
MANUAL_LOG = RUNTIME_DIR / "five_models_paper_live.log"
FRESH_SECONDS = 150.0

SYMBOL_ALIASES = {
    "EURUSD": ["EUR.USD", "symbol='EUR'", "localSymbol='EUR.USD'"],
    "USDJPY": ["USD.JPY", "symbol='USD'", "localSymbol='USD.JPY'"],
    "MES": ["MESU6", "MESZ6", "MESH7", "symbol='MES'"],
    "MNQ": ["MNQU6", "MNQZ6", "MNQH7", "symbol='MNQ'"],
    "ZT": ["ZTM6", "ZTU6", "ZTZ6", "symbol='ZT'"],
    "ZN": ["ZNU6", "ZNZ6", "ZNH7", "symbol='ZN'"],
    "BTC": ["BTC.USD", "symbol='BTC'", "localSymbol='BTC.USD'"],
    "CL": ["symbol='CL'", "localSymbol='CL"],
    "SR3": ["symbol='SR3'", "localSymbol='SR3"],
}

MODEL_GROUPS = {
    "CRYPTO": ["BTC"],
    "FX": ["EURUSD", "USDJPY"],
    "INDEX": ["MES", "MNQ"],
    "OIL": ["CL"],
    "TREASURY": ["ZT", "ZN", "SR3"],
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def load_plist_symbols() -> list[str]:
    if not PLIST.exists():
        return []
    try:
        with PLIST.open("rb") as fh:
            payload = plistlib.load(fh)
        args = payload.get("ProgramArguments", [])
        if "--symbols" in args:
            idx = args.index("--symbols")
            if idx + 1 < len(args):
                return [s.strip().upper() for s in str(args[idx + 1]).split(",") if s.strip()]
    except Exception:
        pass
    return []


def launchd_info() -> dict:
    cmd = ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = proc.stdout if proc.returncode == 0 else proc.stderr
    running = False
    pid = None
    state = "unknown"
    if text:
        m = re.search(r"\bstate = (\w+)", text)
        if m:
            state = m.group(1)
            running = state == "running"
        m = re.search(r"\bpid = (\d+)", text)
        if m:
            pid = int(m.group(1))
    return {"running": running, "pid": pid, "state": state, "raw": text}


def manual_runner_info() -> dict:
    if not MANUAL_PID_FILE.exists():
        return {"configured": False, "running": False, "pid": None}
    try:
        pid = int(MANUAL_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return {"configured": True, "running": False, "pid": None}

    try:
        os.kill(pid, 0)
        running = True
    except OSError:
        running = False
    return {"configured": True, "running": running, "pid": pid}


def heartbeat_info() -> dict:
    if not HEARTBEAT.exists():
        return {"exists": False, "fresh": False, "age_s": None, "symbols": []}
    try:
        payload = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
        epoch = float(payload.get("epoch", 0.0))
        age_s = max(0.0, now_utc().timestamp() - epoch)
        status = payload.get("status", {}) or {}
        return {
            "exists": True,
            "fresh": age_s <= FRESH_SECONDS,
            "age_s": round(age_s, 1),
            "symbols": list(status.get("symbols", [])),
            "scanned": status.get("scanned"),
            "halted": status.get("halted"),
            "pid": payload.get("pid"),
            "ts": payload.get("ts"),
        }
    except Exception as exc:
        return {"exists": True, "fresh": False, "age_s": None, "symbols": [], "error": str(exc)}


def parse_continuous_log() -> tuple[dict, dict]:
    latest_eval: dict[str, datetime] = {}
    reason_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if not CONTINUOUS_LOG.exists():
        return latest_eval, reason_counts
    for line in read_text(CONTINUOUS_LOG).splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("stage") != "evaluate":
            continue
        symbol = str(row.get("symbol", "")).upper()
        ts = row.get("ts")
        if symbol and ts:
            try:
                latest_eval[symbol] = datetime.fromisoformat(ts)
            except Exception:
                pass
        reason = str(row.get("reason", ""))
        if symbol and reason:
            reason_counts[symbol][reason] += 1
    return latest_eval, reason_counts


def stderr_warning_counts() -> dict[str, int]:
    lines = read_text(STDERR_LOG).splitlines()[-200:]
    counts: dict[str, int] = defaultdict(int)
    for line in lines:
        up = line.upper()
        for symbol, aliases in SYMBOL_ALIASES.items():
            if any(alias.upper() in up for alias in aliases):
                counts[symbol] += 1
    return counts


def format_age(dt: datetime | None) -> str:
    if not dt:
        return "N/A"
    delta = (now_utc() - dt.astimezone(timezone.utc)).total_seconds()
    if delta < 60:
        return "<1m"
    if delta < 3600:
        return f"{delta/60:.1f}m"
    return f"{delta/3600:.1f}h"


def symbol_status(symbol: str, configured: bool, service_running: bool, hb_fresh: bool,
                  hb_halted: bool | None, latest_eval: dict[str, datetime],
                  warn_counts: dict[str, int], service_label: str) -> tuple[str, str]:
    if not configured:
        return "NOT_CONFIGURED", "not in current runtime set"
    if not service_running:
        return "INTERRUPTED", f"{service_label} not running"
    if not hb_fresh:
        return "INTERRUPTED", "heartbeat stale or missing"
    if hb_halted:
        return "HALTED", "runtime heartbeat says halted=true"
    if symbol in latest_eval:
        age = (now_utc() - latest_eval[symbol].astimezone(timezone.utc)).total_seconds()
        if age <= FRESH_SECONDS:
            if warn_counts.get(symbol, 0) > 0:
                return "LIVE_WITH_WARNINGS", f"recent eval {format_age(latest_eval[symbol])}, warnings={warn_counts[symbol]}"
            return "LIVE", f"recent eval {format_age(latest_eval[symbol])}"
        return "ATTENTION", f"last eval stale: {format_age(latest_eval[symbol])}"
    if warn_counts.get(symbol, 0) > 0:
        return "ATTENTION", f"no recent eval, warnings={warn_counts[symbol]}"
    return "ATTENTION", "configured but no recent eval found"


def group_status(symbol_rows: dict[str, tuple[str, str]], group_symbols: list[str]) -> tuple[str, str]:
    rows = [symbol_rows[s][0] for s in group_symbols if s in symbol_rows]
    if not rows:
        return "NOT_CONFIGURED", "no symbols in this group are configured"
    if any(r == "INTERRUPTED" for r in rows):
        return "INTERRUPTED", "at least one configured symbol is interrupted"
    if any(r == "HALTED" for r in rows):
        return "HALTED", "runtime halted for at least one configured symbol"
    if all(r == "NOT_CONFIGURED" for r in rows):
        return "NOT_CONFIGURED", "group not in current runtime"
    if any(r == "ATTENTION" for r in rows):
        return "ATTENTION", "at least one configured symbol needs attention"
    if any(r == "LIVE_WITH_WARNINGS" for r in rows):
        return "LIVE_WITH_WARNINGS", "runtime is alive but market-data warnings exist"
    if any(r == "LIVE" for r in rows):
        return "LIVE", "group is actively scanning"
    return "UNKNOWN", "unable to classify group"


def infer_attached_runtime(configured_set: set[str], latest_eval: dict[str, datetime]) -> bool:
    if not configured_set:
        return False
    fresh = 0
    for symbol in configured_set:
        dt = latest_eval.get(symbol)
        if dt is None:
            continue
        age = (now_utc() - dt.astimezone(timezone.utc)).total_seconds()
        if age <= FRESH_SECONDS:
            fresh += 1
    return fresh >= max(1, min(3, len(configured_set)))


def main() -> int:
    launchd = launchd_info()
    manual = manual_runner_info()
    hb = heartbeat_info()
    configured = hb.get("symbols") or load_plist_symbols()
    configured_set = {str(s).upper() for s in configured}
    latest_eval, reasons = parse_continuous_log()
    warn_counts = stderr_warning_counts()
    service_running = launchd["running"] or manual["running"]
    attached_runtime = infer_attached_runtime(configured_set, latest_eval)
    if launchd["running"]:
        service_source = "launchd"
    elif manual["running"]:
        service_source = "manual_pid"
    elif hb.get("fresh") and attached_runtime:
        service_source = "attached_runtime"
    else:
        service_source = "none"

    print("InsightBridge Five Models Runtime Health")
    print("============================================================")
    print(f"base: {BASE}")
    print(f"launchd_label: {LABEL}")
    print(f"service_running: {launchd['running']}")
    print(f"service_state: {launchd['state']}")
    print(f"service_pid: {launchd['pid'] if launchd['pid'] else 'none'}")
    print(f"manual_runner_configured: {manual['configured']}")
    print(f"manual_runner_running: {manual['running']}")
    print(f"manual_runner_pid: {manual['pid'] if manual['pid'] else 'none'}")
    print(f"attached_runtime_detected: {attached_runtime}")
    print(f"effective_runtime_source: {service_source}")
    print(f"heartbeat_exists: {hb.get('exists', False)}")
    print(f"heartbeat_fresh: {hb.get('fresh', False)}")
    print(f"heartbeat_age: {hb.get('age_s', 'N/A')}s")
    print(f"heartbeat_halted: {hb.get('halted', 'N/A')}")
    print(f"configured_symbols: {', '.join(configured) if configured else 'none'}")
    print("------------------------------------------------------------")

    symbol_rows: dict[str, tuple[str, str]] = {}
    all_symbols = ["BTC", "EURUSD", "USDJPY", "MES", "MNQ", "CL", "ZT", "ZN", "SR3"]
    for symbol in all_symbols:
        status, detail = symbol_status(
            symbol=symbol,
            configured=symbol in configured_set,
            service_running=service_running or (service_source == "attached_runtime"),
            hb_fresh=bool(hb.get("fresh")),
            hb_halted=hb.get("halted"),
            latest_eval=latest_eval,
            warn_counts=warn_counts,
            service_label=service_source,
        )
        symbol_rows[symbol] = (status, detail)
        print(f"[{symbol}] {status}")
        print(f"  detail: {detail}")
        if symbol in latest_eval:
            print(f"  last_eval: {latest_eval[symbol].isoformat()} | age={format_age(latest_eval[symbol])}")
        if warn_counts.get(symbol):
            print(f"  recent_warnings: {warn_counts[symbol]}")
        if reasons.get(symbol):
            top_reason = sorted(reasons[symbol].items(), key=lambda x: x[1], reverse=True)[0]
            print(f"  top_reason: {top_reason[0]} ({top_reason[1]})")
        print("------------------------------------------------------------")

    print("Model Groups")
    print("------------------------------------------------------------")
    for group, symbols in MODEL_GROUPS.items():
        status, detail = group_status(symbol_rows, symbols)
        print(f"[{group}] {status}")
        print(f"  symbols: {', '.join(symbols)}")
        print(f"  detail: {detail}")
        print("------------------------------------------------------------")

    effective_running = service_running or (service_source == "attached_runtime")
    if effective_running and hb.get("fresh"):
        overall = "LIVE"
        if hb.get("halted"):
            overall = "HALTED"
    else:
        overall = "INTERRUPTED"

    print(f"Overall: {overall}")
    return 0 if overall == "LIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
