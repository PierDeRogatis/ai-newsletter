"""
One-time Substack publication setup script.
Run locally to configure all publication settings.

Usage:
    SUBSTACK_SID=<your-sid> python scripts/setup_substack.py

How to get your SID:
    1. Log into substack.com in Chrome/Firefox
    2. DevTools → Application → Cookies → substack.com
    3. Copy the value of 'substack.sid'
    4. Set it as an environment variable — do NOT pass it as a CLI argument
       (it would be visible in shell history and process listings)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PUB_URL = "https://pierluigiderogatis.substack.com"

# ── Publication content ────────────────────────────────────────────────────────

PUBLICATION_SETTINGS = {
    "name": "Gradient Descent",
    "hero_text": (
        "Daily AI intelligence for analysts, athletes, and researchers. "
        "Data tools, finance, sports science, and cutting-edge research — "
        "curated every morning into signal you can act on."
    ),
    "email_from_name": "Gradient Descent",
    "copyright": "Gradient Descent",
    "author_bio": (
        "Data Analyst, Financial Analyst, and Sport Performance Analyst. "
        "Competitive athlete and academic researcher. "
        "Building at the intersection of AI, quantitative methods, and human performance."
    ),
}

ABOUT_PAGE = """
<h2>What is Gradient Descent?</h2>

<p>Gradient Descent is a free daily morning briefing for professionals who operate at the intersection of AI, quantitative finance, sports analytics, and research.</p>

<p>The name comes from the optimisation algorithm at the heart of every neural network — the idea that you reach better outcomes by iterating steadily toward the minimum, adjusting one step at a time based on the signal you receive. That's what this newsletter does: each morning, one small step toward staying sharp in a fast-moving field.</p>

<h2>What you get</h2>

<p>Every issue opens with a <strong>cross-domain brief</strong> — 3 sentences identifying the hidden signal or tension connecting the day's stories. The kind of insight a senior fund manager or research director notices after reading everything, that most people miss.</p>

<p>Then, depending on the day:</p>

<ul>
  <li><strong>AI &amp; Data Tools</strong> — every day: pipelines, LLMs, frameworks, tooling that matters for production</li>
  <li><strong>AI in Finance</strong> — Mon, Fri, weekends: quant methods, fintech, markets, regulation</li>
  <li><strong>AI in Sports</strong> — Tue, Thu, weekends: performance analytics, wearables, biomechanics, coaching science</li>
  <li><strong>Research &amp; Academia</strong> — Wed, weekends: arXiv papers, benchmarks, model architecture, alignment</li>
  <li><strong>Podcast pick</strong> — every day: one episode from a rotating lineup of serious academic shows</li>
</ul>

<p>Each article is summarised in exactly 2 sentences: the specific finding (with numbers and names, never vague) and what it concretely changes for your work.</p>

<h2>Who writes it?</h2>

<p>Pierluigi De Rogatis — Data Analyst, Financial Analyst, Sport Performance Analyst, competitive athlete, and academic researcher. The newsletter is automated and curated daily via a custom AI pipeline, but the curation, prompts, and editorial standards are human-designed and maintained.</p>

<h2>Free, forever</h2>

<p>Gradient Descent is and will remain free. No paywalls, no paid tiers. Subscribe and share it with anyone who'd benefit.</p>
"""

WELCOME_EMAIL = {
    "subject": "Welcome to Gradient Descent — here's what to expect",
    "body": """
<p>Thanks for subscribing to <strong>Gradient Descent</strong>.</p>

<p>Starting tomorrow morning you'll receive a daily AI intelligence briefing tailored to professionals at the intersection of data science, finance, sports analytics, and research.</p>

<p><strong>What each issue contains:</strong></p>
<ul>
  <li>A 3-sentence cross-domain brief — the hidden signal connecting the day's stories</li>
  <li>2–3 curated articles per active topic, each summarised into the specific finding and what it changes for your work</li>
  <li>A podcast pick from a rotating lineup of serious academic shows</li>
</ul>

<p><strong>The schedule:</strong> AI & Data Tools and a podcast pick every day. Finance on Mon/Fri/weekends, Sports on Tue/Thu/weekends, Research on Wed/weekends. Full coverage on Saturdays and Sundays.</p>

<p>Each issue is ~3 minutes. No filler, no press releases — just signal.</p>

<p>— Pierluigi</p>
""",
}


# ── API helpers ────────────────────────────────────────────────────────────────

def _headers(sid: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Cookie": f"substack.sid={sid}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Origin": "https://substack.com",
        "Referer": "https://substack.com/publish/settings",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _get(url: str, sid: str) -> dict:
    req = urllib.request.Request(url, headers=_headers(sid))
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _patch(url: str, sid: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(sid), method="PATCH")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _post(url: str, sid: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(sid), method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _call(label: str, fn, *args):
    try:
        result = fn(*args)
        print(f"  ✓ {label}")
        return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  ✗ {label} — HTTP {e.code}: {body}")
        return None
    except Exception as e:
        print(f"  ✗ {label} — {e}")
        return None


# ── Setup steps ───────────────────────────────────────────────────────────────

def fetch_publication(sid: str) -> dict | None:
    print("\n[1/5] Fetching current publication settings…")
    pub = _call("GET publication", _get, f"{PUB_URL}/api/v1/publication", sid)
    if pub:
        print(f"      Found: {pub.get('name')} (id={pub.get('id')})")
    return pub


def update_core_settings(sid: str):
    print("\n[2/5] Updating core publication settings…")
    _call(
        "PATCH publication",
        _patch,
        f"{PUB_URL}/api/v1/publication",
        sid,
        PUBLICATION_SETTINGS,
    )


def create_or_update_about_page(sid: str):
    print("\n[3/5] Setting About page…")
    # Try to update the custom about section via publication settings
    _call(
        "PATCH about/description",
        _patch,
        f"{PUB_URL}/api/v1/publication",
        sid,
        {"description": ABOUT_PAGE},
    )


def set_welcome_email(sid: str):
    print("\n[4/5] Configuring welcome email…")
    # Substack stores the welcome email as a special draft post type
    _call(
        "PATCH welcome email",
        _patch,
        f"{PUB_URL}/api/v1/publication",
        sid,
        {
            "welcome_email_subject": WELCOME_EMAIL["subject"],
            "welcome_email_body": WELCOME_EMAIL["body"],
        },
    )


def print_manual_steps():
    print("\n[5/5] Manual steps (cannot be set via API):")
    print("""
  The following require the Substack dashboard UI — they take ~5 minutes:

  Logo & Cover image  →  Settings → Appearance
    Recommended: dark background (#080E1C), white "GD" monogram logo
    Cover: abstract gradient or neural network visualization (1500×500px)

  Social links  →  Settings → Publication details
    Add your LinkedIn, Twitter/X, GitHub

  Theme colour  →  Settings → Appearance → Accent colour
    Use #00C9A7 (teal) to match the archive landing page

  Sections/Navigation  →  Settings → Sections
    Sections: "Archive", "About" — keep it clean

  Recommendations  →  Settings → Recommendations
    Add 2-3 complementary newsletters to boost discovery

  Custom domain  →  Settings → Custom domain (optional, later)
""")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Set up Gradient Descent on Substack")
    parser.add_argument("--dry-run", action="store_true", help="Print settings without making API calls")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — settings that would be applied:\n")
        print(json.dumps(PUBLICATION_SETTINGS, indent=2))
        print("\nWelcome email subject:", WELCOME_EMAIL["subject"])
        return

    sid = os.environ.get("SUBSTACK_SID", "").strip()
    if not sid:
        print("Error: SUBSTACK_SID environment variable is not set.")
        print("  export SUBSTACK_SID=<your-substack.sid-cookie-value>")
        print("  python scripts/setup_substack.py")
        sys.exit(1)

    print("=" * 55)
    print("  Gradient Descent — Substack setup")
    print(f"  Target: {PUB_URL}")
    print("=" * 55)

    fetch_publication(sid)
    update_core_settings(sid)
    create_or_update_about_page(sid)
    set_welcome_email(sid)
    print_manual_steps()

    print("=" * 55)
    print("  Setup complete. Check your Substack dashboard.")
    print("=" * 55)


if __name__ == "__main__":
    main()
