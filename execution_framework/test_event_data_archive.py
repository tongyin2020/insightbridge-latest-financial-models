"""Offline tests for replayable event-window provenance archives."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from event_data_archive import EventDataArchive


def test_archive_and_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        archive = EventDataArchive(tmp, source="IBKR_PAPER_API")
        t0 = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
        archive.open_event(
            "FOMC@2026-08-27T18:00:00+00:00", "FOMC", t0, "MNQ",
            {"conId": 123, "localSymbol": "MNQU6", "multiplier": "2"})
        archive.append(
            "FOMC@2026-08-27T18:00:00+00:00", "MNQ", "l1",
            {"bid": 18000.0, "ask": 18000.25, "bid_size": 4, "ask_size": 6},
            t0)
        archive.append(
            "FOMC@2026-08-27T18:00:00+00:00", "MNQ", "l2",
            {"bids": [{"level": 0, "price": 18000.0, "size": 4}],
             "asks": [{"level": 0, "price": 18000.25, "size": 6}]},
            t0)
        manifest = archive.seal_event(
            "FOMC@2026-08-27T18:00:00+00:00", "MNQ")
        assert {row["file"] for row in manifest["files"]} == {
            "metadata.json", "l1.jsonl", "l2.jsonl"}
        assert all(len(row["sha256"]) == 64 for row in manifest["files"])
        event_dir = next(Path(tmp).iterdir()) / "MNQ"
        saved = json.loads((event_dir / "manifest.json").read_text())
        assert saved["source"] == "IBKR_PAPER_API"


def test_synthetic_rejected_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            EventDataArchive(tmp, source="simulated_market_feed")
        except ValueError:
            return
        raise AssertionError("synthetic source was not rejected")


if __name__ == "__main__":
    test_archive_and_manifest()
    test_synthetic_rejected_by_default()
    print("✓ replayable event archive provenance and synthetic guard passed")
