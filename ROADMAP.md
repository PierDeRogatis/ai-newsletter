# ROADMAP.md — Gradient Descent

Living document. Every phase follows the same structure: **Plan → Execute → Test → Commit**.
Update the status checkbox as you go. Never start a new phase while the previous one is `[~]`.

Detailed per-phase docs for GTM phases live in the private repo.

---

## Status legend
- `[ ]` Not started
- `[~]` In progress
- `[x]` Done

---

## Phase structure

Each phase has exactly these four steps:

| Step | What happens |
|---|---|
| **Plan** | Understand what changes, which files are touched, what can go wrong |
| **Execute** | Make the code changes — nothing more, nothing less than the scope |
| **Test** | Verify the pipeline still works: run locally, check logs, confirm no regressions |
| **Commit** | Stage only the changed files, write a clear commit message, push |

---

---

# BLOCK 1 — Critical hardening
*Fixes things that are broken or expose the system. Do these before anything else.*

---

## Phase 1 — Env var validation & RECIPIENT_EMAIL [x]

**Goal:** The pipeline must fail loudly at startup if any required env var is missing, and the recipient email must not be hardcoded.

**Scope:** `config.py`, `main.py`, `.env.example`, `.github/workflows/daily-newsletter.yml`

### Plan
- `config.py:3` has `RECIPIENT_EMAIL = "pierluigi.derogatis@live.com"` hardcoded — move to env var.
- `summarizer.py:57` uses `os.environ["GROQ_API"]` which throws a bare `KeyError` — replace with validated startup check.
- All required vars should be validated once at the top of `main()` before any step runs, so a misconfigured run fails immediately with a clear message rather than mid-pipeline.
- Required vars: `GROQ_API`, `SMTP_PASSWORD`, `SENDER_EMAIL`, `RECIPIENT_EMAIL`.
- Soft vars (skip step if missing): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SUBSTACK_SID`, `SUBSTACK_URL`.

### Execute
1. In `config.py`: replace `RECIPIENT_EMAIL = "pierluigi.derogatis@live.com"` with `RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")`.
2. In `main.py`: add a `_validate_env()` function called at the very top of `main()` that checks all required vars and raises `SystemExit` with a message listing any that are missing.
3. In `summarizer.py`: remove `os.environ["GROQ_API"]` direct access — the key is now validated before `summarize()` is ever called; use `os.environ.get("GROQ_API", "")` instead.
4. In `.env.example`: add `RECIPIENT_EMAIL=you@example.com` with a comment.
5. In the GitHub Actions workflow: add `RECIPIENT_EMAIL: ${{ secrets.RECIPIENT_EMAIL }}` to the `env:` block.
6. Add `RECIPIENT_EMAIL` to repo secrets via GitHub UI (Settings → Secrets → Actions).

### Test
- Locally: unset `GROQ_API` and run `python -m newsletter.main` — should exit immediately with a clear error listing the missing var, not a `KeyError` traceback.
- Locally: unset `RECIPIENT_EMAIL` — same behaviour.
- Locally: set all vars and do a dry run (set `DAYS_LOOKBACK=0` temporarily to skip actual sending) — pipeline should complete without errors.
- Check that `emailer.py` and `main._send_failure_alert()` both use `RECIPIENT_EMAIL` from config (no remaining hardcoded strings).

### Commit
```
fix: move RECIPIENT_EMAIL to env var, add startup env validation
```
Files: `config.py`, `main.py`, `summarizer.py`, `.env.example`, `.github/workflows/daily-newsletter.yml`

---

## Phase 2 — Groq reliability [x]

**Goal:** The Groq API call must never hang the job indefinitely and must surface errors clearly.

**Scope:** `newsletter/summarizer.py`

### Plan
- `summarizer.py:61`: `client.chat.completions.create()` has no timeout and no error handling. If Groq is down or rate-limited, the GitHub Actions job runs for 10 minutes then is killed with no useful log.
- `summarizer.py:71`: `response.choices[0]` assumes the list is non-empty — guard against this.
- Errors here should propagate to `main()` so the failure alert is triggered, not be swallowed.

### Execute
1. Wrap `client.chat.completions.create()` in a `try/except` block. Catch `groq.APIStatusError`, `groq.APIConnectionError`, and `groq.RateLimitError` separately with specific log messages. Re-raise all of them so `main()` catches them and sends the failure alert.
2. Add `timeout=60` as a parameter to the `create()` call (Groq SDK supports this).
3. After `response = client.chat.completions.create(...)`, add: `if not response.choices: raise ValueError("Groq returned empty choices list")`.
4. Import `groq` exceptions at the top of the file: `from groq import APIStatusError, APIConnectionError, RateLimitError`.

### Test
- Unit test (manual): mock the Groq client to raise `RateLimitError` — verify the exception propagates out of `summarize()` with a log at ERROR level.
- Unit test (manual): mock `response.choices` as `[]` — verify `ValueError` is raised.
- Live test: run the pipeline end-to-end with a valid `GROQ_API` key — verify the usage log line still appears (`Groq usage — input: X, output: Y tokens`).

### Commit
```
fix: add timeout and error handling to Groq API call
```
Files: `newsletter/summarizer.py`

---

## Phase 3 — Pipeline step isolation [x]

**Goal:** A failure in one distribution step (email, archive, Telegram) must not prevent the others from running.

**Scope:** `newsletter/main.py`

### Plan
- Currently steps 4–7 run sequentially with no individual error handling. If `emailer.send()` raises, `save_to_archive()` never runs — the issue is lost.
- Each step should be independently wrapped. Failures should be collected and included in the failure alert (or logged as errors), but not stop the pipeline.
- The overall `main()` return code should still be `1` if any step failed.

### Execute
1. Wrap each of steps 4–7 in its own `try/except Exception as e:` block.
2. Collect failures into a `step_errors: list[str]` list (e.g. `"Step 4 (email): <error message>"`).
3. At the end of `main()`, if `step_errors` is non-empty: log each at ERROR level, set return code to `1`.
4. Update `_send_failure_alert()` to accept an optional `errors: list[str]` parameter and include them in the alert body.

### Test
- Locally: temporarily make `emailer.send()` raise a `RuntimeError("test")` — verify archive, seen_urls, and Telegram still run and their log lines appear.
- Verify the failure alert email body lists the step that failed.
- Remove the artificial error and run end-to-end — verify all 4 steps complete and return code is `0`.

### Commit
```
fix: isolate pipeline steps so a single failure doesn't abort the run
```
Files: `newsletter/main.py`

---

---

# BLOCK 2 — Code quality
*No behaviour changes — cleaner, safer, more maintainable code.*

---

## Phase 4 — Quick cleanup [x]

**Goal:** Remove dead code, silent failures, and the unbounded thread pool in one focused pass.

**Scope:** `newsletter/fetcher.py`, `newsletter/publisher.py`

### Plan
- `fetcher.py:39`: `import time` inside `_parse_date()` — unused, delete it.
- `fetcher.py:80`: `max_workers=max(1, len(urls))` can spawn 70+ threads — cap at 10.
- `publisher.py:100` and `publisher.py:110`: bare `except Exception: return set()` / `return []` swallows corruption silently — add `logger.error(...)` before returning the empty fallback.

### Execute
1. `fetcher.py`: delete `import time` from inside `_parse_date()`.
2. `fetcher.py`: change `max_workers=max(1, len(urls))` to `max_workers=min(len(urls), 10)`.
3. `publisher.py:100`: change `except Exception: return set()` to `except Exception as e: logger.error("Failed to load seen_urls.json — returning empty: %s", e); return set()`.
4. `publisher.py:110`: same pattern for the manifest load.

### Test
- Run `python -m newsletter.main` locally — verify fetch still works and log shows feed counts.
- Temporarily corrupt `docs/seen_urls.json` (write `{invalid}`) — verify an ERROR log appears and the pipeline continues rather than crashing.
- Restore `seen_urls.json`.

### Commit
```
refactor: remove unused import, cap thread pool, log silent failures
```
Files: `newsletter/fetcher.py`, `newsletter/publisher.py`

---

## Phase 5 — Consolidate shared config [x]

**Goal:** Topic colours and icons defined in two places become one, and duplicate SMTP code becomes one context manager.

**Scope:** `newsletter/config.py`, `newsletter/emailer.py`, `newsletter/publisher.py`, `newsletter/main.py`

### Plan
- `emailer.py` defines `_TOPIC_COLORS` (hex values) and `_TOPIC_ICONS` (HTML entities).
- `publisher.py` defines `_TOPIC_ICONS` (emoji). These are different formats for the same topics — unify.
- `main._send_failure_alert()` and `emailer.send()` both open SMTP with identical `ehlo/starttls/login` — extract to a shared context manager.
- Decision: keep emoji icons in `config.py` (used by both Telegram and Substack HTML), keep HTML entity icons in `emailer.py` (email-client compat). The real duplication to fix is the SMTP logic and ensuring config is the single source for topic metadata.

### Execute
1. In `config.py`: add `TOPIC_COLORS: dict[str, str]` and `TOPIC_ICONS: dict[str, str]` (emoji) mirroring the existing values. Remove `_TOPIC_ICONS` from `publisher.py` and import `TOPIC_ICONS` from `config` there.
2. In `emailer.py`: keep `_TOPIC_COLORS` and `_TOPIC_ICONS` (HTML entities) as-is — email clients need HTML entities, not emoji. Import `TOPIC_COLORS` from `config` and use it as the source, converting to the email format. (Or just keep the emailer dict independent and note the split is intentional in a comment.)
3. In `emailer.py`: extract a `_smtp_send(sender: str, password: str, recipient: str, msg) -> None` helper that handles the full SMTP sequence. Use it in both `send()` and export it so `main._send_failure_alert()` can import and use it instead of duplicating the logic.
4. In `main.py`: replace the inline SMTP block in `_send_failure_alert()` with a call to `emailer._smtp_send()`.

### Test
- Run `python -m newsletter.main` locally end-to-end — verify email is received and looks correct.
- Verify Telegram message still shows the correct emoji icons for each topic.
- Check that `publisher.py` no longer defines its own `_TOPIC_ICONS` dict.

### Commit
```
refactor: consolidate topic icons in config, deduplicate SMTP logic
```
Files: `newsletter/config.py`, `newsletter/emailer.py`, `newsletter/publisher.py`, `newsletter/main.py`

---

---

# BLOCK 3 — Infrastructure
*Dependencies, security, and CI.*

---

## Phase 6 — Dependency pinning & security CI [x]

**Goal:** Lock dependency versions and catch known CVEs automatically on every run.

**Scope:** `requirements.txt`, `.github/workflows/daily-newsletter.yml`, new `requirements-dev.txt`

### Plan
- `requirements.txt` uses `>=` which allows breaking major/minor upgrades silently.
- `pip-audit` will flag known CVEs; add it as a pre-run CI step.
- Dev tools (pytest, mypy, ruff) should be in a separate file so production installs stay lean.

### Execute
1. Update `requirements.txt`:
   ```
   groq~=0.9.0
   feedparser~=6.0.0
   python-dateutil~=2.9.0
   ```
2. Create `requirements-dev.txt`:
   ```
   pytest~=8.0
   pytest-cov~=5.0
   mypy~=1.9
   ruff~=0.4
   pip-audit~=2.7
   ```
3. In `.github/workflows/daily-newsletter.yml`, add a step between "Install dependencies" and "Run newsletter":
   ```yaml
   - name: Audit dependencies
     run: pip install pip-audit && pip-audit
   ```
4. Add a comment in `requirements.txt` explaining the `~=` pinning strategy.

### Test
- Run `pip install -r requirements.txt` locally — verify it resolves cleanly.
- Run `pip install -r requirements-dev.txt` locally — verify all dev tools install.
- Run `pip-audit` locally — if no CVEs, it exits 0. If CVEs exist, assess and either upgrade the dep or note it in a comment.
- Trigger `workflow_dispatch` on GitHub Actions to verify the audit step passes before the newsletter runs.

### Commit
```
chore: pin dependencies with ~= and add pip-audit to CI
```
Files: `requirements.txt`, `requirements-dev.txt`, `.github/workflows/daily-newsletter.yml`

---

## Phase 7 — Security hardening [x]

**Goal:** Credentials are never logged or passed via insecure channels.

**Scope:** `scripts/setup_substack.py`, `newsletter/publisher.py`

### Plan
- `setup_substack.py` takes `--sid` as a CLI argument — visible in shell history and `ps aux`. Read from env var instead.
- `publisher.py:165` builds the Telegram URL with the full token inline. The URL itself is never logged, but add a safeguard to ensure it never appears in logs accidentally.

### Execute
1. In `setup_substack.py`: remove the `--sid` argparse argument. Read `sid = os.environ.get("SUBSTACK_SID")` at the top of the script. If missing, print a clear error and exit. Update the docstring/comments to explain the env var requirement.
2. In `publisher.py`: find any log line that could include the full Telegram API URL and ensure the token is masked. Change any debug/info log that would print the URL to use `token[:8] + "..."` instead of the full token.

### Test
- Run `setup_substack.py` without `SUBSTACK_SID` set — verify it exits with a clear message, not a crash.
- Run `setup_substack.py` with `SUBSTACK_SID=test_value python scripts/setup_substack.py` — verify it reads the value.
- Run the full pipeline and grep the logs for anything resembling a bot token — nothing beyond the first 8 chars should appear.

### Commit
```
security: read Substack SID from env var, mask token in logs
```
Files: `scripts/setup_substack.py`, `newsletter/publisher.py`

---

---

# BLOCK 4 — Tests & documentation
*Safety net before GTM work adds complexity.*

---

## Phase 8 — Test infrastructure [x]

**Goal:** Establish a pytest suite with fixtures and unit tests for all three core modules.

**Scope:** New `tests/` directory, `requirements-dev.txt` (already created in Phase 6), optionally a new `ci.yml` workflow.

### Plan
- No tests currently exist. Start with `conftest.py` fixtures, then unit test the pure/deterministic functions first (no network, no filesystem).
- Defer integration tests (real Groq call, real SMTP) to a separate file that's excluded from CI.
- Priority order: `fetcher.py` helpers → `summarizer.py` JSON parsing → `publisher.py` seen_urls logic.

### Execute
1. Create `tests/__init__.py` (empty).
2. Create `tests/conftest.py` with shared fixtures:
   - `sample_result`: a hardcoded dict matching the `summarize()` return shape with 2 topics and 2 articles each.
   - `sample_rss_xml`: a minimal RSS XML string with 3 entries.
   - `tmp_docs_dir`: a `tmp_path`-based fixture that creates a fake `docs/` structure.
3. Create `tests/test_fetcher.py`:
   - `test_strip_html` — strips tags, collapses whitespace.
   - `test_score_article` — correct keyword count.
   - `test_domain` — extracts domain from various URL formats.
   - `test_parse_date_struct_time` — parses a `time.struct_time`-like tuple.
   - `test_extract_article_missing_title` — returns `None`.
   - `test_extract_article_old` — returns `None` for articles older than cutoff.
4. Create `tests/test_summarizer.py`:
   - `test_summarize_valid_json` — mock Groq client, return valid JSON, assert output shape.
   - `test_summarize_truncated_json` — mock returns truncated JSON, assert regex recovery runs and returns partial result.
   - `test_summarize_empty_articles` — assert returns `{"daily_brief": "", "sections": {}}` immediately.
   - `test_summarize_empty_choices` — mock returns `choices=[]`, assert `ValueError` raised.
5. Create `tests/test_publisher.py`:
   - `test_load_seen_urls_missing_file` — returns empty set.
   - `test_load_seen_urls_corrupted_file` — returns empty set, logs error.
   - `test_load_seen_urls_prunes_old` — entries older than 3 days are excluded.
   - `test_update_seen_urls_appends` — new URLs are written to the file.
   - `test_build_substack_post_structure` — output contains expected HTML landmarks (`<h2>`, `<blockquote>`, `<hr>`).
6. Add a `ci.yml` workflow (or a `test` job in `daily-newsletter.yml`) triggered on push/PR:
   ```yaml
   - name: Run tests
     run: pip install -r requirements-dev.txt && pytest tests/ --cov=newsletter --cov-report=term-missing
   ```

### Test
- Run `pytest tests/ -v` locally — all tests pass.
- Run `pytest --cov=newsletter` — coverage report shows >60% on `fetcher.py`, `summarizer.py`, `publisher.py`.
- Confirm the CI workflow triggers and passes on a test push.

### Commit
```
test: add pytest suite with fixtures and unit tests for fetcher, summarizer, publisher
```
Files: `tests/__init__.py`, `tests/conftest.py`, `tests/test_fetcher.py`, `tests/test_summarizer.py`, `tests/test_publisher.py`, `.github/workflows/ci.yml`

---

## Phase 9 — Documentation [x]

**Goal:** Any new contributor (or future AI) can set up and run the project from scratch using only the repo.

**Scope:** `README.md` (new), `.env.example`

### Plan
- No `README.md` exists. Cover: what it is, prerequisites, local setup, env vars, how to add a feed, how to trigger manually, architecture (ASCII), licence.
- `.env.example` is missing `RECIPIENT_EMAIL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SUBSTACK_SID`.

### Execute
1. Write `README.md` covering:
   - One-paragraph description + screenshot of an email issue
   - Prerequisites: Python 3.11, GitHub account, Groq API key, Gmail App Password
   - Local setup steps (virtualenv, install, copy `.env`, run)
   - Full env vars table (copy from `CLAUDE.md`, keep in sync)
   - ASCII architecture diagram
   - How to add a new RSS feed (edit `config.py`)
   - How to trigger manually (GitHub Actions → `workflow_dispatch`)
   - How GitHub Pages publishing works
   - Licence section
2. Update `.env.example` with all missing vars plus one-line comments for each.

### Test
- Follow the README from scratch in a fresh terminal with a clean virtualenv — verify every step works as written.
- Check all env vars in `.env.example` match what `main._validate_env()` checks (from Phase 1).

### Commit
```
docs: add README.md and complete .env.example
```
Files: `README.md`, `.env.example`

---

---

# BLOCK 5 — GTM: Technical distribution
*Automated reach. Each channel is its own phase so a broken OAuth token doesn't block others.*

---

## Phase 10 — Archive SEO [x]

**Goal:** Every issue page is indexable, has good link previews, and the archive has a sitemap.

**Scope:** `newsletter/emailer.py`, `newsletter/publisher.py`

### Plan
- `emailer.build_html()` generates the archive page but has no `<title>`, `<meta description>`, or Open Graph tags.
- `publisher._write_rss()` could also write a `sitemap.xml` from `manifest.json`.
- These changes improve every past and future issue automatically since HTML is regenerated each run.

### Execute
1. In `emailer.build_html()`: update the `<head>` block to include:
   - `<title>Gradient Descent — {date_str} | Daily AI Intelligence</title>`
   - `<meta name="description" content="{daily_brief[:160]}">`
   - `<meta property="og:title" content="Gradient Descent — {date_str}">`
   - `<meta property="og:description" content="{daily_brief[:160]}">`
   - `<meta property="og:image" content="{ARCHIVE_BASE_URL}/logo.png">`
   - `<meta property="og:url" content="{issue_url}">` — requires passing `date_str` into `build_html()`; update the function signature and all callers.
2. In `publisher._write_rss()`: after writing `feed.xml`, also write `docs/sitemap.xml` listing all issue URLs.

### Test
- Run `python -m newsletter.main` locally (or call `emailer.build_html()` directly with a sample result).
- Open the generated HTML in a browser — verify the `<title>` is visible in the tab.
- Run the HTML through an OG tag checker (e.g. paste the HTML into a local `<meta>` validator) — verify all four OG properties are present.
- Verify `docs/sitemap.xml` is generated and lists the correct URLs.

### Commit
```
feat: add SEO meta tags, Open Graph tags, and sitemap to archive
```
Files: `newsletter/emailer.py`, `newsletter/publisher.py`

---

## Phase 11 — Auto-post to X/Twitter [x]

**Goal:** Every morning, the newsletter headline and archive link are automatically tweeted.

**Scope:** `newsletter/publisher.py`, `newsletter/main.py`, `requirements.txt`, `.env.example`, `.github/workflows/daily-newsletter.yml`

### Plan
- Twitter API v2 free tier: 1,500 tweets/month (50/day), more than enough.
- Use `tweepy` with OAuth 1.0a (required for posting; Bearer Token is read-only).
- Post format: `{headline}\n\n{daily_brief[:200]}\n\n→ {issue_url}\n\nSubscribe: {substack_url}` — trim to stay under 280 chars.
- Credentials needed: `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET`.
- Step is soft: if any credential is missing, log warning and skip — do not fail the run.

### Execute
1. Register a Twitter Developer app at developer.twitter.com (free). Enable OAuth 1.0a with Read+Write permissions. Generate Access Token and Secret.
2. Add `tweepy~=4.14` to `requirements.txt`.
3. In `publisher.py`: add `post_to_twitter(result: dict, date_str: str) -> None`. Build the tweet text, call `tweepy.Client.create_tweet()`. Handle `tweepy.errors.TweepyException` gracefully.
4. In `main.py`: add step 9 calling `publisher.post_to_twitter(result, date_str)`, wrapped in try/except.
5. Add all four Twitter env vars to `.env.example`, `daily-newsletter.yml` env block, and GitHub secrets.

### Test
- Set credentials locally and run `publisher.post_to_twitter(sample_result, "2026-04-21")` directly.
- Verify the tweet appears on the account with correct text and working link.
- Remove one credential and verify the function logs a warning and returns without raising.
- Run the full pipeline — verify the step appears in logs as step 9.

### Commit
```
feat: auto-post daily headline to X/Twitter via Tweepy
```
Files: `newsletter/publisher.py`, `newsletter/main.py`, `requirements.txt`, `.env.example`, `.github/workflows/daily-newsletter.yml`

---

## Phase 12 — Auto-post to LinkedIn [x]

**Goal:** Every morning, the newsletter brief is posted to LinkedIn as a native text post.

**Scope:** `newsletter/publisher.py`, `newsletter/main.py`, `.env.example`, `.github/workflows/daily-newsletter.yml`

### Plan
- LinkedIn API (free for personal use): use the `ugcPosts` endpoint via OAuth 2.0.
- Long-lived tokens last ~60 days; set up a refresh reminder or use a service account.
- Post format: headline as first line (bold via LinkedIn native formatting is not supported in API posts — plain text only), then the `daily_brief`, then the archive link and subscribe CTA.
- Credential needed: `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN` (your personal URN, format `urn:li:person:{id}`).
- Step is soft: skip gracefully if credentials missing.
- No new pip dependencies — use `urllib.request` (already in stdlib).

### Execute
1. Register a LinkedIn OAuth app at developer.linkedin.com. Request the `w_member_social` scope. Obtain an access token via the OAuth 2.0 authorization code flow (one-time manual step; document in README).
2. In `publisher.py`: add `post_to_linkedin(result: dict, date_str: str) -> None`. Build the post text. POST to `https://api.linkedin.com/v2/ugcPosts` with `Authorization: Bearer {token}` header.
3. In `main.py`: add step 10 calling `publisher.post_to_linkedin(result, date_str)`, wrapped in try/except.
4. Add `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_AUTHOR_URN` to `.env.example`, workflow env block, and GitHub secrets.

### Test
- Run `post_to_linkedin()` locally with real credentials — verify a post appears on your LinkedIn profile.
- Verify the post text is under LinkedIn's 3,000-character limit and looks correct on mobile.
- Remove one credential — verify warning log and graceful skip.
- Run full pipeline end-to-end — verify step 10 appears in logs.

### Commit
```
feat: auto-post daily brief to LinkedIn via UGC Posts API
```
Files: `newsletter/publisher.py`, `newsletter/main.py`, `.env.example`, `.github/workflows/daily-newsletter.yml`

---

## Phase 18 — AI prompt & output quality [x]

**Goal:** Eliminate repetitive briefs and give the model richer article context.

**Scope:** `newsletter/summarizer.py`, `newsletter/config.py`

### Execute
- [x] `SNIPPET_MAX_CHARS`: 150 → 300 — doubles semantic context per article.
- [x] `_SYSTEM_PROMPT`: replaced single Sentence-1 example (which the model copied verbatim) with 3 structurally distinct examples; added VARIETY constraint block listing forbidden opening phrases; added domain-specific forcing-function examples for Sentence 3.
- [x] `_build_user_message()`: added published date to each article block.
- [x] Temperature: 0.4 → 0.5 to break convergent phrasing.

### Commit
```
feat: improve prompt variety, increase snippet context, bump temperature
```

---

## Phase 19 — GitHub Pages web experience [x]

**Goal:** Issue pages get a web nav bar; homepage footer gets social links.

**Scope:** `newsletter/publisher.py`, `docs/index.html`

### Execute
- [x] `save_to_archive()`: inject dark web nav bar (← Archive + Subscribe free) via `re.sub` into saved archive HTML — email template untouched.
- [x] `docs/index.html` footer: added Twitter/X and LinkedIn links.

### Commit
```
feat: add Twitter/X and LinkedIn social links to homepage footer
feat: add web nav bar to archive pages, improve Substack post HTML, add RSS categories
```

---

## Phase 20 — Substack post quality [x]

**Goal:** Cleaner Substack post HTML, proper RSS category tags, and a pinned About post.

**Scope:** `newsletter/publisher.py` (code), Substack UI (manual).

### Execute — code (done)
- [x] `build_substack_post()`: replaced CSS dot divider with `<hr>`; simplified footer CTA to link archive instead of duplicating native subscribe button.
- [x] `_write_rss()`: added `<category>` tags per topic for Substack auto-tagging.

### Execute — manual (done)
- [x] Created and pinned "About Gradient Descent" post on Substack.
- [x] Publication logo and cover image set.
- ~~Navigation sections~~ — not possible; Substack sections must be internal topic groupings, not external URLs.

### Commit
```
feat: add web nav bar to archive pages, improve Substack post HTML, add RSS categories
```

---

# Backlog (unscheduled)

- Multi-recipient support — prerequisite: Phase 1 (RECIPIENT_EMAIL as env var)
- Web UI to manage feed sources without editing `config.py`
- Topic-level open rate tracking → data-driven `TOPIC_ROTATION` adjustments
- Digest mode: weekly summary for lower-frequency subscribers
- Webhook trigger: run pipeline on demand from a Telegram bot command
- Source quality scoring: weight feeds that consistently produce high-score articles
- Personalised edition: different email content per subscriber segment
