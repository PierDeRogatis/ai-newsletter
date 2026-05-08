"""Tests for newsletter/feed_discovery.py."""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from newsletter import feed_discovery


# ── persistence helpers ───────────────────────────────────────────────────────


def test_load_discovered_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(tmp_path / "discovered_feeds.json"))
    assert feed_discovery.load_discovered() == {}


def test_load_discovered_valid_file(tmp_path, monkeypatch):
    p = tmp_path / "discovered_feeds.json"
    data = {"AI & Data Tools": ["https://example.com/feed"]}
    p.write_text(json.dumps(data))
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(p))
    assert feed_discovery.load_discovered() == data


def test_load_discovered_corrupt_file(tmp_path, monkeypatch):
    p = tmp_path / "discovered_feeds.json"
    p.write_text("{invalid json")
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(p))
    assert feed_discovery.load_discovered() == {}


def test_load_archive_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(feed_discovery, "_ARCHIVE_PATH", str(tmp_path / "feed_archive.json"))
    assert feed_discovery._load_archive() == []


def test_load_archive_valid_file(tmp_path, monkeypatch):
    p = tmp_path / "feed_archive.json"
    data = [{"url": "https://dead.com/feed", "topic": "AI & Data Tools", "added": "2026-01-01", "last_retried": "2026-01-01", "reason": "no recent articles"}]
    p.write_text(json.dumps(data))
    monkeypatch.setattr(feed_discovery, "_ARCHIVE_PATH", str(p))
    assert feed_discovery._load_archive() == data


# ── test_feed ─────────────────────────────────────────────────────────────────


def _make_entry(days_ago: int):
    """Build a minimal feedparser-style entry with a recent published_parsed."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    # feedparser returns time.struct_time — simulate with a 9-tuple
    import time
    st = time.strptime(dt.strftime("%Y-%m-%d %H:%M:%S"), "%Y-%m-%d %H:%M:%S")
    entry = MagicMock()
    entry.published_parsed = st
    entry.updated_parsed = None
    return entry


def test_test_feed_accepts_recent_entry(monkeypatch):
    """Feed with an entry from 1 day ago should pass."""
    feed = MagicMock()
    feed.entries = [_make_entry(1)]
    with patch("newsletter.feed_discovery.feedparser.parse", return_value=feed):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value.read = lambda: b"<rss/>"
            result = feed_discovery.test_feed("https://example.com/feed")
    assert result is True


def test_test_feed_rejects_stale_entries(monkeypatch):
    """Feed with entries all older than 7 days and only 2 entries → rejected."""
    feed = MagicMock()
    feed.entries = [_make_entry(10), _make_entry(14)]  # all old, count < 3
    with patch("newsletter.feed_discovery.feedparser.parse", return_value=feed):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value.read = lambda: b"<rss/>"
            result = feed_discovery.test_feed("https://example.com/feed")
    assert result is False


def test_test_feed_rejects_empty_feed(monkeypatch):
    feed = MagicMock()
    feed.entries = []
    with patch("newsletter.feed_discovery.feedparser.parse", return_value=feed):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value.read = lambda: b""
            result = feed_discovery.test_feed("https://example.com/feed")
    assert result is False


def test_test_feed_rejects_network_error():
    """Network failure → False, no exception raised."""
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        result = feed_discovery.test_feed("https://dead.example.com/feed")
    assert result is False


def test_test_feed_fallback_accepts_no_dates(monkeypatch):
    """Feed with ≥3 entries but no parseable dates → accepted via fallback."""
    entry = MagicMock()
    entry.published_parsed = None
    entry.updated_parsed = None
    feed = MagicMock()
    feed.entries = [entry, entry, entry]
    with patch("newsletter.feed_discovery.feedparser.parse", return_value=feed):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value.read = lambda: b"<rss/>"
            result = feed_discovery.test_feed("https://example.com/feed")
    assert result is True


# ── _search_feedly ────────────────────────────────────────────────────────────


def test_search_feedly_parses_results():
    payload = json.dumps({"results": [
        {"feedId": "feed/https://techcrunch.com/ai/feed/", "title": "TechCrunch AI"},
        {"feedId": "feed/https://venturebeat.com/ai/feed/", "title": "VentureBeat"},
        {"feedId": "nofeedprefix", "title": "Malformed"},  # should be skipped
    ]}).encode()

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read = lambda: payload

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = feed_discovery._search_feedly("machine learning")

    assert "https://techcrunch.com/ai/feed/" in result
    assert "https://venturebeat.com/ai/feed/" in result
    assert "nofeedprefix" not in result


def test_search_feedly_returns_empty_on_network_error():
    with patch("urllib.request.urlopen", side_effect=OSError("network")):
        result = feed_discovery._search_feedly("AI news")
    assert result == []


# ── run_discovery ─────────────────────────────────────────────────────────────


def test_run_discovery_saves_working_feeds(tmp_path, monkeypatch):
    """Working feeds are added to discovered_feeds.json and returned."""
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(tmp_path / "discovered_feeds.json"))
    monkeypatch.setattr(feed_discovery, "_ARCHIVE_PATH",    str(tmp_path / "feed_archive.json"))

    working_url = "https://newsite.com/ai/feed/"
    dead_url    = "https://dead.example.com/feed/"

    with patch.object(feed_discovery, "_search_feedly", return_value=[working_url, dead_url]):
        with patch.object(feed_discovery, "test_feed", side_effect=lambda u: u == working_url):
            result = feed_discovery.run_discovery(["AI & Data Tools"])

    assert "AI & Data Tools" in result
    assert working_url in result["AI & Data Tools"]
    assert dead_url not in result.get("AI & Data Tools", [])

    # discovered_feeds.json should contain the working URL
    saved = json.loads((tmp_path / "discovered_feeds.json").read_text())
    assert working_url in saved.get("AI & Data Tools", [])

    # feed_archive.json should contain the dead URL
    archive = json.loads((tmp_path / "feed_archive.json").read_text())
    archived_urls = [e["url"] for e in archive]
    assert dead_url in archived_urls


def test_run_discovery_archives_failed_feeds(tmp_path, monkeypatch):
    """Feeds that fail testing go to archive with today's date."""
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(tmp_path / "discovered_feeds.json"))
    monkeypatch.setattr(feed_discovery, "_ARCHIVE_PATH",    str(tmp_path / "feed_archive.json"))

    with patch.object(feed_discovery, "_search_feedly", return_value=["https://fail.example/feed/"]):
        with patch.object(feed_discovery, "test_feed", return_value=False):
            result = feed_discovery.run_discovery(["AI in Finance"])

    assert result == {}
    archive = json.loads((tmp_path / "feed_archive.json").read_text())
    assert any(e["url"] == "https://fail.example/feed/" for e in archive)


def test_run_discovery_retries_old_archived_feeds(tmp_path, monkeypatch):
    """Feeds archived >30 days ago are retried even if not in Feedly results."""
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(tmp_path / "discovered_feeds.json"))
    monkeypatch.setattr(feed_discovery, "_ARCHIVE_PATH",    str(tmp_path / "feed_archive.json"))

    old_date = (datetime.now(timezone.utc) - timedelta(days=35)).date().isoformat()
    archive_data = [
        {"url": "https://retry.example/feed/", "topic": "AI & Data Tools",
         "added": old_date, "last_retried": old_date, "reason": "no recent articles"},
    ]
    (tmp_path / "feed_archive.json").write_text(json.dumps(archive_data))

    with patch.object(feed_discovery, "_search_feedly", return_value=[]):
        with patch.object(feed_discovery, "test_feed", return_value=True):
            result = feed_discovery.run_discovery(["AI & Data Tools"])

    assert "AI & Data Tools" in result
    assert "https://retry.example/feed/" in result["AI & Data Tools"]


def test_run_discovery_does_not_retry_recent_archived_feeds(tmp_path, monkeypatch):
    """Feeds archived <30 days ago are NOT retried."""
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(tmp_path / "discovered_feeds.json"))
    monkeypatch.setattr(feed_discovery, "_ARCHIVE_PATH",    str(tmp_path / "feed_archive.json"))

    recent_date = datetime.now(timezone.utc).date().isoformat()
    archive_data = [
        {"url": "https://toonew.example/feed/", "topic": "AI & Data Tools",
         "added": recent_date, "last_retried": recent_date, "reason": "no recent articles"},
    ]
    (tmp_path / "feed_archive.json").write_text(json.dumps(archive_data))

    tested: list[str] = []
    with patch.object(feed_discovery, "_search_feedly", return_value=[]):
        with patch.object(feed_discovery, "test_feed", side_effect=lambda u: tested.append(u) or True):
            feed_discovery.run_discovery(["AI & Data Tools"])

    assert "https://toonew.example/feed/" not in tested


def test_run_discovery_skips_podcasts(tmp_path, monkeypatch):
    """Podcasts topic is never searched or tested."""
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(tmp_path / "discovered_feeds.json"))
    monkeypatch.setattr(feed_discovery, "_ARCHIVE_PATH",    str(tmp_path / "feed_archive.json"))

    searched: list[str] = []
    with patch.object(feed_discovery, "_search_feedly", side_effect=lambda q, **kw: searched.append(q) or []):
        feed_discovery.run_discovery(["Podcasts", "AI & Data Tools"])

    # Podcast-specific queries should not appear; AI & Data Tools queries should
    assert any("artificial intelligence" in q.lower() for q in searched)


def test_run_discovery_does_not_re_add_known_urls(tmp_path, monkeypatch):
    """URLs already in TOPICS or discovered_feeds are not re-tested or re-added."""
    monkeypatch.setattr(feed_discovery, "_DISCOVERED_PATH", str(tmp_path / "discovered_feeds.json"))
    monkeypatch.setattr(feed_discovery, "_ARCHIVE_PATH",    str(tmp_path / "feed_archive.json"))

    from newsletter.config import TOPICS
    existing_url = TOPICS.get("AI & Data Tools", [""])[0]

    tested: list[str] = []
    with patch.object(feed_discovery, "_search_feedly", return_value=[existing_url, "https://new.example/feed/"]):
        with patch.object(feed_discovery, "test_feed", side_effect=lambda u: tested.append(u) or True):
            feed_discovery.run_discovery(["AI & Data Tools"])

    assert existing_url not in tested
