"""Unit tests for newsletter/emailer.py — no SMTP calls."""
import pytest
from newsletter.emailer import build_html


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
