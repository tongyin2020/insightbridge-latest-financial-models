"""Real historical news-tone from the GDELT 2.0 DOC API (free, no key).

This is the price-INDEPENDENT news feed the full-stack replay was missing: GDELT
indexes global online news every 15 minutes back to 2017 and exposes an average
"tone" (linguistic positivity, negative = negative coverage) per topic over time.
Unlike Firecrawl it CAN be queried for a past timestamp, so we can attach the
real news mood around each 2024-2025 macro release.

Caveat kept explicit for the caller: tone is *emotional positivity of coverage*,
not a market-directional surprise. Whether it predicts asset direction is exactly
what the replay measures -- we do NOT assume it does.

Responses are cached to `<data>/gdelt_cache/` so the study is re-runnable
offline; live requests are throttled to GDELT's 1-request-per-5s limit.
"""
from __future__ import annotations

import json
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import data_dir

_API = "https://api.gdeltproject.org/api/v2/doc/doc"
_MIN_INTERVAL_S = 8.0            # GDELT throttles aggressively; keep well clear
_MAX_RETRIES = 4                 # exponential backoff on 429 / transient errors
_WINDOW_H = 3                    # hours of tone sampled each side of T0
_last_call = [0.0]

# macro-topic keyword query per event type (broad, high-volume topics)
TOPIC = {
    "CPI":  "inflation",
    "NFP":  "unemployment",
    "FOMC": "federal reserve",
}


def _cache_dir() -> Path:
    p = data_dir() / "gdelt_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "eventalpha-research/1.0"})
    for attempt in range(_MAX_RETRIES):
        wait = _MIN_INTERVAL_S - (_time.time() - _last_call[0])
        if wait > 0:
            _time.sleep(wait)
        body = None
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                body = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < _MAX_RETRIES - 1:
                backoff = _MIN_INTERVAL_S * (2 ** (attempt + 1))
                print(f"[gdelt] 429, backing off {backoff:.0f}s")
                _last_call[0] = _time.time()
                _time.sleep(backoff)
                continue
            print(f"[gdelt] request failed: {exc}")
            _last_call[0] = _time.time()
            return None
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[gdelt] request failed: {exc}")
            _last_call[0] = _time.time()
            return None
        finally:
            _last_call[0] = _time.time()
        body = body.strip()
        if not body.startswith("{"):
            # rate-limit / error text page -> retry with backoff
            if attempt < _MAX_RETRIES - 1:
                backoff = _MIN_INTERVAL_S * (2 ** (attempt + 1))
                print(f"[gdelt] throttled text, backing off {backoff:.0f}s")
                _time.sleep(backoff)
                continue
            print(f"[gdelt] non-json response: {body[:80]!r}")
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None
    return None


def _timeline_tone(event_type: str, t0: datetime) -> list[tuple[datetime, float]]:
    topic = TOPIC.get(event_type)
    if topic is None:
        return []
    start = (t0 - timedelta(hours=_WINDOW_H)).strftime("%Y%m%d%H%M%S")
    end = (t0 + timedelta(hours=_WINDOW_H)).strftime("%Y%m%d%H%M%S")
    q = urllib.parse.urlencode({
        "query": topic,
        "mode": "timelinetone",
        "startdatetime": start,
        "enddatetime": end,
        "format": "json",
    })
    payload = _fetch_json(f"{_API}?{q}")
    if not payload:
        return []
    out = []
    for series in payload.get("timeline", []):
        if series.get("series") != "Average Tone":
            continue
        for pt in series.get("data", []):
            try:
                ts = datetime.strptime(pt["date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                out.append((ts, float(pt["value"])))
            except (KeyError, ValueError):
                continue
    return out


def tone_signal_cached(event_id: str) -> dict | None:
    """Read a previously-fetched tone summary from cache only (no network)."""
    cache = _cache_dir() / f"{event_id}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            return None
    return None


def tone_signal(event_id: str, event_type: str, t0: datetime) -> dict | None:
    """Return the news-tone summary around one event (cached), or None.

    Keys: pre_tone, post_tone, tone_change (post-pre), n_pre, n_post.
    tone_change > 0 == coverage turned more positive after the release.
    """
    cache = _cache_dir() / f"{event_id}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            pass
    series = _timeline_tone(event_type, t0)
    if not series:
        return None
    pre = [v for ts, v in series if ts < t0]
    post = [v for ts, v in series if ts >= t0]
    if not pre or not post:
        return None
    summary = {
        "pre_tone": round(sum(pre) / len(pre), 4),
        "post_tone": round(sum(post) / len(post), 4),
        "tone_change": round(sum(post) / len(post) - sum(pre) / len(pre), 4),
        "n_pre": len(pre),
        "n_post": len(post),
    }
    cache.write_text(json.dumps(summary))
    return summary
