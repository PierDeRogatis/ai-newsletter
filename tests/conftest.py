"""
Shared fixtures and env-var setup for the test suite.
These env vars must be set before any newsletter module is imported because
config.py reads them at import time.
"""
import json
import os

import pytest

os.environ.setdefault("RECIPIENT_EMAIL", "test-recipient@example.com")
os.environ.setdefault("SENDER_EMAIL", "test-sender@example.com")
os.environ.setdefault("GROQ_API", "test_groq_key_for_tests")
os.environ.setdefault("SMTP_PASSWORD", "test_smtp_password")


@pytest.fixture
def sample_result():
    """Canonical result dict matching summarizer.summarize() output shape."""
    return {
        "headline": "Inference costs beat benchmark races",
        "daily_brief": (
            "Sentence one about structural forces in the market. "
            "Sentence two tracing a second-order consequence. "
            "Sentence three posing a concrete forcing function."
        ),
        "sections": {
            "AI & Data Tools": [
                {
                    "title": "LLMs Get Cheaper Again",
                    "url": "https://example.com/llm-costs",
                    "summary": "Inference costs dropped 40% this quarter. This changes your build-vs-buy calculus for any production pipeline.",
                    "source": "example.com",
                },
                {
                    "title": "New Python RAG Framework",
                    "url": "https://example.com/rag",
                    "summary": "A new retrieval framework cuts latency in half. Worth benchmarking against your current vector store setup.",
                    "source": "other.com",
                },
            ],
            "AI in Finance": [
                {
                    "title": "Quant Funds Shift to Foundation Models",
                    "url": "https://finance.example.com/quant",
                    "summary": "Three major quant funds disclosed LLM-based signal generation. The alpha from traditional factors is compressing.",
                    "source": "finance.example.com",
                },
            ],
        },
    }


@pytest.fixture
def sample_rss_xml():
    """Minimal but valid RSS 2.0 feed with three entries."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>A test feed</description>
    <item>
      <title>First Article</title>
      <link>https://example.com/1</link>
      <pubDate>Mon, 21 Apr 2026 06:00:00 +0000</pubDate>
      <description>Snippet for the first article.</description>
    </item>
    <item>
      <title>Second Article</title>
      <link>https://example.com/2</link>
      <pubDate>Mon, 21 Apr 2026 07:00:00 +0000</pubDate>
      <description>Snippet for the second article.</description>
    </item>
    <item>
      <title>Third Article</title>
      <link>https://example.com/3</link>
      <pubDate>Sun, 20 Apr 2026 08:00:00 +0000</pubDate>
      <description>Snippet for the third article.</description>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def docs_dir(tmp_path):
    """Temporary docs/ directory tree mirroring the production layout."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "issues").mkdir()
    return d
