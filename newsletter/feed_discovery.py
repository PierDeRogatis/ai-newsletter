"""
Feed discovery — finds, tests, and persists new RSS sources.

Triggered from main.py when fetch_all() returns fewer than MIN_ARTICLES_TRIGGER
articles total. Queries Feedly's free search API for candidates, tests each with
feedparser, and persists working feeds to docs/discovered_feeds.json (committed
automatically by the daily workflow). Dead feeds are archived to
docs/feed_archive.json and retried once every ARCHIVE_RETRY_DAYS days.
"""
import json
import logging
import urllib.parse
import urllib.request
import urllib.error
import os
from datetime import datetime, timezone, timedelta

import feedparser

from newsletter.config import TOPICS, TOPIC_ROTATION
from newsletter.fetcher import _is_safe_url

logger = logging.getLogger(__name__)

MIN_ARTICLES_TRIGGER = 3
_ARCHIVE_RETRY_DAYS = 30
_MAX_CANDIDATES_PER_TOPIC = 10
_FEED_TIMEOUT = 8

_FEEDLY_SEARCH = "https://cloud.feedly.com/v3/search/feeds"

# Search queries sent to Feedly per topic. Multiple queries widen the candidate pool.
_TOPIC_QUERIES: dict[str, list[str]] = {
    "AI & Data Tools": [
        "artificial intelligence tools developer",
        "machine learning engineering",
        "LLM open source news",
    ],
    "AI in Finance": [
        "AI quantitative finance algorithmic",
        "fintech machine learning",
        "quant trading AI",
    ],
    "AI in Sports": [
        "sports analytics performance technology",
        "athlete wearable AI",
        "sports science performance",
    ],
    "Research & Academia": [
        "AI research machine learning paper",
        "deep learning arxiv preprint",
        "neural network benchmark",
    ],
}

_docs_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
_DISCOVERED_PATH = os.path.join(_docs_dir, "discovered_feeds.json")
_ARCHIVE_PATH    = os.path.join(_docs_dir, "feed_archive.json")


# ── persistence ──────────────────────────────────────────────────────────────


def load_discovered() -> dict[str, list[str]]:
    """Load feeds found in previous discovery runs (docs/discovered_feeds.json)."""
    try:
        with open(_DISCOVERED_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logger.error("discovered_feeds.json corrupt — starting fresh: %s", e)
        return {}


def _save_discovered(feeds: dict[str, list[str]]) -> None:
    with open(_DISCOVERED_PATH, "w") as f:
        json.dump(feeds, f, indent=2)


def _load_archive() -> list[dict]:
    try:
        with open(_ARCHIVE_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        logger.error("feed_archive.json corrupt — starting fresh: %s", e)
        return []


def _save_archive(archive: list[dict]) -> None:
    with open(_ARCHIVE_PATH, "w") as f:
        json.dump(archive, f, indent=2)


def _known_urls() -> set[str]:
    """All feed URLs already active in config or discovered — skip during search."""
    known: set[str] = set()
    for urls in TOPICS.values():
        known.update(urls)
    for urls in load_discovered().values():
        known.update(urls)
    return known


# ── feed testing ─────────────────────────────────────────────────────────────


def test_feed(url: str) -> bool:
    """Return True if the feed is parseable and has ≥1 entry from the last 7 days."""
    if not _is_safe_url(url):
        logger.warning("Skipping feed with unsafe URL: %s", url)
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-newsletter/1.0"})
        with urllib.request.urlopen(req, timeout=_FEED_TIMEOUT) as resp:
            content = resp.read()
        feed = feedparser.parse(content)
        if not feed.entries:
            return False
        for entry in feed.entries[:10]:
            for attr in ("published_parsed", "updated_parsed"):
                val = getattr(entry, attr, None)
                if val:
                    try:
                        pub = datetime(*val[:6], tzinfo=timezone.utc)
                        if pub >= cutoff:
                            return True
                    except Exception:
                        pass
        # Fallback: if no dates are parseable, accept a feed with ≥3 entries
        # (live feeds almost always have content even when dates are malformed)
        return len(feed.entries) >= 3
    except Exception as e:
        logger.debug("Feed test failed for %s: %s", url, e)
        return False


# ── Feedly search ─────────────────────────────────────────────────────────────


def _search_feedly(query: str, count: int = 20) -> list[str]:
    """Return feed URLs from Feedly's public search API (no auth required)."""
    try:
        params = urllib.parse.urlencode({"query": query, "count": count})
        req = urllib.request.Request(
            f"{_FEEDLY_SEARCH}?{params}",
            headers={"User-Agent": "ai-newsletter/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        urls: list[str] = []
        for item in data.get("results", []):
            feed_id = item.get("feedId", "")
            if feed_id.startswith("feed/"):
                urls.append(feed_id[5:])  # strip "feed/" prefix
        return urls
    except Exception as e:
        logger.warning("Feedly search failed for %r: %s", query, e)
        return []


# ── main entry point ──────────────────────────────────────────────────────────


def run_discovery(active_topics: list[str] | None = None) -> dict[str, list[str]]:
    """Search for, test, and persist new RSS feeds.

    active_topics: topics to search for (Podcasts excluded automatically).
    If None, searches all non-Podcast topics.

    Returns {topic: [new_feed_urls]} for feeds added this run.
    Side-effects: writes docs/discovered_feeds.json and docs/feed_archive.json.
    """
    topics = [t for t in (active_topics or list(TOPICS.keys())) if t != "Podcasts"]
    today = datetime.now(timezone.utc).date().isoformat()
    retry_cutoff = datetime.now(timezone.utc) - timedelta(days=_ARCHIVE_RETRY_DAYS)

    known    = _known_urls()
    archive  = _load_archive()
    arc_map: dict[str, dict] = {e["url"]: e for e in archive}

    # Archived feeds eligible for monthly retry
    retry_pool: dict[str, list[str]] = {}
    for entry in archive:
        t = entry.get("topic", "")
        if t not in topics:
            continue
        last = entry.get("last_retried", "2000-01-01")
        try:
            if datetime.fromisoformat(last).replace(tzinfo=timezone.utc) < retry_cutoff:
                retry_pool.setdefault(t, []).append(entry["url"])
        except ValueError:
            pass

    new_feeds: dict[str, list[str]] = {}

    for topic in topics:
        # Start with archived feeds eligible for retry, then Feedly results
        candidates: list[str] = list(retry_pool.get(topic, []))
        for query in _TOPIC_QUERIES.get(topic, [topic]):
            for url in _search_feedly(query):
                if url not in known and url not in candidates:
                    candidates.append(url)
            if len(candidates) >= _MAX_CANDIDATES_PER_TOPIC:
                break

        if not candidates:
            logger.info("Discovery: no candidates found for '%s'", topic)
            continue

        batch = candidates[:_MAX_CANDIDATES_PER_TOPIC]
        logger.info("Discovery: testing %d candidates for '%s'…", len(batch), topic)

        for url in batch:
            if test_feed(url):
                logger.info("  ✓ %s", url)
                new_feeds.setdefault(topic, []).append(url)
                known.add(url)
                # Promote out of archive if it was there
                if url in arc_map:
                    archive = [e for e in archive if e["url"] != url]
                    del arc_map[url]
            else:
                logger.info("  ✗ %s", url)
                if url in arc_map:
                    arc_map[url]["last_retried"] = today
                else:
                    new_entry: dict = {
                        "url": url,
                        "topic": topic,
                        "added": today,
                        "last_retried": today,
                        "reason": "no recent articles",
                    }
                    archive.append(new_entry)
                    arc_map[url] = new_entry

    if new_feeds:
        total = sum(len(v) for v in new_feeds.values())
        logger.info("Discovery complete: %d new feeds across %d topics", total, len(new_feeds))
        discovered = load_discovered()
        for topic, urls in new_feeds.items():
            existing = set(discovered.get(topic, []))
            discovered[topic] = discovered.get(topic, []) + [u for u in urls if u not in existing]
        _save_discovered(discovered)
    else:
        logger.warning("Discovery complete: no new working feeds found")

    _save_archive(archive)
    return new_feeds
