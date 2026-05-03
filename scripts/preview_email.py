"""Quick header/email preview — runs without any API keys or env vars."""
import sys
import os
import webbrowser
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Minimal stub so config imports don't fail without env vars
os.environ.setdefault("RECIPIENT_EMAIL", "you@example.com")
os.environ.setdefault("SENDER_EMAIL", "sender@example.com")

from newsletter.emailer import build_html

SAMPLE_RESULT = {
    "headline": "AI just got too cheap to keep ignoring",
    "daily_brief": (
        "Running AI used to cost enough that you'd actually think twice — this week, across half"
        " a dozen releases, that changed, a bit like when texting stopped costing per message"
        " and you just started using it for everything."
        " Quant teams that were refreshing strategies weekly can now do it daily for the same"
        " budget; sports labs that ran biomechanics checks once a season are looking at"
        " continuous monitoring — the tools didn't get smarter, they just got cheap enough"
        " that saying no is the weird choice."
        " Somewhere in your workflow there's a task you've been doing by hand for months because"
        " automation felt expensive — that excuse expired this week, and the awkward question"
        " is whether you'll notice before someone on your team does."
    ),
    "sections": {
        "AI & Data Tools": [
            {
                "title": "Llama 4 Scout benchmarks close gap with GPT-4o",
                "url": "https://example.com/1",
                "summary": "Meta's Scout variant hits 87% on MMLU at half the inference cost of its predecessor. Any pipeline using GPT-4o for classification tasks has a cheaper drop-in replacement today.",
                "source": "The Decoder",
            },
            {
                "title": "Hugging Face ships ml-intern: automated preference dataset builder",
                "url": "https://example.com/2",
                "summary": "The tool bootstraps RLHF preference pairs from model outputs with a seed set under 500 examples. Teams without a labelling budget can now fine-tune domain-specific models without it.",
                "source": "Hugging Face Blog",
            },
            {
                "title": "OpenAI workspace agent automates multi-step spreadsheet workflows",
                "url": "https://example.com/3",
                "summary": "The agent handles conditional formatting, pivot tables, and formula chaining across linked sheets via natural language. The same class of tasks that occupies junior analysts for 40% of their week.",
                "source": "Wired",
            },
        ],
        "AI in Finance": [
            {
                "title": "JPMorgan pilots real-time AI risk scoring on derivatives desk",
                "url": "https://example.com/4",
                "summary": "The system re-prices a 10,000-instrument book in under 400ms using a fine-tuned transformer, replacing a batch job that ran every 15 minutes. Latency is now the constraint, not compute.",
                "source": "Bloomberg",
            },
        ],
        "Podcasts": [
            {
                "title": "Dwarkesh Patel — Demis Hassabis on AlphaFold 3 and what comes next",
                "url": "https://example.com/5",
                "summary": "Hassabis argues the next five years in biology will produce more validated drug targets than the previous fifty, driven by structure prediction at scale. The limiting factor shifts to clinical trial throughput, not discovery.",
                "source": "Dwarkesh Podcast",
            },
        ],
    },
}

html = build_html(SAMPLE_RESULT, iso_date="2026-04-24")

with tempfile.NamedTemporaryFile(
    mode="w", suffix=".html", delete=False, prefix="gradient_descent_preview_"
) as f:
    f.write(html)
    path = f.name

print(f"Preview saved: {path}")
webbrowser.open(f"file://{path}")
