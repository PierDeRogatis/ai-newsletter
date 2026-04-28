"""One-off script: inject web-override <style> block + nav bar into existing issue HTML files.
Run once from the repo root: python scripts/patch_issues.py
"""
import os

STYLE_MARKER = "web-only overrides"

STYLE_BLOCK = """  <style>
    /* ── web-only overrides (email clients ignore <style> blocks) ── */
    @media screen {
      body { background: #03080F !important; }
      body::before {
        content: '';
        position: fixed; inset: 0; z-index: 0; pointer-events: none;
        background-image: radial-gradient(circle, rgba(0,255,200,0.04) 1px, transparent 1px);
        background-size: 36px 36px;
      }
      table[width="100%"]:first-of-type > tbody > tr > td {
        background: transparent !important; position: relative; z-index: 1;
      }
      table[width="600"] { border-radius: 16px; overflow: hidden; }
      table[width="600"] > tbody > tr:first-child > td {
        background: #06101A !important;
        border-bottom: 1px solid rgba(0,255,200,0.15) !important;
      }
      table[width="600"] > tbody > tr:nth-child(2) > td {
        background: #06101A !important;
        border-radius: 0 0 16px 16px !important;
      }
      table[width="600"] td { color: #C8E0F0 !important; }
      table[width="600"] td a[style*="color:#111827"] { color: #ECF5FF !important; }
      table[width="600"] td p[style*="color:#4B5563"] { color: #7A95B0 !important; }
      td[style*="background:#F0FDF4"] {
        background: rgba(0,255,200,0.05) !important;
        border-left: 3px solid #00FFC8 !important;
        border-radius: 0 8px 8px 0 !important;
      }
      td[style*="background:#F0FDF4"] p:first-child { color: #00FFC8 !important; }
      td[style*="background:#F0FDF4"] p:last-child  { color: #B8D4E8 !important; }
      td[style*="border-bottom:1px solid #F3F4F6"] {
        border-bottom: 1px solid rgba(255,255,255,0.05) !important;
      }
      td[style*="background:#080E1C"] {
        background: #030810 !important;
        border: 1px solid rgba(0,255,200,0.12) !important;
        border-radius: 12px !important;
      }
    }
  </style>"""

ARCHIVE_BASE = "https://pierderogatis.github.io/ai-newsletter"
SUBSTACK_URL = "https://pierluigiderogatis.substack.com"

NAV_BAR = (
    f'  <div style="background:#03080F;padding:12px 24px;display:flex;'
    f'justify-content:space-between;align-items:center;'
    f'border-bottom:1px solid rgba(0,255,200,0.15);position:relative;z-index:1;">\n'
    f'    <a href="{ARCHIVE_BASE}/index.html" style="color:#00FFC8;font-size:12px;'
    f'font-weight:700;text-decoration:none;letter-spacing:0.06em;'
    f'text-shadow:0 0 8px rgba(0,255,200,0.4);">&larr; Archive</a>\n'
    f'    <a href="{SUBSTACK_URL}/subscribe" style="color:#6B82A0;font-size:12px;'
    f'font-weight:600;text-decoration:none;">Subscribe free &rarr;</a>\n'
    f'  </div>'
)

issues_dir = "docs/issues"
patched = 0
skipped = 0

for fname in sorted(os.listdir(issues_dir)):
    if not fname.endswith(".html"):
        continue
    path = os.path.join(issues_dir, fname)
    with open(path, encoding="utf-8") as f:
        html = f.read()

    if STYLE_MARKER in html:
        skipped += 1
        continue

    # inject style block before </head>
    html = html.replace("</head>", STYLE_BLOCK + "\n</head>", 1)

    # update legacy accent colors in nav/header (safe; already dark elements)
    html = html.replace("color:#6EE7B7", "color:#00FFC8")
    html = html.replace("background:#00C9A7", "background:#00FFC8")

    # inject nav bar after <body ...> (skip if one already exists)
    if "Archive</a>" not in html:
        body_tag_end = html.find(">", html.find("<body"))
        if body_tag_end != -1:
            html = html[:body_tag_end + 1] + "\n" + NAV_BAR + "\n" + html[body_tag_end + 1:]

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Patched: {fname}")
    patched += 1

print(f"\nDone — {patched} patched, {skipped} already up-to-date.")
