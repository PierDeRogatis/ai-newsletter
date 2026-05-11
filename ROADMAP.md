# Roadmap

_Last updated: 2026-05-11_

---

## 🚀 Current phase

- **Feed discovery tuning** — `feed_discovery.py` is live; `docs/discovered_feeds.json` and `docs/feed_archive.json` are created on first run and need a few daily cycles before scoring data is meaningful enough to trust auto-promoted feeds
- **LinkedIn distribution** — `post_to_linkedin()` is fully implemented but disabled in `main.py` (step 10); decision pending: re-enable with a dedicated `LINKEDIN_ACCESS_TOKEN` secret rotation, or remove the channel entirely
- **Brevo subscriber flow** — email capture gate and Brevo contact creation (`capture-email.yml`) are live; welcome email and double-opt-in confirmation are not yet implemented
- **Single-recipient delivery** — `RECIPIENT_EMAIL` accepts one address; the pipeline sends one email per run with no BCC list or per-subscriber personalisation
- **Substack direct publish blocked** — `post_to_substack()` is implemented but disabled; Cloudflare blocks GitHub Actions IPs, so Substack ingests via RSS import from `docs/feed.xml` instead

---

## 📅 Next phase

- **Welcome email** — trigger a one-time welcome message via Brevo when a new contact is added (extend `capture-email.yml` or add a dedicated workflow)
- **Multi-recipient delivery** — replace single `RECIPIENT_EMAIL` with a Brevo list send so captured subscribers receive the daily issue directly, not just via archive
- **LinkedIn re-enable or remove** — test `post_to_linkedin()` with a refreshed token; if token rotation is too fragile, delete the function and remove `LINKEDIN_*` secrets from the workflow
- **Feed score review** — after 14+ pipeline runs with `feed_discovery.py` active, audit `docs/feed_archive.json`; graduate high-scoring discovered feeds into `config.py` and drop zero-yield ones
- **Groq model upgrade path** — `_MODEL` and `_FALLBACK_MODEL` are in `config.py`; evaluate `llama-3.3-70b` → `llama-4` once Groq makes it available at the same rate tier

---

## 🔮 Future ideas

- **Reader-facing web app** — replace the static GitHub Pages archive with a lightweight authenticated reader (per-issue pages, topic filtering, search, read-later)
- **Per-reader personalisation** — store topic preferences per Brevo contact, generate a personalised digest subset rather than one fixed rotation
- **Multiple independent pipelines** — extend `config.py` topic rotation so a second newsletter (e.g. a weekly deep-dive) can run from the same codebase with a different cron and topic set
- **Open-rate and click analytics** — integrate Brevo campaign sends for proper open/click tracking instead of relying on Substack's opaque stats

---

## ✅ Done

- **Prev / next navigation in archive** — issue pages link to the previous and next issue; RSS auto-discovery tag added to `<head>` (`feat: add prev/next nav, rss autodiscovery, gate UX improvements`)
- **Archive search** — full-text search across all issues in the GitHub Pages archive (`feat: unsubscribe link, share CTA, archive search`)
- **Feed discovery** — `feed_discovery.py` auto-finds new RSS sources when a topic yields < 3 articles; scores feeds across runs and archives candidates (`feat: add feed discovery`)
- **Email capture gate on archive** — Brevo-backed gate on `docs/issues/*.html`; `patch-gate` workflow re-embeds the PAT across all pages on a schedule
- **Per-topic summarisation** — fixed Groq silently dropping articles by splitting summarisation by topic instead of one megaprompt (`fix: per-topic summarisation`)
- **Feed scoring and dead-feed pruning** — `feed_scores` entries purged on startup; 4 confirmed-dead feeds removed from `config.py`; private-IP and non-HTTP URLs blocked before fetch
- **Security hardening** — private-IP blocking, HTML-escaping of RSS-derived fields in emailer and publisher, `pip-audit` step in daily workflow
- **Twitter / X distribution** — `post_to_twitter()` live via Tweepy OAuth 1.0a; posts daily headline + archive link
- **Telegram distribution** — `post_to_telegram()` live; sends headline, brief, and archive link to channel
- **Substack RSS import** — `docs/feed.xml` with `content:encoded` Substack HTML; Substack ingests daily without Cloudflare interference
- **GitHub Pages archive** — `docs/issues/YYYY-MM-DD.html` per issue, `manifest.json` index, rolling `seen_urls.json` deduplication
- **Core pipeline** — RSS → Groq (`llama-3.3-70b-versatile`) → Gmail SMTP → archive → Telegram → Twitter, running daily at 03:55 UTC via GitHub Actions
