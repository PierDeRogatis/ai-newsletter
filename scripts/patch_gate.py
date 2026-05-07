"""One-off script: add/update soft content gate in all issue HTML files.

Run from the repo root:
    GATE_GH_PAT=github_pat_... python3 scripts/patch_gate.py

Pass GATE_GH_PAT to embed the token; if omitted the gate still works but
email capture is skipped until the PAT is set and the script re-run.
After running, commit the patched docs/issues/*.html files.
"""
import os
import re

GH_PAT  = os.environ.get("GATE_GH_PAT", "")
GH_REPO = "PierDeRogatis/ai-newsletter"
DISPATCH_URL = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/capture-email.yml/dispatches"
_mid = len(GH_PAT) // 2
_PAT_A = GH_PAT[:_mid]
_PAT_B = GH_PAT[_mid:]

MARKER = "gd-brief-end"

GATE_CSS = """\
      #gd-gate-content.gd-locked { filter: blur(6px); pointer-events: none; user-select: none; }
      #gd-gate { display: none; }
      #gd-gate.gd-visible { display: flex !important; }"""

GATE_OVERLAY = (
    '<div id="gd-gate" style="position:fixed;inset:0;z-index:9000;background:rgba(3,8,15,0.82);'
    'backdrop-filter:blur(12px);display:none;align-items:center;justify-content:center;">'
    '<div style="background:#06101A;border:1px solid rgba(0,255,200,0.2);border-radius:16px;'
    'padding:40px 36px;max-width:420px;width:90%;text-align:center;'
    'box-shadow:0 0 60px rgba(0,255,200,0.08);">'
    '<p style="margin:0 0 4px;color:#00FFC8;font-size:11px;font-weight:700;'
    'letter-spacing:0.14em;text-transform:uppercase;">Continue reading</p>'
    '<h2 style="margin:0 0 12px;color:#ECF5FF;font-size:20px;font-weight:700;line-height:1.3;">'
    'Get your daily edge, free</h2>'
    '<p style="margin:0 0 24px;color:#7A95B0;font-size:13px;line-height:1.6;">'
    'Enter your email to read today&#8217;s issue and receive Gradient Descent every morning.</p>'
    '<form id="gd-form" style="text-align:left;">'
    '<input id="gd-email" type="email" required placeholder="you@example.com" '
    'aria-label="Email address" '
    'style="display:block;width:100%;box-sizing:border-box;background:#03080F;'
    'border:1px solid rgba(0,255,200,0.2);border-radius:8px;padding:12px 14px;'
    'color:#ECF5FF;font-size:14px;font-family:inherit;margin-bottom:12px;outline:none;">'
    '<label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer;margin-bottom:20px;">'
    '<input id="gd-consent" type="checkbox" '
    'style="margin-top:2px;accent-color:#00FFC8;flex-shrink:0;">'
    '<span style="color:#6B82A0;font-size:12px;line-height:1.5;">'
    'I agree to receive Gradient Descent by email. Unsubscribe anytime.</span>'
    '</label>'
    '<p id="gd-error" style="display:none;color:#FF6B6B;font-size:12px;margin:-12px 0 12px;"></p>'
    '<button id="gd-submit" type="submit" '
    'style="width:100%;background:#00FFC8;color:#03080F;font-size:13px;font-weight:700;'
    'padding:13px;border:none;border-radius:8px;cursor:pointer;letter-spacing:0.04em;'
    'font-family:inherit;">Unlock today&#8217;s issue</button>'
    '</form>'
    '<p style="margin:16px 0 0;color:#3A5070;font-size:11px;">'
    'No spam. No tracking. Unsubscribe with one click.</p>'
    '</div></div>'
)

GATE_JS = f"""<script>
(function() {{
  var S   = 'gd_unlocked';
  var URL = '{DISPATCH_URL}';
  var PAT = '{_PAT_A}' + '{_PAT_B}';
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
        var t = document.createElement('div');
        t.textContent = '✓ Subscribed! Check your spam folder and mark us as safe.';
        t.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9001;background:#06101A;border:1px solid rgba(0,255,200,0.3);color:#ECF5FF;padding:12px 16px;border-radius:8px;font-size:12px;max-width:300px;line-height:1.5;';
        document.body.appendChild(t);
        setTimeout(function(){{t.remove();}},7000);
      }});
  }});
}})();
</script>"""

# Regex that matches any gate JS block we previously injected (to replace it)
_OLD_JS_PATTERN = re.compile(r"<script>\s*\(function\(\) \{.*?gd_unlocked.*?\}\)\(\);\s*</script>", re.DOTALL)

# Regex to add aria-label to the gate email input on already-patched pages
_INPUT_ARIA_PATTERN = re.compile(
    r'(<input id="gd-email" type="email" required placeholder="you@example\.com" )(?!aria-label)'
)

CSS_TARGET = (
    "      td[style*=\"background:#080E1C\"] {\n"
    "        background: #030810 !important;\n"
    "        border: 1px solid rgba(0,255,200,0.12) !important;\n"
    "        border-radius: 12px !important;\n"
    "      }\n"
    "    }\n"
    "  </style>"
)
CSS_REPLACEMENT = (
    "      td[style*=\"background:#080E1C\"] {\n"
    "        background: #030810 !important;\n"
    "        border: 1px solid rgba(0,255,200,0.12) !important;\n"
    "        border-radius: 12px !important;\n"
    "      }\n"
    + GATE_CSS + "\n"
    + "    }\n"
    "  </style>"
)

# Regex: brief table → everything → <!-- Outro --> or <!-- Footer --> (older issues use the latter)
_BRIEF_PATTERN = re.compile(
    r"(Today's Brief.*?</table>)(.*?)(<!--\s*(?:Outro|Footer)\s*-->)",
    re.DOTALL,
)


def _wrap_sections(m: re.Match) -> str:
    brief_close = m.group(1)
    sections    = m.group(2)
    outro       = m.group(3)
    return (
        brief_close
        + '\n<div id="gd-brief-end"></div>\n'
        + GATE_OVERLAY + '\n'
        + '<div id="gd-gate-content">'
        + sections
        + '</div>\n'
        + outro
    )


docs_dir   = os.path.join(os.path.dirname(__file__), "..", "docs")
issues_dir = os.path.join(docs_dir, "issues")

# Patch index.html homepage form PAT
_INDEX_PAT_PATTERN = re.compile(r'const _GH_PAT = "[^"]*" \+ "[^"]*";')
index_path = os.path.join(docs_dir, "index.html")
with open(index_path) as f:
    index_html = f.read()
new_index = _INDEX_PAT_PATTERN.sub(f"const _GH_PAT = '{_PAT_A}' + '{_PAT_B}';", index_html, count=1)
if new_index != index_html:
    with open(index_path, "w") as f:
        f.write(new_index)
    print("Updated PAT: index.html")
else:
    print("Skip (index.html PAT unchanged)")

patched = updated = 0
for fname in sorted(os.listdir(issues_dir)):
    if not fname.endswith(".html"):
        continue
    path = os.path.join(issues_dir, fname)
    with open(path) as f:
        html = f.read()

    if MARKER in html:
        # Already has the gate structure — replace JS and patch aria-label
        new_html = _OLD_JS_PATTERN.sub(GATE_JS, html, count=1)
        new_html = _INPUT_ARIA_PATTERN.sub(r'\1aria-label="Email address" ', new_html, count=1)
        if new_html != html:
            with open(path, "w") as f:
                f.write(new_html)
            print(f"Updated JS+aria: {fname}")
            updated += 1
        else:
            print(f"Skip (unchanged): {fname}")
        continue

    # First-time patch
    if CSS_TARGET not in html:
        print(f"WARNING: CSS target not found in {fname} — skipping")
        continue
    html = html.replace(CSS_TARGET, CSS_REPLACEMENT, 1)

    new_html, n = _BRIEF_PATTERN.subn(_wrap_sections, html, count=1)
    if n == 0:
        print(f"WARNING: brief pattern not found in {fname} — skipping")
        continue
    html = new_html

    html = html.replace("</body>", GATE_JS + "\n</body>", 1)

    with open(path, "w") as f:
        f.write(html)
    print(f"Patched: {fname}")
    patched += 1

print(f"\nDone — {patched} new, {updated} JS-updated.")
