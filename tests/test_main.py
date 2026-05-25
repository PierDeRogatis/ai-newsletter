"""Tests for newsletter/main.py — Step 2b discovery trigger."""
from unittest.mock import patch

import newsletter.main as main_mod

_MINIMAL_RESULT = {
    "headline": "h",
    "daily_brief": "b",
    "sections": {"AI & Data Tools": [{"title": "T", "url": "u", "summary": "s", "source": "src"}]},
}


def _patch_pipeline(monkeypatch):
    monkeypatch.setattr("newsletter.main.publisher.load_seen_urls", lambda: set())
    monkeypatch.setattr("newsletter.main.publisher.load_feed_scores", lambda: {})
    monkeypatch.setattr("newsletter.main.publisher.save_to_archive", lambda *a, **kw: None)
    monkeypatch.setattr("newsletter.main.publisher.update_seen_urls", lambda *a, **kw: None)
    monkeypatch.setattr("newsletter.main.publisher.update_feed_scores", lambda *a, **kw: None)
    monkeypatch.setattr("newsletter.main.publisher.post_to_telegram", lambda *a, **kw: None)
    monkeypatch.setattr("newsletter.main.publisher.post_to_twitter", lambda *a, **kw: None)
    monkeypatch.setattr("newsletter.main.publisher.post_to_linkedin", lambda *a, **kw: None)
    monkeypatch.setattr("newsletter.main.emailer.send", lambda *a, **kw: None)
    monkeypatch.setattr("newsletter.main.summarizer.summarize", lambda *a, **kw: _MINIMAL_RESULT)
    monkeypatch.setattr("newsletter.main.feed_discovery.load_discovered", lambda: {})


_FIVE_ARTICLES = {"AI & Data Tools": [
    {"title": f"T{i}", "url": f"u{i}", "snippet": "", "source": "s", "published": None, "score": 0, "feed_url": ""}
    for i in range(5)
]}
_NO_ARTICLES = {"AI & Data Tools": []}


def test_main_does_not_trigger_discovery_above_threshold(monkeypatch):
    """total >= MIN_ARTICLES_TRIGGER → run_discovery NOT called."""
    _patch_pipeline(monkeypatch)
    monkeypatch.setattr("newsletter.main.fetcher.fetch_all", lambda **kw: (_FIVE_ARTICLES, set()))

    called = []
    monkeypatch.setattr("newsletter.main.feed_discovery.run_discovery",
                        lambda *a, **kw: called.append(1) or {})

    main_mod.main()
    assert called == []


def test_main_triggers_discovery_below_threshold(monkeypatch):
    """total < MIN_ARTICLES_TRIGGER → run_discovery called once."""
    _patch_pipeline(monkeypatch)
    monkeypatch.setattr("newsletter.main.fetcher.fetch_all", lambda **kw: (_NO_ARTICLES, set()))

    called = []
    monkeypatch.setattr("newsletter.main.feed_discovery.run_discovery",
                        lambda *a, **kw: called.append(1) or {})

    main_mod.main()
    assert len(called) == 1


def test_main_refetches_after_discovery_finds_new_feeds(monkeypatch):
    """Discovery returns new feeds → fetch_all called twice."""
    fat = {"AI & Data Tools": [
        {"title": "T", "url": "u", "snippet": "", "source": "s", "published": None, "score": 0, "feed_url": ""}
    ]}
    call_count = []

    def fake_fetch(**kw):
        call_count.append(1)
        return (_NO_ARTICLES, set()) if len(call_count) == 1 else (fat, set())

    _patch_pipeline(monkeypatch)
    monkeypatch.setattr("newsletter.main.fetcher.fetch_all", fake_fetch)
    monkeypatch.setattr("newsletter.main.feed_discovery.run_discovery",
                        lambda *a, **kw: {"AI & Data Tools": ["https://new.example/feed/"]})

    main_mod.main()
    assert len(call_count) == 2
