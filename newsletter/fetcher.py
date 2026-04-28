import re
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import feedparser
from dateutil import parser as dateparser

from newsletter.config import (
    TOPICS,
    TOPIC_KEYWORDS,
    TOPIC_ROTATION,
    MAX_ARTICLES_PER_TOPIC,
    SNIPPET_MAX_CHARS,
    DAYS_LOOKBACK,
    PODCAST_DAYS_LOOKBACK,
    MAX_PODCASTS,
)

logger = logging.getLogger(__name__)

Article = dict  # {title, url, snippet, source, published, score, feed_url}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    text = _HTML_TAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return dateparser.parse(val).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def _score_article(title: str, snippet: str, keywords: list[str]) -> float:
    text = (title + " " + snippet).lower()
    return sum(1.0 for kw in keywords if kw in text)


def _feed_multiplier(stats: dict) -> float:
    """Boost multiplier based on rolling hit/miss history (1.0x–1.5x).
    Requires ≥3 data points to activate; below that returns the neutral 1.0x.
    """
    hits = stats.get("recent_hits", [])
    if len(hits) < 3:
        return 1.0
    return 1.0 + 0.5 * (sum(hits) / len(hits))


_FEED_TIMEOUT = 8  # seconds per HTTP request


def _fetch_feed(url: str) -> tuple[str, list]:
    """Fetch one RSS feed. Returns (url, entries) so callers know the source."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-newsletter/1.0"})
        with urllib.request.urlopen(req, timeout=_FEED_TIMEOUT) as resp:
            content = resp.read()
        feed = feedparser.parse(content)
        return url, feed.entries or []
    except Exception as e:
        logger.warning("Skipping feed %s — %s: %s", url, type(e).__name__, e)
        return url, []


def _entries_from_urls(urls: list[str]) -> list:
    if not urls:
        return []
    entries = []
    # Give each future _FEED_TIMEOUT + a 3-second grace margin
    wall_timeout = _FEED_TIMEOUT + 3
    with ThreadPoolExecutor(max_workers=min(len(urls), 10)) as executor:
        futures = {executor.submit(_fetch_feed, url): url for url in urls}
        try:
            for future in as_completed(futures, timeout=wall_timeout):
                try:
                    source_url, result = future.result()
                    for entry in result:
                        entry["_source_url"] = source_url
                    entries.extend(result)
                except Exception as e:
                    logger.warning("Error processing future: %s", e)
        except TimeoutError:
            finished = sum(1 for f in futures if f.done())
            logger.warning(
                "Feed batch timed out after %ds — got %d/%d feeds",
                wall_timeout, finished, len(urls),
            )
    return entries


def _extract_article(
    entry, source_domain: str, keywords: list[str], cutoff: datetime, feed_url: str = ""
) -> Article | None:
    pub = _parse_date(entry)
    if pub and pub < cutoff:
        return None

    title = _strip_html(getattr(entry, "title", "") or "").strip()
    if not title:
        return None

    url = getattr(entry, "link", "") or ""
    if not url:
        return None

    raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    snippet = _strip_html(raw_summary)[:SNIPPET_MAX_CHARS].strip()

    score = _score_article(title, snippet, keywords)

    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "source": source_domain,
        "published": pub,
        "score": score,
        "feed_url": feed_url,
    }


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lstrip("www.")
    except Exception:
        return url


def _fetch_podcast_of_day(urls: list[str], cutoff: datetime, now: datetime) -> list[Article]:
    """Pick one episode per day by rotating through feeds using day-of-year."""
    if not urls:
        return []
    day_of_year = now.timetuple().tm_yday
    # Rotate starting feed so each day a different show is tried first
    rotated = urls[day_of_year % len(urls):] + urls[:day_of_year % len(urls)]
    for url in rotated:
        _, entries = _fetch_feed(url)
        source = _domain(url)
        for entry in entries:
            try:
                article = _extract_article(entry, source, [], cutoff, feed_url=url)
                if article is not None:
                    logger.info("  → podcast of the day from %s", source)
                    return [article]
            except Exception:
                continue
    return []


def fetch_all(
    cross_day_seen: set[str] | None = None,
    feed_scores: dict | None = None,
) -> tuple[dict[str, list[Article]], set[str]]:
    """Return (articles_by_topic, attempted_feed_urls).

    attempted_feed_urls is every non-podcast feed URL that was passed to the
    HTTP layer today — used by publisher.update_feed_scores() to record misses
    (0) alongside hits (1) so the multiplier reflects real hit-rate, not just
    a list of winners.
    """
    now = datetime.now(timezone.utc)
    regular_cutoff = now - timedelta(days=DAYS_LOOKBACK)
    podcast_cutoff = now - timedelta(days=PODCAST_DAYS_LOOKBACK)

    weekday = now.weekday()  # 0=Mon … 6=Sun
    active_topics = TOPIC_ROTATION.get(weekday, list(TOPICS.keys()))
    logger.info("Weekday %d — active topics: %s", weekday, active_topics)

    cross_day_seen = cross_day_seen or set()
    result: dict[str, list[Article]] = {}
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    attempted_feeds: set[str] = set()   # non-podcast feeds attempted this run

    for topic, urls in TOPICS.items():
        if topic not in active_topics:
            continue
        try:
            is_podcast = topic == "Podcasts"
            cutoff = podcast_cutoff if is_podcast else regular_cutoff
            keywords = TOPIC_KEYWORDS.get(topic, [])

            logger.info("Fetching topic '%s' from %d feeds…", topic, len(urls))

            if is_podcast:
                result[topic] = _fetch_podcast_of_day(urls, cutoff, now)
                logger.info("  → kept %d articles for 'Podcasts'", len(result[topic]))
                continue

            attempted_feeds.update(urls)
            raw_entries = _entries_from_urls(urls)

            articles: list[Article] = []
            for entry in raw_entries:
                try:
                    feed_url = entry.get("_source_url", "")
                    source = _domain(feed_url)
                    article = _extract_article(entry, source, keywords, cutoff, feed_url=feed_url)
                    if article is None:
                        continue
                    if article["url"] in seen_urls or article["url"] in cross_day_seen:
                        continue
                    norm_title = article["title"].lower().strip()
                    if norm_title in seen_titles:
                        continue
                    article["score"] *= _feed_multiplier((feed_scores or {}).get(feed_url, {}))
                    seen_urls.add(article["url"])
                    seen_titles.add(norm_title)
                    articles.append(article)
                except Exception as e:
                    logger.warning("Skipping malformed entry in '%s': %s", topic, e)

            articles.sort(key=lambda a: (a["score"], a["published"] or now), reverse=True)
            result[topic] = articles[:MAX_ARTICLES_PER_TOPIC]
            logger.info("  → kept %d/%d articles for '%s'", len(result[topic]), len(articles), topic)
        except Exception as e:
            logger.error("Failed to fetch topic '%s': %s — skipping", topic, e)
            result[topic] = []

    return result, attempted_feeds
