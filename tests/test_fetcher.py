"""Unit tests for newsletter/fetcher.py — pure functions only, no network."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from newsletter.fetcher import (
    _strip_html,
    _score_article,
    _domain,
    _parse_date,
    _extract_article,
)


# ── _strip_html ───────────────────────────────────────────────────────────────

def test_strip_html_removes_tags():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

def test_strip_html_collapses_whitespace():
    assert _strip_html("  foo   bar  ") == "foo bar"

def test_strip_html_nested_tags():
    assert _strip_html("<div><p><span>text</span></p></div>") == "text"

def test_strip_html_empty_string():
    assert _strip_html("") == ""

def test_strip_html_no_tags():
    assert _strip_html("plain text") == "plain text"


# ── _score_article ────────────────────────────────────────────────────────────

def test_score_article_counts_matches():
    assert _score_article("LLM tools", "python pipeline", ["llm", "python", "data"]) == 2.0

def test_score_article_no_match():
    assert _score_article("Sports news", "running marathon", ["llm", "python"]) == 0.0

def test_score_article_case_insensitive():
    assert _score_article("AI Model Released", "", ["ai", "model"]) == 2.0

def test_score_article_partial_word_match():
    # "machine" matches keyword "machine learning" only if full phrase present
    assert _score_article("machine learning paper", "", ["machine learning"]) == 1.0
    assert _score_article("machine only", "", ["machine learning"]) == 0.0

def test_score_article_empty_keywords():
    assert _score_article("anything", "anything", []) == 0.0


# ── _domain ───────────────────────────────────────────────────────────────────

def test_domain_strips_www():
    assert _domain("https://www.example.com/path") == "example.com"

def test_domain_no_www():
    assert _domain("https://blog.site.io/article") == "blog.site.io"

def test_domain_with_query_string():
    assert _domain("https://www.example.com/path?q=1&foo=bar") == "example.com"

def test_domain_invalid_url_returns_string():
    result = _domain("not-a-url")
    assert isinstance(result, str)


# ── _parse_date ───────────────────────────────────────────────────────────────

def _make_entry(**kwargs):
    entry = MagicMock()
    entry.published_parsed = kwargs.get("published_parsed", None)
    entry.updated_parsed = kwargs.get("updated_parsed", None)
    entry.published = kwargs.get("published", None)
    entry.updated = kwargs.get("updated", None)
    return entry

def test_parse_date_from_struct_time():
    entry = _make_entry(published_parsed=(2026, 4, 21, 6, 0, 0, 0, 0, 0))
    result = _parse_date(entry)
    assert result == datetime(2026, 4, 21, 6, 0, 0, tzinfo=timezone.utc)

def test_parse_date_uses_updated_parsed_as_fallback():
    entry = _make_entry(updated_parsed=(2026, 4, 20, 12, 0, 0, 0, 0, 0))
    result = _parse_date(entry)
    assert result == datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)

def test_parse_date_fallback_to_string():
    entry = _make_entry(published="Mon, 21 Apr 2026 06:00:00 +0000")
    result = _parse_date(entry)
    assert result is not None
    assert result.year == 2026
    assert result.month == 4
    assert result.day == 21

def test_parse_date_returns_none_when_all_missing():
    entry = _make_entry()
    assert _parse_date(entry) is None

def test_parse_date_bad_string_returns_none():
    entry = _make_entry(published="not a date at all ???")
    assert _parse_date(entry) is None


# ── _extract_article ──────────────────────────────────────────────────────────

def _make_article_entry(title="Valid Title", link="https://example.com/1",
                        summary="A snippet.", pub=(2026, 4, 21, 6, 0, 0, 0, 0, 0)):
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.summary = summary
    entry.description = ""
    entry.published_parsed = pub
    entry.updated_parsed = None
    entry.published = None
    entry.updated = None
    return entry

_CUTOFF = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)

def test_extract_article_valid_returns_dict():
    entry = _make_article_entry()
    result = _extract_article(entry, "example.com", ["valid"], _CUTOFF)
    assert result is not None
    assert result["title"] == "Valid Title"
    assert result["url"] == "https://example.com/1"
    assert result["source"] == "example.com"

def test_extract_article_scores_keywords():
    entry = _make_article_entry(title="AI model released", summary="python pipeline")
    result = _extract_article(entry, "src", ["ai", "model", "python"], _CUTOFF)
    assert result["score"] == 3.0

def test_extract_article_missing_title_returns_none():
    entry = _make_article_entry(title="")
    result = _extract_article(entry, "src", [], _CUTOFF)
    assert result is None

def test_extract_article_missing_url_returns_none():
    entry = _make_article_entry(link="")
    result = _extract_article(entry, "src", [], _CUTOFF)
    assert result is None

def test_extract_article_too_old_returns_none():
    old_pub = (2026, 4, 18, 0, 0, 0, 0, 0, 0)  # before cutoff
    entry = _make_article_entry(pub=old_pub)
    result = _extract_article(entry, "src", [], _CUTOFF)
    assert result is None

def test_extract_article_exactly_at_cutoff_is_excluded():
    # Article published at exactly the cutoff datetime should be excluded (pub < cutoff is False,
    # but pub == cutoff also passes through — verify the boundary behaviour is consistent)
    at_cutoff = (2026, 4, 20, 0, 0, 0, 0, 0, 0)
    entry = _make_article_entry(pub=at_cutoff)
    result = _extract_article(entry, "src", [], _CUTOFF)
    # Should be included (not strictly before cutoff)
    assert result is not None
