from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
RUNTIME_DIR = BASE / "reports" / "runtime_logs"
PID_FILE = RUNTIME_DIR / "eventalpha_runtime.pid"
STATE_FILE = RUNTIME_DIR / "eventalpha_runtime_state.json"
RUNS_DIR = BASE / "reports" / "eventalpha_runs"


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def latest_event_reports(limit: int = 7) -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted(RUNS_DIR.glob("eventalpha_paper_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def age_minutes(path: Path) -> float:
    return round((datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 60.0, 1)


def main() -> int:
    pid = None
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None
    running = bool(pid and is_running(pid))

    print("InsightBridge EventAlpha Continuous Check")
    print("=" * 60)
    print(f"base: {BASE}")
    print(f"runner_pid: {pid or 'none'}")
    print(f"runner_running: {running}")
    print("-" * 60)
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            print(f"last_cycle_status: {state.get('status')}")
            print(f"last_cycle_number: {state.get('cycle_number')}")
            print(f"last_started_at: {state.get('started_at')}")
            print(f"last_finished_at: {state.get('finished_at')}")
            print(f"last_duration_seconds: {state.get('duration_seconds')}")
            print(f"last_ok_count: {state.get('ok_count')}/{state.get('event_count')}")
        except Exception as exc:
            print(f"last_state_error: {exc}")
    else:
        print("last_state: none")
    print("-" * 60)
    reports = latest_event_reports()
    if not reports:
        print("recent_reports: none")
    else:
        for path in reports:
            print(f"{path.name} | age={age_minutes(path)}m")
    print("-" * 60)
    if running:
        print("Overall: LIVE")
    elif reports:
        print("Overall: RECENT OUTPUTS PRESENT, BUT BACKGROUND RUNNER NOT ACTIVE")
    else:
        print("Overall: STOPPED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
