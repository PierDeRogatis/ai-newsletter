# CLAUDE.md — Gradient Descent Newsletter

Source of truth for anyone (human or AI) working on this codebase.

---

## What this is

**Gradient Descent** is an automated daily AI newsletter pipeline. It runs every morning via GitHub Actions, fetches curated articles from RSS feeds, summarises them using Groq's LLM API, and distributes the result through multiple channels: Gmail, a GitHub Pages static archive, a Telegram channel, and Substack (via RSS import).

---

## Repository layout

```
ai-newsletter/
├── newsletter/           # Core pipeline (the only thing that runs in production)
│   ├── config.py         # All constants: emails, feed URLs, keywords, rotation schedule
│   ├── fetcher.py        # RSS ingestion, scoring, deduplication
│   ├── summarizer.py     # Groq API call, JSON parsing, recovery logic
│   ├── emailer.py        # HTML email builder + Gmail SMTP sender
│   ├── publisher.py      # Archive writer, RSS feed, Telegram, Substack draft
│   └── main.py           # Orchestrator — runs steps 1-7 in sequence
├── docs/                 # GitHub Pages static site (committed by GitHub Actions)
│   ├── issues/           # One HTML file per date (e.g. 2026-04-21.html)
│   ├── feed.xml          # RSS feed consumed by Substack for import
│   ├── manifest.json     # Index of all issues (date, brief snippet, article count)
│   ├── seen_urls.json    # Cross-day dedup store (rolling 3-day window)
│   ├── .nojekyll         # Prevents GitHub Pages from running Jekyll
│   └── index.html        # Archive homepage
├── scripts/
│   └── setup_substack.py # One-time Substack configuration helper (not in pipeline)
├── .github/workflows/
│   └── daily-newsletter.yml  # Cron job: 3:55 AM UTC daily + workflow_dispatch
├── .env.example          # Template for local env vars (never commit .env)
└── requirements.txt      # Runtime dependencies only
```

---

## Pipeline execution order

```
main()
  1. publisher.load_seen_urls()          → set of URLs from last 3 days
  2. fetcher.fetch_all(cross_day_seen)   → dict[topic → list[Article]]
  3. summarizer.summarize(articles)      → {headline, daily_brief, sections}
  4. emailer.send(result)                → Gmail SMTP
  5. publisher.save_to_archive(result)   → docs/issues/YYYY-MM-DD.html + manifest + feed.xml
  6. publisher.update_seen_urls(result)  → docs/seen_urls.json
  7. publisher.post_to_telegram(result)  → Telegram Bot API
  8. [DISABLED] publisher.post_to_substack() — blocked by Cloudflare on GH Actions IPs
     Substack ingests via RSS import from feed.xml instead.
```

If `main()` raises uncaught, `_send_failure_alert()` sends a plain-text failure email before `sys.exit(1)`.

---

## Environment variables

All secrets live in GitHub Actions secrets and are injected via the workflow. For local runs, copy `.env.example` to `.env` and fill in every variable.

| Variable | Required | Used in | Description |
|---|---|---|---|
| `GROQ_API` | Yes | `summarizer.py` | Groq API key (`gsk_...`) |
| `SMTP_PASSWORD` | Yes | `emailer.py`, `main.py` | Gmail App Password (not your account password) |
| `SENDER_EMAIL` | Yes | `config.py`, `emailer.py` | Gmail address used to send |
| `TELEGRAM_BOT_TOKEN` | Soft | `publisher.py` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Soft | `publisher.py` | Channel or chat ID (e.g. `-100...`) |
| `SUBSTACK_SID` | Soft | `publisher.py` | Substack session cookie (direct publish, currently disabled) |
| `SUBSTACK_URL` | Soft | `config.py`, `publisher.py` | Full Substack pub URL e.g. `https://yourpub.substack.com` |
| `ARCHIVE_BASE_URL` | No | `publisher.py` | Archive base URL, defaults to `https://pierderogatis.github.io/ai-newsletter` |

"Soft" means the step is skipped gracefully if the var is missing, rather than failing the whole run.

**`RECIPIENT_EMAIL` is currently hardcoded in `config.py:3`.** This is a known issue — it must be moved to an env var before the pipeline can be reused or multi-recipient.

---

## Module responsibilities and rules

### `config.py`
- Single source of truth for all constants: emails, feed lists, keywords, rotation schedule.
- No logic — only data.
- To add a new topic: add it to `TOPICS`, `TOPIC_KEYWORDS`, and every relevant day in `TOPIC_ROTATION`.
- To add a feed: append its URL to the correct topic list. URLs must be valid RSS/Atom endpoints.

### `fetcher.py`
- Fetches all active-topic feeds concurrently via `ThreadPoolExecutor`.
- Each feed fetch has an 8-second timeout (`_FEED_TIMEOUT`). The batch wall-clock timeout is `_FEED_TIMEOUT + 3`.
- Articles are scored by keyword overlap (`_score_article`), deduped by URL and normalised title, then sorted descending — top `MAX_ARTICLES_PER_TOPIC` survive.
- Deduplication is two-layer: within-run (`seen_urls` set) and cross-day (`cross_day_seen` from `seen_urls.json`).
- Podcasts use a separate path (`_fetch_podcast_of_day`) — one episode per day, rotated by day-of-year.
- Topic rotation is by weekday; see `TOPIC_ROTATION` in `config.py`.
- **Do not add blocking calls here.** Fetching must stay concurrent and time-bounded.

### `summarizer.py`
- Makes one Groq API call with all fetched articles as context.
- Model: `llama-3.3-70b-versatile`, max 4096 output tokens, temperature 0.4.
- Expects Groq to return valid JSON matching the schema in `_SYSTEM_PROMPT`. If it doesn't, falls back to regex recovery for truncated responses.
- The system prompt is carefully tuned — do not rewrite it casually. The persona, tone, and output schema are load-bearing.
- Returns `{"headline": str, "daily_brief": str, "sections": {topic: [articles]}}`.

### `emailer.py`
- `build_html(result)` — renders the full email HTML (table-based, inline CSS for email client compat).
- `send(result)` — connects to Gmail SMTP, builds and sends the email.
- HTML also serves as the archive page (reused by `publisher.save_to_archive`).
- Topic colours and icons are defined here. If you add a topic, add its colour and icon here.

### `publisher.py`
- `save_to_archive` — writes `docs/issues/YYYY-MM-DD.html`, updates `manifest.json`, regenerates `feed.xml`.
- `update_seen_urls` — appends today's article URLs to `docs/seen_urls.json`; prunes entries older than 3 days.
- `post_to_telegram` — sends headline + brief + link to Telegram channel via Bot API (HTML parse mode).
- `post_to_substack` — **disabled in `main.py`**. Fully implemented but not called because Cloudflare blocks GitHub Actions IPs. Substack ingests the newsletter via RSS import from `feed.xml` instead.
- `build_substack_post` — generates clean semantic HTML for Substack's renderer (no tables, no inline CSS beyond basic styling). Used both in `post_to_substack` and embedded in `feed.xml` as `content:encoded`.

### `main.py`
- Owns the execution sequence and the failure alert.
- Each step (steps 4–7) should be independently error-handled. A failure in email sending must not prevent archive and Telegram from running.
- `_send_failure_alert` is a best-effort function — if SMTP creds are missing it logs and returns silently.

---

## Coding conventions

- **Python 3.11+.** Use `X | Y` union types, `match` statements, and `tomllib` if appropriate.
- **Type hints everywhere.** All public functions must have fully annotated signatures.
- **Logging over print.** Use `logger = logging.getLogger(__name__)` per module. Log at INFO for normal flow, WARNING for skipped/degraded, ERROR for actionable failures.
- **No comments explaining what the code does.** Only comment when the WHY is non-obvious (workarounds, invariants, constraints). The existing exception is `config.py` feed section headers — those are navigation aids, keep them.
- **No bare `except: pass`.** Always log at minimum. Swallowed exceptions hide bugs.
- **Context managers for all I/O.** File writes, SMTP, and URL opens all use `with`.
- **No new dependencies without justification.** The stdlib is preferred. Adding a dep requires updating `requirements.txt` with a pinned minor version (e.g. `groq~=0.9.0`, not `>=`).

---

## Adding a new distribution channel

1. Implement `post_to_X(result: dict, date_str: str) -> None` in `publisher.py`.
2. Read credentials from `os.environ.get(...)`. If missing, log a warning and return early (do not raise).
3. Call it in `main.py` as a new numbered step, wrapped in `try/except Exception`.
4. Add the secrets to the GitHub Actions workflow env block and to the repo secrets.
5. Update `.env.example` with the new variable name and a description comment.

---

## Adding or changing the Groq model

Change `_MODEL` in `summarizer.py`. Verify the new model supports the token budget (currently 4096 output). If switching to a model with a smaller context window, also reduce the number of articles passed in or truncate snippets earlier.

---

## Local development

```bash
# 1. Create and activate a virtualenv
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill env vars
cp .env.example .env
# edit .env with real values

# 4. Run the pipeline
source .env && python -m newsletter.main
```

GitHub Actions uses Python 3.11. Match this locally to avoid surprises.

---

## GitHub Actions workflow

- Runs at 3:55 AM UTC (5:55 AM CEST / 4:55 AM CET). GitHub Actions has no timezone support — adjust the cron hour manually for DST transitions.
- Also triggerable manually via `workflow_dispatch` in the GitHub UI.
- After the pipeline succeeds, the workflow commits and pushes changes to `docs/` on the feature branch, then mirrors `docs/` to `main` so GitHub Pages serves the updated archive.
- The workflow has `contents: write` permission for this commit/push.
- `timeout-minutes: 10` — if the job runs longer than 10 minutes it is killed. The Groq call is the most likely culprit; ensure it has an explicit timeout.

---

## GitHub Pages

- Serves `docs/` from the `main` branch automatically (no build step needed).
- `docs/.nojekyll` is required — prevents GitHub Pages from running Jekyll processing.
- The archive URL is `https://pierderogatis.github.io/ai-newsletter`.
- The RSS feed is at `/feed.xml` — this is what Substack imports.
- Configured under repo Settings → Pages → Source: `main` branch, `/docs` folder.

---

## What is NOT in this repo

- Subscriber management — handled by Substack.
- Analytics — GitHub Pages has no built-in analytics; Substack handles open rates.
- A/B testing or personalisation — out of scope for now.
- Authentication or user accounts — this is a single-author pipeline.

---

## Known issues and deferred work

See `ROADMAP.md` for the full prioritised list. Critical items:

1. `RECIPIENT_EMAIL` is hardcoded in `config.py:3` — move to env var.
2. `os.environ["GROQ_API"]` in `summarizer.py:57` throws `KeyError` with no message — validate all env vars at startup.
3. The Groq API call in `summarizer.py:61` has no error handling and no timeout — wrap in try/except, add `timeout` param.
4. Steps 4–7 in `main.py` are not individually error-handled — a failure in one silently skips the rest.
