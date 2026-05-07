import json
import os
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone

from newsletter.config import SENDER_EMAIL, TOPIC_COLORS

logger = logging.getLogger(__name__)

_GATE_GH_PAT  = os.environ.get("GATE_GH_PAT", "")
_GATE_GH_REPO = "PierDeRogatis/ai-newsletter"

_DEFAULT_COLOR = "#374151"

# HTML-entity icons — kept here because email clients render emoji unreliably;
# Substack/Telegram use the emoji version from config.TOPIC_ICONS instead.
_TOPIC_ICONS: dict[str, str] = {
    "AI & Data Tools":     "&#128202;",  # chart
    "AI in Finance":       "&#128200;",  # chart up
    "AI in Sports":        "&#127939;",  # running
    "Research & Academia": "&#128218;",  # books
    "Podcasts":            "&#127911;",  # headphones
}


_GATE_OVERLAY = '<div id="gd-gate" style="position:fixed;inset:0;z-index:9000;background:rgba(3,8,15,0.82);backdrop-filter:blur(12px);display:none;align-items:center;justify-content:center;"><div style="background:#06101A;border:1px solid rgba(0,255,200,0.2);border-radius:16px;padding:40px 36px;max-width:420px;width:90%;text-align:center;box-shadow:0 0 60px rgba(0,255,200,0.08);"><p style="margin:0 0 4px;color:#00FFC8;font-size:11px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;">Continue reading</p><h2 style="margin:0 0 12px;color:#ECF5FF;font-size:20px;font-weight:700;line-height:1.3;">Get your daily edge, free</h2><p style="margin:0 0 24px;color:#7A95B0;font-size:13px;line-height:1.6;">Enter your email to read today&#8217;s issue and receive Gradient Descent every morning.</p><form id="gd-form" style="text-align:left;"><input id="gd-email" type="email" required placeholder="you@example.com" aria-label="Email address" style="display:block;width:100%;box-sizing:border-box;background:#03080F;border:1px solid rgba(0,255,200,0.2);border-radius:8px;padding:12px 14px;color:#ECF5FF;font-size:14px;font-family:inherit;margin-bottom:12px;outline:none;"><label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer;margin-bottom:20px;"><input id="gd-consent" type="checkbox" style="margin-top:2px;accent-color:#00FFC8;flex-shrink:0;"><span style="color:#6B82A0;font-size:12px;line-height:1.5;">I agree to receive Gradient Descent by email. Unsubscribe anytime.</span></label><p id="gd-error" style="display:none;color:#FF6B6B;font-size:12px;margin:-12px 0 12px;"></p><button id="gd-submit" type="submit" style="width:100%;background:#00FFC8;color:#03080F;font-size:13px;font-weight:700;padding:13px;border:none;border-radius:8px;cursor:pointer;letter-spacing:0.04em;font-family:inherit;">Unlock today&#8217;s issue</button></form><p style="margin:16px 0 0;color:#3A5070;font-size:11px;">No spam. No tracking. Unsubscribe with one click.</p></div></div>'


def _build_gate_js(gh_pat: str, gh_repo: str) -> str:
    dispatch_url = f"https://api.github.com/repos/{gh_repo}/actions/workflows/capture-email.yml/dispatches"
    mid = len(gh_pat) // 2
    pat_a, pat_b = gh_pat[:mid], gh_pat[mid:]
    return f"""<script>
(function() {{
  var S   = 'gd_unlocked';
  var URL = '{dispatch_url}';
  var PAT = '{pat_a}' + '{pat_b}';
  if (localStorage.getItem(S)) return;
  var sent = document.getElementById('gd-brief-end');
  var gate = document.getElementById('gd-gate');
  var cont = document.getElementById('gd-gate-content');
  if (!sent || !gate || !cont) return;
  var io = new IntersectionObserver(function(es) {{
    es.forEach(function(e) {{
      if (!e.isIntersecting) {{ gate.classList.add('gd-visible'); cont.classList.add('gd-locked'); }}
    }});
  }}, {{threshold: 0}});
  io.observe(sent);
  document.getElementById('gd-form').addEventListener('submit', function(e) {{
    e.preventDefault();
    var email = document.getElementById('gd-email').value.trim();
    var ok    = document.getElementById('gd-consent').checked;
    var err   = document.getElementById('gd-error');
    var btn   = document.getElementById('gd-submit');
    if (!ok) {{ err.textContent = 'Please accept to continue.'; err.style.display = 'block'; return; }}
    err.style.display = 'none';
    btn.disabled = true; btn.textContent = 'Unlocking…';
    fetch(URL, {{
      method: 'POST',
      headers: {{
        'Authorization': 'Bearer ' + PAT,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28'
      }},
      body: JSON.stringify({{ref: 'main', inputs: {{email: email}}}})
    }})
      .catch(function() {{}})
      .finally(function() {{
        localStorage.setItem(S, '1');
        gate.classList.remove('gd-visible');
        cont.classList.remove('gd-locked');
        io.disconnect();
      }});
  }});
}})();
</script>"""



def _fetch_brevo_contacts(api_key: str, list_id: int) -> list[str]:
    emails: list[str] = []
    offset = 0
    while True:
        url = f"https://api.brevo.com/v3/contacts?listId={list_id}&limit=500&offset={offset}"
        req = urllib.request.Request(
            url, headers={"api-key": api_key, "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        page = [c["email"] for c in data.get("contacts", []) if c.get("email")]
        emails += page
        if len(emails) >= data.get("count", 0) or not page:
            break
        offset += 500
    return emails


def _brevo_send(
    api_key: str, sender_email: str, recipients: list[str], subject: str, html: str
) -> None:
    payload = json.dumps({
        "sender":      {"name": "Gradient Descent", "email": sender_email},
        "to":          [{"email": e} for e in recipients],
        "subject":     subject,
        "htmlContent": html,
    }).encode()
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={"api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        logger.info("Brevo send OK (HTTP %d) to %d recipients", resp.status, len(recipients))


def _section_html(topic: str, articles: list[dict]) -> str:
    if not articles:
        return ""
    color = TOPIC_COLORS.get(topic, _DEFAULT_COLOR)
    icon = _TOPIC_ICONS.get(topic, "")
    rows = ""
    for a in articles:
        title = a.get("title", "")
        url = a.get("url", "#")
        summary = a.get("summary", "")
        source = a.get("source", "")
        label = "Listen" if topic == "Podcasts" else "Read"
        rows += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #F3F4F6;">
            <a href="{url}" style="color:#111827;font-weight:600;font-size:14px;text-decoration:none;line-height:1.4;">{title}</a>
            <p style="margin:6px 0 0;color:#4B5563;font-size:13px;line-height:1.6;">{summary}</p>
            <p style="margin:6px 0 0;">
              <span style="color:#9CA3AF;font-size:12px;">{source}</span>
              &nbsp;&bull;&nbsp;
              <a href="{url}" style="color:{color};font-size:12px;font-weight:600;text-decoration:none;">&rarr; {label}</a>
            </p>
          </td>
        </tr>"""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
      <tr>
        <td style="padding:0 0 10px;">
          <span style="background:{color};color:#fff;font-size:11px;font-weight:700;
                        letter-spacing:0.08em;text-transform:uppercase;
                        padding:3px 10px;border-radius:12px;">
            {icon} {topic}
          </span>
        </td>
      </tr>
      {rows}
    </table>"""


def _build_jsonld(iso_date: str, headline: str, meta_desc: str, issue_url: str, pub_base: str, keywords: list[str]) -> str:
    logo_url = f"{pub_base}/logo.png"
    kw_str = ", ".join(keywords) if keywords else "AI, machine learning, data science"
    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "NewsArticle",
  "headline": "{headline}",
  "description": "{meta_desc}",
  "datePublished": "{iso_date}",
  "dateModified": "{iso_date}",
  "timeRequired": "PT3M",
  "keywords": "{kw_str}",
  "url": "{issue_url}",
  "image": {{
    "@type": "ImageObject",
    "url": "{logo_url}",
    "width": 1080,
    "height": 1080
  }},
  "author": {{
    "@type": "Person",
    "name": "Pierluigi De Rogatis"
  }},
  "publisher": {{
    "@type": "Organization",
    "name": "Gradient Descent",
    "logo": {{
      "@type": "ImageObject",
      "url": "{logo_url}",
      "width": 1080,
      "height": 1080
    }}
  }},
  "isPartOf": {{
    "@type": "Periodical",
    "name": "Gradient Descent",
    "url": "{pub_base}/"
  }},
  "breadcrumb": {{
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "Archive", "item": "{pub_base}/"}},
      {{"@type": "ListItem", "position": 2, "name": "{iso_date}", "item": "{issue_url}"}}
    ]
  }}
}}
</script>"""


def build_html(result: dict, iso_date: str | None = None) -> str:
    daily_brief: str = result.get("daily_brief", "")
    sections: dict[str, list[dict]] = result.get("sections", {})

    if iso_date:
        now = datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
        iso_date = now.strftime("%Y-%m-%d")
    date_str = now.strftime("%A, %B %-d %Y")
    total = sum(len(v) for v in sections.values())

    pub_base = os.environ.get(
        "ARCHIVE_BASE_URL", "https://pierderogatis.github.io/ai-newsletter"
    ).rstrip("/")
    issue_url = f"{pub_base}/issues/{iso_date}.html"
    meta_desc = (daily_brief or "")[:160].replace('"', "&quot;")

    brief_block = ""
    if daily_brief:
        brief_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
          <tr>
            <td style="background:#F0FDF4;border-left:4px solid #059669;border-radius:0 8px 8px 0;padding:16px 20px;">
              <p style="margin:0 0 6px;color:#065F46;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">Today's Brief</p>
              <p style="margin:0;color:#1F2937;font-size:14px;line-height:1.7;">{daily_brief}</p>
            </td>
          </tr>
        </table>"""

    sections_html = "".join(
        _section_html(topic, articles)
        for topic, articles in sections.items()
        if articles
    )

    substack_url = os.environ.get("SUBSTACK_URL", "https://pierluigiderogatis.substack.com").rstrip("/")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>Gradient Descent — {date_str} | Daily AI Intelligence</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="{issue_url}">
  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Gradient Descent">
  <meta property="og:title" content="Gradient Descent — {date_str} | Daily AI Intelligence">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:image" content="{pub_base}/logo.png">
  <meta property="og:url" content="{issue_url}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Gradient Descent — {date_str} | Daily AI Intelligence">
  <meta name="twitter:description" content="{meta_desc}">
  <meta name="twitter:image" content="{pub_base}/logo.png">
  <style>
    /* ── web-only overrides (email clients ignore <style> blocks) ── */
    @media screen {{
      body {{ background: #03080F !important; }}
      body::before {{
        content: '';
        position: fixed; inset: 0; z-index: 0; pointer-events: none;
        background-image: radial-gradient(circle, rgba(0,255,200,0.04) 1px, transparent 1px);
        background-size: 36px 36px;
      }}
      table[width="100%"]:first-of-type > tbody > tr > td {{
        background: transparent !important; position: relative; z-index: 1;
      }}
      table[width="600"] {{ border-radius: 16px; overflow: hidden; }}
      table[width="600"] > tbody > tr:first-child > td {{
        background: #06101A !important;
        border-bottom: 1px solid rgba(0,255,200,0.15) !important;
      }}
      table[width="600"] > tbody > tr:nth-child(2) > td {{
        background: #06101A !important;
        border-radius: 0 0 16px 16px !important;
      }}
      table[width="600"] td {{ color: #C8E0F0 !important; }}
      table[width="600"] td a[style*="color:#111827"] {{ color: #ECF5FF !important; }}
      table[width="600"] td p[style*="color:#4B5563"] {{ color: #7A95B0 !important; }}
      td[style*="background:#F0FDF4"] {{
        background: rgba(0,255,200,0.05) !important;
        border-left: 3px solid #00FFC8 !important;
        border-radius: 0 8px 8px 0 !important;
      }}
      td[style*="background:#F0FDF4"] p:first-child {{ color: #00FFC8 !important; }}
      td[style*="background:#F0FDF4"] p:last-child  {{ color: #B8D4E8 !important; }}
      td[style*="border-bottom:1px solid #F3F4F6"] {{
        border-bottom: 1px solid rgba(255,255,255,0.05) !important;
      }}
      td[style*="background:#080E1C"] {{
        background: #030810 !important;
        border: 1px solid rgba(0,255,200,0.12) !important;
        border-radius: 12px !important;
      }}
      #gd-gate-content.gd-locked {{ filter: blur(6px); pointer-events: none; user-select: none; }}
      #gd-gate {{ display: none; }}
      #gd-gate.gd-visible {{ display: flex !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#F9FAFB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="background:#03080F;padding:12px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(0,255,200,0.15);position:relative;z-index:1;">
    <a href="{pub_base}/index.html" style="color:#00FFC8;font-size:12px;font-weight:700;text-decoration:none;letter-spacing:0.06em;text-shadow:0 0 8px rgba(0,255,200,0.4);">&larr; Archive</a>
    <a href="{substack_url}/subscribe" style="color:#6B82A0;font-size:12px;font-weight:600;text-decoration:none;">Subscribe free &rarr;</a>
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F9FAFB;">
    <tr><td align="center" style="padding:32px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:#111827;border-radius:12px 12px 0 0;padding:28px 32px;">
            <table cellpadding="0" cellspacing="0" style="margin-bottom:14px;">
              <tr>
                <td style="padding-right:12px;vertical-align:middle;">
                  <img src="{pub_base}/logo.png"
                       alt="Gradient Descent" width="44" height="44"
                       style="display:block;border-radius:8px;">
                </td>
                <td style="vertical-align:middle;">
                  <p style="margin:0;color:#00FFC8;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;">Gradient Descent</p>
                  <p style="margin:2px 0 0;color:#9CA3AF;font-size:11px;">Daily AI Intelligence</p>
                </td>
              </tr>
            </table>
            <h1 style="margin:0 0 6px;color:#FFFFFF;font-size:22px;font-weight:700;">{date_str}</h1>
            <p style="margin:0;color:#9CA3AF;font-size:13px;">Good morning &mdash; {total} items &bull; ~3 min read</p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="background:#FFFFFF;border-radius:0 0 12px 12px;padding:28px 32px;">
            {brief_block}
            <div id="gd-brief-end"></div>
            {_GATE_OVERLAY}
            <div id="gd-gate-content">
            {sections_html}
            </div>

            <!-- Outro -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:32px;">
              <tr>
                <td style="background:#080E1C;border-radius:10px;padding:24px 28px;">
                  <p style="margin:0 0 4px;color:#00FFC8;font-size:11px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;">That's your edge for today.</p>
                  <p style="margin:0 0 16px;color:#9CA3AF;font-size:13px;line-height:1.7;">
                    See you tomorrow morning with the next gradient step.
                  </p>
                  <table cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding-right:10px;">
                        <a href="{substack_url}/subscribe"
                           style="display:inline-block;background:#00FFC8;color:#080E1C;
                                  font-size:12px;font-weight:700;padding:8px 16px;
                                  border-radius:6px;text-decoration:none;letter-spacing:0.02em;">
                          Subscribe on Substack &rarr;
                        </a>
                      </td>
                      <td>
                        <a href="{substack_url}"
                           style="display:inline-block;color:#6B7280;font-size:12px;
                                  font-weight:600;text-decoration:none;padding:8px 0;">
                          Forward to a colleague
                        </a>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>

            <!-- Footer -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px;">
              <tr>
                <td style="color:#D1D5DB;font-size:10px;text-align:center;line-height:1.8;">
                  Gradient Descent &bull; Powered by Groq &bull; Sources: curated RSS across 15+ publications<br>
                  You&rsquo;re receiving this because you subscribed to Gradient Descent.
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
  {_build_gate_js(_GATE_GH_PAT, _GATE_GH_REPO)}
  {_build_jsonld(iso_date, result.get("headline", "").replace('"', "&quot;"), meta_desc, issue_url, pub_base, list(sections.keys()))}
</body>
</html>"""


def send(result: dict) -> None:
    api_key = os.environ.get("BREVO_KEY", "")
    if not api_key:
        raise EnvironmentError("BREVO_KEY is not set")
    if not SENDER_EMAIL:
        raise EnvironmentError("SENDER_EMAIL is not set")

    now = datetime.now(timezone.utc)
    headline = result.get("headline", "").strip()
    subject = f"Gradient Descent — {now.strftime('%a %b %-d')}"
    if headline:
        subject = f"{subject} · {headline}"

    html = build_html(result)

    from newsletter.config import BREVO_LIST_ID
    recipients = _fetch_brevo_contacts(api_key, BREVO_LIST_ID)
    if not recipients:
        logger.warning("Brevo list %d has no contacts — skipping send", BREVO_LIST_ID)
        return

    _brevo_send(api_key, SENDER_EMAIL, recipients, subject, html)
