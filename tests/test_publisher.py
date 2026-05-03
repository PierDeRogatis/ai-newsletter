"""Unit tests for newsletter/publisher.py — filesystem operations use tmp_path."""
import json
import logging
import os
import pytest
import tweepy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from newsletter.publisher import (
    load_seen_urls,
    update_seen_urls,
    build_substack_post,
    _write_sitemap,
    _build_tweet_text,
    post_to_twitter,
    _build_linkedin_post_text,
    post_to_linkedin,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_seen(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries), "utf-8")

def _read_seen(path: Path) -> list[dict]:
    return json.loads(path.read_text("utf-8"))

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


# ── load_seen_urls ────────────────────────────────────────────────────────────

def test_load_seen_urls_missing_file(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        result = load_seen_urls()
    assert result == set()

def test_load_seen_urls_empty_file(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    _write_seen(seen_path, [])
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        result = load_seen_urls()
    assert result == set()

def test_load_seen_urls_corrupted_file_returns_empty_set(docs_dir, caplog):
    seen_path = docs_dir / "seen_urls.json"
    seen_path.write_text("{bad json}", "utf-8")
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path), \
         caplog.at_level(logging.ERROR, logger="newsletter.publisher"):
        result = load_seen_urls()
    assert result == set()
    assert any("Failed to load seen_urls.json" in r.message for r in caplog.records)

def test_load_seen_urls_returns_recent_entries(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    _write_seen(seen_path, [
        {"url": "https://recent.com", "date": _today()},
        {"url": "https://yesterday.com", "date": _days_ago(1)},
    ])
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        result = load_seen_urls()
    assert "https://recent.com" in result
    assert "https://yesterday.com" in result

def test_load_seen_urls_prunes_old_entries(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    _write_seen(seen_path, [
        {"url": "https://recent.com", "date": _today()},
        {"url": "https://old.com", "date": _days_ago(5)},
        {"url": "https://ancient.com", "date": _days_ago(10)},
    ])
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        result = load_seen_urls()
    assert "https://recent.com" in result
    assert "https://old.com" not in result
    assert "https://ancient.com" not in result

def test_load_seen_urls_boundary_3_days(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    _write_seen(seen_path, [
        {"url": "https://within.com", "date": _days_ago(2)},
        {"url": "https://outside.com", "date": _days_ago(4)},
    ])
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        result = load_seen_urls()
    assert "https://within.com" in result
    assert "https://outside.com" not in result


# ── update_seen_urls ──────────────────────────────────────────────────────────

def _make_result(*urls: str) -> dict:
    return {"sections": {"AI": [{"url": u} for u in urls]}}

def test_update_seen_urls_writes_new_urls(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        update_seen_urls(_make_result("https://a.com", "https://b.com"), _today())
    written = {e["url"] for e in _read_seen(seen_path)}
    assert "https://a.com" in written
    assert "https://b.com" in written

def test_update_seen_urls_no_duplicates(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    _write_seen(seen_path, [{"url": "https://a.com", "date": _today()}])
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        update_seen_urls(_make_result("https://a.com"), _today())
    written = _read_seen(seen_path)
    assert len([e for e in written if e["url"] == "https://a.com"]) == 1

def test_update_seen_urls_appends_to_existing(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    _write_seen(seen_path, [{"url": "https://existing.com", "date": _today()}])
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        update_seen_urls(_make_result("https://new.com"), _today())
    written = {e["url"] for e in _read_seen(seen_path)}
    assert "https://existing.com" in written
    assert "https://new.com" in written

def test_update_seen_urls_prunes_old_on_write(docs_dir):
    seen_path = docs_dir / "seen_urls.json"
    _write_seen(seen_path, [
        {"url": "https://old.com", "date": _days_ago(10)},
        {"url": "https://recent.com", "date": _today()},
    ])
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path):
        update_seen_urls(_make_result("https://new.com"), _today())
    written = {e["url"] for e in _read_seen(seen_path)}
    assert "https://old.com" not in written
    assert "https://recent.com" in written
    assert "https://new.com" in written

def test_update_seen_urls_corrupted_file_continues(docs_dir, caplog):
    seen_path = docs_dir / "seen_urls.json"
    seen_path.write_text("{bad json}", "utf-8")
    with patch("newsletter.publisher._SEEN_URLS_PATH", seen_path), \
         caplog.at_level(logging.ERROR, logger="newsletter.publisher"):
        update_seen_urls(_make_result("https://new.com"), _today())
    written = {e["url"] for e in _read_seen(seen_path)}
    assert "https://new.com" in written
    assert any("Failed to load" in r.message for r in caplog.records)


# ── build_substack_post ───────────────────────────────────────────────────────

def test_build_substack_post_contains_daily_brief(sample_result):
    html = build_substack_post(sample_result)
    assert "Sentence one about structural forces" in html

def test_build_substack_post_has_blockquote_for_brief(sample_result):
    html = build_substack_post(sample_result)
    assert "<blockquote>" in html

def test_build_substack_post_contains_h2_sections(sample_result):
    html = build_substack_post(sample_result)
    assert "<h2>" in html
    assert "AI &amp; Data Tools" in html or "AI & Data Tools" in html
    assert "AI in Finance" in html

def test_build_substack_post_contains_article_links(sample_result):
    html = build_substack_post(sample_result)
    assert "https://example.com/llm-costs" in html
    assert "https://finance.example.com/quant" in html
    assert "LLMs Get Cheaper Again" in html

def test_build_substack_post_has_hr_dividers(sample_result):
    html = build_substack_post(sample_result)
    assert html.count("<hr>") >= 2

def test_build_substack_post_uses_emoji_icons(sample_result):
    html = build_substack_post(sample_result)
    assert "📊" in html  # AI & Data Tools
    assert "📈" in html  # AI in Finance

def test_build_substack_post_empty_sections():
    result = {"headline": "H", "daily_brief": "B.", "sections": {}}
    html = build_substack_post(result)
    assert "<hr>" in html  # at least the footer divider
    assert "<h2>" not in html

def test_build_substack_post_no_brief():
    result = {
        "headline": "H",
        "daily_brief": "",
        "sections": {"AI & Data Tools": [
            {"title": "T", "url": "https://x.com", "summary": "S", "source": "x"}
        ]},
    }
    html = build_substack_post(result)
    assert "<blockquote>" not in html
    assert "<h2>" in html


# ── _write_sitemap ────────────────────────────────────────────────────────────

def _make_manifest(*dates: str) -> list:
    return [{"date": d, "path": f"issues/{d}.html"} for d in dates]

def test_write_sitemap_creates_file(docs_dir):
    with patch("newsletter.publisher._DOCS_DIR", docs_dir):
        _write_sitemap(_make_manifest("2026-04-21"), "https://example.netlify.app")
    assert (docs_dir / "sitemap.xml").exists()

def test_write_sitemap_contains_base_url(docs_dir):
    with patch("newsletter.publisher._DOCS_DIR", docs_dir):
        _write_sitemap(_make_manifest("2026-04-21"), "https://example.netlify.app")
    content = (docs_dir / "sitemap.xml").read_text()
    assert "https://example.netlify.app/" in content

def test_write_sitemap_contains_issue_url(docs_dir):
    with patch("newsletter.publisher._DOCS_DIR", docs_dir):
        _write_sitemap(_make_manifest("2026-04-21"), "https://example.netlify.app")
    content = (docs_dir / "sitemap.xml").read_text()
    assert "issues/2026-04-21.html" in content

def test_write_sitemap_contains_lastmod(docs_dir):
    with patch("newsletter.publisher._DOCS_DIR", docs_dir):
        _write_sitemap(_make_manifest("2026-04-21"), "https://example.netlify.app")
    content = (docs_dir / "sitemap.xml").read_text()
    assert "<lastmod>2026-04-21</lastmod>" in content

def test_write_sitemap_multiple_issues(docs_dir):
    with patch("newsletter.publisher._DOCS_DIR", docs_dir):
        _write_sitemap(
            _make_manifest("2026-04-21", "2026-04-20", "2026-04-19"),
            "https://example.netlify.app",
        )
    content = (docs_dir / "sitemap.xml").read_text()
    assert content.count("<url>") == 4  # index + 3 issues

def test_write_sitemap_empty_manifest_has_index(docs_dir):
    with patch("newsletter.publisher._DOCS_DIR", docs_dir):
        _write_sitemap([], "https://example.netlify.app")
    content = (docs_dir / "sitemap.xml").read_text()
    assert content.count("<url>") == 1  # index page only


# ── _build_tweet_text ─────────────────────────────────────────────────────────

_ISSUE_URL = "https://example.netlify.app/issues/2026-04-21.html"

def test_build_tweet_text_contains_headline():
    text = _build_tweet_text("Big AI news", "Brief details.", _ISSUE_URL)
    assert "Big AI news" in text

def test_build_tweet_text_contains_issue_url():
    text = _build_tweet_text("Headline", "Brief.", _ISSUE_URL)
    assert _ISSUE_URL in text

def test_build_tweet_text_contains_subscribe_url():
    text = _build_tweet_text("Headline", "Brief.", _ISSUE_URL)
    assert "pierluigiderogatis.substack.com" in text

def test_build_tweet_text_under_280_chars_with_long_brief():
    long_brief = "A" * 500
    text = _build_tweet_text("Short headline", long_brief, _ISSUE_URL)
    assert len(text) <= 280

def test_build_tweet_text_empty_brief_still_valid():
    text = _build_tweet_text("Headline", "", _ISSUE_URL)
    assert "Headline" in text
    assert len(text) <= 280

def test_build_tweet_text_brief_trimmed_when_budget_tight():
    # Headline + footer already leaves minimal budget for brief
    long_headline = "H" * 200
    text = _build_tweet_text(long_headline, "Some brief text.", _ISSUE_URL)
    assert len(text) <= 280

def test_build_tweet_text_includes_brief_when_space_available():
    text = _build_tweet_text("Short", "This is the brief.", _ISSUE_URL)
    assert "This is the brief" in text


# ── post_to_twitter ───────────────────────────────────────────────────────────

_TWITTER_ENV = {
    "TWITTER_API_KEY":       "key",
    "TWITTER_API_SECRET":    "secret",
    "TWITTER_ACCESS_TOKEN":  "token",
    "TWITTER_ACCESS_SECRET": "tokensecret",
}

def test_post_to_twitter_skips_when_credentials_missing(caplog):
    with patch.dict("os.environ", {}, clear=False), \
         caplog.at_level(logging.WARNING, logger="newsletter.publisher"):
        # ensure vars are absent
        for k in _TWITTER_ENV:
            os.environ.pop(k, None)
        post_to_twitter({"headline": "H", "daily_brief": "B", "sections": {}}, "2026-04-21")
    assert any("Twitter credentials incomplete" in r.message for r in caplog.records)

def test_post_to_twitter_calls_create_tweet(sample_result):
    mock_response = MagicMock()
    mock_response.data = {"id": "123456789"}
    with patch.dict("os.environ", _TWITTER_ENV), \
         patch("newsletter.publisher.tweepy.Client") as MockClient:
        MockClient.return_value.create_tweet.return_value = mock_response
        post_to_twitter(sample_result, "2026-04-21")
    MockClient.return_value.create_tweet.assert_called_once()
    call_text = MockClient.return_value.create_tweet.call_args.kwargs["text"]
    assert "Inference costs beat benchmark races" in call_text

def test_post_to_twitter_tweet_text_under_280(sample_result):
    mock_response = MagicMock()
    mock_response.data = {"id": "999"}
    captured = {}
    def fake_create_tweet(text):
        captured["text"] = text
        return mock_response
    with patch.dict("os.environ", _TWITTER_ENV), \
         patch("newsletter.publisher.tweepy.Client") as MockClient:
        MockClient.return_value.create_tweet.side_effect = fake_create_tweet
        post_to_twitter(sample_result, "2026-04-21")
    assert len(captured["text"]) <= 280

def test_post_to_twitter_handles_tweepy_exception(sample_result, caplog):
    with patch.dict("os.environ", _TWITTER_ENV), \
         patch("newsletter.publisher.tweepy.Client") as MockClient, \
         caplog.at_level(logging.ERROR, logger="newsletter.publisher"):
        MockClient.return_value.create_tweet.side_effect = tweepy.errors.TweepyException("fail")
        post_to_twitter(sample_result, "2026-04-21")
    assert any("Twitter post failed" in r.message for r in caplog.records)


# ── _build_linkedin_post_text ─────────────────────────────────────────────────

_LI_ISSUE_URL = "https://example.netlify.app/issues/2026-04-21.html"

def test_build_linkedin_post_text_contains_headline():
    text = _build_linkedin_post_text("Big AI news", "Brief.", _LI_ISSUE_URL)
    assert "Big AI news" in text

def test_build_linkedin_post_text_contains_issue_url():
    text = _build_linkedin_post_text("Headline", "Brief.", _LI_ISSUE_URL)
    assert _LI_ISSUE_URL in text

def test_build_linkedin_post_text_contains_subscribe_url():
    text = _build_linkedin_post_text("Headline", "Brief.", _LI_ISSUE_URL)
    assert "pierluigiderogatis.substack.com" in text

def test_build_linkedin_post_text_under_3000_chars():
    long_brief = "B" * 5000
    text = _build_linkedin_post_text("Headline", long_brief, _LI_ISSUE_URL)
    assert len(text) <= 3000

def test_build_linkedin_post_text_includes_brief():
    text = _build_linkedin_post_text("H", "This is the brief.", _LI_ISSUE_URL)
    assert "This is the brief." in text

def test_build_linkedin_post_text_empty_brief_still_valid():
    text = _build_linkedin_post_text("Headline", "", _LI_ISSUE_URL)
    assert "Headline" in text
    assert _LI_ISSUE_URL in text


# ── post_to_linkedin ──────────────────────────────────────────────────────────

_LI_ENV = {
    "LINKEDIN_ACCESS_TOKEN": "test-li-token",
    "LINKEDIN_AUTHOR_URN":   "urn:li:person:abc123",
}

def test_post_to_linkedin_skips_when_credentials_missing(caplog):
    for k in _LI_ENV:
        os.environ.pop(k, None)
    with caplog.at_level(logging.WARNING, logger="newsletter.publisher"):
        post_to_linkedin({"headline": "H", "daily_brief": "B", "sections": {}}, "2026-04-21")
    assert any("LinkedIn credentials missing" in r.message for r in caplog.records)

def test_post_to_linkedin_calls_ugcposts_endpoint(sample_result):
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 201
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch.dict("os.environ", _LI_ENV), \
         patch("newsletter.publisher.urllib.request.urlopen", return_value=mock_resp) as mock_open:
        post_to_linkedin(sample_result, "2026-04-21")
    req = mock_open.call_args.args[0]
    assert "ugcPosts" in req.full_url

def test_post_to_linkedin_payload_contains_author_urn(sample_result):
    import json as _json
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 201
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    captured = {}
    def fake_urlopen(req, timeout=None):
        captured["body"] = _json.loads(req.data.decode())
        return mock_resp
    with patch.dict("os.environ", _LI_ENV), \
         patch("newsletter.publisher.urllib.request.urlopen", side_effect=fake_urlopen):
        post_to_linkedin(sample_result, "2026-04-21")
    assert captured["body"]["author"] == "urn:li:person:abc123"

def test_post_to_linkedin_handles_http_error(sample_result, caplog):
    import urllib.error as _ue
    err = _ue.HTTPError(url="", code=401, msg="Unauthorized", hdrs={}, fp=None)
    err.read = lambda: b"token expired"
    with patch.dict("os.environ", _LI_ENV), \
         patch("newsletter.publisher.urllib.request.urlopen", side_effect=err), \
         caplog.at_level(logging.ERROR, logger="newsletter.publisher"):
        post_to_linkedin(sample_result, "2026-04-21")
    assert any("LinkedIn API error 401" in r.message for r in caplog.records)

def test_post_to_linkedin_handles_generic_exception(sample_result, caplog):
    with patch.dict("os.environ", _LI_ENV), \
         patch("newsletter.publisher.urllib.request.urlopen", side_effect=OSError("network down")), \
         caplog.at_level(logging.ERROR, logger="newsletter.publisher"):
        post_to_linkedin(sample_result, "2026-04-21")
    assert any("LinkedIn post failed" in r.message for r in caplog.records)
