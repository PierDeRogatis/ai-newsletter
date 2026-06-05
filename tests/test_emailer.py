"""Unit tests for newsletter/emailer.py — no network calls."""
import json
import os
import urllib.error
from unittest.mock import MagicMock, call, patch

import pytest
from newsletter.emailer import build_html, send


# ── build_html without iso_date (email path) ─────────────────────────────────

def test_build_html_contains_body(sample_result):
    html = build_html(sample_result)
    assert "<body" in html
    assert "Gradient Descent" in html

def test_build_html_has_title_tag(sample_result):
    html = build_html(sample_result)
    assert "<title>" in html
    assert "Gradient Descent" in html
    assert "Daily AI Intelligence" in html

def test_build_html_has_meta_description(sample_result):
    html = build_html(sample_result)
    assert 'name="description"' in html
    assert "Sentence one" in html  # from daily_brief

def test_build_html_has_og_tags(sample_result):
    html = build_html(sample_result)
    assert 'property="og:title"' in html
    assert 'property="og:description"' in html
    assert 'property="og:image"' in html
    assert 'property="og:url"' in html

def test_build_html_og_url_contains_archive_domain(sample_result):
    html = build_html(sample_result)
    assert "pierderogatis.github.io" in html

def test_build_html_contains_sections(sample_result):
    html = build_html(sample_result)
    assert "LLMs Get Cheaper Again" in html
    assert "Quant Funds Shift to Foundation Models" in html

def test_build_html_empty_brief_no_meta_description_content(sample_result):
    sample_result["daily_brief"] = ""
    html = build_html(sample_result)
    # meta description tag still present, content just empty
    assert 'name="description"' in html


# ── build_html with iso_date (archive path) ───────────────────────────────────

def test_build_html_with_iso_date_in_title(sample_result):
    html = build_html(sample_result, iso_date="2026-04-21")
    assert "April" in html
    assert "2026" in html

def test_build_html_with_iso_date_og_url_contains_date(sample_result):
    html = build_html(sample_result, iso_date="2026-04-21")
    assert "2026-04-21.html" in html

def test_build_html_with_iso_date_consistent_title_and_og(sample_result):
    html = build_html(sample_result, iso_date="2026-04-21")
    # Both <title> and og:title should carry the same date
    assert html.count("April 21 2026") >= 2

def test_build_html_meta_description_truncated_at_160(sample_result):
    sample_result["daily_brief"] = "X" * 300
    html = build_html(sample_result, iso_date="2026-04-21")
    # The meta description content must not exceed 160 chars
    import re
    match = re.search(r'name="description"\s+content="([^"]*)"', html)
    assert match is not None
    assert len(match.group(1)) <= 160


# ── content gate ──────────────────────────────────────────────────────────────

def test_build_html_has_gate_sentinel(sample_result):
    html = build_html(sample_result)
    assert 'id="gd-brief-end"' in html

def test_build_html_has_gate_overlay(sample_result):
    html = build_html(sample_result)
    assert 'id="gd-gate"' in html
    assert "Unlock today" in html

def test_build_html_has_gate_content_wrapper(sample_result):
    html = build_html(sample_result)
    assert 'id="gd-gate-content"' in html

def test_build_html_has_gate_css(sample_result):
    html = build_html(sample_result)
    assert "gd-locked" in html
    assert "gd-visible" in html

def test_build_html_has_gate_js(sample_result):
    html = build_html(sample_result)
    assert "gd_unlocked" in html
    assert "capture-email.yml" in html

def test_build_html_sections_inside_gate_content(sample_result):
    html = build_html(sample_result)
    gate_open  = html.index('id="gd-gate-content"')
    gate_close = html.index("</div>", gate_open + 50)
    # Both article titles must appear between the gate div open and its close
    assert html.index("LLMs Get Cheaper Again") > gate_open
    assert html.index("LLMs Get Cheaper Again") < gate_close

def test_build_html_gate_sentinel_before_sections(sample_result):
    html = build_html(sample_result)
    sentinel_pos = html.index('id="gd-brief-end"')
    content_pos  = html.index('id="gd-gate-content"')
    assert sentinel_pos < content_pos

def test_build_html_gate_present_with_empty_brief(sample_result):
    sample_result["daily_brief"] = ""
    html = build_html(sample_result)
    assert 'id="gd-brief-end"' in html
    assert 'id="gd-gate"' in html

def test_build_html_gate_has_honeypot(sample_result):
    html = build_html(sample_result)
    assert 'id="gd-hp"' in html

def test_build_html_gate_js_has_email_validation(sample_result):
    html = build_html(sample_result)
    assert r"\s@" in html  # regex in gate JS

def test_build_html_gate_js_has_success_state(sample_result):
    html = build_html(sample_result)
    assert "tomorrow morning" in html

def test_build_html_gate_js_has_abort_controller(sample_result):
    html = build_html(sample_result)
    assert "AbortController" in html

def test_build_html_has_rss_autodiscovery(sample_result):
    html = build_html(sample_result)
    assert 'type="application/rss+xml"' in html
    assert "feed.xml" in html

def test_build_html_has_issue_nav(sample_result):
    html = build_html(sample_result)
    assert 'id="gd-issue-nav"' in html


# ── email=True mode (no JS — Brevo Campaign API rejects <script>) ─────────────

def test_build_html_email_mode_has_no_script_tags(sample_result):
    html = build_html(sample_result, email=True)
    assert "<script" not in html

def test_build_html_email_mode_still_has_content(sample_result):
    html = build_html(sample_result, email=True)
    assert "LLMs Get Cheaper Again" in html
    assert "Gradient Descent" in html

def test_build_html_archive_mode_has_gate_js(sample_result):
    html = build_html(sample_result, email=False)
    assert "gd_unlocked" in html
    assert 'id="gd-issue-nav"' in html


# ── send() — Brevo Campaign API ──────────────────────────────────────────────

def _make_urlopen_mock(send_status: int = 204):
    """Return a side_effect list for two POST calls: create campaign then sendNow."""
    create_resp = MagicMock()
    create_resp.read.return_value = json.dumps({"id": 42}).encode()
    create_resp.status = 201
    create_resp.__enter__ = lambda s: s
    create_resp.__exit__ = MagicMock(return_value=False)

    send_resp = MagicMock()
    send_resp.read.return_value = b""
    send_resp.status = send_status
    send_resp.__enter__ = lambda s: s
    send_resp.__exit__ = MagicMock(return_value=False)

    return [create_resp, send_resp]


def test_send_creates_campaign_and_triggers_send(sample_result):
    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock()) as mock_open:
        send(sample_result)
    assert mock_open.call_count == 2  # create campaign + sendNow
    create_req = mock_open.call_args_list[0][0][0]
    send_req = mock_open.call_args_list[1][0][0]
    assert "emailCampaigns" in create_req.full_url
    assert "sendNow" in send_req.full_url


def test_send_campaign_targets_correct_list(sample_result):
    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock()) as mock_open:
        send(sample_result)
    create_req = mock_open.call_args_list[0][0][0]
    body = json.loads(create_req.data.decode())
    assert body["recipients"]["listIds"] == [3]  # BREVO_LIST_ID default


def test_send_raises_if_brevo_key_missing(sample_result):
    original = os.environ.pop("BREVO_KEY", None)
    try:
        with pytest.raises(EnvironmentError, match="BREVO_KEY"):
            send(sample_result)
    finally:
        if original is not None:
            os.environ["BREVO_KEY"] = original


def test_send_subject_contains_headline(sample_result):
    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock()) as mock_open:
        send(sample_result)
    create_req = mock_open.call_args_list[0][0][0]
    body = json.loads(create_req.data.decode())
    assert "Inference costs beat benchmark races" in body["subject"]


def test_send_html_body_contains_article_titles(sample_result):
    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock()) as mock_open:
        send(sample_result)
    create_req = mock_open.call_args_list[0][0][0]
    body = json.loads(create_req.data.decode())
    assert "LLMs Get Cheaper Again" in body["htmlContent"]
    assert "Quant Funds Shift to Foundation Models" in body["htmlContent"]


def test_send_sendnow_url_contains_campaign_id(sample_result):
    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock()) as mock_open:
        send(sample_result)
    send_req = mock_open.call_args_list[1][0][0]
    assert "/42/sendNow" in send_req.full_url


def test_send_409_skips_gracefully(sample_result):
    err = urllib.error.HTTPError(
        url="https://api.brevo.com/v3/emailCampaigns",
        code=409, msg="Conflict",
        hdrs=None, fp=None,
    )
    err.read = lambda: b'{"message":"Campaign already exists"}'
    with patch("urllib.request.urlopen", side_effect=err) as mock_open:
        send(sample_result)  # must not raise
    assert mock_open.call_count == 1  # create attempted, sendNow never called


def test_send_create_http_error_propagates(sample_result):
    err = urllib.error.HTTPError(
        url="https://api.brevo.com/v3/emailCampaigns",
        code=400, msg="Bad Request",
        hdrs=None, fp=None,
    )
    err.read = lambda: b'{"message":"Invalid payload"}'
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(urllib.error.HTTPError):
            send(sample_result)


def test_send_missing_id_in_response_raises(sample_result):
    create_resp = MagicMock()
    create_resp.read.return_value = json.dumps({"status": "draft"}).encode()  # no 'id'
    create_resp.status = 201
    create_resp.__enter__ = lambda s: s
    create_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", side_effect=[create_resp]):
        with pytest.raises(ValueError, match="missing 'id'"):
            send(sample_result)


def test_send_sendnow_http_error_propagates(sample_result):
    err = urllib.error.HTTPError(
        url="https://api.brevo.com/v3/emailCampaigns/42/sendNow",
        code=500, msg="Internal Server Error",
        hdrs=None, fp=None,
    )
    err.read = lambda: b'{"message":"Internal error"}'
    create_resp = _make_urlopen_mock()[0]  # reuse the create-campaign mock
    with patch("urllib.request.urlopen", side_effect=[create_resp, err]):
        with pytest.raises(urllib.error.HTTPError):
            send(sample_result)


# ── compliance / CTA ──────────────────────────────────────────────────────────

def test_build_html_escapes_malicious_title(sample_result):
    sample_result["sections"]["AI & Data Tools"][0]["title"] = "<script>alert(1)</script>"
    html = build_html(sample_result)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_build_html_sanitises_javascript_url(sample_result):
    sample_result["sections"]["AI & Data Tools"][0]["url"] = "javascript:alert(1)"
    html = build_html(sample_result)
    assert 'href="javascript:' not in html


def test_build_html_has_unsubscribe_link(sample_result):
    html = build_html(sample_result)
    assert "unsubscribe" in html.lower()
    assert "{{unsubscribe}}" not in html


def test_build_html_has_share_cta(sample_result):
    html = build_html(sample_result)
    assert "Share this issue" in html
    assert "pierderogatis.github.io" in html
