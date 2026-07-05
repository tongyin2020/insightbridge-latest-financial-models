"""Offline self-check for the RSS news feed parser (no network needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from news_feed import RssNewsFeed, _parse_feed

_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Fed Press</title>
  <item>
    <title>Federal Reserve issues FOMC statement</title>
    <description>The Committee decided to raise the target range.</description>
    <link>https://ex.com/a</link>
    <guid>guid-a</guid>
    <pubDate>Wed, 01 Jul 2026 18:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Speech by Chair on the economic outlook</title>
    <link>https://ex.com/b</link>
    <pubDate>Wed, 01 Jul 2026 12:00:00 GMT</pubDate>
  </item>
</channel></rss>"""

_ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>ECB monetary policy decision</title>
    <summary>Rates left unchanged.</summary>
    <link href="https://ecb.example/x"/>
    <id>atom-x</id>
    <updated>2026-07-01T13:00:00Z</updated>
  </entry>
</feed>"""


def test_parse_rss():
    items = _parse_feed(_RSS, "feedurl")
    assert len(items) == 2
    a = items[0]
    assert a.item_id == "guid-a" and a.title.startswith("Federal Reserve")
    assert a.url == "https://ex.com/a" and "raise the target" in a.summary


def test_parse_atom_href_and_id():
    items = _parse_feed(_ATOM, "feedurl")
    assert len(items) == 1
    x = items[0]
    assert x.item_id == "atom-x"
    assert x.url == "https://ecb.example/x"
    assert x.title == "ECB monetary policy decision"


def test_parse_garbage_returns_empty():
    assert _parse_feed(b"not xml at all", "u") == []
    assert _parse_feed(b"", "u") == []


def test_env_feeds_override(monkeypatch=None):
    import os
    os.environ["EVENTALPHA_NEWS_RSS"] = "https://one.example/rss, https://two.example/rss"
    try:
        f = RssNewsFeed()
        assert f.feeds == ["https://one.example/rss", "https://two.example/rss"]
    finally:
        del os.environ["EVENTALPHA_NEWS_RSS"]


def test_default_feeds_when_no_env():
    import os
    os.environ.pop("EVENTALPHA_NEWS_RSS", None)
    f = RssNewsFeed()
    assert len(f.feeds) >= 1 and all(u.startswith("http") for u in f.feeds)


if __name__ == "__main__":
    test_parse_rss()
    test_parse_atom_href_and_id()
    test_parse_garbage_returns_empty()
    test_env_feeds_override()
    test_default_feeds_when_no_env()
    print("ALL NEWS-FEED TESTS PASSED")
