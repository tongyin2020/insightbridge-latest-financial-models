from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class TraceStore:
    def __init__(self, trace_dir: Path, prefix: str = "agent_trace") -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.trace_dir / f"{prefix}.jsonl"

    @staticmethod
    def _json_default(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    def append(self, record: dict[str, Any]) -> Path:
        line = json.dumps(record, ensure_ascii=False, default=self._json_default) + "\n"
        fd, tmp = tempfile.mkstemp(dir=self.trace_dir, suffix=".jsonl.tmp")
        tmp_path = Path(tmp)
        try:
            with os.fdopen(fd, "wb") as dst:
                if self.log_path.exists():
                    with open(self.log_path, "rb") as src:
                        dst.write(src.read())
                dst.write(line.encode("utf-8"))
            tmp_path.replace(self.log_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        return self.log_path

    def tail(self, n: int = 100) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        with open(self.log_path, encoding="utf-8") as fh:
            lines = fh.readlines()
        records = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records
