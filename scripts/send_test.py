"""Send a real test issue to specific addresses — bypasses the Brevo subscriber list.

Usage:
    BREVO_KEY=... SENDER_EMAIL=... GROQ_API=... python scripts/send_test.py a@example.com b@example.com

Or trigger via the test-send GitHub Actions workflow.
"""
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Defaults so config imports don't fail; overridden by real env vars when set.
os.environ.setdefault("RECIPIENT_EMAIL", "test@example.com")


def main(recipients: list[str]) -> None:
    from newsletter import emailer, fetcher, summarizer
    from newsletter.config import SENDER_EMAIL
    from newsletter.publisher import load_seen_urls

    api_key = os.environ.get("BREVO_KEY", "")
    if not api_key:
        raise EnvironmentError("BREVO_KEY is not set")
    if not SENDER_EMAIL:
        raise EnvironmentError("SENDER_EMAIL is not set")

    logging.info("Fetching articles...")
    cross_day_seen = load_seen_urls()
    articles = fetcher.fetch_all(cross_day_seen)

    logging.info("Summarising via Groq...")
    result = summarizer.summarize(articles)

    logging.info("Building HTML...")
    html = emailer.build_html(result)

    now = datetime.now(timezone.utc)
    headline = result.get("headline", "").strip()
    subject = f"[TEST] Gradient Descent — {now.strftime('%a %b %-d')}"
    if headline:
        subject = f"{subject} · {headline}"

    for recipient in recipients:
        logging.info("Sending to %s...", recipient)
        emailer._brevo_send(api_key, SENDER_EMAIL, recipient, subject, html)

    logging.info("Done — sent to %d recipient(s): %s", len(recipients), ", ".join(recipients))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_test.py email1@example.com [email2@example.com ...]")
        sys.exit(1)
    main(sys.argv[1:])
