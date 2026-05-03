"""Unit tests for newsletter/summarizer.py — Groq client is always mocked."""
import json
import pytest
from unittest.mock import MagicMock, patch
from groq import RateLimitError, APITimeoutError, APIConnectionError

from newsletter.summarizer import summarize


# ── Helpers ───────────────────────────────────────────────────────────────────

def _groq_response(content: str) -> MagicMock:
    """Build a mock Groq response with a single choice containing `content`."""
    choice = MagicMock()
    choice.message.content = content
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 200
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


_VALID_JSON = json.dumps({
    "headline": "Inference costs beat benchmark races",
    "daily_brief": "Sentence one. Sentence two. Sentence three.",
    "sections": [
        {
            "topic": "AI & Data Tools",
            "articles": [
                {"title": "T1", "url": "https://x.com/1", "summary": "S1"},
                {"title": "T2", "url": "https://x.com/2", "summary": "S2"},
            ],
        },
        {
            "topic": "AI in Finance",
            "articles": [
                {"title": "F1", "url": "https://f.com/1", "summary": "FS1"},
            ],
        },
    ],
})

_ARTICLES = [{"title": "T", "url": "https://x.com", "snippet": "s", "source": "x.com"}]


# ── Early exits ───────────────────────────────────────────────────────────────

def test_summarize_empty_dict():
    assert summarize({}) == {"daily_brief": "", "sections": {}}

def test_summarize_all_empty_topic_lists():
    assert summarize({"AI": [], "Finance": []}) == {"daily_brief": "", "sections": {}}


# ── Happy path ────────────────────────────────────────────────────────────────

def test_summarize_valid_json_returns_correct_shape():
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = _groq_response(_VALID_JSON)
        result = summarize({"AI & Data Tools": _ARTICLES})
    assert result["headline"] == "Inference costs beat benchmark races"
    assert result["daily_brief"].startswith("Sentence one")
    assert "AI & Data Tools" in result["sections"]
    assert len(result["sections"]["AI & Data Tools"]) == 2

def test_summarize_valid_json_maps_all_sections():
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = _groq_response(_VALID_JSON)
        result = summarize({"AI & Data Tools": _ARTICLES, "AI in Finance": _ARTICLES})
    assert "AI in Finance" in result["sections"]
    assert len(result["sections"]["AI in Finance"]) == 1


# ── Markdown-fenced JSON ──────────────────────────────────────────────────────

def test_summarize_strips_markdown_fences():
    fenced = f"```json\n{_VALID_JSON}\n```"
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = _groq_response(fenced)
        result = summarize({"AI & Data Tools": _ARTICLES})
    assert result["headline"] == "Inference costs beat benchmark races"

def test_summarize_strips_plain_fences():
    fenced = f"```\n{_VALID_JSON}\n```"
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = _groq_response(fenced)
        result = summarize({"AI & Data Tools": _ARTICLES})
    assert result["headline"] == "Inference costs beat benchmark races"


# ── Truncated / malformed JSON recovery ──────────────────────────────────────

def test_summarize_truncated_json_recovers_headline_and_brief():
    truncated = (
        '{"headline":"Recovered headline","daily_brief":"Recovered brief.",'
        '"sections":[{"topic":"AI & Data Tools","articles":[{"title":"T","url":"u","summary":"S"}]'
        # intentionally cut off here — no closing brackets/braces
    )
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = _groq_response(truncated)
        result = summarize({"AI & Data Tools": _ARTICLES})
    assert result["headline"] == "Recovered headline"
    assert result["daily_brief"] == "Recovered brief."

def test_summarize_truncated_json_recovers_partial_sections():
    truncated = (
        '{"headline":"H","daily_brief":"B.",'
        '"sections":[{"topic":"AI & Data Tools","articles":[{"title":"T","url":"u","summary":"S"}]},'
        '{"topic":"AI in Finance","articles":[{"title":"F","url":"f","summary":"FS"}'
        # cut off mid-second section
    )
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = _groq_response(truncated)
        result = summarize({"AI & Data Tools": _ARTICLES, "AI in Finance": _ARTICLES})
    # First section is fully formed and should be recovered
    assert "AI & Data Tools" in result["sections"]


# ── Empty choices guard ───────────────────────────────────────────────────────

def test_summarize_empty_choices_raises_value_error():
    resp = MagicMock()
    resp.choices = []
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = resp
        with pytest.raises(ValueError, match="empty choices"):
            summarize({"AI & Data Tools": _ARTICLES})


# ── API error propagation ─────────────────────────────────────────────────────

def test_summarize_rate_limit_error_propagates():
    mock_http_resp = MagicMock()
    mock_http_resp.status_code = 429
    err = RateLimitError("rate limited", response=mock_http_resp, body={})
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = err
        with pytest.raises(RateLimitError):
            summarize({"AI & Data Tools": _ARTICLES})

def test_summarize_connection_error_propagates():
    err = APIConnectionError.__new__(APIConnectionError)
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = err
        with pytest.raises(APIConnectionError):
            summarize({"AI & Data Tools": _ARTICLES})

def test_summarize_timeout_error_propagates():
    err = APITimeoutError.__new__(APITimeoutError)
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = err
        with pytest.raises(APITimeoutError):
            summarize({"AI & Data Tools": _ARTICLES})
