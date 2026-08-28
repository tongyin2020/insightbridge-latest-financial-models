"""Replayable event-window archive with explicit provenance.

The archive stores observations, not derived signals.  Every event/symbol pair
has an immutable metadata file plus append-only JSONL streams for bars, L1,
L2, trades and broker lifecycle facts.  ``seal_event`` writes SHA-256 hashes
so a later backtest can prove exactly which source files it consumed.

Synthetic and simulated sources are rejected by default to prevent accidental
contamination of real-data validation directories.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


ALLOWED_STREAMS = {"bars", "l1", "l2", "trades", "broker"}
SYNTHETIC_MARKERS = {"synthetic", "simulated", "generated", "random"}


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "unknown"


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EventDataArchive:
    def __init__(self, root: str, source: str,
                 allow_synthetic: bool = False) -> None:
        self.root = Path(root)
        self.source = source.strip()
        if not self.source:
            raise ValueError("source is required")
        source_lower = self.source.lower()
        if (not allow_synthetic and
                any(marker in source_lower for marker in SYNTHETIC_MARKERS)):
            raise ValueError("synthetic/simulated sources require explicit opt-in")
        self.root.mkdir(parents=True, exist_ok=True)

    def _event_dir(self, event_id: str, symbol: str) -> Path:
        return self.root / _safe_name(event_id) / _safe_name(symbol.upper())

    def open_event(self, event_id: str, event_name: str, t0_utc: datetime,
                   symbol: str, contract: Dict[str, Any],
                   extra: Optional[Dict[str, Any]] = None) -> Path:
        path = self._event_dir(event_id, symbol)
        path.mkdir(parents=True, exist_ok=True)
        metadata = {
            "schema_version": 1,
            "event_id": event_id,
            "event_name": event_name,
            "t0_utc": _utc_iso(t0_utc),
            "symbol": symbol.upper(),
            "source": self.source,
            "contract": contract,
            "opened_at_utc": datetime.now(timezone.utc).isoformat(),
            "synthetic": False,
            "extra": extra or {},
        }
        target = path / "metadata.json"
        tmp = path / "metadata.json.tmp"
        tmp.write_text(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8")
        os.replace(tmp, target)
        return path

    def append(self, event_id: str, symbol: str, stream: str,
               payload: Dict[str, Any],
               observed_at: Optional[datetime] = None) -> Path:
        if stream not in ALLOWED_STREAMS:
            raise ValueError(f"unsupported stream: {stream}")
        path = self._event_dir(event_id, symbol)
        if not (path / "metadata.json").exists():
            raise FileNotFoundError("open_event must be called before append")
        stamp = observed_at or datetime.now(timezone.utc)
        row = {
            "observed_at_utc": _utc_iso(stamp),
            "source": self.source,
            "payload": payload,
        }
        target = path / f"{stream}.jsonl"
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return target

    def append_many(self, event_id: str, symbol: str, stream: str,
                    payloads: Iterable[Dict[str, Any]],
                    observed_at: Optional[datetime] = None) -> int:
        count = 0
        for payload in payloads:
            self.append(event_id, symbol, stream, payload, observed_at)
            count += 1
        return count

    def seal_event(self, event_id: str, symbol: str) -> Dict[str, Any]:
        path = self._event_dir(event_id, symbol)
        files = []
        for item in sorted(path.iterdir()):
            if not item.is_file() or item.name.endswith(".tmp") or item.name == "manifest.json":
                continue
            files.append({
                "file": item.name,
                "bytes": item.stat().st_size,
                "sha256": _sha256(item),
            })
        manifest = {
            "schema_version": 1,
            "event_id": event_id,
            "symbol": symbol.upper(),
            "source": self.source,
            "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": files,
        }
        target = path / "manifest.json"
        tmp = path / "manifest.json.tmp"
        tmp.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8")
        os.replace(tmp, target)
        return manifest
