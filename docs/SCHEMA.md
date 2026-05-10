# docs/ JSON data file schemas

## feed_scores.json

Per-feed hit-rate store. A "hit" means the feed placed ≥1 article in the final
selected set for that run.

```json
{
  "https://example.com/feed": {
    "recent_hits": [1, 0, 1, 1, 0],
    "last_run": "2026-05-09"
  }
}
```

| Field | Type | Description |
|---|---|---|
| key | string | Feed URL (exact match against `TOPICS` and `discovered_feeds.json`) |
| `recent_hits` | int[] | Rolling window of 0/1 values (last `_MAX_RECENT_RUNS` = 10 runs) |
| `last_run` | ISO date string | Date of last recorded run; prevents double-counting within one day |

Written by `publisher.update_feed_scores()`. Read by `fetcher._feed_multiplier()`.

---

## seen_urls.json

Cross-day deduplication store. Prevents the same article URL appearing in
consecutive issues.

```json
[
  {"url": "https://example.com/article-1", "date": "2026-05-09"},
  {"url": "https://example.com/article-2", "date": "2026-05-08"}
]
```

| Field | Type | Description |
|---|---|---|
| `url` | string | Article URL |
| `date` | ISO date string | Date the article appeared in an issue |

Written by `publisher.update_seen_urls()`. Read by `publisher.load_seen_urls()`.
Entries older than 3 days are pruned automatically on each write.

---

## manifest.json

Index of all published issues. Powers the archive homepage (`index.html`) and
is used by `_write_rss()` to regenerate `feed.xml`.

```json
[
  {
    "date": "2026-05-09",
    "headline": "AI security gets real",
    "brief": "First two sentences of the daily brief…",
    "topics": ["AI & Data Tools", "Podcasts"],
    "article_count": 4,
    "path": "issues/2026-05-09.html"
  }
]
```

| Field | Type | Description |
|---|---|---|
| `date` | ISO date string | Publication date |
| `headline` | string | Issue headline (≤60 chars) |
| `brief` | string | Truncated daily brief (first ~200 chars) |
| `topics` | string[] | Topics that had ≥1 article this issue |
| `article_count` | int | Total articles across all topics |
| `path` | string | Relative path to the HTML archive file under `docs/` |

Written by `publisher.save_to_archive()`. Sorted descending by date (newest first).

---

## discovered_feeds.json

Feed URLs found by `feed_discovery.run_discovery()` and validated with
`test_feed()`. Merged at runtime with the static `TOPICS` list without
modifying `config.py`.

```json
{
  "AI & Data Tools": [
    "https://example.com/new-feed/rss"
  ],
  "Research & Academia": [
    "https://another.example.com/feed.xml"
  ]
}
```

| Field | Type | Description |
|---|---|---|
| key | string | Topic name (must match a key in `TOPICS`) |
| value | string[] | Feed URLs that passed `test_feed()` |

Written by `feed_discovery._save_discovered()`. Read by `main.py` and passed
to `fetcher.fetch_all()` as `extra_feeds`.

---

## feed_archive.json

Dead or unconfirmed feeds awaiting a monthly retry. A feed is archived when
`test_feed()` returns False; it is promoted back to `discovered_feeds.json` if
a later retry succeeds.

```json
[
  {
    "url": "https://example.com/stale-feed",
    "topic": "AI & Data Tools",
    "added": "2026-04-01",
    "last_retried": "2026-05-01",
    "reason": "no recent articles"
  }
]
```

| Field | Type | Description |
|---|---|---|
| `url` | string | Feed URL |
| `topic` | string | Topic it was discovered under |
| `added` | ISO date string | Date first archived |
| `last_retried` | ISO date string | Date of most recent retry attempt |
| `reason` | string | Human-readable reason for archiving |

Written by `feed_discovery.run_discovery()`. Feeds are retried after
`_ARCHIVE_RETRY_DAYS` (30) days.
