"""
seo_agent.py
============
Generates Hindi/India-flavoured YouTube SEO metadata with Gemini.
Title is Hindi+English mixed (better discoverability for the Indian audience).
"""

import json
import re

from agents.gemini_client import generate_json


_PROMPT_TEMPLATE = """
Generate YouTube SEO metadata for this Hindi YouTube Short about today's date
in Indian history.

Topic:  {topic}
Script: {script}

RULES:
- title:        max 80 chars. Mix Hindi (Devanagari) with English keywords like
                "India", "History", "Today", "Itihaas". Start with the date in
                Devanagari (e.g. "26 अप्रैल"). Add 1-2 emojis.
- description:  140-200 words, Hindi-leaning but Hinglish OK. End with the line
                "रोज़ इतिहास की एक नई कहानी के लिए चैनल को सब्सक्राइब करें!"
                Then a blank line, then 6-10 hashtags including:
                #aajkaitihaas #todayinhistory #indianhistory #hindishorts #shorts
- tags:         18 SEO-relevant tags mixing Hindi and English keywords.

CONTENT GUARDRAILS:
- Title and description must be accurate, not misleading or clickbait.
- Be respectful of religious / cultural sentiments.
- Be politically neutral.
- No fabricated stats; stick to historically established facts.

Return ONLY valid JSON:
{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2"]
}}
""".strip()


def _extract_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in SEO response:\n{raw[:500]}")
    return json.loads(match.group(0))


class SEOAgent:
    def generate_seo(self, topic: str, script: str) -> dict:
        raw = generate_json(
            prompt=_PROMPT_TEMPLATE.format(topic=topic, script=script),
            system_instruction="You are a precise YouTube metadata writer. Return valid JSON only.",
            max_tokens=1200,
        )
        data = _extract_json(raw)

        # Always-present India/Hindi tags for discoverability
        baseline = [
            "Shorts", "Hindi Shorts", "India History", "Aaj Ka Itihaas",
            "Today in History", "इतिहास", "हिंदी", "भारत",
        ]
        existing = {tag.lower() for tag in data.get("tags", [])}
        for tag in baseline:
            if tag.lower() not in existing:
                data.setdefault("tags", []).append(tag)
        return data
