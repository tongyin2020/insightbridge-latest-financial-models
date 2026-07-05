"""Step 2 · Phase E — LLM news gateway (macro-event awareness + directional prior).

═══════════════════════════════════════════════════════════════════════════════
IMPORTANT — every numeric default in this module is an UNVALIDATED PLACEHOLDER.
═══════════════════════════════════════════════════════════════════════════════
The wake threshold and the keyword→confidence heuristics are provisional priors so
the *mechanism* can run observe-only. They are NOT measured facts and must be
calibrated on real event history before any switch is turned on.

Idea: watch macro news / the economic calendar, classify whether an item is a
market-moving event (Fed / CPI / NFP / OPEC / geopolitics …), and attach a coarse
risk sentiment + confidence. This is an *awareness / prior* layer — it never
initiates a trade, it only says "a relevant event is here, here's the read". The
per-symbol long/short translation is deliberately deferred to Phase C calibration.

Design rules (mirror ``microstructure.py`` / ``timeseries_confirm.py``):
  - Pure logic in :func:`assess_news`; the classifier is injected.
  - Heavy/paid deps (an LLM client) are **lazily imported**; if no API key or the
    client is unavailable we fall back to a dependency-free
    :class:`KeywordNewsClassifier` and label the backend honestly, so nothing is
    overstated and the live loop never breaks.
  - Degrades to "not relevant / neutral" (never a hard failure) on any error.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


# ── provisional, UNVALIDATED defaults ────────────────────────────────────────
@dataclass(frozen=True)
class NewsGatewayConfig:
    """News-gateway parameters (all provisional placeholders)."""
    min_confidence_wake: float = 0.60      # confidence needed to "wake" on an item
    relevant_categories: tuple = (
        "FOMC", "CPI", "PPI", "NFP", "RETAIL_SALES",
        "ECB", "BOJ", "OPEC", "GEOPOLITICS", "TREASURY_AUCTION",
    )


@dataclass
class NewsAssessment:
    """One classified news / calendar item."""
    is_relevant: bool
    category: str
    sentiment: str            # "risk_on" / "risk_off" / "neutral"
    confidence: float
    backend: str
    reason: str
    keywords: List[str] = field(default_factory=list)

    def would_wake(self, config: NewsGatewayConfig) -> bool:
        return bool(self.is_relevant
                    and self.category in config.relevant_categories
                    and self.confidence >= config.min_confidence_wake)


# ── keyword baseline (dependency-free) ───────────────────────────────────────
# Placeholder patterns: category detection + coarse risk sentiment. These are
# rules-of-thumb, NOT validated mappings; Phase C will replace them.
_CATEGORY_PATTERNS: List[tuple] = [
    ("FOMC", r"\b(fomc|federal reserve|fed\b|rate decision|powell|interest rate)\b"),
    ("CPI", r"\b(cpi|consumer price|inflation report)\b"),
    ("PPI", r"\b(ppi|producer price)\b"),
    ("NFP", r"\b(nonfarm|non-farm|payrolls|jobs report|unemployment rate)\b"),
    ("RETAIL_SALES", r"\b(retail sales)\b"),
    ("ECB", r"\b(ecb|european central bank|lagarde)\b"),
    ("BOJ", r"\b(boj|bank of japan|ueda)\b"),
    ("OPEC", r"\b(opec|crude output|oil production|barrels per day)\b"),
    ("GEOPOLITICS", r"\b(war|invasion|sanction|strike|attack|conflict|missile)\b"),
    ("TREASURY_AUCTION", r"\b(treasury auction|ust auction|bond auction)\b"),
]
_RISK_OFF = re.compile(
    r"\b(hawkish|rate hike|hikes|raises rates|higher than expected|hotter|"
    r"surges?|escalat\w+|war|invasion|attack|sanction|misses?|worse than expected)\b",
    re.I)
_RISK_ON = re.compile(
    r"\b(dovish|rate cut|cuts rates|lower than expected|cooler|beats?|"
    r"better than expected|de-escalat\w+|ceasefire|truce|softer)\b",
    re.I)


class KeywordNewsClassifier:
    """Dependency-free baseline: regex category + coarse risk sentiment. NOT an
    LLM. ``backend="keyword"`` so it is never mistaken for a model read. Exists so
    the observe-only plumbing + tests work before any LLM key is configured."""

    backend = "keyword"

    def classify(self, text: str) -> Dict[str, Any]:
        t = (text or "").strip()
        if not t:
            return {"is_relevant": False, "category": "NONE", "sentiment": "neutral",
                    "confidence": 0.0, "backend": self.backend,
                    "reason": "empty_text", "keywords": []}
        low = t.lower()
        category = "NONE"
        hits: List[str] = []
        for name, pat in _CATEGORY_PATTERNS:
            m = re.search(pat, low, re.I)
            if m:
                category = name
                hits.append(m.group(0))
                break
        if category == "NONE":
            return {"is_relevant": False, "category": "NONE", "sentiment": "neutral",
                    "confidence": 0.0, "backend": self.backend,
                    "reason": "no_category_match", "keywords": []}
        # coarse sentiment + placeholder confidence
        off = _RISK_OFF.search(t)
        on = _RISK_ON.search(t)
        if off and not on:
            sentiment, conf = "risk_off", 0.70
            hits.append(off.group(0))
        elif on and not off:
            sentiment, conf = "risk_on", 0.70
            hits.append(on.group(0))
        else:
            # category matched but no clear directional phrase (e.g. a scheduled
            # event title) -> relevant awareness, but low directional confidence.
            sentiment, conf = "neutral", 0.50
        return {"is_relevant": True, "category": category, "sentiment": sentiment,
                "confidence": conf, "backend": self.backend,
                "reason": f"keyword:{category}:{sentiment}", "keywords": hits}


# ── optional LLM backend (lazy, needs API key) ───────────────────────────────
_LLM_SYSTEM_PROMPT = (
    "You classify a financial news headline for a macro event-driven trader. "
    "Return STRICT JSON with keys: is_relevant (bool), category (one of FOMC, CPI, "
    "PPI, NFP, RETAIL_SALES, ECB, BOJ, OPEC, GEOPOLITICS, TREASURY_AUCTION, NONE), "
    "sentiment (risk_on, risk_off, or neutral — risk_off = hawkish/hot/escalation), "
    "confidence (0..1), reason (short). No prose, JSON only."
)


class LLMNewsClassifier:
    """LLM-backed classifier (lazy import). Supports OpenAI or Anthropic, selected
    by whichever API key is present. Raises at construction if no client/key is
    available, so :func:`build_classifier` can fall back cleanly."""

    backend = "llm"

    def __init__(self, provider: Optional[str] = None,
                 model: Optional[str] = None) -> None:
        prov = (provider or os.environ.get("EVENTALPHA_NEWS_LLM_PROVIDER") or "").lower()
        if not prov:
            if os.environ.get("OPENAI_API_KEY"):
                prov = "openai"
            elif os.environ.get("ANTHROPIC_API_KEY"):
                prov = "anthropic"
        if prov == "openai":
            from openai import OpenAI  # type: ignore
            self._client = OpenAI()
            self._provider = "openai"
            self._model = model or os.environ.get(
                "EVENTALPHA_NEWS_LLM_MODEL", "gpt-4o-mini")
        elif prov == "anthropic":
            import anthropic  # type: ignore
            self._client = anthropic.Anthropic()
            self._provider = "anthropic"
            self._model = model or os.environ.get(
                "EVENTALPHA_NEWS_LLM_MODEL", "claude-3-5-haiku-latest")
        else:
            raise RuntimeError("no LLM provider/key available")
        self.backend = f"llm:{self._provider}"

    def _raw(self, text: str) -> str:
        if self._provider == "openai":
            resp = self._client.chat.completions.create(
                model=self._model, temperature=0,
                messages=[{"role": "system", "content": _LLM_SYSTEM_PROMPT},
                          {"role": "user", "content": text}])
            return resp.choices[0].message.content or ""
        resp = self._client.messages.create(
            model=self._model, max_tokens=300, temperature=0,
            system=_LLM_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}])
        return "".join(getattr(b, "text", "") for b in resp.content)

    def classify(self, text: str) -> Dict[str, Any]:
        raw = self._raw(text or "")
        obj = _extract_json(raw)
        if not obj:
            return {"is_relevant": False, "category": "NONE", "sentiment": "neutral",
                    "confidence": 0.0, "backend": self.backend,
                    "reason": "llm_unparseable", "keywords": []}
        return {
            "is_relevant": bool(obj.get("is_relevant")),
            "category": str(obj.get("category", "NONE")).upper(),
            "sentiment": str(obj.get("sentiment", "neutral")).lower(),
            "confidence": float(obj.get("confidence", 0.0) or 0.0),
            "backend": self.backend,
            "reason": str(obj.get("reason", "llm")),
            "keywords": [],
        }


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:                           # noqa: BLE001
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:                       # noqa: BLE001
            return None


def build_classifier(backend: str = "auto"):
    """Return a classifier. ``auto`` tries an LLM (if a key is set) then falls
    back to the keyword baseline. Never raises."""
    b = (backend or "auto").lower()
    if b in ("llm", "auto"):
        try:
            return LLMNewsClassifier()
        except Exception:                       # noqa: BLE001
            if b == "llm":
                return KeywordNewsClassifier()
    return KeywordNewsClassifier()


def assess_news(text: str, classifier,
                config: NewsGatewayConfig = NewsGatewayConfig()) -> NewsAssessment:
    """Classify one item and build a :class:`NewsAssessment`. Never raises: any
    classifier error degrades to a not-relevant/neutral assessment."""
    backend = getattr(classifier, "backend", "unknown")
    try:
        out = classifier.classify(text or "")
    except Exception as exc:                     # noqa: BLE001
        return NewsAssessment(False, "NONE", "neutral", 0.0, backend,
                              f"classify_error:{exc}", [])
    return NewsAssessment(
        is_relevant=bool(out.get("is_relevant")),
        category=str(out.get("category", "NONE")).upper(),
        sentiment=str(out.get("sentiment", "neutral")).lower(),
        confidence=float(out.get("confidence", 0.0) or 0.0),
        backend=str(out.get("backend", backend)),
        reason=str(out.get("reason", "")),
        keywords=list(out.get("keywords", []) or []),
    )
