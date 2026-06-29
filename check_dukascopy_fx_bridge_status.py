#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import urlopen

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
PID_FILE = BASE / "reports" / "dukascopy_bridge" / "dukascopy_fx_backend.pid"
LOG_FILE = BASE / "reports" / "dukascopy_bridge" / "dukascopy_fx_backend.log"
ROOT = "http://127.0.0.1:8001"
LAUNCHD_LABEL = "com.insightbridge.dukascopy.fx.bridge"
TARGET_RUNTIME_PAIRS = [
    "AUD/USD",
    "NZD/USD",
    "EUR/USD",
    "USD/JPY",
    "GBP/USD",
    "AUD/JPY",
    "NZD/JPY",
]


def fetch_json(path: str) -> dict | None:
    try:
        with urlopen(ROOT + path, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def fmt_age(ts: str | None) -> str:
    if not ts:
        return "n/a"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        sec = max(0, int(delta.total_seconds()))
        if sec < 60:
            return f"{sec}s"
        if sec < 3600:
            return f"{sec // 60}m {sec % 60}s"
        return f"{sec // 3600}h {(sec % 3600) // 60}m"
    except ValueError:
        return ts


def launchd_pid() -> tuple[bool, str | None, str]:
    proc = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, None, "not_loaded"

    pid = None
    state = "loaded"
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("state ="):
            state = line.split("=", 1)[1].strip()
        elif line.startswith("pid ="):
            raw = line.split("=", 1)[1].strip()
            if raw != "0":
                pid = raw
    return True, pid, state


def pair_status(pair: str, configured: set[str], latest_ticks: dict) -> tuple[str, str]:
    if pair not in configured:
        return "NOT_CONFIGURED", "not in current Dukascopy runtime config"
    tick = latest_ticks.get(pair) or {}
    if tick.get("timestamp"):
        return (
            "LIVE_TICKING",
            f"mid={tick.get('mid')} spread_pips={tick.get('spread_pips')} age={fmt_age(tick.get('timestamp'))}",
        )
    return "CONFIGURED_WAITING_FIRST_TICK", "configured but no live tick has arrived yet"


def main() -> int:
    health = fetch_json("/api/health")
    duk = fetch_json("/api/broker/dukascopy/status")
    pos = fetch_json("/api/broker/positions")

    print("InsightBridge Dukascopy FX Bridge Status")
    print("=" * 60)
    print(f"backend_pid_file: {PID_FILE} | exists={PID_FILE.exists()}")
    print(f"backend_log: {LOG_FILE} | exists={LOG_FILE.exists()}")
    launchd_loaded, launchd_live_pid, launchd_state = launchd_pid()
    print(f"launchd_label: {LAUNCHD_LABEL} | loaded={launchd_loaded} | state={launchd_state} | pid={launchd_live_pid or 'none'}")
    pid_text = PID_FILE.read_text().strip() if PID_FILE.exists() else ""
    pid_alive = False
    if pid_text.isdigit():
        pid_alive = os.path.exists(f"/proc/{pid_text}") if os.path.exists("/proc") else True
        try:
            os.kill(int(pid_text), 0)
            pid_alive = True
        except OSError:
            pid_alive = False
    print(f"backend_pid: {pid_text or 'none'} | alive={pid_alive}")
    print("-" * 60)

    if not health:
        print("backend_api: UNREACHABLE")
        print("Overall: ATTENTION")
        return 1

    print(f"backend_api: LIVE | status={health.get('status')} | pairs={', '.join(health.get('pairs', []))}")
    print(f"event_state: {health.get('event_state')}")
    print("-" * 60)

    configured_pairs = set(health.get("pairs", []))
    latest_ticks = duk.get("latest_ticks", {}) if duk else {}
    print("[Pair Runtime Status]")
    for pair in TARGET_RUNTIME_PAIRS:
        state, detail = pair_status(pair, configured_pairs, latest_ticks)
        print(f"[{pair}] {state}")
        print(f"  detail: {detail}")
    extra_pairs = sorted(configured_pairs.difference(TARGET_RUNTIME_PAIRS))
    if extra_pairs:
        print("extra_configured_pairs:", ", ".join(extra_pairs))
    print("-" * 60)

    if duk:
        print("[Dukascopy Adapter]")
        print(f"connected: {duk.get('connected')}")
        print(f"status: {duk.get('status')}")
        print(f"account_id: {duk.get('account_id')}")
        print(f"equity: {duk.get('equity')}")
        print(f"last_seen: {duk.get('last_seen')} | age={fmt_age(duk.get('last_seen'))}")
        latest_ticks = duk.get("latest_ticks", {})
        if latest_ticks:
            for pair, tick in latest_ticks.items():
                print(f"tick {pair}: mid={tick.get('mid')} spread_pips={tick.get('spread_pips')} age={fmt_age(tick.get('timestamp'))}")
        else:
            print("tick: none yet")
        print("-" * 60)

    if pos:
        print("[Broker Positions]")
        print(f"count: {pos.get('count')}")
        for item in pos.get("positions", [])[:10]:
            print(
                f"{item.get('pair')} | {item.get('direction')} | {item.get('status')} | "
                f"entry={item.get('entry_price')} | label={item.get('label')}"
            )
        print("-" * 60)

    if duk and duk.get("connected"):
        print("Overall: LIVE")
        return 0

    print("Overall: BACKEND_READY_ADAPTER_IDLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
