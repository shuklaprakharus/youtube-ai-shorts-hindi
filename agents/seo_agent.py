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
Generate YouTube SEO metadata for this Hindi YouTube Short.
{framing}

Topic:  {topic}
Script: {script}

RULES:
{rules}
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


_MODE_TEXT = {
    "history": (
        "It is about today's date in Indian history.",
        """- title:        max 80 chars. Mix Hindi (Devanagari) with English keywords like
                "India", "History", "Today", "Itihaas". Start with the date in
                Devanagari (e.g. "26 अप्रैल"). Add 1-2 emojis.
- description:  140-200 words, Hindi-leaning but Hinglish OK. End with the line
                "रोज़ इतिहास की एक नई कहानी के लिए चैनल को सब्सक्राइब करें!"
                Then a blank line, then 6-10 hashtags including:
                #aajkaitihaas #todayinhistory #indianhistory #hindishorts #shorts""",
    ),
    "trending": (
        "It explains a topic connected to what Indian viewers are watching most today.",
        """- title:        max 80 chars. Curiosity-led Hindi (Devanagari) with 1-2 English
                search keywords. Add 1-2 emojis. Never name another creator's video,
                film, actor, song or channel.
- description:  120-180 words, Hindi-leaning but Hinglish OK. Include the line
                "स्रोत: Wikipedia" and end with
                "रोज़ एक नई रोचक कहानी के लिए चैनल को सब्सक्राइब करें!"
                Then a blank line, then 6-10 hashtags including
                #hindishorts #shorts #hindifacts""",
    ),
}

CHANNEL_TAGS = {
    "history":  "#Shorts #AajKaItihaas #TodayInHistory #IndianHistory #HindiShorts",
    "trending": "#Shorts #HindiShorts #HindiFacts #AajKaItihaas",
}


class SEOAgent:
    def generate_seo(self, topic: str, script: str) -> dict:
        try:
            mode = json.loads(topic).get("mode", "history")
        except (json.JSONDecodeError, AttributeError):
            mode = "history"
        framing, rules = _MODE_TEXT.get(mode, _MODE_TEXT["history"])
        raw = generate_json(
            prompt=_PROMPT_TEMPLATE.format(topic=topic, script=script, framing=framing, rules=rules),
            system_instruction="You are a precise YouTube metadata writer. Return valid JSON only.",
            max_tokens=1200,
        )
        data = _extract_json(raw)
        data["channel_tags"] = CHANNEL_TAGS.get(mode, CHANNEL_TAGS["history"])

        # Always-present India/Hindi tags for discoverability
        baseline = [
            "Shorts", "Hindi Shorts", "Aaj Ka Itihaas", "हिंदी", "भारत",
        ] + ([
            "India History", "Today in History", "इतिहास",
        ] if mode == "history" else ["Hindi Facts", "AI Generated"]) + [
        ]
        existing = {tag.lower() for tag in data.get("tags", [])}
        for tag in baseline:
            if tag.lower() not in existing:
                data.setdefault("tags", []).append(tag)
        return data
