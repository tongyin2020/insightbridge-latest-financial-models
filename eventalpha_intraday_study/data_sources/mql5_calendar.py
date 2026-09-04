"""Real historical macro consensus forecasts from the MQL5 economic calendar
(free, public, no key). This is the one input the study could not get for free:
the market's *consensus forecast* alongside the *actual* release, which together
give the true macro **surprise = actual - forecast** that moves price.

Trading Economics gates its calendar API behind the Enterprise plan; FXStreet's
endpoint returned empty and Investing.com sits behind Cloudflare. MQL5 exposes a
per-indicator history page (`.../<slug>/history`) whose rows carry actual /
forecast / previous, reachable with a plain request.

Responses are cached under `<data>/mql5_cache/` so the study is re-runnable
offline.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ..config import data_dir

_BASE = "https://www.mql5.com/en/economic-calendar/united-states"

# MQL5 slug per event type. CPI uses headline month-over-month (the most
# surprise-sensitive headline print); FOMC uses the policy-rate decision.
SLUG = {
    "NFP":  "nonfarm-payrolls",
    "CPI":  "consumer-price-index-mm",
    "FOMC": "fed-interest-rate-decision",
}


def _cache_dir() -> Path:
    p = data_dir() / "mql5_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _num(raw: str) -> float | None:
    """Parse '57 K' / '0.2%' / '-1.3 K' / '4.50%' -> float magnitude."""
    if raw is None:
        return None
    s = raw.replace("&#xA0;", " ").replace("\xa0", " ")
    s = re.sub(r"<[^>]+>", "", s).strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    val = float(m.group(0))
    if re.search(r"\bM\b", s):        # millions -> thousands (keep K units)
        val *= 1000.0
    return val


def _fetch_history_html(slug: str) -> str | None:
    url = f"{_BASE}/{slug}/history"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"[mql5] fetch failed for {slug}: {exc}")
        return None


_DATE_RE = re.compile(r'data-date="(\d+)"')
_ACTUAL_RE = re.compile(r'event-table-history__actual[^"]*">(.*?)</div>', re.DOTALL)
_FC_RE = re.compile(r'event-table-history__forecast">(.*?)</div>', re.DOTALL)
_PREV_RE = re.compile(r'event-table-history__previous">(.*?)</div>', re.DOTALL)


def _parse(html: str) -> list[dict]:
    """Split into per-event blocks and pull each field within its own block so
    a missing field in one row can't bleed into the next."""
    out = []
    for block in html.split("event-table-history__item")[1:]:
        d = _DATE_RE.search(block)
        if not d:
            continue
        ts = datetime.fromtimestamp(int(d.group(1)) / 1000, tz=timezone.utc)
        a = _ACTUAL_RE.search(block)
        f = _FC_RE.search(block)
        p = _PREV_RE.search(block)
        out.append({
            "date": ts.strftime("%Y-%m-%d"),
            "ym": ts.strftime("%Y-%m"),
            "actual": _num(a.group(1)) if a else None,
            "forecast": _num(f.group(1)) if f else None,
            "previous": _num(p.group(1)) if p else None,
        })
    return out


def history(event_type: str) -> list[dict]:
    """Return cached/fetched list of {date, ym, actual, forecast, previous}."""
    slug = SLUG.get(event_type)
    if not slug:
        return []
    cache = _cache_dir() / f"{event_type}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            pass
    html = _fetch_history_html(slug)
    if not html:
        return []
    rows = _parse(html)
    if rows:
        cache.write_text(json.dumps(rows))
    return rows


def surprise_map(event_type: str) -> dict[str, dict]:
    """Map release-month 'YYYY-MM' -> {actual, forecast, surprise} (actual-forecast)."""
    out = {}
    for r in history(event_type):
        if r["actual"] is None or r["forecast"] is None:
            continue
        out[r["ym"]] = {
            "actual": r["actual"],
            "forecast": r["forecast"],
            "surprise": round(r["actual"] - r["forecast"], 4),
        }
    return out
