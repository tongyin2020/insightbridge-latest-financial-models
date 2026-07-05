"""Step 2 · Phase E-2 — free RSS news feed for the news gateway.

Fetches recent headlines from macro-focused RSS/Atom feeds so the Phase-E gateway
has a *continuous* stream to classify (the economic calendar alone is too sparse —
no upcoming event => nothing to read). Dependency-free (urllib + xml stdlib),
fault-tolerant (any network / parse error => empty list, never raises), and it
opens **no** subscriptions and places no orders — it only reads public feeds.

Defaults are official, low-volume, highly-relevant sources (Fed & ECB press
releases) so LLM cost stays negligible. Override / extend with
``EVENTALPHA_NEWS_RSS`` (comma-separated feed URLs).
"""
from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional
from xml.etree import ElementTree as ET

# Official, low-volume, macro-relevant defaults (no API key required).
DEFAULT_FEEDS: List[str] = [
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.ecb.europa.eu/rss/press.html",
]

_UA = "Mozilla/5.0 (compatible; InsightBridgeNewsShadow/1.0)"


@dataclass
class NewsItem:
    item_id: str          # stable id (guid/link) for dedupe
    title: str
    summary: str = ""
    url: str = ""
    published: str = ""
    feed: str = ""


@dataclass
class RssNewsFeed:
    """Poll a set of RSS/Atom feeds and return recent items (newest first)."""
    feeds: List[str] = field(default_factory=list)
    timeout: float = 6.0
    max_items_per_feed: int = 15

    def __post_init__(self) -> None:
        if not self.feeds:
            env = os.environ.get("EVENTALPHA_NEWS_RSS", "").strip()
            self.feeds = ([u.strip() for u in env.split(",") if u.strip()]
                          if env else list(DEFAULT_FEEDS))

    def _fetch_one(self, url: str) -> List[NewsItem]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except Exception:                       # noqa: BLE001
            return []
        return _parse_feed(raw, url)[: self.max_items_per_feed]

    def fetch(self, max_items: int = 20) -> List[NewsItem]:
        """Return up to ``max_items`` recent items across all feeds. Never raises;
        a feed that fails is simply skipped."""
        out: List[NewsItem] = []
        for url in self.feeds:
            out.extend(self._fetch_one(url))
        return out[:max_items]


def _text(el: Optional[ET.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_feed(raw: bytes, feed_url: str) -> List[NewsItem]:
    """Parse RSS 2.0 or Atom into ``NewsItem``s. Tolerant of namespaces and of
    either ``<item>`` (RSS) or ``<entry>`` (Atom)."""
    try:
        root = ET.fromstring(raw)
    except Exception:                           # noqa: BLE001
        return []
    items: List[NewsItem] = []
    for node in root.iter():
        if _strip_ns(node.tag) not in ("item", "entry"):
            continue
        title = summary = url = pub = gid = ""
        for child in list(node):
            t = _strip_ns(child.tag)
            if t == "title":
                title = _text(child)
            elif t in ("description", "summary", "content"):
                summary = _text(child)
            elif t == "link":
                # RSS: text; Atom: href attribute
                url = _text(child) or child.attrib.get("href", "")
            elif t in ("pubdate", "published", "updated", "date"):
                pub = _text(child)
            elif t in ("guid", "id"):
                gid = _text(child)
        item_id = gid or url or title
        if not item_id:
            continue
        items.append(NewsItem(item_id=item_id, title=title, summary=summary,
                              url=url, published=pub, feed=feed_url))
    return items
