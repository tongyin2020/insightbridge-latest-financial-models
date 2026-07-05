"""Offline self-check for the LLM news gateway (no LLM key / client needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eventalpha_core.advanced.news_gateway import (
    KeywordNewsClassifier,
    NewsGatewayConfig,
    assess_news,
    build_classifier,
)


def test_keyword_detects_hawkish_fed_risk_off():
    a = assess_news("Fed delivers hawkish surprise, signals another rate hike",
                    KeywordNewsClassifier())
    assert a.is_relevant and a.category == "FOMC"
    assert a.sentiment == "risk_off"
    assert a.would_wake(NewsGatewayConfig())


def test_keyword_detects_dovish_risk_on():
    a = assess_news("ECB turns dovish, hints at rate cut as inflation cools",
                    KeywordNewsClassifier())
    assert a.is_relevant and a.category in ("ECB", "FOMC", "CPI")
    assert a.sentiment == "risk_on"


def test_scheduled_title_relevant_but_neutral_low_conf():
    cfg = NewsGatewayConfig()
    a = assess_news("Nonfarm Payrolls", KeywordNewsClassifier())
    assert a.is_relevant and a.category == "NFP"
    assert a.sentiment == "neutral"
    # neutral scheduled title should NOT clear the wake threshold (placeholder)
    assert a.would_wake(cfg) is False


def test_irrelevant_text():
    a = assess_news("Local bakery wins county pie contest", KeywordNewsClassifier())
    assert a.is_relevant is False and a.category == "NONE"
    assert a.would_wake(NewsGatewayConfig()) is False


def test_geopolitics_risk_off():
    a = assess_news("Missile strike escalates conflict, oil surges",
                    KeywordNewsClassifier())
    assert a.is_relevant and a.category in ("GEOPOLITICS", "OPEC")
    assert a.sentiment == "risk_off"


def test_classifier_error_degrades():
    class _Boom:
        backend = "boom"

        def classify(self, text):
            raise RuntimeError("llm exploded")

    a = assess_news("Fed hikes rates", _Boom())
    assert a.is_relevant is False and a.reason.startswith("classify_error")


def test_build_classifier_falls_back_to_keyword():
    # No LLM key in CI -> must degrade to keyword, never raise.
    c = build_classifier("auto")
    assert hasattr(c, "classify")
    out = c.classify("CPI comes in hotter than expected")
    assert out["category"] == "CPI" and out["backend"] in ("keyword",) or "llm" in out["backend"]


if __name__ == "__main__":
    test_keyword_detects_hawkish_fed_risk_off()
    test_keyword_detects_dovish_risk_on()
    test_scheduled_title_relevant_but_neutral_low_conf()
    test_irrelevant_text()
    test_geopolitics_risk_off()
    test_classifier_error_degrades()
    test_build_classifier_falls_back_to_keyword()
    print("ALL NEWS-GATEWAY TESTS PASSED")
