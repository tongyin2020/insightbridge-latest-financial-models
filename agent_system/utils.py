from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def parse_ts(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.now(timezone.utc)


def recent_jsonl(log_path: Path, lookback_minutes: float) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    records: list[dict[str, Any]] = []
    try:
        with open(log_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if parse_ts(rec.get("ts", "")) >= cutoff:
                    records.append(rec)
    except Exception:
        return []
    return records
