"""Tests for the capture-email workflow's list-ID logic.

The inline Python in capture-email.yml reads BREVO_LIST_ID from the
environment and puts it in the Brevo contact payload. These tests verify
that logic without making any network calls.
"""
import json
import os


def _build_contact_payload(email: str) -> dict:
    """Mirrors the payload logic from capture-email.yml."""
    _raw = os.environ.get("BREVO_LIST_ID", "").strip()
    list_id = int(_raw) if _raw else 3
    raw = json.dumps(
        {"email": email, "listIds": [list_id], "updateEnabled": True}
    ).encode()
    return json.loads(raw)


def test_default_list_id_is_3(monkeypatch):
    monkeypatch.delenv("BREVO_LIST_ID", raising=False)
    body = _build_contact_payload("test@example.com")
    assert body["listIds"] == [3]


def test_empty_string_list_id_defaults_to_3(monkeypatch):
    """GitHub injects undefined secrets as '' — must not crash."""
    monkeypatch.setenv("BREVO_LIST_ID", "")
    body = _build_contact_payload("test@example.com")
    assert body["listIds"] == [3]


def test_list_id_read_from_env(monkeypatch):
    monkeypatch.setenv("BREVO_LIST_ID", "99")
    body = _build_contact_payload("test@example.com")
    assert body["listIds"] == [99]


def test_list_id_matches_daily_workflow_default(monkeypatch):
    """Capture and daily pipeline must target the same list when no secret is set."""
    monkeypatch.delenv("BREVO_LIST_ID", raising=False)
    from newsletter.config import BREVO_LIST_ID
    body = _build_contact_payload("test@example.com")
    assert body["listIds"] == [BREVO_LIST_ID]


def test_email_preserved_in_payload():
    body = _build_contact_payload("subscriber@example.com")
    assert body["email"] == "subscriber@example.com"
    assert body["updateEnabled"] is True
