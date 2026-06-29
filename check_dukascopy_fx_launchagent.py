#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
LABEL = "com.insightbridge.dukascopy.fx.bridge"
PLIST = Path("/Users/tongyin/Library/LaunchAgents/com.insightbridge.dukascopy.fx.bridge.plist")
LOG_DIR = BASE / "reports" / "dukascopy_bridge"


def launchd_info() -> tuple[bool, str, str | None]:
    cmd = ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, "not_loaded", None

    pid = None
    state = "loaded"
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("state ="):
            state = line.split("=", 1)[1].strip()
        if line.startswith("pid ="):
            raw = line.split("=", 1)[1].strip()
            pid = None if raw == "0" else raw
    return True, state, pid


def tail_text(path: Path, lines: int = 5) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(errors="ignore").splitlines()[-lines:]


def main() -> int:
    loaded, state, pid = launchd_info()
    print("InsightBridge Dukascopy FX LaunchAgent")
    print("=" * 60)
    print(f"label: {LABEL}")
    print(f"plist_installed: {PLIST.exists()}")
    print(f"launchd_loaded: {loaded}")
    print(f"launchd_state: {state}")
    print(f"launchd_pid: {pid or 'none'}")
    print(f"stdout_log: {LOG_DIR / 'launchd_stdout.log'}")
    print(f"stderr_log: {LOG_DIR / 'launchd_stderr.log'}")
    print("-" * 60)
    for line in tail_text(LOG_DIR / "launchd_stdout.log"):
        print(f"stdout> {line}")
    for line in tail_text(LOG_DIR / "launchd_stderr.log"):
        print(f"stderr> {line}")
    print("-" * 60)
    print("Overall: LIVE" if loaded and state == "running" else "Overall: ATTENTION")
    return 0 if loaded and state == "running" else 1


if __name__ == "__main__":
    raise SystemExit(main())
