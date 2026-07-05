"""Offline self-check for the news-gateway shadow (no LLM key needed)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from news_shadow import NewsShadow


class _StubClassifier:
    backend = "stub"

    def classify(self, text):
        return {"is_relevant": True, "category": "FOMC", "sentiment": "risk_off",
                "confidence": 0.9, "backend": self.backend, "reason": "stub",
                "keywords": ["hawkish"]}


def test_disabled_writes_nothing(tmp_path):
    log = tmp_path / "news.log"
    sh = NewsShadow(enabled=False, log_path=str(log))
    assert sh.observe("Fed hikes", item_id="a") is None
    assert not log.exists()


def test_enabled_records_and_maps_symbols(tmp_path):
    log = tmp_path / "news.log"
    sh = NewsShadow(enabled=True, log_path=str(log),
                    enabled_symbols=["BTC", "EURUSD", "MES"],
                    classifier=_StubClassifier())
    rec = sh.observe("Fed hawkish surprise", item_id="fomc-1", source="calendar")
    assert rec is not None
    assert rec["stage"] == "news_shadow"
    assert rec["would_wake"] is True and rec["category"] == "FOMC"
    # FOMC impacts a broad set; only enabled symbols kept
    assert set(rec["affected_symbols"]) == {"BTC", "EURUSD", "MES"}
    obj = json.loads(log.read_text(encoding="utf-8").strip())
    assert obj["sentiment"] == "risk_off"


def test_dedupe_by_item_id(tmp_path):
    log = tmp_path / "news.log"
    sh = NewsShadow(enabled=True, log_path=str(log),
                    classifier=_StubClassifier())
    assert sh.observe("x", item_id="same") is not None
    assert sh.observe("x", item_id="same") is None   # second time deduped
    assert len(log.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_bad_classifier_never_raises(tmp_path):
    class _Boom:
        backend = "boom"

        def classify(self, text):
            raise RuntimeError("boom")

    log = tmp_path / "news.log"
    sh = NewsShadow(enabled=True, log_path=str(log), classifier=_Boom())
    rec = sh.observe("Fed hikes", item_id="b")
    # assess_news swallows the error -> not relevant, still a line, never raises
    assert rec is not None and rec["is_relevant"] is False


def test_auto_backend_keyword_fallback(tmp_path):
    log = tmp_path / "news.log"
    sh = NewsShadow(enabled=True, log_path=str(log))  # builds real classifier
    rec = sh.observe("CPI comes in hotter than expected", item_id="cpi-1")
    assert rec is not None
    assert rec["backend"] == "keyword" or rec["backend"].startswith("llm")


if __name__ == "__main__":
    import tempfile

    for fn in (test_disabled_writes_nothing, test_enabled_records_and_maps_symbols,
               test_dedupe_by_item_id, test_bad_classifier_never_raises,
               test_auto_backend_keyword_fallback):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("ALL NEWS-SHADOW TESTS PASSED")
