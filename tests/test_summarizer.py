"""Unit tests for newsletter/summarizer.py — Groq client is always mocked."""
import json
import pytest
from unittest.mock import MagicMock, patch
from groq import RateLimitError, APITimeoutError, APIConnectionError

from newsletter.summarizer import summarize


# ── Helpers ───────────────────────────────────────────────────────────────────

def _groq_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 200
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def _topic_resp(articles: list[dict]) -> MagicMock:
    """Mock response for a per-topic summarisation call."""
    return _groq_response(json.dumps({"articles": articles}))


def _brief_resp(headline: str = "Test Headline", daily_brief: str = "Sentence one. Two. Three.") -> MagicMock:
    """Mock response for the headline + daily_brief call."""
    return _groq_response(json.dumps({"headline": headline, "daily_brief": daily_brief}))


_ARTICLE = {"title": "T", "url": "https://x.com/1", "snippet": "s", "source": "x.com"}
_SUMMARISED = {"title": "T", "url": "https://x.com/1", "summary": "Summary sentence one. Two."}
_SUMMARISED_F = {"title": "F", "url": "https://f.com/1", "summary": "Finance summary. Two."}


# ── Early exits ───────────────────────────────────────────────────────────────

def test_summarize_empty_dict():
    assert summarize({}) == {"daily_brief": "", "sections": {}}

def test_summarize_all_empty_topic_lists():
    assert summarize({"AI": [], "Finance": []}) == {"daily_brief": "", "sections": {}}


# ── Happy path — single topic ─────────────────────────────────────────────────

def test_summarize_single_topic_shape():
    """One topic → topic call + brief call → correct keys and values."""
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = [
            _topic_resp([_SUMMARISED]),
            _brief_resp("AI is cheaper now", "Sentence one. Two. Three."),
        ]
        result = summarize({"AI & Data Tools": [_ARTICLE]})

    assert result["headline"] == "AI is cheaper now"
    assert result["daily_brief"].startswith("Sentence one")
    assert "AI & Data Tools" in result["sections"]
    assert result["sections"]["AI & Data Tools"][0]["summary"] == _SUMMARISED["summary"]


def test_summarize_groq_called_once_per_topic_plus_brief():
    """With 2 topics, Groq is called exactly 3 times (2 topics + 1 brief)."""
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = [
            _topic_resp([_SUMMARISED]),
            _topic_resp([_SUMMARISED_F]),
            _brief_resp(),
        ]
        summarize({"AI & Data Tools": [_ARTICLE], "AI in Finance": [_ARTICLE]})

    assert MockGroq.return_value.chat.completions.create.call_count == 3


# ── Happy path — multiple topics ──────────────────────────────────────────────

def test_summarize_all_topics_in_sections():
    """Both topics appear in sections after per-topic calls."""
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = [
            _topic_resp([_SUMMARISED]),
            _topic_resp([_SUMMARISED_F]),
            _brief_resp(),
        ]
        result = summarize({"AI & Data Tools": [_ARTICLE], "AI in Finance": [_ARTICLE]})

    assert "AI & Data Tools" in result["sections"]
    assert "AI in Finance" in result["sections"]
    assert len(result["sections"]["AI & Data Tools"]) == 1
    assert len(result["sections"]["AI in Finance"]) == 1


# ── Markdown fences ───────────────────────────────────────────────────────────

def test_summarize_topic_strips_markdown_fences():
    fenced = f"```json\n{json.dumps({'articles': [_SUMMARISED]})}\n```"
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = [
            _groq_response(fenced),
            _brief_resp("Headline"),
        ]
        result = summarize({"AI & Data Tools": [_ARTICLE]})
    assert result["sections"]["AI & Data Tools"][0]["summary"] == _SUMMARISED["summary"]


def test_summarize_brief_strips_markdown_fences():
    fenced = f"```\n{json.dumps({'headline': 'H', 'daily_brief': 'B.'})}\n```"
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = [
            _topic_resp([_SUMMARISED]),
            _groq_response(fenced),
        ]
        result = summarize({"AI & Data Tools": [_ARTICLE]})
    assert result["headline"] == "H"


# ── Topic fallback on bad JSON ────────────────────────────────────────────────

def test_summarize_topic_bad_json_uses_empty_summaries():
    """If topic call returns unparseable JSON, article is included with empty summary."""
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = [
            _groq_response("not valid json at all"),
            _brief_resp(),
        ]
        result = summarize({"AI & Data Tools": [_ARTICLE]})
    articles = result["sections"]["AI & Data Tools"]
    assert len(articles) == 1
    assert articles[0]["title"] == "T"
    assert articles[0]["summary"] == ""


# ── Brief recovery on truncated JSON ─────────────────────────────────────────

def test_summarize_brief_truncated_recovers_fields():
    """Truncated brief JSON falls back to regex extraction."""
    truncated = '{"headline":"Recovered head","daily_brief":"Recovered brief."'  # no closing brace
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = [
            _topic_resp([_SUMMARISED]),
            _groq_response(truncated),
        ]
        result = summarize({"AI & Data Tools": [_ARTICLE]})
    assert result["headline"] == "Recovered head"
    assert result["daily_brief"] == "Recovered brief."


# ── Empty choices guard ───────────────────────────────────────────────────────

def test_summarize_empty_choices_raises_value_error():
    resp = MagicMock()
    resp.choices = []
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = resp
        with pytest.raises(ValueError, match="empty choices"):
            summarize({"AI & Data Tools": [_ARTICLE]})


# ── API error propagation ─────────────────────────────────────────────────────

def test_summarize_rate_limit_error_propagates():
    mock_http_resp = MagicMock()
    mock_http_resp.status_code = 429
    err = RateLimitError("rate limited", response=mock_http_resp, body={})
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = err
        with pytest.raises(RateLimitError):
            summarize({"AI & Data Tools": [_ARTICLE]})

def test_summarize_connection_error_propagates():
    err = APIConnectionError.__new__(APIConnectionError)
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = err
        with pytest.raises(APIConnectionError):
            summarize({"AI & Data Tools": [_ARTICLE]})

def test_summarize_timeout_error_propagates():
    err = APITimeoutError.__new__(APITimeoutError)
    with patch("newsletter.summarizer.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = err
        with pytest.raises(APITimeoutError):
            summarize({"AI & Data Tools": [_ARTICLE]})
