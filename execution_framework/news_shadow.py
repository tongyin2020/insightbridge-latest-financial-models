"""Step 2 · Phase E — observe-only ("shadow") recorder for the LLM news gateway.

Mirrors ``MicrostructureShadow`` / ``TimeSeriesShadow``: per scan it takes macro
news / calendar items, classifies each (LLM if a key is configured, else a
labelled keyword baseline) and records *whether the gateway WOULD wake* on it and
with what sentiment/confidence — **without ever touching orders or the live
decision**. This lets us watch, on the paper feed, whether the news read looks
sane before it is ever used, and produces the log Phase C will calibrate against.

Default OFF. Enable with ``EVENTALPHA_NEWS_SHADOW=1`` (or ``enabled=True``).
Import is fault-tolerant and the LLM client is lazy-loaded: if the core module or
the LLM client/key is unavailable the observer degrades to the keyword baseline /
no-op so it can never break the live loop.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_NEWS_OK = True
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from eventalpha_core.advanced.news_gateway import (
        NewsGatewayConfig,
        assess_news,
        build_classifier,
    )
except Exception:                               # noqa: BLE001
    _NEWS_OK = False
    NewsGatewayConfig = None
    assess_news = None
    build_classifier = None

try:
    from economic_calendar import EVENT_IMPACT
except Exception:                               # noqa: BLE001
    EVENT_IMPACT = {}


def _enabled_from_env() -> bool:
    return os.environ.get(
        "EVENTALPHA_NEWS_SHADOW", "").lower() in {"1", "true", "yes", "on"}


class NewsShadow:
    """Observe-only news-gateway recorder. Never places, modifies, or blocks
    orders; only appends JSONL describing what the gateway would say. Dedupes by
    item id so a scheduled event is logged once, not every scan."""

    def __init__(self, enabled: Optional[bool] = None,
                 log_path: Optional[str] = None,
                 config: Optional["NewsGatewayConfig"] = None,
                 backend: str = "auto",
                 enabled_symbols: Optional[List[str]] = None,
                 classifier: Optional[Any] = None) -> None:
        if enabled is None:
            enabled = _enabled_from_env()
        self.enabled = bool(enabled) and _NEWS_OK
        self.news_ok = _NEWS_OK
        self.log_path = Path(log_path) if log_path else None
        self.config = config or (NewsGatewayConfig() if _NEWS_OK else None)
        self.backend = backend
        self.enabled_symbols = set(enabled_symbols or [])
        self._classifier = classifier          # lazily built on first use if None
        self._seen: set = set()
        self.n_observed = 0

    def _get_classifier(self):
        if self._classifier is None and _NEWS_OK:
            self._classifier = build_classifier(self.backend)
        return self._classifier

    def _symbols_for(self, category: str) -> List[str]:
        syms = list(EVENT_IMPACT.get(category, []))
        if self.enabled_symbols:
            syms = [s for s in syms if s in self.enabled_symbols]
        return syms

    def observe(self, text: str, item_id: Optional[str] = None,
                source: str = "calendar") -> Optional[Dict[str, Any]]:
        """Classify one news / calendar item and log one JSONL line. Returns
        ``None`` when disabled or when this ``item_id`` was already logged.
        Fail-safe: any error is swallowed so the live loop is never disturbed."""
        if not self.enabled:
            return None
        try:
            key = item_id or (text or "")
            if key in self._seen:
                return None
            classifier = self._get_classifier()
            if classifier is None:
                return None
            a = assess_news(text or "", classifier, self.config)
            rec = {
                "stage": "news_shadow",
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "item_id": item_id,
                "text": (text or "")[:280],
                "backend": a.backend,
                "is_relevant": bool(a.is_relevant),
                "category": a.category,
                "sentiment": a.sentiment,
                "confidence": round(a.confidence, 4),
                "would_wake": bool(a.would_wake(self.config)),
                "affected_symbols": self._symbols_for(a.category),
                "reason": a.reason,
                "keywords": a.keywords,
            }
            self._seen.add(key)
            self.n_observed += 1
            if self.log_path:
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            return rec
        except Exception:                       # noqa: BLE001
            return None
