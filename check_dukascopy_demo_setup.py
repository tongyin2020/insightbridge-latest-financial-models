#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
ENV_FILE = BASE / ".env.dukascopy_demo.local"
LATEST_IBKR_MATRIX = BASE / "reports" / "market_data_diagnostics" / "ibkr_market_data_matrix_latest.json"
REPORTS_DIR = BASE / "reports" / "broker_diagnostics"
PREP_REPORT = BASE / "dukascopy_runtime" / "reports" / "prepare_dukascopy_demo_runtime.json"

PRODUCT_MATRIX = [
    {
        "symbol": "EURUSD",
        "asset_group": "FX",
        "dukascopy_strength": "strong",
        "notes": "Spot FX is the cleanest Dukascopy fit.",
    },
    {
        "symbol": "USDJPY",
        "asset_group": "FX",
        "dukascopy_strength": "strong",
        "notes": "Spot FX is the cleanest Dukascopy fit.",
    },
    {
        "symbol": "BTC",
        "asset_group": "CRYPTO",
        "dukascopy_strength": "partial",
        "notes": "Possible via Dukascopy crypto/CFD style instruments; verify exact demo availability.",
    },
    {
        "symbol": "ETH",
        "asset_group": "CRYPTO",
        "dukascopy_strength": "partial",
        "notes": "Possible via Dukascopy crypto/CFD style instruments; verify exact demo availability.",
    },
    {
        "symbol": "SOL",
        "asset_group": "CRYPTO",
        "dukascopy_strength": "partial",
        "notes": "May not map cleanly; verify exact instrument support in demo.",
    },
    {
        "symbol": "CL",
        "asset_group": "OIL",
        "dukascopy_strength": "partial",
        "notes": "Could be proxied through energy CFD / spot-style instruments, not exact CME CL futures.",
    },
    {
        "symbol": "MES",
        "asset_group": "INDEX",
        "dukascopy_strength": "weak",
        "notes": "No clean 1:1 micro future mapping expected; only index-CFD style approximation may exist.",
    },
    {
        "symbol": "MNQ",
        "asset_group": "INDEX",
        "dukascopy_strength": "weak",
        "notes": "No clean 1:1 micro future mapping expected; only index-CFD style approximation may exist.",
    },
    {
        "symbol": "ZT",
        "asset_group": "TREASURY",
        "dukascopy_strength": "weak",
        "notes": "Treasury futures usually do not map cleanly into Dukascopy demo instruments.",
    },
    {
        "symbol": "ZN",
        "asset_group": "TREASURY",
        "dukascopy_strength": "weak",
        "notes": "Treasury futures usually do not map cleanly into Dukascopy demo instruments.",
    },
    {
        "symbol": "SR3",
        "asset_group": "TREASURY",
        "dukascopy_strength": "weak",
        "notes": "Short-rate futures are unlikely to have a clean Dukascopy demo equivalent.",
    },
]


@dataclass
class CheckResult:
    ok: bool
    detail: str
    extra: dict[str, Any] | None = None


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_local_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def load_prep_candidates() -> dict[str, list[str]]:
    if not PREP_REPORT.exists():
        return {}
    try:
        payload = json.loads(PREP_REPORT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    detected = payload.get("detected_candidates", {})
    if not isinstance(detected, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, value in detected.items():
        if isinstance(value, list):
            out[key] = [str(item) for item in value]
    return out


def check_credentials(env: dict[str, str]) -> CheckResult:
    required = [
        "DUKASCOPY_DEMO_URL",
        "DUKASCOPY_DEMO_JNLP_URL",
        "DUKASCOPY_DEMO_USER",
        "DUKASCOPY_DEMO_PASSWORD",
    ]
    missing = [key for key in required if not env.get(key)]
    if missing:
        return CheckResult(False, "missing demo credentials", {"missing": missing})
    return CheckResult(
        True,
        "demo credentials present locally",
        {
            "url": env.get("DUKASCOPY_DEMO_URL"),
            "jnlp_url": env.get("DUKASCOPY_DEMO_JNLP_URL"),
            "user_present": bool(env.get("DUKASCOPY_DEMO_USER")),
            "password_present": bool(env.get("DUKASCOPY_DEMO_PASSWORD")),
        },
    )


def check_java(env: dict[str, str], prep: dict[str, list[str]]) -> CheckResult:
    java_candidates = []
    if env.get("DUKASCOPY_JAVA_BIN"):
        java_candidates.append(env["DUKASCOPY_JAVA_BIN"])
    java_candidates.extend(prep.get("java_bins", []))
    java_candidates.append("/usr/bin/java")
    java_bin = next((item for item in java_candidates if item), "/usr/bin/java")
    try:
        proc = subprocess.run([java_bin, "-version"], capture_output=True, text=True, timeout=8)
    except FileNotFoundError:
        return CheckResult(False, "java binary not found", {"java_bin": java_bin})
    except Exception as exc:
        return CheckResult(False, "java runtime check failed", {"java_bin": java_bin, "error": str(exc)})
    text = (proc.stderr or proc.stdout or "").strip()
    if proc.returncode != 0:
        return CheckResult(False, "java runtime unavailable", {"java_bin": java_bin, "output": text})
    return CheckResult(
        True,
        "java runtime available",
        {
            "java_bin": java_bin,
            "output": text.splitlines()[:2],
            "source": "env_or_detected_bundle" if java_bin != "/usr/bin/java" else "system_default",
        },
    )


def check_sdk_jars(env: dict[str, str], prep: dict[str, list[str]]) -> CheckResult:
    sdk_jar = env.get("DUKASCOPY_JFOREX_SDK_JAR", "").strip()
    jnlp_jar = env.get("DUKASCOPY_JNLP_JAR", "").strip()
    if not sdk_jar:
        for candidate in prep.get("sdk_jars", []):
            name = Path(candidate).name.lower()
            if "jforex-api" in name or "jforex4" in name:
                sdk_jar = candidate
                break
    if not jnlp_jar:
        for candidate in prep.get("jnlp_jars", []):
            name = Path(candidate).name.lower()
            if "demo" in name or "live" in name:
                jnlp_jar = candidate
                break
    sdk_exists = bool(sdk_jar) and Path(sdk_jar).exists()
    jnlp_exists = bool(jnlp_jar) and Path(jnlp_jar).exists()
    if sdk_exists and (jnlp_exists or not jnlp_jar):
        return CheckResult(
            True,
            "dukascopy sdk jar path configured",
            {
                "sdk_jar": sdk_jar,
                "jnlp_jar": jnlp_jar or None,
                "source": "env_or_detected_jforex_install",
            },
        )
    return CheckResult(
        False,
        "dukascopy sdk jars not ready yet",
        {
            "sdk_jar": sdk_jar or None,
            "sdk_jar_exists": sdk_exists,
            "jnlp_jar": jnlp_jar or None,
            "jnlp_jar_exists": jnlp_exists,
        },
    )


def load_ibkr_causes() -> dict[str, str]:
    if not LATEST_IBKR_MATRIX.exists():
        return {}
    try:
        payload = json.loads(LATEST_IBKR_MATRIX.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in payload.get("results", []):
        symbol = str(row.get("symbol", "")).upper()
        cause = str(row.get("diagnosis", {}).get("primary_cause_code", "unknown"))
        if symbol:
            out[symbol] = cause
    return out


def build_supplement_matrix(ibkr_causes: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in PRODUCT_MATRIX:
        symbol = item["symbol"]
        ibkr_cause = ibkr_causes.get(symbol, "no_recent_ibkr_diagnostic")
        if ibkr_cause in {"subscription_missing", "delayed_only", "competing_session"}:
            if item["dukascopy_strength"] == "strong":
                recommendation = "high_priority_supplement"
            elif item["dukascopy_strength"] == "partial":
                recommendation = "conditional_supplement"
            else:
                recommendation = "low_probability_supplement"
        elif ibkr_cause == "ok":
            recommendation = "ibkr_already_ok"
        else:
            recommendation = "verify_manually"
        rows.append(
            {
                "symbol": symbol,
                "asset_group": item["asset_group"],
                "ibkr_cause": ibkr_cause,
                "dukascopy_strength": item["dukascopy_strength"],
                "recommendation": recommendation,
                "notes": item["notes"],
            }
        )
    return rows


def write_reports(checks: dict[str, dict[str, Any]], supplement_rows: list[dict[str, Any]], overall: str) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = REPORTS_DIR / "dukascopy_demo_setup_latest.json"
    latest_md = REPORTS_DIR / "dukascopy_demo_setup_latest.md"
    payload = {
        "generated_at": now_utc(),
        "project": str(BASE),
        "env_file": str(ENV_FILE),
        "checks": checks,
        "supplement_rows": supplement_rows,
        "overall": overall,
    }
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Dukascopy Demo Setup Report",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- project: `{BASE}`",
        f"- env_file: `{ENV_FILE}`",
        f"- overall: **{overall}**",
        "",
        "## Setup Checks",
        "",
    ]
    for name, check in checks.items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- status: {'OK' if check['ok'] else 'ATTENTION'}")
        lines.append(f"- detail: {check['detail']}")
        extra = check.get("extra") or {}
        if extra:
            lines.append(f"- extra: `{json.dumps(extra, ensure_ascii=False)}`")
        lines.append("")
    lines.extend(
        [
            "## Broker Supplement Matrix",
            "",
            "| Symbol | Group | IBKR Cause | Dukascopy Strength | Recommendation |",
            "|---|---|---|---|---|",
        ]
    )
    for row in supplement_rows:
        lines.append(
            f"| {row['symbol']} | {row['asset_group']} | {row['ibkr_cause']} | "
            f"{row['dukascopy_strength']} | {row['recommendation']} |"
        )
    lines.append("")
    latest_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return latest_json, latest_md


def main() -> int:
    env = load_local_env(ENV_FILE)
    prep = load_prep_candidates()
    checks = {
        "credentials": asdict(check_credentials(env)),
        "java_runtime": asdict(check_java(env, prep)),
        "sdk_jars": asdict(check_sdk_jars(env, prep)),
    }
    ibkr_causes = load_ibkr_causes()
    supplement_rows = build_supplement_matrix(ibkr_causes)

    ready = all(checks[key]["ok"] for key in ("credentials", "java_runtime", "sdk_jars"))
    partial = checks["credentials"]["ok"] and not ready

    print("Dukascopy Demo Setup Check")
    print("=" * 60)
    print(f"project: {BASE}")
    print(f"generated_at: {now_utc()}")
    print(f"env_file: {ENV_FILE} {'(present)' if ENV_FILE.exists() else '(missing)'}")
    print("-" * 60)
    for name, payload in checks.items():
        print(f"[{name}] {'OK' if payload['ok'] else 'ATTENTION'}")
        print(f"  detail: {payload['detail']}")
        extra = payload.get("extra") or {}
        if extra:
            print(f"  extra: {json.dumps(extra, ensure_ascii=False)}")
        print("-" * 60)

    print("Broker Supplement Matrix")
    print("-" * 60)
    for row in supplement_rows:
        print(f"[{row['symbol']}] {row['recommendation']}")
        print(f"  ibkr_cause: {row['ibkr_cause']}")
        print(f"  dukascopy_strength: {row['dukascopy_strength']}")
        print(f"  notes: {row['notes']}")
        print("-" * 60)

    if ready:
        overall = "READY - local Dukascopy demo bridge prerequisites are present."
        write_reports(checks, supplement_rows, overall)
        print("Overall: READY - local Dukascopy demo bridge prerequisites are present.")
        return 0
    if partial:
        overall = "PARTIAL - credentials are stored locally, but Java / SDK is not ready yet."
        json_path, md_path = write_reports(checks, supplement_rows, overall)
        print(f"saved_json: {json_path}")
        print(f"saved_md: {md_path}")
        print("Overall: PARTIAL - credentials are stored locally, but Java / SDK is not ready yet.")
        return 0
    overall = "ATTENTION - local Dukascopy demo bridge is not ready yet."
    json_path, md_path = write_reports(checks, supplement_rows, overall)
    print(f"saved_json: {json_path}")
    print(f"saved_md: {md_path}")
    print("Overall: ATTENTION - local Dukascopy demo bridge is not ready yet.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
