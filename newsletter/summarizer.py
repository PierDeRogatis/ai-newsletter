"""Two-stage Groq summarisation: one call per topic, then one call for headline + brief."""
import json
import logging
import os
import re

from groq import Groq, APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from newsletter.config import GROQ_MODEL, GROQ_MAX_OUTPUT_TOKENS, GROQ_TEMPERATURE, GROQ_API_TIMEOUT

logger = logging.getLogger(__name__)

_TOPIC_SYSTEM_PROMPT = """\
Write a 2-sentence summary for each article.
• Sentence 1: the specific fact, number, result, or argument. Never open with "The article", "This paper", or any hedge. Write as if texting a smart friend what you just read.
• Sentence 2: name exactly what this changes — the tool, the workflow, the decision — concrete enough that the reader could act on it today.

Return ONLY valid JSON, no markdown fences, no trailing commas:
{"articles":[{"title":"...","url":"...","summary":"..."}]}

Include every article. Do not skip or merge any.
"""

_BRIEF_SYSTEM_PROMPT = """\
You write the Morning AI Brief for a smart, curious reader who works across data, finance, and sports performance. Write directly to the reader as "you".

Your voice: a sharp friend who read the whole internet this morning — plain language, concrete examples, occasionally funny, never corporate. A smart 16-year-old should follow it; a PhD should find it genuinely interesting.

HEADLINE — ≤60 characters, no trailing punctuation:
One punchy declarative statement of today's dominant theme. No hype words. Newspaper front page, not a startup pitch.

DAILY BRIEF — exactly 3 sentences, no more, no less:
• Sentence 1: the one thing connecting today's stories. Use a concrete analogy if the mechanism is abstract.
• Sentence 2: follow the consequence into a different domain (trading desk, sports lab, data team). The sentence that earns the brief — a connection only a cross-domain reader would catch.
• Sentence 3: one specific thing worth sitting with — a question, a decision to revisit. A little provocative.

VARIETY — mandatory:
Never open the brief with "Inference cost", "The convergence of", "A structural shift", or any phrase that could describe any AI news week.
Never name or quote article titles. Never list the topics. Never write like an AI summarising news.

Return ONLY valid JSON, no markdown fences, no trailing commas:
{"headline":"...","daily_brief":"..."}
"""


def _build_topic_message(articles: list[dict]) -> str:
    lines = []
    for a in articles:
        lines.append(f"- Title: {a['title']}")
        lines.append(f"  URL: {a['url']}")
        if a.get("snippet"):
            lines.append(f"  Snippet: {a['snippet']}")
    return "\n".join(lines)


def _build_brief_message(sections: dict[str, list[dict]]) -> str:
    lines = ["Today's summarised articles by topic:"]
    for topic, articles in sections.items():
        lines.append(f"\n=== {topic} ===")
        for a in articles:
            lines.append(f"• {a['title']}: {a.get('summary', '')}")
    return "\n".join(lines)


def _parse_json(raw: str) -> dict | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return None


def _call_groq(client, system_prompt: str, user_message: str) -> str:
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=GROQ_MAX_OUTPUT_TOKENS,
        temperature=GROQ_TEMPERATURE,
        timeout=GROQ_API_TIMEOUT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    if not response.choices:
        raise ValueError("Groq returned an empty choices list — cannot extract content")
    raw = response.choices[0].message.content.strip()
    finish_reason = response.choices[0].finish_reason
    logger.info(
        "Groq usage — input: %s, output: %s tokens, finish_reason: %s",
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        finish_reason,
    )
    if finish_reason != "stop":
        logger.warning("Groq finish_reason=%s — response may be truncated", finish_reason)
    return raw


def _summarize_topic(client, topic: str, articles: list[dict]) -> list[dict]:
    """Summarise one topic's articles. API errors propagate; parse failures fall back."""
    raw = _call_groq(client, _TOPIC_SYSTEM_PROMPT, _build_topic_message(articles))
    data = _parse_json(raw)
    if data and isinstance(data.get("articles"), list):
        result = data["articles"]
        if len(result) == len(articles):
            return result
        logger.warning("Topic '%s': gave %d articles, got back %d", topic, len(articles), len(result))
        by_url = {a.get("url", ""): a for a in result}
        return [
            by_url.get(orig["url"], {"title": orig["title"], "url": orig["url"], "summary": ""})
            for orig in articles
        ]
    logger.warning("Topic '%s': JSON parse failed — using empty summaries", topic)
    return [{"title": a["title"], "url": a["url"], "summary": ""} for a in articles]


def _generate_brief(client, sections: dict[str, list[dict]]) -> tuple[str, str]:
    """Generate headline + daily_brief from already-summarised sections."""
    raw = ""
    try:
        raw = _call_groq(client, _BRIEF_SYSTEM_PROMPT, _build_brief_message(sections))
        data = _parse_json(raw)
        if data:
            return data.get("headline", ""), data.get("daily_brief", "")
    except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError):
        raise
    except Exception as e:
        logger.error("Brief generation failed: %s", e)
    if raw:
        h = re.search(r'"headline"\s*:\s*"([^"]*)"', raw)
        b = re.search(r'"daily_brief"\s*:\s*"([^"]*)"', raw)
        return (h.group(1) if h else ""), (b.group(1) if b else "")
    return "", ""


def summarize(articles_by_topic: dict[str, list[dict]]) -> dict:
    """Summarise all topics independently, then generate headline + daily_brief."""
    non_empty = {t: a for t, a in articles_by_topic.items() if a}
    if not non_empty:
        logger.warning("No articles to summarize.")
        return {"daily_brief": "", "sections": {}}

    client = Groq(api_key=os.environ.get("GROQ_API", ""))
    n_articles = sum(len(v) for v in non_empty.values())
    logger.info("Calling Groq (%s) — %d topics, %d articles", GROQ_MODEL, len(non_empty), n_articles)

    sections: dict[str, list[dict]] = {}
    for topic, articles in non_empty.items():
        logger.info("  summarising '%s' (%d articles)…", topic, len(articles))
        try:
            sections[topic] = _summarize_topic(client, topic, articles)
        except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError):
            raise

    headline, daily_brief = _generate_brief(client, sections)
    logger.info(
        "Groq complete: %d topics, %d articles | headline: %r",
        len(sections), sum(len(v) for v in sections.values()), headline,
    )

    return {"headline": headline, "daily_brief": daily_brief, "sections": sections}
