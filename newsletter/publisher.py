import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

import tweepy

from newsletter import emailer
from newsletter.config import TOPIC_ICONS

logger = logging.getLogger(__name__)


def build_substack_post(result: dict) -> str:
    """Clean semantic HTML for Substack's native renderer — no tables, no inline CSS."""
    daily_brief = result.get("daily_brief", "")
    sections = result.get("sections", {})
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %-d, %Y")
    total = sum(len(v) for v in sections.values())

    parts: list[str] = []

    # Eyebrow
    parts.append(
        f'<p><span style="color:#00C9A7;font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;font-size:12px;">Gradient Descent</span>'
        f'&ensp;·&ensp;<span style="color:#6B7280;font-size:13px;">'
        f'{date_str}&ensp;·&ensp;{total} articles&ensp;·&ensp;~3 min read</span></p>'
    )

    # Daily brief callout
    if daily_brief:
        parts.append("<hr>")
        parts.append(
            "<blockquote>"
            "<p><strong>Today's Brief</strong></p>"
            f"<p>{daily_brief}</p>"
            "</blockquote>"
        )

    # Topic sections
    for topic, articles in sections.items():
        if not articles:
            continue
        icon = TOPIC_ICONS.get(topic, "")
        action = "Listen" if topic == "Podcasts" else "Read"
        parts.append("<hr>")
        parts.append(f"<h2>{icon}&ensp;{topic}</h2>")

        for i, a in enumerate(articles):
            title = a.get("title", "")
            url = a.get("url", "#")
            summary = a.get("summary", "")
            source = a.get("source", "")
            source_tag = (
                f'&ensp;<span style="color:#9CA3AF;font-size:12px;font-weight:400;">— {source}</span>'
                if source else ""
            )
            parts.append(f'<h3><a href="{url}">{title}</a>{source_tag}</h3>')
            parts.append(f'<p>{summary}&ensp;<a href="{url}">→ {action}</a></p>')
            if i < len(articles) - 1:
                parts.append('<hr style="border:none;border-top:1px solid #E5E7EB;margin:12px 0;">')

    # Footer CTA — links to archive rather than duplicating Substack's native subscribe button
    pub_base = os.environ.get(
        "ARCHIVE_BASE_URL", "https://pierderogatis.github.io/ai-newsletter"
    ).rstrip("/")
    parts.append("<hr>")
    parts.append(
        f'<p style="color:#6B7280;font-size:13px;"><em>Gradient Descent is free and automated. '
        f'<a href="{pub_base}">Browse the full archive</a> or '
        f'<a href="https://pierluigiderogatis.substack.com/subscribe">subscribe</a> '
        f"to get it every morning.</em></p>"
    )

    return "\n".join(parts)

_DOCS_DIR = Path(__file__).parent.parent / "docs"
_ISSUES_DIR = _DOCS_DIR / "issues"
_MANIFEST_PATH = _DOCS_DIR / "manifest.json"
_SEEN_URLS_PATH = _DOCS_DIR / "seen_urls.json"
_FEED_SCORES_PATH = _DOCS_DIR / "feed_scores.json"
_SEEN_DAYS = 3       # how many days back to remember URLs
_MAX_RECENT_RUNS = 10  # rolling window for per-feed hit history


# ── Cross-day deduplication ──────────────────────────────────────────────────

def load_seen_urls() -> set[str]:
    """Return URLs published in the last _SEEN_DAYS days."""
    if not _SEEN_URLS_PATH.exists():
        return set()
    try:
        data = json.loads(_SEEN_URLS_PATH.read_text("utf-8"))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=_SEEN_DAYS)).strftime("%Y-%m-%d")
        return {e["url"] for e in data if e.get("date", "") >= cutoff}
    except Exception as e:
        logger.error("Failed to load seen_urls.json — returning empty set: %s", e)
        return set()


def update_seen_urls(result: dict, date_str: str) -> None:
    """Append today's article URLs and prune entries older than _SEEN_DAYS."""
    existing: list[dict] = []
    if _SEEN_URLS_PATH.exists():
        try:
            existing = json.loads(_SEEN_URLS_PATH.read_text("utf-8"))
        except Exception as e:
            logger.error("Failed to load seen_urls.json for update — starting fresh: %s", e)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=_SEEN_DAYS)).strftime("%Y-%m-%d")
    existing = [e for e in existing if e.get("date", "") >= cutoff]

    known = {e["url"] for e in existing}
    sections = result.get("sections", {})
    for arts in sections.values():
        for a in arts:
            url = a.get("url", "")
            if url and url not in known:
                existing.append({"url": url, "date": date_str})
                known.add(url)

    _SEEN_URLS_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Seen-URLs store updated (%d entries)", len(existing))


# ── Feed quality scoring ─────────────────────────────────────────────────────

def load_feed_scores() -> dict:
    """Return the per-feed hit-rate store, or {} if missing or unreadable."""
    if not _FEED_SCORES_PATH.exists():
        return {}
    try:
        return json.loads(_FEED_SCORES_PATH.read_text("utf-8"))
    except Exception as e:
        logger.error("Failed to load feed_scores.json — returning empty: %s", e)
        return {}


def update_feed_scores(articles_by_topic: dict[str, list[dict]], date_str: str) -> None:
    """Record which feeds produced articles today (one update per feed per run)."""
    scores = load_feed_scores()
    winning_feeds: set[str] = set()
    for articles in articles_by_topic.values():
        for a in articles:
            feed_url = a.get("feed_url", "")
            if feed_url:
                winning_feeds.add(feed_url)
    for feed_url in winning_feeds:
        entry = scores.setdefault(feed_url, {"recent_hits": [], "last_run": ""})
        if entry.get("last_run") != date_str:
            entry["recent_hits"] = (entry["recent_hits"] + [1])[-_MAX_RECENT_RUNS:]
            entry["last_run"] = date_str
    _FEED_SCORES_PATH.write_text(json.dumps(scores, indent=2, ensure_ascii=False), "utf-8")
    logger.info("Feed scores updated (%d feeds tracked)", len(scores))


# ── Telegram ─────────────────────────────────────────────────────────────────

def post_to_telegram(result: dict, date_str: str) -> None:
    """Post headline + brief to a Telegram channel via Bot API."""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping Telegram")
        return

    headline    = result.get("headline", "").strip()
    daily_brief = result.get("daily_brief", "").strip()
    dt          = datetime.strptime(date_str, "%Y-%m-%d")
    date_fmt    = dt.strftime("%A, %B %-d")
    pub_base    = os.environ.get("ARCHIVE_BASE_URL", "https://pierderogatis.github.io/ai-newsletter").rstrip("/")
    issue_url   = f"{pub_base}/issues/{date_str}.html"

    def esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lines = [f"<b>Gradient Descent</b> — {esc(date_fmt)}"]
    if headline:
        lines.append(f"\n<i>{esc(headline)}</i>")
    if daily_brief:
        lines.append(f"\n{esc(daily_brief)}")
    lines.append(f'\n<a href="{issue_url}">Read full issue →</a>  |  <a href="https://pierluigiderogatis.substack.com">Subscribe</a>')

    payload = json.dumps({
        "chat_id":    chat_id,
        "text":       "\n".join(lines),
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": False},
    }).encode("utf-8")

    token_safe = f"{token[:8]}..."
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Telegram message sent (HTTP %d)", resp.getcode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        logger.error("Telegram API error %d (token: %s): %s", e.code, token_safe, body)
    except Exception as e:
        # Avoid logging str(e) directly — urllib exceptions may include the
        # full request URL containing the bot token.
        logger.error("Telegram post failed (token: %s): %s", token_safe, type(e).__name__)


def _load_manifest() -> list:
    if _MANIFEST_PATH.exists():
        try:
            return json.loads(_MANIFEST_PATH.read_text("utf-8"))
        except Exception:
            pass
    return []


def save_to_archive(result: dict, date_str: str) -> None:
    """Write a dated issue HTML file, update manifest.json, and regenerate RSS feed."""
    import re as _re
    _ISSUES_DIR.mkdir(parents=True, exist_ok=True)

    html = emailer.build_html(result, date_str)

    # Inject a thin web navigation bar into the archive page without touching the
    # email HTML itself. The email template is designed for email clients; this
    # wrapper makes issue pages navigable when opened in a browser.
    pub_base = os.environ.get(
        "ARCHIVE_BASE_URL", "https://pierderogatis.github.io/ai-newsletter"
    ).rstrip("/")
    _web_nav = (
        '<div style="background:#080E1C;padding:10px 24px;display:flex;'
        'justify-content:space-between;align-items:center;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
        f'<a href="{pub_base}" style="color:#6EE7B7;font-size:13px;'
        'font-weight:600;text-decoration:none;letter-spacing:0.01em;">&#8592; Archive</a>'
        '<a href="https://pierluigiderogatis.substack.com/subscribe" '
        'style="background:#00C9A7;color:#080E1C;font-size:12px;font-weight:700;'
        'padding:6px 14px;border-radius:6px;text-decoration:none;">Subscribe free</a>'
        '</div>'
    )
    html = _re.sub(r'(<body[^>]*>)', r'\1' + _web_nav, html, count=1)

    issue_path = _ISSUES_DIR / f"{date_str}.html"
    issue_path.write_text(html, encoding="utf-8")

    sections = result.get("sections", {})
    topics = [t for t, arts in sections.items() if arts]
    article_count = sum(len(v) for v in sections.values())
    brief = result.get("daily_brief", "")

    manifest = _load_manifest()
    manifest = [m for m in manifest if m.get("date") != date_str]
    manifest.insert(0, {
        "date": date_str,
        "headline": result.get("headline", "")[:120],
        "brief": brief[:250],
        "topics": topics,
        "article_count": article_count,
        "path": f"issues/{date_str}.html",
    })
    _MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_rss(manifest, results_by_date={date_str: result})
    logger.info("Archive saved: docs/issues/%s.html — manifest updated (%d issues)", date_str, len(manifest))


def _write_sitemap(manifest: list, pub_base: str) -> None:
    """Write docs/sitemap.xml listing the archive index and all issue pages."""
    entries = [f"  <url><loc>{pub_base}/</loc></url>"]
    for m in manifest:
        url = f"{pub_base}/{m['path']}"
        entries.append(f"  <url><loc>{url}</loc><lastmod>{m['date']}</lastmod></url>")
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>"
    )
    (_DOCS_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    logger.info("Sitemap updated: docs/sitemap.xml (%d URLs)", len(entries))


def _write_rss(manifest: list, results_by_date: dict | None = None) -> None:
    """Generate docs/feed.xml with full <content:encoded> for Substack import."""
    pub_base = os.environ.get("ARCHIVE_BASE_URL", "https://pierderogatis.github.io/ai-newsletter").rstrip("/")
    items = []
    for m in manifest[:20]:
        dt = datetime.strptime(m["date"], "%Y-%m-%d")
        rfc822 = dt.strftime("%a, %d %b %Y 06:00:00 +0000")
        url = f"{pub_base}/{m['path']}"
        title = f"Gradient Descent — {dt.strftime('%A, %B %-d, %Y')}"

        # Brief as plain-text description
        brief = (m.get("brief") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        desc = f"<description>{brief}</description>" if brief else "<description/>"

        # Full Substack-formatted HTML in content:encoded if we have it cached
        content_block = ""
        if results_by_date and m["date"] in results_by_date:
            html = build_substack_post(results_by_date[m["date"]])
            content_block = f"\n    <content:encoded><![CDATA[{html}]]></content:encoded>"

        # Category tags per topic so Substack and feed readers can auto-tag posts
        categories = "".join(
            f"\n    <category>{t}</category>"
            for t in (m.get("topics") or [])
        )

        items.append(f"""  <item>
    <title>{title}</title>
    <link>{url}</link>
    <guid isPermaLink="true">{url}</guid>
    <pubDate>{rfc822}</pubDate>
    {desc}{categories}{content_block}
  </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:atom="http://www.w3.org/2005/Atom"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>Gradient Descent</title>
  <link>{pub_base}</link>
  <description>Daily AI intelligence briefing — data science, finance, sports, and research.</description>
  <language>en-us</language>
  <atom:link href="{pub_base}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
</channel>
</rss>"""
    (_DOCS_DIR / "feed.xml").write_text(rss, encoding="utf-8")
    logger.info("RSS feed updated: docs/feed.xml (%d items)", len(items))
    _write_sitemap(manifest, pub_base)


def _build_tweet_text(headline: str, brief: str, issue_url: str) -> str:
    """Compose tweet text, trimming the brief to keep the total under 280 chars."""
    sub_url = "https://pierluigiderogatis.substack.com"
    footer = f"\n\n{issue_url}\n\nSubscribe: {sub_url}"
    budget = 280 - len(headline) - len(footer) - 2  # -2 for '\n\n' before brief
    if brief and budget >= 4:
        snippet = brief[:budget].rstrip()
        return f"{headline}\n\n{snippet}{footer}"
    return (headline + footer)[:280]


def post_to_twitter(result: dict, date_str: str) -> None:
    """Post the daily headline to X/Twitter via Tweepy OAuth 1.0a."""
    api_key    = os.environ.get("TWITTER_API_KEY", "")
    api_secret = os.environ.get("TWITTER_API_SECRET", "")
    acc_token  = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    acc_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")
    if not all([api_key, api_secret, acc_token, acc_secret]):
        logger.warning(
            "Twitter credentials incomplete — skipping Twitter post "
            "(set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)"
        )
        return

    headline  = result.get("headline", "").strip()
    brief     = result.get("daily_brief", "").strip()
    pub_base  = os.environ.get(
        "ARCHIVE_BASE_URL", "https://pierderogatis.github.io/ai-newsletter"
    ).rstrip("/")
    issue_url = f"{pub_base}/issues/{date_str}.html"
    text = _build_tweet_text(headline, brief, issue_url)

    logger.info("Tweet text (%d chars): %r", len(text), text[:120])
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=acc_token,
            access_token_secret=acc_secret,
        )
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]
        logger.info("Twitter post published (tweet id: %s)", tweet_id)
    except tweepy.errors.TweepyException as e:
        logger.error("Twitter post failed (HTTP %s): %s", getattr(e, 'response', {}) and getattr(e.response, 'status_code', '?'), e)


def _build_linkedin_post_text(headline: str, brief: str, issue_url: str) -> str:
    """Compose LinkedIn post text, capped at LinkedIn's 3,000-char limit."""
    sub_url = "https://pierluigiderogatis.substack.com"
    parts = [headline]
    if brief:
        parts.append(f"\n{brief}")
    parts.append(f"\n→ Full issue: {issue_url}")
    parts.append(f"Subscribe free: {sub_url}")
    return "\n".join(parts)[:3000]


def post_to_linkedin(result: dict, date_str: str) -> None:
    """Post the daily headline and brief to LinkedIn via the UGC Posts API."""
    token      = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    author_urn = os.environ.get("LINKEDIN_AUTHOR_URN", "")
    if not token or not author_urn:
        logger.warning(
            "LinkedIn credentials missing — skipping LinkedIn post "
            "(set LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN)"
        )
        return

    headline  = result.get("headline", "").strip()
    brief     = result.get("daily_brief", "").strip()
    pub_base  = os.environ.get(
        "ARCHIVE_BASE_URL", "https://pierderogatis.github.io/ai-newsletter"
    ).rstrip("/")
    issue_url = f"{pub_base}/issues/{date_str}.html"
    text = _build_linkedin_post_text(headline, brief, issue_url)

    payload = json.dumps({
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://api.linkedin.com/v2/ugcPosts",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("LinkedIn post published (HTTP %d)", resp.getcode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        logger.error("LinkedIn API error %d: %s", e.code, body)
    except Exception as e:
        logger.error("LinkedIn post failed: %s", e)


def post_to_substack(result: dict, date_str: str) -> None:
    """Publish issue to Substack via unofficial draft API."""
    sid = os.environ.get("SUBSTACK_SID", "")
    pub_url = os.environ.get("SUBSTACK_URL", "").rstrip("/")

    if not sid or not pub_url:
        logger.warning("SUBSTACK_SID or SUBSTACK_URL not set — skipping Substack publish")
        return

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    title = f"Gradient Descent — {dt.strftime('%A, %B %-d, %Y')}"
    daily_brief = result.get("daily_brief", "")
    subtitle = daily_brief[:280] if daily_brief else ""
    html_body = build_substack_post(result)  # clean semantic HTML, not email tables

    draft_payload = json.dumps({
        "draft_title": title,
        "draft_subtitle": subtitle,
        "draft_body": html_body,
        "audience": "everyone",
        "draft_section_id": None,
        "section_chosen": False,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{pub_url}/api/v1/drafts",
            data=draft_payload,
            headers={
                "Content-Type": "application/json",
                "Cookie": f"substack-sid={sid}",
                "User-Agent": "ai-newsletter/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            draft = json.loads(resp.read())

        draft_id = draft.get("id")
        if not draft_id:
            logger.error("Substack draft creation returned no ID — response: %s", draft)
            return

        publish_payload = json.dumps({
            "send_email": True,
            "share_automatically": False,
            "is_published": True,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{pub_url}/api/v1/drafts/{draft_id}/publish",
            data=publish_payload,
            headers={
                "Content-Type": "application/json",
                "Cookie": f"substack-sid={sid}",
                "User-Agent": "ai-newsletter/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            logger.info("Published to Substack (HTTP %d): %s", resp.getcode(), title)

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        logger.error("Substack API error %d: %s", e.code, body)
    except Exception as e:
        logger.error("Substack publish failed: %s", e)
