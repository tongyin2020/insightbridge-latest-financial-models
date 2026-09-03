"""Offline tests for the read-only event replayer.

This test module never submits an order and never mutates configuration.  It
only creates a temporary archive with EventDataArchive, seals it and asserts
the replayer's filtering / fail-closed behaviour.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from event_data_archive import EventDataArchive
from event_replayer import EventReplayer, verify_manifest


def _seed(tmp_path: Path, *, source: str = "unit-test-source",
          synthetic: bool = False) -> tuple[str, str, datetime]:
    root = tmp_path / "archive"
    archive = EventDataArchive(str(root), source=source,
                               allow_synthetic=synthetic)
    event_id = "2026-09-01T14:00Z:CPI"
    symbol = "ES"
    t0 = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    archive.open_event(event_id, "CPI", t0, symbol,
                       {"secType": "FUT", "exchange": "CME"})
    if synthetic:
        # Rewrite metadata to include synthetic marker to test fail-closed.
        meta_path = root / _safe(event_id) / _safe(symbol.upper()) / "metadata.json"
        meta = json.loads(meta_path.read_text())
        meta["synthetic"] = True
        meta_path.write_text(json.dumps(meta, sort_keys=True, indent=2))
    base = t0 - timedelta(minutes=5)
    for i in range(4):
        stamp = base + timedelta(minutes=i)
        archive.append(event_id, symbol, "bars",
                       {"o": 100 + i, "h": 100 + i, "l": 100 + i,
                        "c": 100 + i, "v": 10 + i},
                       observed_at=stamp)
    archive.append(event_id, symbol, "l1", {"bid": 100.0, "ask": 100.1},
                   observed_at=base)
    archive.append(event_id, symbol, "trades", {"price": 100.05, "size": 1},
                   observed_at=t0 + timedelta(minutes=1))
    archive.seal_event(event_id, symbol)
    return event_id, symbol, t0


def _safe(v: str) -> str:
    import re
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", v.strip())
    return cleaned.strip("._") or "unknown"


def test_load_and_cutoff_filters(tmp_path: Path) -> None:
    event_id, symbol, t0 = _seed(tmp_path)
    replayer = EventReplayer(str(tmp_path / "archive"))
    assert replayer.read_only is True
    assert replayer.may_submit_orders is False
    cutoff = t0  # includes bars but excludes the post-event trade
    view = replayer.load_event(event_id, symbol, cutoff_utc=cutoff)
    assert view.read_only is True
    assert view.may_submit_orders is False
    bars = view.bars()
    assert len(bars) >= 4
    # All returned bars must be <= cutoff
    for row in bars:
        assert row["observed_at_utc"] <= cutoff.isoformat()
    trades = view.trades()
    assert trades == [], "trade after cutoff must not appear"


def test_future_rows_never_returned(tmp_path: Path) -> None:
    event_id, symbol, t0 = _seed(tmp_path)
    replayer = EventReplayer(str(tmp_path / "archive"))
    view = replayer.load_event(event_id, symbol,
                               cutoff_utc=t0 - timedelta(minutes=3))
    # Only bars strictly at or before cutoff should be included.
    bars = view.bars()
    assert bars, "expected at least one bar before cutoff"
    for row in bars:
        assert row["observed_at_utc"] <= (t0 - timedelta(minutes=3)).isoformat()


def test_naive_cutoff_raises(tmp_path: Path) -> None:
    event_id, symbol, _ = _seed(tmp_path)
    replayer = EventReplayer(str(tmp_path / "archive"))
    with pytest.raises(ValueError):
        replayer.load_event(event_id, symbol,
                            cutoff_utc=datetime(2026, 9, 1, 14, 0))


def test_manifest_mismatch_fails_closed(tmp_path: Path) -> None:
    event_id, symbol, t0 = _seed(tmp_path)
    event_dir = tmp_path / "archive" / _safe(event_id) / _safe(symbol.upper())
    bars_file = event_dir / "bars.jsonl"
    with bars_file.open("a", encoding="utf-8") as fh:
        fh.write('{"observed_at_utc":"2099-01-01T00:00:00+00:00",'
                 '"source":"tamper","payload":{"o":0,"h":0,"l":0,"c":0}}\n')
    replayer = EventReplayer(str(tmp_path / "archive"))
    with pytest.raises(ValueError):
        replayer.load_event(event_id, symbol, cutoff_utc=t0)
    report = verify_manifest(event_dir)
    assert report["status"] == "MISMATCH"
    assert any(m["file"] == "bars.jsonl" for m in report["mismatches"])


def test_synthetic_metadata_rejected(tmp_path: Path) -> None:
    event_id, symbol, t0 = _seed(tmp_path)
    # Toggle metadata.synthetic to True without touching listed files
    from event_replayer import _safe_name  # noqa: WPS437
    meta_path = (tmp_path / "archive" / _safe_name(event_id)
                 / _safe_name(symbol.upper()) / "metadata.json")
    meta = json.loads(meta_path.read_text())
    meta["synthetic"] = True
    meta_path.write_text(json.dumps(meta, sort_keys=True, indent=2))
    # Re-seal so the new metadata hash matches manifest
    archive = EventDataArchive(str(tmp_path / "archive"),
                               source="unit-test-source")
    archive.seal_event(event_id, symbol)
    replayer = EventReplayer(str(tmp_path / "archive"))
    with pytest.raises(ValueError):
        replayer.load_event(event_id, symbol, cutoff_utc=t0)


def test_synthetic_source_rejected(tmp_path: Path) -> None:
    from event_replayer import _safe_name  # noqa: WPS437
    event_id, symbol, t0 = _seed(tmp_path)
    meta_path = (tmp_path / "archive" / _safe_name(event_id)
                 / _safe_name(symbol.upper()) / "metadata.json")
    meta = json.loads(meta_path.read_text())
    meta["source"] = "internal-synthetic-generator"
    meta_path.write_text(json.dumps(meta, sort_keys=True, indent=2))
    archive = EventDataArchive(str(tmp_path / "archive"),
                               source="unit-test-source")
    archive.seal_event(event_id, symbol)
    replayer = EventReplayer(str(tmp_path / "archive"))
    with pytest.raises(ValueError):
        replayer.load_event(event_id, symbol, cutoff_utc=t0)
