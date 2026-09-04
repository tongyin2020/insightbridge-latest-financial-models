#!/usr/bin/env python3
"""五金融模型运行健康数据汇总 Automation 入口。

运行仓库自带的健康检查脚本并解析其文本输出，另探测 IB Gateway 纸交易
端口（默认 4002），输出 AutomationOutput JSON：{"artifact": {...}}。
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/tongyin/InsightBridge_Financial_Models_Latest")
HEALTH_SCRIPT = BASE / "check_five_models_runtime_health.py"
PY = "/opt/anaconda3/bin/python3"
IBKR_PORT = 4002

ALL_SYMBOLS = ["BTC", "EURUSD", "USDJPY", "MES", "MNQ", "CL", "ZT", "ZN", "SR3"]
GROUP_ORDER = ["CRYPTO", "FX", "INDEX", "OIL", "TREASURY"]


def run_health_text() -> str:
    try:
        proc = subprocess.run(
            [PY, str(HEALTH_SCRIPT)],
            capture_output=True, text=True, timeout=90,
        )
        return proc.stdout or ""
    except Exception:
        return ""


def parse_health(text: str) -> dict:
    service = {"running": False, "state": "unknown", "pid": None,
               "source": "none", "heartbeat_age_s": None, "halted": False}
    symbols: dict[str, dict] = {}
    groups: dict[str, dict] = {}
    overall = "UNKNOWN"

    current_sym = None
    in_groups = False
    current_group = None

    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^service_running: (\w+)", line)
        if m:
            service["running"] = m.group(1) == "True"
            continue
        m = re.match(r"^service_state: (.+)", line)
        if m:
            service["state"] = m.group(1).strip()
            continue
        m = re.match(r"^service_pid: (.+)", line)
        if m:
            v = m.group(1).strip()
            service["pid"] = int(v) if v.isdigit() else None
            continue
        m = re.match(r"^effective_runtime_source: (.+)", line)
        if m:
            service["source"] = m.group(1).strip()
            continue
        m = re.match(r"^heartbeat_age: ([\d.]+)s", line)
        if m:
            service["heartbeat_age_s"] = float(m.group(1))
            continue
        m = re.match(r"^heartbeat_halted: (.+)", line)
        if m:
            service["halted"] = m.group(1).strip() == "True"
            continue
        if line.startswith("Model Groups"):
            in_groups = True
            current_sym = None
            continue
        m = re.match(r"^Overall: (\w+)", line)
        if m:
            overall = m.group(1)
            continue

        m = re.match(r"^\[([A-Z0-9]+)\] (\w+)", line)
        if m:
            name, status = m.group(1), m.group(2)
            if in_groups or name in GROUP_ORDER:
                in_groups = True
                current_group = name
                groups[name] = {"name": name, "status": status, "symbols": ""}
                current_sym = None
            else:
                current_sym = name
                symbols[name] = {"name": name, "status": status,
                                 "last_eval_age": "", "top_reason": ""}
            continue

        m = re.match(r"^\s+symbols: (.+)", line)
        if m and current_group:
            groups[current_group]["symbols"] = m.group(1).strip()
            continue
        m = re.match(r"^\s+last_eval: .+ \| age=(\S+)", line)
        if m and current_sym:
            symbols[current_sym]["last_eval_age"] = m.group(1)
            continue
        m = re.match(r"^\s+top_reason: (.+?) \((\d+)\)", line)
        if m and current_sym:
            symbols[current_sym]["top_reason"] = m.group(1)
            continue

    return {
        "overall": overall,
        "service": service,
        "groups": [groups[g] for g in GROUP_ORDER if g in groups],
        "symbols": [symbols[s] for s in ALL_SYMBOLS if s in symbols],
    }


def ibkr_port_open(port: int = IBKR_PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            return True
    except OSError:
        return False


def build_artifact() -> dict:
    parsed = parse_health(run_health_text())
    svc = parsed["service"]
    return {
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "overall": parsed["overall"],
        "service": {
            "running": bool(svc["running"]),
            "state": svc["state"],
            "pid": svc["pid"],
            "source": svc["source"],
            "heartbeat_age_s": svc["heartbeat_age_s"],
            "halted": bool(svc["halted"]),
        },
        "ibkr": {"port_open": ibkr_port_open(), "port": IBKR_PORT},
        "groups": parsed["groups"],
        "symbols": parsed["symbols"],
    }


def run(ctx):
    """托管 Python runner 入口：必须返回可 JSON 序列化的 artifact。"""
    return {"artifact": build_artifact()}


if __name__ == "__main__":
    print(json.dumps(run(None), ensure_ascii=False))
