from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
RUNNER = BASE / "eventalpha_continuous_runner.py"
RUNTIME_DIR = BASE / "reports" / "runtime_logs"
PID_FILE = RUNTIME_DIR / "eventalpha_runtime.pid"
LOG_FILE = RUNTIME_DIR / "eventalpha_runtime.log"
STATE_FILE = RUNTIME_DIR / "eventalpha_runtime_state.json"


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def load_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def cmd_start(args: argparse.Namespace) -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    pid = load_pid()
    if pid and is_running(pid):
        print(f"[start] already running PID {pid}")
        print(f"[start] log: {LOG_FILE}")
        return 0
    with LOG_FILE.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [
                args.python_bin,
                str(RUNNER),
                "--interval-minutes",
                str(args.interval_minutes),
                "--sleep-between-events",
                str(args.sleep_between_events),
                "--timeout-seconds",
                str(args.timeout_seconds),
                "--top-n",
                str(args.top_n),
                "--trigger",
                "background",
                "--event-types",
                args.event_types,
                "--telegram-alerts" if args.telegram_alerts else "--no-telegram-alerts",
            ],
            cwd=str(BASE),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"[start] launched EventAlpha background runner PID {proc.pid}")
    print(f"[start] log: {LOG_FILE}")
    return 0


def cmd_stop() -> int:
    pid = load_pid()
    if not pid:
        print("[stop] no PID file found")
        return 0
    if not is_running(pid):
        PID_FILE.unlink(missing_ok=True)
        print(f"[stop] stale PID file cleared ({pid})")
        return 0
    os.killpg(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    print(f"[stop] stopped EventAlpha runner PID {pid}")
    return 0


def cmd_status() -> int:
    pid = load_pid()
    running = bool(pid and is_running(pid))
    print("InsightBridge EventAlpha Runtime Status")
    print("=" * 60)
    print(f"base: {BASE}")
    print(f"runner_pid: {pid or 'none'}")
    print(f"runner_running: {running}")
    print(f"log_file: {LOG_FILE}")
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding='utf-8'))
            print(f"last_state: {json.dumps(state, ensure_ascii=False)}")
        except Exception:
            print("last_state: unreadable")
    else:
        print("last_state: none")
    return 0


def cmd_once(args: argparse.Namespace) -> int:
    return subprocess.call(
        [
            args.python_bin,
            str(RUNNER),
            "--once",
            "--interval-minutes",
            str(args.interval_minutes),
            "--sleep-between-events",
            str(args.sleep_between_events),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--top-n",
            str(args.top_n),
            "--trigger",
            "manual_once",
            "--event-types",
            args.event_types,
            "--telegram-alerts" if args.telegram_alerts else "--no-telegram-alerts",
        ],
        cwd=str(BASE),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage continuous EventAlpha runtime")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--interval-minutes", type=int, default=30)
        p.add_argument("--sleep-between-events", type=int, default=3)
        p.add_argument("--timeout-seconds", type=int, default=600)
        p.add_argument("--top-n", type=int, default=5)
        p.add_argument("--event-types", default="")
        p.add_argument("--python-bin", default=sys.executable or "/opt/anaconda3/bin/python3")
        p.add_argument("--telegram-alerts", action=argparse.BooleanOptionalAction, default=True)

    add_common(sub.add_parser("start"))
    sub.add_parser("stop")
    sub.add_parser("status")
    add_common(sub.add_parser("once"))

    args = parser.parse_args()
    if args.cmd == "start":
        return cmd_start(args)
    if args.cmd == "stop":
        return cmd_stop()
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "once":
        return cmd_once(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
