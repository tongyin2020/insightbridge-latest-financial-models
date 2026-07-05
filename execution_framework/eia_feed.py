"""Step 2 · Phase E-3 — EIA weekly petroleum-status feed for the news gateway.

Turns the U.S. Energy Information Administration (EIA) Weekly Petroleum Status
Report into a *structured* headline the Phase-E gateway can classify, so an oil
inventory build/draw is captured observe-only alongside the RSS headlines.

Unlike a generic RSS title, EIA gives numbers (crude ending stocks, thousand
barrels). We fetch the latest weekly commercial crude stocks, compute the
week-over-week change (build = bearish for oil / risk_off, draw = bullish), and
emit ONE headline per weekly release (deduped by period date).

Design (mirrors ``news_feed.RssNewsFeed``):
  - Reads the API key from ``EIA_API_KEY`` (the v2 API requires a *free* key:
    https://www.eia.gov/opendata/register.php). **No key => fetch returns []**,
    so the gateway simply has no EIA items — never an error.
  - Dependency-free (urllib + json stdlib), fault-tolerant (any network / parse
    error => empty list, never raises), read-only (opens no subscriptions, places
    no orders).
  - Default OFF: the live loop only builds this feed when ``EVENTALPHA_EIA_FEED``
    is truthy AND a key is present.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from news_feed import NewsItem  # reuse the gateway's item shape

# EIA v2 series: Weekly U.S. Ending Stocks excluding SPR of Crude Oil (Mbbl).
_EIA_ENDPOINT = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
_CRUDE_SERIES = "WCESTUS1"
_UA = "Mozilla/5.0 (compatible; InsightBridgeNewsShadow/1.0)"


def _enabled_from_env() -> bool:
    return os.environ.get("EVENTALPHA_EIA_FEED", "").lower() in {
        "1", "true", "yes", "on"}


@dataclass
class EiaPetroleumFeed:
    """Poll the EIA weekly crude-stocks series and emit a classifiable headline.

    Returns ``[]`` (never raises) when no API key is configured or on any network
    / parse error, so it is safe to wire unconditionally."""

    api_key: Optional[str] = None
    series: str = _CRUDE_SERIES
    timeout: float = 6.0
    n_recent: int = 2          # need current + prior week to compute the change

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("EIA_API_KEY", "").strip() or None

    def _url(self) -> str:
        params = [
            ("api_key", self.api_key or ""),
            ("frequency", "weekly"),
            ("data[0]", "value"),
            ("facets[series][]", self.series),
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "desc"),
            ("offset", "0"),
            ("length", str(max(2, self.n_recent))),
        ]
        return _EIA_ENDPOINT + "?" + urllib.parse.urlencode(params)

    def _fetch_raw(self) -> Optional[bytes]:
        if not self.api_key:
            return None
        try:
            req = urllib.request.Request(self._url(), headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except Exception:                       # noqa: BLE001
            return None

    def fetch(self, max_items: int = 1) -> List[NewsItem]:
        raw = self._fetch_raw()
        if not raw:
            return []
        return _build_items(raw)[:max_items]


def _build_items(raw: bytes) -> List[NewsItem]:
    """Parse the EIA v2 JSON payload into a single week-over-week headline."""
    try:
        rows = json.loads(raw)["response"]["data"]
    except Exception:                           # noqa: BLE001
        return []
    # Keep only rows with a usable numeric value, newest first.
    parsed = []
    for r in rows:
        try:
            parsed.append((str(r["period"]), float(r["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not parsed:
        return []
    parsed.sort(key=lambda x: x[0], reverse=True)
    period, level = parsed[0]
    change = None
    if len(parsed) >= 2:
        change = level - parsed[1][1]

    # Compose a directional headline the classifier can read.
    #   build (stocks up)  => bearish crude  => risk_off
    #   draw  (stocks down) => bullish crude => risk_on
    lvl_mm = level / 1000.0                      # thousand bbl -> million bbl
    if change is None:
        title = (f"EIA Weekly Petroleum Status: U.S. commercial crude oil "
                 f"inventories at {lvl_mm:.1f} million barrels (week of {period}).")
    else:
        chg_mm = change / 1000.0
        if chg_mm >= 0:
            phrase = (f"rose {chg_mm:.1f} million barrels (crude oil inventory "
                      f"build, bearish for oil prices)")
        else:
            phrase = (f"fell {abs(chg_mm):.1f} million barrels (crude oil "
                      f"inventory draw, bullish for oil prices)")
        title = (f"EIA Weekly Petroleum Status: U.S. commercial crude oil "
                 f"inventories {phrase}, to {lvl_mm:.1f} million barrels "
                 f"(week of {period}).")

    return [NewsItem(
        item_id=f"eia:{_CRUDE_SERIES}:{period}",   # dedupe: one per weekly release
        title=title,
        summary="",
        url="https://www.eia.gov/petroleum/supply/weekly/",
        published=period,
        feed="eia_weekly_petroleum_status",
    )]
