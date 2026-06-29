#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")

LOG_FILES = [
    BASE / "reports" / "dukascopy_bridge" / "dukascopy_fx_backend.log",
    BASE / "reports" / "dukascopy_bridge" / "launchd_stderr.log",
    BASE / "reports" / "dukascopy_bridge" / "launchd_stdout.log",
    BASE / "reports" / "runtime" / "launchd_stderr.log",
    BASE / "reports" / "runtime" / "launchd_stdout.log",
]

STATE_FILES = [
    BASE / "reports" / "eventalpha_telegram_alert_state.json",
]


def main() -> int:
    print("InsightBridge Telegram History Cleanup")
    print("=" * 60)
    cleared_bytes = 0

    for path in LOG_FILES:
        if path.exists():
            size = path.stat().st_size
            path.write_text("", encoding="utf-8")
            cleared_bytes += size
            print(f"[CLEARED] {path} | removed_bytes={size}")
        else:
            print(f"[SKIP] {path} | missing")

    for path in STATE_FILES:
        payload = {"last_trade_open_key": None, "last_trade_close_key": None}
        old_size = path.stat().st_size if path.exists() else 0
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cleared_bytes += old_size
        print(f"[RESET]   {path} | old_bytes={old_size}")

    print("-" * 60)
    print(f"total_removed_bytes: {cleared_bytes}")
    print("Meaning: old Telegram-related history was cleared; only new reminders generated after this point will remain visible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
