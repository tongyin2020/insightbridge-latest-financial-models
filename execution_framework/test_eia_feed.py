"""Offline self-check for the EIA weekly petroleum feed (no network needed)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eia_feed import EiaPetroleumFeed, _build_items, _enabled_from_env
from eventalpha_core.advanced.news_gateway import (
    KeywordNewsClassifier, NewsGatewayConfig, assess_news)


def _payload(rows):
    return json.dumps({"response": {"data": rows}}).encode()


# EIA v2 returns newest-first; values are thousand barrels.
_BUILD = _payload([
    {"period": "2026-06-26", "value": 421000.0},   # +5.0 Mbbl WoW -> build
    {"period": "2026-06-19", "value": 416000.0},
])
_DRAW = _payload([
    {"period": "2026-06-26", "value": 410000.0},    # -6.0 Mbbl WoW -> draw
    {"period": "2026-06-19", "value": 416000.0},
])


def test_no_key_returns_empty():
    f = EiaPetroleumFeed(api_key=None)
    assert f.fetch() == []


def test_build_headline_and_dedupe_id():
    items = _build_items(_BUILD)
    assert len(items) == 1
    it = items[0]
    assert "build" in it.title.lower() and "5.0 million" in it.title
    assert it.item_id == "eia:WCESTUS1:2026-06-26"
    assert it.published == "2026-06-26"


def test_draw_headline():
    items = _build_items(_DRAW)
    assert "draw" in items[0].title.lower() and "6.0 million" in items[0].title


def test_single_row_no_change_still_reports_level():
    items = _build_items(_payload([{"period": "2026-06-26", "value": 421000.0}]))
    assert len(items) == 1
    assert "421.0 million" in items[0].title
    assert "build" not in items[0].title.lower()


def test_malformed_payload_never_raises():
    assert _build_items(b"not json") == []
    assert _build_items(_payload([{"period": "x"}])) == []   # missing value


def test_gateway_classifies_build_as_oil_risk_off():
    title = _build_items(_BUILD)[0].title
    a = assess_news(title, KeywordNewsClassifier(), NewsGatewayConfig())
    assert a.category == "EIA"
    assert a.sentiment == "risk_off"          # inventory build => bearish oil
    assert a.would_wake(NewsGatewayConfig())


def test_gateway_classifies_draw_as_oil_risk_on():
    title = _build_items(_DRAW)[0].title
    a = assess_news(title, KeywordNewsClassifier(), NewsGatewayConfig())
    assert a.category == "EIA"
    assert a.sentiment == "risk_on"           # inventory draw => bullish oil


def test_env_switch():
    import os
    old = os.environ.get("EVENTALPHA_EIA_FEED")
    try:
        os.environ["EVENTALPHA_EIA_FEED"] = "1"
        assert _enabled_from_env() is True
        os.environ["EVENTALPHA_EIA_FEED"] = "0"
        assert _enabled_from_env() is False
    finally:
        if old is None:
            os.environ.pop("EVENTALPHA_EIA_FEED", None)
        else:
            os.environ["EVENTALPHA_EIA_FEED"] = old


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
