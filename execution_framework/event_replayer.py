"""Read-only replayer for sealed event archives.

This module does not send orders, does not modify configuration and does not
issue any network call.  It only opens local files sealed by
``event_data_archive.EventDataArchive`` and returns an immutable view whose
methods filter every row by ``observed_at_utc <= cutoff``.

The replayer intentionally refuses synthetic or simulated archives so real-data
validation cannot be silently contaminated.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SYNTHETIC_MARKERS = {"synthetic", "simulated", "generated", "random", "fake"}
STREAM_NAMES = ("bars", "l1", "l2", "trades", "broker")


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return cleaned.strip("._") or "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def verify_manifest(event_dir: str | Path) -> Dict[str, Any]:
    """Return a dict with ``status``, ``files_checked`` and ``mismatches``.

    Callable independently from :class:`EventReplayer` so operational tooling
    can audit an archive without instantiating the replayer.
    """
    path = Path(event_dir)
    manifest_file = path / "manifest.json"
    if not manifest_file.exists():
        return {
            "status": "MANIFEST_MISSING",
            "files_checked": 0,
            "mismatches": [{"file": "manifest.json", "reason": "not_found"}],
        }
    try:
        manifest = _load_json(manifest_file)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "MANIFEST_UNREADABLE",
            "files_checked": 0,
            "mismatches": [{"file": "manifest.json", "reason": str(exc)}],
        }
    entries = manifest.get("files") or []
    mismatches: List[Dict[str, Any]] = []
    checked = 0
    for entry in entries:
        name = str(entry.get("file", ""))
        expected = str(entry.get("sha256", ""))
        expected_bytes = entry.get("bytes")
        file_path = path / name
        if not file_path.exists():
            mismatches.append({"file": name, "reason": "missing"})
            continue
        actual = _sha256(file_path)
        checked += 1
        if actual != expected:
            mismatches.append({"file": name,
                               "reason": "sha256_mismatch",
                               "expected": expected, "actual": actual})
            continue
        if expected_bytes is not None:
            actual_bytes = file_path.stat().st_size
            if int(expected_bytes) != int(actual_bytes):
                mismatches.append({"file": name,
                                   "reason": "size_mismatch",
                                   "expected": int(expected_bytes),
                                   "actual": int(actual_bytes)})
    status = "OK" if not mismatches else "MISMATCH"
    return {"status": status, "files_checked": checked,
            "mismatches": mismatches}


def _parse_observed(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _require_aware(cutoff: datetime) -> datetime:
    if not isinstance(cutoff, datetime):
        raise ValueError("cutoff must be a datetime")
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    return cutoff.astimezone(timezone.utc)


@dataclass(frozen=True)
class ReplayView:
    """Immutable, read-only view of a sealed event.

    All accessors re-apply the ``observed_at_utc <= cutoff`` filter every call
    so callers cannot leak future information by mutating state.
    """

    metadata: Dict[str, Any]
    _dir: Path
    _cutoff: datetime
    strict: bool = True
    skipped_rows: Dict[str, int] = field(default_factory=dict)
    read_only: bool = True
    may_submit_orders: bool = False

    def _read_stream(self, name: str, cutoff: Optional[datetime]) -> List[Dict[str, Any]]:
        """Rows of ``name`` observed at or before the cutoff.

        In ``strict`` mode (default) a malformed line or a row without a
        parseable ``observed_at_utc`` raises ``ValueError`` so a damaged
        archive can never silently replay with gaps.  A lenient view skips
        such rows and counts them in ``self.skipped_rows[name]``.
        """
        if name not in STREAM_NAMES:
            raise ValueError(f"unknown stream: {name}")
        active_cutoff = self._cutoff if cutoff is None else _require_aware(cutoff)
        target = self._dir / f"{name}.jsonl"
        if not target.exists():
            return []
        results: List[Dict[str, Any]] = []
        skipped = 0
        with target.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    if self.strict:
                        raise ValueError(
                            f"{target.name}:{lineno} malformed JSON: {exc}") from exc
                    skipped += 1
                    continue
                observed = _parse_observed(row.get("observed_at_utc"))
                if observed is None:
                    if self.strict:
                        raise ValueError(
                            f"{target.name}:{lineno} missing or invalid observed_at_utc")
                    skipped += 1
                    continue
                if observed > active_cutoff:
                    continue
                results.append(row)
        self.skipped_rows[name] = skipped
        return results

    def bars(self, cutoff: Optional[datetime] = None) -> List[Dict[str, Any]]:
        return self._read_stream("bars", cutoff)

    def l1(self, cutoff: Optional[datetime] = None) -> List[Dict[str, Any]]:
        return self._read_stream("l1", cutoff)

    def l2(self, cutoff: Optional[datetime] = None) -> List[Dict[str, Any]]:
        return self._read_stream("l2", cutoff)

    def trades(self, cutoff: Optional[datetime] = None) -> List[Dict[str, Any]]:
        return self._read_stream("trades", cutoff)

    def broker(self, cutoff: Optional[datetime] = None) -> List[Dict[str, Any]]:
        return self._read_stream("broker", cutoff)


class EventReplayer:
    """Load sealed event archives in a read-only, point-in-time manner."""

    read_only = True
    may_submit_orders = False

    def __init__(self, archive_root: str | Path) -> None:
        self.archive_root = Path(archive_root)
        if not self.archive_root.exists():
            raise FileNotFoundError(
                f"archive root does not exist: {self.archive_root}")

    def load_event(self, event_id: str, symbol: str,
                   cutoff_utc: datetime, *, strict: bool = True) -> ReplayView:
        cutoff = _require_aware(cutoff_utc)
        event_dir = self.archive_root / _safe_name(event_id) / _safe_name(str(symbol).upper())
        if not event_dir.exists():
            raise FileNotFoundError(f"event directory not found: {event_dir}")
        metadata_file = event_dir / "metadata.json"
        if not metadata_file.exists():
            raise FileNotFoundError(f"metadata.json missing: {metadata_file}")
        metadata = _load_json(metadata_file)
        if bool(metadata.get("synthetic", False)):
            raise ValueError(
                "archive marked synthetic=True cannot be replayed")
        source_value = str(metadata.get("source", "")).lower()
        for marker in SYNTHETIC_MARKERS:
            if marker in source_value:
                raise ValueError(
                    f"archive source contains disallowed marker: {marker}")
        verification = verify_manifest(event_dir)
        if verification["status"] != "OK":
            raise ValueError(
                "manifest verification failed: "
                f"{verification['status']} {verification['mismatches']}")
        return ReplayView(metadata=metadata, _dir=event_dir, _cutoff=cutoff,
                          strict=bool(strict))
