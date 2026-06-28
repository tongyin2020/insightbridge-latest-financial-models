#!/usr/bin/env python3
"""
IBKR paper-trading readiness check for the local Mac.

This script is read-only:
- checks installed desktop apps / Jts traces
- checks Python dependencies
- checks local process and port state when possible
- optionally tries a read-only account connection to paper port 7497

It never places orders.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


HOST = "127.0.0.1"
PAPER_PORT = 7497
LIVE_PORT = 7496
DEFAULT_CLIENT_ID = 97


@dataclass
class CheckResult:
    ok: bool
    detail: str
    extra: dict[str, Any] | None = None


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


def check_installation() -> CheckResult:
    home = Path.home()
    candidates = [
        home / "Applications" / "Trader Workstation",
        home / "Applications" / "IB Gateway 10.45",
        home / "Applications" / "IBKR Desktop",
        home / "Jts",
        home / "Library" / "Application Support" / "Trader Workstation",
        home / "Library" / "Application Support" / "IB Gateway 10.45",
        home / "Library" / "Application Support" / "IBKR Desktop",
    ]
    existing = [str(p) for p in candidates if p.exists()]
    ok = bool(existing)
    return CheckResult(
        ok=ok,
        detail="found local IBKR desktop installation traces" if ok else "no local IBKR installation traces found",
        extra={"paths": existing},
    )


def check_python_packages() -> CheckResult:
    packages: dict[str, str] = {}
    missing: list[str] = []
    for name in ("ib_insync", "ibapi"):
        try:
            mod = __import__(name)
            version = getattr(mod, "__version__", "installed")
            packages[name] = str(version)
        except Exception:
            missing.append(name)
    ok = "ib_insync" in packages
    return CheckResult(
        ok=ok,
        detail="ib_insync available" if ok else "ib_insync missing",
        extra={"installed": packages, "missing": missing},
    )


def check_jts_config() -> CheckResult:
    jts_ini = Path.home() / "Jts" / "jts.ini"
    extra: dict[str, Any] = {"jts_ini": str(jts_ini), "exists": jts_ini.exists()}
    if not jts_ini.exists():
        return CheckResult(False, "Jts config not found", extra)

    trusted_ips = None
    supports_ssl = None
    try:
        for line in jts_ini.read_text(errors="ignore").splitlines():
            if line.startswith("TrustedIPs="):
                trusted_ips = line.split("=", 1)[1].strip()
            elif line.startswith("SupportsSSL="):
                supports_ssl = line.split("=", 1)[1].strip()
    except Exception as exc:
        extra["read_error"] = str(exc)
        return CheckResult(False, "unable to read Jts config", extra)

    extra["trusted_ips"] = trusted_ips
    extra["supports_ssl"] = supports_ssl
    ok = trusted_ips is not None
    return CheckResult(ok, "Jts config present" if ok else "Jts config present but key API hints missing", extra)


def check_processes() -> CheckResult:
    patterns = [
        "Trader Workstation",
        "IB Gateway",
        "IBKR Desktop",
        "tws",
        "ibgateway",
    ]
    matches: list[str] = []
    errors: list[str] = []
    for pattern in patterns:
        code, out, err = run_cmd(["pgrep", "-fal", pattern])
        if out:
            matches.extend([line for line in out.splitlines() if line.strip()])
        if err and "operation not permitted" not in err.lower():
            errors.append(err)
    unique_matches = sorted(set(matches))
    return CheckResult(
        ok=bool(unique_matches),
        detail="IBKR-related desktop process found" if unique_matches else "no IBKR desktop process currently visible",
        extra={"matches": unique_matches, "errors": errors},
    )


def check_port(host: str, port: int) -> CheckResult:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.5)
    try:
        rc = sock.connect_ex((host, port))
        if rc == 0:
            return CheckResult(True, f"TCP port {port} is reachable on {host}")
        return CheckResult(False, f"TCP port {port} is not reachable on {host}", {"connect_ex": rc})
    except Exception as exc:
        return CheckResult(False, f"socket check failed for {host}:{port}", {"error": str(exc)})
    finally:
        sock.close()


def try_read_only_connection(host: str, port: int, client_id: int) -> CheckResult:
    try:
        from ib_insync import IB  # type: ignore
    except Exception as exc:
        return CheckResult(False, "ib_insync import failed", {"error": str(exc)})

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=4, readonly=True)
        accounts = ib.managedAccounts()
        summary_rows = ib.accountSummary()
        fields = {}
        for row in summary_rows:
            if row.tag in {"NetLiquidation", "AvailableFunds", "TotalCashValue", "RealizedPnL", "UnrealizedPnL"}:
                fields[row.tag] = row.value
        positions = ib.positions()
        return CheckResult(
            ok=True,
            detail="read-only paper connection succeeded",
            extra={
                "accounts": accounts,
                "account_summary": fields,
                "position_count": len(positions),
            },
        )
    except Exception as exc:
        return CheckResult(False, "read-only paper connection failed", {"error": str(exc)})
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local IBKR paper-trading readiness.")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PAPER_PORT)
    parser.add_argument("--client-id", type=int, default=DEFAULT_CLIENT_ID)
    parser.add_argument("--skip-connect", action="store_true", help="Skip the read-only IBKR connection attempt.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    results = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "host": args.host,
        "paper_port": args.port,
        "live_port": LIVE_PORT,
        "checks": {
            "installation": asdict(check_installation()),
            "python_packages": asdict(check_python_packages()),
            "jts_config": asdict(check_jts_config()),
            "processes": asdict(check_processes()),
            "paper_port": asdict(check_port(args.host, args.port)),
        },
    }

    if not args.skip_connect:
        results["checks"]["read_only_connection"] = asdict(
            try_read_only_connection(args.host, args.port, args.client_id)
        )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    print("IBKR Paper Trading Readiness Check")
    print("=" * 60)
    print(f"project: /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
    print(f"host: {args.host}")
    print(f"paper_port: {args.port}")
    print("-" * 60)

    for key, payload in results["checks"].items():
        status = "OK" if payload["ok"] else "ATTENTION"
        print(f"[{status}] {key}")
        print(f"  {payload['detail']}")
        extra = payload.get("extra") or {}
        if extra:
            extra_str = json.dumps(extra, ensure_ascii=False)
            if len(extra_str) > 600:
                extra_str = extra_str[:600] + "..."
            print(f"  extra: {extra_str}")
        print("-" * 60)

    read_only = results["checks"].get("read_only_connection")
    if read_only and read_only["ok"]:
        print("Overall: READY - local paper account connection is working.")
    elif results["checks"]["paper_port"]["ok"]:
        print("Overall: PARTIAL - IBKR endpoint is up, but read-only account fetch did not complete.")
    else:
        print("Overall: NOT READY - local desktop/API endpoint is not open yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
