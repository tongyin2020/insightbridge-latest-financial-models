#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
LABELS = [
    "com.insightbridge.five-models.paper",
    "com.insightbridge.dukascopy.fx.bridge",
]


def launchd_info(label: str) -> list[str]:
    proc = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return [f"{label}: NOT_LOADED"]

    state = "unknown"
    pid = "none"
    program = "N/A"
    for line in proc.stdout.splitlines():
        item = line.strip()
        if item.startswith("state ="):
            state = item.split("=", 1)[1].strip()
        elif item.startswith("pid ="):
            raw = item.split("=", 1)[1].strip()
            pid = raw if raw != "0" else "none"
        elif item.startswith("program ="):
            program = item.split("=", 1)[1].strip()
    return [f"{label}: state={state} pid={pid} program={program}"]


def telegram_processes() -> list[str]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
        )
    except PermissionError:
        return ["process list unavailable in current sandbox; run this script directly in your Mac terminal for full results"]
    lines: list[str] = []
    if proc.returncode != 0:
        return ["unable_to_read_process_list"]

    keywords = ("telegram", "eventalpha_continuous_runner.py", "run_tws_continuous.py", "dukascopy")
    for raw in proc.stdout.splitlines():
        text = raw.strip()
        low = text.lower()
        if any(k.lower() in low for k in keywords):
            lines.append(text)
    return lines


def main() -> int:
    print("InsightBridge Active Telegram Source Check")
    print("=" * 60)
    print("launchd_services:")
    for label in LABELS:
        for line in launchd_info(label):
            print(f"  - {line}")

    print("-" * 60)
    print("matching_processes:")
    matches = telegram_processes()
    if matches:
        for line in matches:
            print(f"  - {line}")
    else:
        print("  - none")

    print("-" * 60)
    print("Interpretation:")
    print("Only the currently running live broker services should appear here.")
    print("If an old eventalpha_continuous_runner.py process appears again, that is a stale reminder source and should be stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
