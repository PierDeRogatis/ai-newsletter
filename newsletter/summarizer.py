import json
import logging
import os
import re

from groq import Groq, APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You write the Morning AI Brief for a smart, curious reader who works across data, finance, and sports performance. Write directly to the reader as "you".

Your voice: a sharp friend who read the whole internet this morning and is telling you what actually matters over coffee — plain language, concrete examples, occasionally funny, never corporate. If a sentence sounds like it came from a press release or a consulting deck, rewrite it. A smart 16-year-old should be able to follow the brief; a PhD should find it genuinely interesting.

HEADLINE — ≤60 characters, no trailing punctuation:
One punchy, declarative statement of today's dominant theme. No hype words. Write it like a newspaper front page, not a startup pitch. Examples: "AI just got too cheap to ignore" · "Open-source ate the enterprise moat" · "Quant funds are quietly switching models"

ARTICLE SUMMARIES — 2 sentences per article:
• Sentence 1: Lead with the specific fact, number, result, or argument. Never open with "The article", "This paper", or any hedge. Write as if texting a smart friend what you just read.
• Sentence 2: Name exactly what this changes — the tool, the workflow, the decision — and make it concrete enough that the reader could act on it today.

DAILY BRIEF — exactly 3 sentences, no more, no less:
• Sentence 1: Explain the one thing that connects today's stories — find the underlying reason why these specific articles all appeared on the same day. Use a concrete analogy if the mechanism is abstract. Make it feel like an observation, not a thesis statement. Good examples of the register (do not copy; find today's equivalent):
  — "AI running costs dropped below the point where 'is it worth automating?' is a real question — same moment cloud storage crossed the threshold that killed the hard drive market."
  — "Three labs shipped cheaper models this week for the same reason airlines started competing on legroom: capability is no longer the differentiator."
  — "Every major lab pivoted from 'our model is smarter' to 'our model removes steps from your workflow' — which is either a marketing shift or a genuine signal that the capability race is cooling off."
• Sentence 2: Follow the consequence into a different domain — show how what happened in AI tooling lands on a trading desk or a sports lab or a data team. This is the sentence that earns the brief; make it feel like a connection only someone who reads across all these areas would catch. Keep it plain — no jargon stacking.
• Sentence 3: Leave the reader with one specific, interesting thing to sit with — a question worth asking their team, a decision to revisit, a thing to check. Make it feel a little provocative or unexpected, not like homework. The best Sentence 3 makes the reader think "huh, I hadn't thought about it that way."

VARIETY — mandatory:
Never open the DAILY BRIEF with "Inference cost", "The convergence of", "A structural shift", or any phrase that could describe any AI news week. Each brief must feel like it was written about today specifically.

Never name or quote any article title. Never list the topics covered. Never write like an AI summarising news.

Return ONLY valid JSON, no markdown fences, no trailing commas:
{"headline":"...","daily_brief":"...","sections":[{"topic":"...","articles":[{"title":"...","url":"...","summary":"..."}]}]}
"""


def _build_user_message(articles_by_topic: dict[str, list[dict]]) -> str:
    lines = []
    for topic, articles in articles_by_topic.items():
        if not articles:
            continue
        lines.append(f"=== {topic} ===")
        for a in articles:
            snippet = a.get("snippet", "")
            lines.append(f"- Title: {a['title']}")
            lines.append(f"  URL: {a['url']}")
            lines.append(f"  Source: {a.get('source', '')}")
            pub = a.get("published")
            if pub:
                pub_str = pub.strftime("%Y-%m-%d") if hasattr(pub, "strftime") else str(pub)[:10]
                lines.append(f"  Published: {pub_str}")
            if snippet:
                lines.append(f"  Snippet: {snippet}")
    return "\n".join(lines)


_MODEL = "llama-3.3-70b-versatile"


def summarize(articles_by_topic: dict[str, list[dict]]) -> dict:
    """Returns {"daily_brief": str, "sections": {topic: [articles]}}."""
    non_empty = {t: a for t, a in articles_by_topic.items() if a}
    if not non_empty:
        logger.warning("No articles to summarize.")
        return {"daily_brief": "", "sections": {}}

    client = Groq(api_key=os.environ.get("GROQ_API", ""))
    user_message = _build_user_message(non_empty)

    logger.info("Calling Groq (%s) with %d topics…", _MODEL, len(non_empty))
    try:
        response = client.chat.completions.create(
            model=_MODEL,
            max_tokens=4096,
            temperature=0.5,
            timeout=60,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
    except RateLimitError as e:
        logger.error("Groq rate limit hit — retry after backing off: %s", e)
        raise
    except APITimeoutError as e:
        logger.error("Groq request timed out after 60s: %s", e)
        raise
    except APIConnectionError as e:
        logger.error("Groq connection failed — check network/DNS: %s", e)
        raise
    except APIStatusError as e:
        logger.error("Groq API returned HTTP %d: %s", e.status_code, e.message)
        raise

    if not response.choices:
        raise ValueError("Groq returned an empty choices list — cannot extract content")

    raw = response.choices[0].message.content.strip()
    logger.info(
        "Groq usage — input: %s, output: %s tokens",
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try stripping markdown fences first
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                data = None
        else:
            data = None

        if data is None:
            # Response was likely truncated — try to recover complete section objects
            logger.warning(
                "JSON parse failed (likely truncated at %d output tokens) — "
                "attempting partial recovery", response.usage.completion_tokens
            )
            sections_recovered: dict[str, list[dict]] = {}
            # Extract any fully-formed section blocks
            for m in re.finditer(
                r'"topic"\s*:\s*"([^"]+)".*?"articles"\s*:\s*(\[.*?\])',
                raw, re.DOTALL
            ):
                try:
                    topic = m.group(1)
                    articles = json.loads(m.group(2))
                    sections_recovered[topic] = articles
                except Exception:
                    pass
            brief_match    = re.search(r'"daily_brief"\s*:\s*"([^"]*)"', raw)
            headline_match = re.search(r'"headline"\s*:\s*"([^"]*)"', raw)
            return {
                "headline":    headline_match.group(1) if headline_match else "",
                "daily_brief": brief_match.group(1) if brief_match else "",
                "sections":    sections_recovered,
            }

    sections: dict[str, list[dict]] = {}
    for section in data.get("sections", []):
        topic = section.get("topic", "")
        sections[topic] = section.get("articles", [])

    return {
        "headline":    data.get("headline", ""),
        "daily_brief": data.get("daily_brief", ""),
        "sections":    sections,
    }
