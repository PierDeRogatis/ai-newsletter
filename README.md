# Gradient Descent

A free, automated daily AI newsletter. Every morning it fetches articles from
70+ curated RSS feeds, summarises them with a single Groq LLM call, and
distributes the result via Gmail, a GitHub Pages static archive, and a Telegram
channel. Substack is updated automatically via RSS import.

Live archive: **[pierderogatis.github.io/ai-newsletter](https://pierderogatis.github.io/ai-newsletter)**

---

## Architecture

```
GitHub Actions (3:55 AM UTC)
        │
        ▼
  fetcher.fetch_all()          ← 70+ RSS feeds, concurrent, 8s timeout each
        │ articles_by_topic
        ▼
  summarizer.summarize()       ← single Groq API call (llama-3.3-70b-versatile)
        │ {headline, daily_brief, sections}
        ├──▶ emailer.send()             → Gmail SMTP
        ├──▶ publisher.save_to_archive()→ docs/issues/YYYY-MM-DD.html
        │                                  docs/manifest.json
        │                                  docs/feed.xml  ←── Substack imports this
        ├──▶ publisher.update_seen_urls()→ docs/seen_urls.json (3-day dedup)
        └──▶ publisher.post_to_telegram()→ Telegram Bot API
        │
        ▼
  git commit + push docs/ → main
        │
        ▼
  GitHub Pages serves from main/docs/
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Match the CI version to avoid surprises |
| [Groq API key](https://console.groq.com) | Free tier is sufficient (~150 req/day limit) |
| Gmail account | Must have 2FA enabled to generate an App Password |
| GitHub account | For Actions (the scheduler and deployment mechanism) |
| Telegram Bot (optional) | Create via [@BotFather](https://t.me/BotFather) |
| Substack publication (optional) | Configured to import from `feed.xml` |

---

## Local setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/PierDeRogatis/ai-newsletter.git
cd ai-newsletter

# 2. Create and activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install runtime dependencies
pip install -r requirements.txt

# 4. Copy and fill in environment variables
cp .env.example .env
# Edit .env — at minimum set GROQ_API, SENDER_EMAIL, SMTP_PASSWORD, RECIPIENT_EMAIL

# 5. Run the pipeline
set -a && source .env && set +a
python -m newsletter.main
```

The pipeline logs to stdout. A successful run looks like:

```
06:00:01 [INFO] newsletter.main: === Morning AI Brief — starting ===
06:00:01 [INFO] newsletter.fetcher: Weekday 0 — active topics: ['AI & Data Tools', 'AI in Finance', 'Podcasts']
06:00:09 [INFO] newsletter.fetcher:   → kept 3/47 articles for 'AI & Data Tools'
06:00:09 [INFO] newsletter.summarizer: Calling Groq (llama-3.3-70b-versatile) with 3 topics…
06:00:14 [INFO] newsletter.summarizer: Groq usage — input: 2341, output: 1089 tokens
06:00:14 [INFO] newsletter.emailer: Email sent via Gmail SMTP to you@example.com
06:00:15 [INFO] newsletter.publisher: Archive saved: docs/issues/2026-04-21.html
06:00:15 [INFO] newsletter.publisher: Telegram message sent (HTTP 200)
06:00:15 [INFO] newsletter.main: === Newsletter delivered successfully (2026-04-21) ===
```

---

## Environment variables

| Variable | Required | Where to get it |
|---|---|---|
| `GROQ_API` | Yes | [console.groq.com](https://console.groq.com) → API Keys |
| `SENDER_EMAIL` | Yes | Your Gmail address |
| `SMTP_PASSWORD` | Yes | Google Account → Security → 2-Step Verification → App passwords |
| `RECIPIENT_EMAIL` | Yes | The address that receives the newsletter |
| `TELEGRAM_BOT_TOKEN` | Optional | [@BotFather](https://t.me/BotFather) → /newbot |
| `TELEGRAM_CHAT_ID` | Optional | Channel or group ID (e.g. `-100123456789`) |
| `SUBSTACK_SID` | Optional | Substack session cookie — only used for direct publish (currently disabled) |
| `SUBSTACK_URL` | Optional | Your Substack publication URL |
| `ARCHIVE_BASE_URL` | Optional | Defaults to `https://pierderogatis.github.io/ai-newsletter`; override for a custom domain |

For local development, copy `.env.example` to `.env` and fill in each value.
For CI, add them as **GitHub Actions repository secrets** (Settings → Secrets and variables → Actions).

---

## Topic rotation

Topics rotate by weekday to keep each issue focused:

| Day | Topics |
|---|---|
| Mon | AI & Data Tools · AI in Finance · Podcasts |
| Tue | AI & Data Tools · AI in Sports · Podcasts |
| Wed | AI & Data Tools · Research & Academia · Podcasts |
| Thu | AI & Data Tools · AI in Sports · Podcasts |
| Fri | AI & Data Tools · AI in Finance · Podcasts |
| Sat–Sun | All topics · Podcasts |

Configure in `newsletter/config.py` → `TOPIC_ROTATION`.

---

## How to add an RSS feed

Open `newsletter/config.py` and append the feed URL to the relevant topic list:

```python
TOPICS: dict[str, list[str]] = {
    "AI & Data Tools": [
        ...
        "https://your-new-feed.com/rss",   # ← add here
    ],
```

The feed will be picked up on the next run. Feeds that fail to respond within
8 seconds are skipped silently and logged at WARNING level.

---

## How to trigger a run manually

1. Go to the repo on GitHub → **Actions** tab
2. Select **Daily AI Newsletter** in the left sidebar
3. Click **Run workflow** → **Run workflow**

This is the same job that runs on the cron schedule — useful for testing or
recovering a missed run.

---

## Deployment (GitHub Pages + GitHub Actions)

After each successful pipeline run, GitHub Actions commits the generated files
to `docs/` and pushes them:

```
docs/
  issues/YYYY-MM-DD.html   ← individual archive pages
  feed.xml                 ← RSS feed (also imported by Substack)
  manifest.json            ← issue index used by the archive homepage
  seen_urls.json           ← 3-day deduplication store
  index.html               ← static archive homepage
  .nojekyll               ← prevents Jekyll processing
  logo.png
```

The workflow pushes `docs/` to `main`. GitHub Pages serves the site directly
from that folder — no build step, no separate deploy. Archive URL:
`https://pierderogatis.github.io/ai-newsletter`

---

## Development

```bash
# Install dev tools (pytest, mypy, ruff, pip-audit)
pip install -r requirements-dev.txt

# Run the test suite
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=newsletter --cov-report=term-missing

# Lint
ruff check newsletter/

# Type check
mypy newsletter/
```

CI runs automatically on every push and pull request via `.github/workflows/ci.yml`.
The newsletter cron job also runs `pip-audit` against `requirements.txt` before
each delivery to catch newly published CVEs.

---

## Project structure

```
ai-newsletter/
├── newsletter/           # Pipeline modules
│   ├── config.py         # Feed URLs, keywords, topic rotation, colours, icons
│   ├── fetcher.py        # RSS ingestion, scoring, deduplication
│   ├── summarizer.py     # Groq API call + JSON parsing/recovery
│   ├── emailer.py        # HTML email builder + Gmail SMTP sender
│   ├── publisher.py      # Archive, RSS feed, Telegram, Substack
│   └── main.py           # Orchestrator — runs and isolates each step
├── tests/                # pytest suite (56 tests)
├── docs/                 # GitHub Pages static site (committed by CI)
├── scripts/
│   └── setup_substack.py # One-time Substack configuration helper
├── .github/workflows/
│   ├── daily-newsletter.yml  # Cron job + archive commit
│   └── ci.yml                # Test runner on push/PR
├── CLAUDE.md             # Architecture and coding conventions for AI assistants
├── ROADMAP.md            # Phased implementation plan
├── requirements.txt      # Runtime deps (pinned with ~=)
└── requirements-dev.txt  # Dev/CI tooling
```

---

## Licence

MIT — do whatever you want with it.
