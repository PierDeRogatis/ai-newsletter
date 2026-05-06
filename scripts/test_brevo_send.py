"""One-off test: send today's issue via Brevo to a single address.

Run from the repo root:
    BREVO_KEY=xkeysib-... SENDER_EMAIL=you@gmail.com python3 scripts/test_brevo_send.py

Does NOT touch Brevo list 3 — sends directly to TEST_RECIPIENT only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from newsletter.emailer import _brevo_send, build_html

TEST_RECIPIENT = "pierluigi.derogatis@live.com"

SAMPLE_RESULT = {
    "headline": "Test send — Brevo integration check",
    "daily_brief": (
        "This is a test email to verify the Brevo transactional send works end-to-end. "
        "If you're reading this in your inbox the pipeline is wired up correctly. "
        "No action needed — tomorrow's real issue will arrive automatically."
    ),
    "sections": {
        "AI & Data Tools": [
            {
                "title": "Brevo Send Working ✓",
                "url": "https://pierderogatis.github.io/ai-newsletter",
                "summary": "The newsletter pipeline now sends to all Brevo list 3 contacts. "
                           "This test confirms the HTML renders correctly and lands in your inbox.",
                "source": "gradient-descent",
            },
        ],
    },
}

api_key     = os.environ.get("BREVO_KEY", "")
sender      = os.environ.get("SENDER_EMAIL", "")

if not api_key:
    sys.exit("Set BREVO_KEY env var before running.")
if not sender:
    sys.exit("Set SENDER_EMAIL env var before running.")

html    = build_html(SAMPLE_RESULT)
subject = "Gradient Descent — Brevo integration test"

print(f"Sending to {TEST_RECIPIENT} via Brevo...")
_brevo_send(api_key, sender, [TEST_RECIPIENT], subject, html)
print("Done. Check your inbox.")
