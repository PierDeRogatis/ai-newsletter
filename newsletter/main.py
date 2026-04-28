import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from email.mime.text import MIMEText

from newsletter import fetcher, summarizer, emailer, publisher
from newsletter.config import RECIPIENT_EMAIL, SENDER_EMAIL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_REQUIRED_ENV_VARS = ["GROQ_API", "SMTP_PASSWORD", "SENDER_EMAIL", "RECIPIENT_EMAIL"]


def _validate_env() -> None:
    missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Set them in .env (local) or GitHub Actions secrets (CI)."
        )


def _send_failure_alert(
    date_str: str,
    tb: str,
    step_errors: list[str] | None = None,
) -> None:
    """Best-effort failure email so a broken run doesn't go unnoticed."""
    password = os.environ.get("SMTP_PASSWORD", "")
    sender   = SENDER_EMAIL
    if not password or not sender:
        logger.warning("Cannot send failure alert — SMTP credentials missing")
        return
    try:
        body_parts = [f"Gradient Descent delivery failed on {date_str}."]
        if step_errors:
            body_parts.append("\nStep errors:")
            body_parts.extend(f"  • {e}" for e in step_errors)
        if tb:
            body_parts.append(f"\n{tb}")
        msg = MIMEText("\n".join(body_parts), "plain", "utf-8")
        msg["Subject"] = f"Gradient Descent — delivery FAILED ({date_str})"
        msg["From"]    = sender
        msg["To"]      = RECIPIENT_EMAIL
        emailer._smtp_send(sender, password, RECIPIENT_EMAIL, msg)
        logger.info("Failure alert sent to %s", RECIPIENT_EMAIL)
    except Exception as e:
        logger.error("Could not send failure alert: %s", e)


def main() -> int:
    _validate_env()
    logger.info("=== Morning AI Brief — starting ===")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Step 1: load cross-day seen URLs and feed quality scores
    cross_day_seen = publisher.load_seen_urls()
    logger.info("Cross-day dedup: %d URLs remembered from last 3 days", len(cross_day_seen))
    feed_scores = publisher.load_feed_scores()
    logger.info("Feed scores loaded (%d feeds tracked)", len(feed_scores))

    # Step 2: fetch articles (skipping already-seen URLs, boosting high-quality feeds)
    articles_by_topic, attempted_feeds = fetcher.fetch_all(
        cross_day_seen=cross_day_seen, feed_scores=feed_scores
    )
    total_fetched = sum(len(v) for v in articles_by_topic.values())
    logger.info("Fetched %d articles total across %d topics", total_fetched, len(articles_by_topic))

    if total_fetched == 0:
        logger.warning("No articles found — skipping.")
        return 0

    # Step 3: single Groq call — headline + summaries + daily brief
    result = summarizer.summarize(articles_by_topic)
    sections = result.get("sections", {})
    total_summarized = sum(len(v) for v in sections.values())
    logger.info(
        "Summarized %d articles | headline: %r",
        total_summarized, result.get("headline", ""),
    )

    if total_summarized == 0:
        logger.error("Summarizer returned no content.")
        return 1

    step_errors: list[str] = []

    # Step 4: send personal copy via Gmail SMTP
    try:
        emailer.send(result)
    except Exception as e:
        logger.error("Step 4 (email) failed: %s", e)
        step_errors.append(f"Step 4 (email): {e}")

    # Step 5: save to GitHub Pages archive + regenerate RSS feed
    try:
        publisher.save_to_archive(result, date_str)
    except Exception as e:
        logger.error("Step 5 (archive) failed: %s", e)
        step_errors.append(f"Step 5 (archive): {e}")

    # Step 6: update cross-day dedup store
    try:
        publisher.update_seen_urls(result, date_str)
    except Exception as e:
        logger.error("Step 6 (seen_urls) failed: %s", e)
        step_errors.append(f"Step 6 (seen_urls): {e}")

    # Step 6b: update per-feed quality scores
    try:
        publisher.update_feed_scores(articles_by_topic, attempted_feeds, date_str)
    except Exception as e:
        logger.error("Step 6b (feed_scores) failed: %s", e)
        step_errors.append(f"Step 6b (feed_scores): {e}")

    # Step 7: post to Telegram channel
    try:
        publisher.post_to_telegram(result, date_str)
    except Exception as e:
        logger.error("Step 7 (telegram) failed: %s", e)
        step_errors.append(f"Step 7 (telegram): {e}")

    # Step 8: Substack direct publish — disabled until official API approved
    # Cloudflare blocks GitHub Actions IPs; RSS import at feed.xml is active instead.
    # publisher.post_to_substack(result, date_str)

    # Step 9: post to X/Twitter
    try:
        publisher.post_to_twitter(result, date_str)
    except Exception as e:
        logger.error("Step 9 (twitter) failed: %s", e)
        step_errors.append(f"Step 9 (twitter): {e}")

    # Step 10: LinkedIn direct post — disabled. LinkedIn's UGC Posts API requires
    # manual OAuth token refresh every 60 days; daily automation is not reliable.
    # Post manually from the personal profile instead.
    # publisher.post_to_linkedin(result, date_str)

    if step_errors:
        _send_failure_alert(date_str, "", step_errors=step_errors)
        return 1

    logger.info("=== Newsletter delivered successfully (%s) ===", date_str)
    return 0


if __name__ == "__main__":
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        logger.critical("Unhandled exception:\n%s", tb)
        _send_failure_alert(date_str, tb)
        sys.exit(1)
