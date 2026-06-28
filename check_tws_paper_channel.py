#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
CHECK_SCRIPT = BASE / "check_ibkr_paper_setup.py"


def main() -> int:
    proc = subprocess.run(
        ["/opt/anaconda3/bin/python3", str(CHECK_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        timeout=25,
    )
    if proc.returncode != 0:
        print("TWS Paper Channel Check")
        print("=" * 60)
        print(f"generated_at: {datetime.now().isoformat(timespec='seconds')}")
        print("status: ATTENTION")
        print(proc.stderr.strip() or proc.stdout.strip())
        return 1

    payload = json.loads(proc.stdout)
    checks = payload.get("checks", {})
    print("TWS Paper Channel Check")
    print("=" * 60)
    print(f"generated_at: {datetime.now().isoformat(timespec='seconds')}")
    print(f"paper_port: {checks.get('paper_port', {}).get('detail', 'n/a')}")
    print(f"read_only_connection: {checks.get('read_only_connection', {}).get('detail', 'n/a')}")
    print(f"processes: {checks.get('processes', {}).get('detail', 'n/a')}")
    if checks.get("read_only_connection", {}).get("extra", {}).get("accounts"):
        print(f"accounts: {checks['read_only_connection']['extra']['accounts']}")
    overall = "READY" if checks.get("read_only_connection", {}).get("ok") else "NOT READY"
    print(f"overall: {overall}")
    return 0 if overall == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
