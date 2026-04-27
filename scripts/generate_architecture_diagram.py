"""Generate ph-image-3-architecture.png — Excalidraw-style dark diagram."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1400, 900
BG = "#1e1e2e"
BOX_BG = "#2a2a3e"
BOX_BORDER = "#6EE7B7"
TEXT_MAIN = "#FFFFFF"
TEXT_DIM = "#9CA3AF"
ARROW = "#6EE7B7"
ACCENT = "#00C9A7"

img = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

def try_font(size):
    for name in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/Library/Fonts/Arial.ttf",
    ]:
        if os.path.exists(name):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                pass
    return ImageFont.load_default()

font_lg = try_font(18)
font_md = try_font(14)
font_sm = try_font(12)
font_xs = try_font(11)

def box(x, y, w, h, label, sublabel=None, color=BOX_BORDER):
    r = 10
    draw.rounded_rectangle([x, y, x+w, y+h], radius=r, fill=BOX_BG, outline=color, width=2)
    if sublabel:
        draw.text((x + w//2, y + h//2 - 10), label, fill=TEXT_MAIN, font=font_md, anchor="mm")
        draw.text((x + w//2, y + h//2 + 10), sublabel, fill=TEXT_DIM, font=font_xs, anchor="mm")
    else:
        draw.text((x + w//2, y + h//2), label, fill=TEXT_MAIN, font=font_md, anchor="mm")

def arrow_down(x, y1, y2):
    draw.line([(x, y1), (x, y2 - 8)], fill=ARROW, width=2)
    draw.polygon([(x-6, y2-8), (x+6, y2-8), (x, y2)], fill=ARROW)

def arrow_right(x1, x2, y):
    draw.line([(x1, y), (x2 - 8, y)], fill=ARROW, width=2)
    draw.polygon([(x2-8, y-6), (x2-8, y+6), (x2, y)], fill=ARROW)

# ── Title ────────────────────────────────────────────────────────────────────
draw.text((W//2, 36), "Gradient Descent — Pipeline Architecture", fill=TEXT_MAIN, font=try_font(22), anchor="mm")
draw.text((W//2, 62), "Free · Automated · Open Source  ·  Gmail · GitHub Pages · Telegram · X/Twitter", fill=TEXT_DIM, font=font_sm, anchor="mm")

# ── Top node: cron ───────────────────────────────────────────────────────────
cron_w, cron_h = 300, 56
cron_x = W//2 - cron_w//2
cron_y = 90
box(cron_x, cron_y, cron_w, cron_h, "GitHub Actions cron", "3:55 AM UTC · daily", color=ACCENT)

# ── Arrow down ───────────────────────────────────────────────────────────────
arrow_down(W//2, cron_y + cron_h, cron_y + cron_h + 36)

# ── RSS fetch ────────────────────────────────────────────────────────────────
fetch_w, fetch_h = 340, 56
fetch_x = W//2 - fetch_w//2
fetch_y = cron_y + cron_h + 36
box(fetch_x, fetch_y, fetch_w, fetch_h, "70+ RSS Feeds", "concurrent · 8s timeout · keyword scoring")

arrow_down(W//2, fetch_y + fetch_h, fetch_y + fetch_h + 36)

# ── Groq ─────────────────────────────────────────────────────────────────────
groq_w, groq_h = 340, 56
groq_x = W//2 - groq_w//2
groq_y = fetch_y + fetch_h + 36
box(groq_x, groq_y, groq_w, groq_h, "Groq API  ·  1 call", "llama-3.3-70b-versatile · ~10s", color=ACCENT)

arrow_down(W//2, groq_y + groq_h, groq_y + groq_h + 36)

# ── Distribute label ─────────────────────────────────────────────────────────
dist_y = groq_y + groq_h + 36
draw.text((W//2, dist_y + 14), "Distribute simultaneously", fill=TEXT_DIM, font=font_sm, anchor="mm")

# ── Fan-out line ─────────────────────────────────────────────────────────────
fan_y = dist_y + 36
channels = [
    ("Gmail\nSMTP",       280),
    ("GitHub\nPages",     560),
    ("Telegram\nBot",     840),
    ("X / Twitter\nAPI v2", 1120),
]
chan_w, chan_h = 180, 64
for label, cx in channels:
    box_x = cx - chan_w // 2
    # vertical line from mid to box top
    draw.line([(W//2, fan_y - 22), (W//2, fan_y - 22)], fill=ARROW, width=2)
    draw.line([(cx, fan_y - 22), (cx, fan_y)], fill=ARROW, width=2)
    box(box_x, fan_y, chan_w, chan_h, label.replace("\n", " "), None)

# horizontal line connecting all channel tops
leftmost_cx  = channels[0][1]
rightmost_cx = channels[-1][1]
draw.line([(leftmost_cx, fan_y - 22), (rightmost_cx, fan_y - 22)], fill=ARROW, width=2)
# stem from groq down to horizontal line
draw.line([(W//2, groq_y + groq_h + 36 + 28), (W//2, fan_y - 22)], fill=ARROW, width=2)
# arrowheads pointing down into each box
for _, cx in channels:
    draw.polygon([(cx-5, fan_y-6), (cx+5, fan_y-6), (cx, fan_y)], fill=ARROW)

# ── Substack note ────────────────────────────────────────────────────────────
sub_y = fan_y + chan_h + 28
draw.text((W//2, sub_y),
    "Substack imports via RSS  ·  feed.xml committed to GitHub Pages after every run",
    fill=TEXT_DIM, font=font_sm, anchor="mm")

# ── Dedup note ───────────────────────────────────────────────────────────────
draw.text((W//2, sub_y + 26),
    "3-day URL deduplication  ·  per-feed quality scoring  ·  seen_urls.json + feed_scores.json",
    fill=TEXT_DIM, font=font_sm, anchor="mm")

# ── Corner badge ─────────────────────────────────────────────────────────────
badge_x, badge_y = W - 260, H - 70
draw.rounded_rectangle([badge_x, badge_y, badge_x+220, badge_y+44],
    radius=8, fill="#0f3d30", outline=ACCENT, width=2)
draw.text((badge_x + 110, badge_y + 14), "~15 seconds  ·  $0/month",
    fill=ACCENT, font=font_md, anchor="mm")
draw.text((badge_x + 110, badge_y + 30), "open source · github.com/PierDeRogatis/ai-newsletter",
    fill=TEXT_DIM, font=font_xs, anchor="mm")

out_path = "docs/ph-image-3-architecture.png"
img.save(out_path, "PNG")
print(f"Saved: {out_path}  ({W}×{H}px)")
