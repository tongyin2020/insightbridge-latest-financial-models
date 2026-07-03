"""V2 audit logger: one JSONL line per v2 decision, gate-by-gate.

Complements the existing ``decision_log`` (which records EventAlphaBrain
decisions). This records the v2 gate chain so every NO_TRADE/ENTER can be
reviewed: which gate rejected, the EV, size, and the human-readable reason.
Dependency-light: stdlib json + append-only file.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Optional


def _jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return str(obj)


class V2AuditLogger:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get(
            "EVENTALPHA_V2_AUDIT_LOG", "logs/v2_decisions.jsonl")

    def log(self, symbol: str, decision, gates: Optional[dict] = None,
            extra: Optional[dict] = None) -> dict:
        record = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "decision": _jsonable(decision),
            "gates": _jsonable(gates or {}),
            "extra": _jsonable(extra or {}),
        }
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
