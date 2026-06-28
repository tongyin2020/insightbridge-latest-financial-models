#!/usr/bin/env python3
"""
Local watchdog for IBKR paper-session availability.

Purpose:
- detect when TWS / IB Gateway / paper port 7497 goes down
- detect when paper account API becomes available again
- write a simple state file and append a log
- optionally send Telegram alerts via existing EventAlpha notifier env vars

This script does not place any orders.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
STATE_DIR = BASE / "reports" / "ibkr_watchdog"
STATE_FILE = STATE_DIR / "ibkr_watchdog_state.json"
LOG_FILE = STATE_DIR / "ibkr_watchdog.log"
HOST = "127.0.0.1"
PORT = 7497


def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def process_ok() -> tuple[bool, list[str]]:
    matches: list[str] = []
    for pattern in ["Trader Workstation", "IB Gateway", "IBKR Desktop", "tws", "ibgateway"]:
        code, out, _ = run_cmd(["pgrep", "-fal", pattern])
        if code == 0 and out:
            matches.extend([line for line in out.splitlines() if line.strip()])
    uniq = sorted(set(matches))
    return bool(uniq), uniq


def port_ok() -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.5)
    try:
        return sock.connect_ex((HOST, PORT)) == 0
    finally:
        sock.close()


def read_only_ok() -> tuple[bool, dict]:
    try:
        from ib_insync import IB  # type: ignore
    except Exception as exc:
        return False, {"error": f"ib_insync import failed: {exc}"}

    ib = IB()
    try:
        ib.connect(HOST, PORT, clientId=98, timeout=4, readonly=True)
        accounts = ib.managedAccounts()
        summary = {}
        for row in ib.accountSummary():
            if row.tag in {"AvailableFunds", "NetLiquidation", "TotalCashValue", "RealizedPnL", "UnrealizedPnL"}:
                summary[row.tag] = row.value
        positions = ib.positions()
        return True, {
            "accounts": accounts,
            "position_count": len(positions),
            "account_summary": summary,
        }
    except Exception as exc:
        return False, {"error": str(exc)}
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def load_last_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def append_log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(message + "\n")


def maybe_send_telegram(message: str) -> bool:
    try:
        if str(BASE) not in sys.path:
            sys.path.insert(0, str(BASE))
        from eventalpha_core.telegram_notify import EventAlphaTelegramNotifier  # type: ignore

        notifier = EventAlphaTelegramNotifier.from_env()
        if not notifier.enabled:
            return False
        notifier.send_message(message)
        return True
    except Exception:
        return False


def main() -> int:
    proc_live, proc_matches = process_ok()
    port_live = port_ok()
    api_live = False
    api_extra: dict = {}
    if port_live:
        api_live, api_extra = read_only_ok()

    current = {
        "checked_at": now_str(),
        "process_live": proc_live,
        "process_matches": proc_matches,
        "port_live": port_live,
        "api_live": api_live,
        "api_extra": api_extra,
        "overall": "UP" if (proc_live and port_live and api_live) else "DOWN",
    }

    previous = load_last_state()
    prev_overall = previous.get("overall")
    changed = prev_overall != current["overall"]

    save_state(current)

    line = f"[{current['checked_at']}] overall={current['overall']} process={proc_live} port={port_live} api={api_live}"
    append_log(line)

    if changed:
        transition = f"IBKR paper session changed: {prev_overall or 'UNKNOWN'} -> {current['overall']}"
        append_log(f"[{current['checked_at']}] {transition}")
        maybe_send_telegram(f"EventAlpha IBKR Watchdog\n{transition}\nprocess={proc_live} port={port_live} api={api_live}")

    print("IBKR Session Watchdog")
    print("=" * 60)
    print(f"checked_at: {current['checked_at']}")
    print(f"process_live: {proc_live}")
    print(f"port_live: {port_live}")
    print(f"api_live: {api_live}")
    if api_extra:
        print(f"api_extra: {json.dumps(api_extra, ensure_ascii=False)}")
    print(f"overall: {current['overall']}")
    print(f"state_file: {STATE_FILE}")
    print(f"log_file: {LOG_FILE}")
    print(f"state_changed: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
