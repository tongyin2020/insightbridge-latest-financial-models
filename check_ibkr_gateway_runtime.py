#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
RUNTIME_DIR = BASE / "ibkr_runtime"
PID_FILE = RUNTIME_DIR / "ib_gateway.pid"
STATE_FILE = RUNTIME_DIR / "runtime_state.json"
LAUNCH_LOG = RUNTIME_DIR / "logs" / "ib_gateway_launch.log"
CHECK_SCRIPT = BASE / "check_ibkr_paper_setup.py"


@dataclass
class PortState:
    ok: bool
    host: str
    port: int
    detail: str


def port_state(port: int, host: str = "127.0.0.1") -> PortState:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.5)
    try:
        rc = sock.connect_ex((host, port))
        ok = rc == 0
        detail = "reachable" if ok else f"not reachable (connect_ex={rc})"
        return PortState(ok=ok, host=host, port=port, detail=detail)
    finally:
        sock.close()


def read_runtime_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text())


def read_pid() -> tuple[str | None, bool]:
    if not PID_FILE.exists():
        code = subprocess.run(
            ["pgrep", "-f", "ibcalpha.ibc.IbcGateway"],
            capture_output=True,
            text=True,
        )
        pids = [line.strip() for line in code.stdout.splitlines() if line.strip()]
        if pids:
            return pids[-1], True
        return None, False
    pid = PID_FILE.read_text().strip()
    if not pid:
        return None, False
    alive = subprocess.call(["kill", "-0", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    if alive:
        return pid, True
    code = subprocess.run(
        ["pgrep", "-f", "ibcalpha.ibc.IbcGateway"],
        capture_output=True,
        text=True,
    )
    pids = [line.strip() for line in code.stdout.splitlines() if line.strip()]
    if pids:
        return pids[-1], True
    return pid, False


def tail_log(path: Path, lines: int = 8) -> list[str]:
    if not path.exists():
        return []
    content = path.read_text(errors="ignore").splitlines()
    return content[-lines:]


def run_readiness() -> dict[str, Any]:
    proc = subprocess.run(
        ["/opt/anaconda3/bin/python3", str(CHECK_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        timeout=25,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or proc.stdout.strip(), "returncode": proc.returncode}
    return {"ok": True, "payload": json.loads(proc.stdout)}


def main() -> int:
    state = read_runtime_state()
    api_port = int(state.get("api_port", 7497))
    command_port = int(state.get("command_server_port", 7462))
    pid, running = read_pid()
    api_state = asdict(port_state(api_port))
    command_state = asdict(port_state(command_port))
    readiness = run_readiness()

    print("IBKR Paper Gateway Runtime Check")
    print("=" * 60)
    print(f"base: {BASE}")
    print(f"generated_at: {datetime.now().isoformat(timespec='seconds')}")
    print(f"pid_file: {PID_FILE}")
    print(f"pid: {pid or 'none'}")
    print(f"process_running: {running}")
    print("-" * 60)
    print(f"api_port_{api_port}: {api_state['detail']}")
    print(f"command_server_{command_port}: {command_state['detail']}")
    print("-" * 60)
    print(f"launch_log: {LAUNCH_LOG}")
    log_tail = tail_log(LAUNCH_LOG)
    if log_tail:
        for line in log_tail:
            print(f"log> {line}")
    else:
        print("log> no log lines yet")
    print("-" * 60)
    if readiness.get("ok"):
        payload = readiness["payload"]
        checks = payload.get("checks", {})
        read_only = checks.get("read_only_connection", {})
        print("readiness_check: OK")
        print(f"paper_port: {checks.get('paper_port', {}).get('detail', 'n/a')}")
        print(f"read_only_connection: {read_only.get('detail', 'n/a')}")
        extra = read_only.get("extra") or {}
        if extra.get("accounts"):
            print(f"accounts: {extra['accounts']}")
        if extra.get("account_summary"):
            print(f"account_summary: {extra['account_summary']}")
    else:
        print("readiness_check: ATTENTION")
        print(f"error: {readiness.get('error', 'unknown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
