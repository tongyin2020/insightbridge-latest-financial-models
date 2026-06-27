from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
RUNNER = BASE / "run_eventalpha_paper.py"
RUNTIME_DIR = BASE / "reports" / "runtime_logs"
STATE_FILE = RUNTIME_DIR / "eventalpha_runtime_state.json"
LOCK_FILE = RUNTIME_DIR / "eventalpha_runtime.lock"
LOG_FILE = RUNTIME_DIR / "eventalpha_runtime.log"


@dataclass
class EventSpec:
    event_type: str
    title: str
    top_n: int = 5


DEFAULT_EVENTS = [
    EventSpec("cpi", "Continuous scan: CPI regime monitor"),
    EventSpec("fomc", "Continuous scan: FOMC regime monitor"),
    EventSpec("nfp", "Continuous scan: NFP regime monitor"),
    EventSpec("opec", "Continuous scan: OPEC regime monitor"),
    EventSpec("eia_inventory", "Continuous scan: EIA inventory monitor"),
    EventSpec("geopolitical", "Continuous scan: Geopolitical regime monitor"),
    EventSpec("liquidity_shock", "Continuous scan: Liquidity shock monitor"),
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")


def append_log(line: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"[{ts()}] {line}\n")


def save_state(payload: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ensure_singleton() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            old_pid = 0
        if old_pid > 0:
            try:
                Path(f"/proc/{old_pid}")
            except Exception:
                pass
            try:
                import os

                os.kill(old_pid, 0)
                raise SystemExit(f"Another EventAlpha continuous runner is already active (PID {old_pid}).")
            except OSError:
                pass
    LOCK_FILE.write_text(str(__import__("os").getpid()), encoding="utf-8")


def clear_lock() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def resolve_events(names: str | None, top_n: int) -> list[EventSpec]:
    if not names:
        return [EventSpec(x.event_type, x.title, top_n) for x in DEFAULT_EVENTS]
    wanted = {name.strip() for name in names.split(",") if name.strip()}
    resolved = [EventSpec(x.event_type, x.title, top_n) for x in DEFAULT_EVENTS if x.event_type in wanted]
    if not resolved:
        raise SystemExit(f"No valid event types found in: {names}")
    return resolved


def run_one_event(python_bin: str, event: EventSpec, telegram_alerts: bool, timeout_seconds: int) -> dict[str, Any]:
    cmd = [
        python_bin,
        str(RUNNER),
        "--event-type",
        event.event_type,
        "--title",
        event.title,
        "--top-n",
        str(event.top_n),
        "--telegram-alerts" if telegram_alerts else "--no-telegram-alerts",
    ]
    started = time.time()
    completed = subprocess.run(
        cmd,
        cwd=str(BASE),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    duration = round(time.time() - started, 2)
    saved_path = ""
    telegram_line = ""
    for line in completed.stdout.splitlines():
        if line.startswith("Saved: "):
            saved_path = line.replace("Saved: ", "", 1).strip()
        if line.startswith("Telegram status: "):
            telegram_line = line.strip()
    return {
        "event_type": event.event_type,
        "title": event.title,
        "returncode": completed.returncode,
        "duration_seconds": duration,
        "saved_report": saved_path,
        "telegram_status": telegram_line,
        "stdout_tail": completed.stdout.splitlines()[-12:],
        "stderr_tail": completed.stderr.splitlines()[-12:],
    }


def run_cycle(
    *,
    python_bin: str,
    events: list[EventSpec],
    telegram_alerts: bool,
    timeout_seconds: int,
    sleep_between_events: int,
    trigger: str,
    cycle_number: int,
) -> dict[str, Any]:
    cycle_started = utc_now()
    append_log(f"cycle {cycle_number} start trigger={trigger}")
    results = []
    ok_count = 0
    for idx, event in enumerate(events, start=1):
        append_log(f"event {idx}/{len(events)} start type={event.event_type}")
        result = run_one_event(python_bin, event, telegram_alerts, timeout_seconds)
        results.append(result)
        if result["returncode"] == 0:
            ok_count += 1
            append_log(
                f"event {event.event_type} ok duration={result['duration_seconds']}s report={result['saved_report'] or 'n/a'}"
            )
        else:
            append_log(
                f"event {event.event_type} fail rc={result['returncode']} duration={result['duration_seconds']}s"
            )
        if idx < len(events) and sleep_between_events > 0:
            time.sleep(sleep_between_events)
    cycle_finished = utc_now()
    state = {
        "status": "ok" if ok_count == len(events) else "attention",
        "trigger": trigger,
        "cycle_number": cycle_number,
        "started_at": cycle_started.isoformat(),
        "finished_at": cycle_finished.isoformat(),
        "duration_seconds": round((cycle_finished - cycle_started).total_seconds(), 2),
        "event_count": len(events),
        "ok_count": ok_count,
        "fail_count": len(events) - ok_count,
        "telegram_alerts": telegram_alerts,
        "events": [asdict(e) for e in events],
        "results": results,
    }
    save_state(state)
    append_log(
        f"cycle {cycle_number} finish status={state['status']} ok={ok_count}/{len(events)} duration={state['duration_seconds']}s"
    )
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuous local EventAlpha runner")
    parser.add_argument("--interval-minutes", type=int, default=30)
    parser.add_argument("--sleep-between-events", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--event-types", default="")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--python-bin", default=sys.executable or "/opt/anaconda3/bin/python3")
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--telegram-alerts", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    ensure_singleton()
    try:
        events = resolve_events(args.event_types or None, args.top_n)
        cycle_number = int(load_state().get("cycle_number", 0))
        while True:
            cycle_number += 1
            run_cycle(
                python_bin=args.python_bin,
                events=events,
                telegram_alerts=bool(args.telegram_alerts),
                timeout_seconds=args.timeout_seconds,
                sleep_between_events=args.sleep_between_events,
                trigger=args.trigger if cycle_number == 1 else "loop",
                cycle_number=cycle_number,
            )
            if args.once:
                break
            time.sleep(max(60, args.interval_minutes * 60))
    finally:
        clear_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
