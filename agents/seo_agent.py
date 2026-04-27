"""
seo_agent.py
============
Generates Hindi/India-flavoured YouTube SEO metadata using Groq.
Title is Hindi+English mixed (better discoverability for the Indian YouTube audience).
"""

import json
import re
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL


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

Return ONLY valid JSON (no markdown, no fences):
{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2", ...]
}}
""".strip()


class SEOAgent:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)

    def generate_seo(self, topic: str, script: str) -> dict:
        prompt = _PROMPT_TEMPLATE.format(topic=topic, script=script)
        response = self.client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system",
                 "content": "You are a precise JSON generator. Respond with ONE valid JSON object only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1000,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in SEO agent response:\n{raw[:300]}")
        raw = match.group(0).strip()

        data = json.loads(raw)

        # Always-present India/Hindi tags for discoverability
        baseline = [
            "Shorts", "Hindi Shorts", "India History", "Aaj Ka Itihaas",
            "Today in History", "इतिहास", "हिंदी", "भारत",
        ]
        existing = {t.lower() for t in data.get("tags", [])}
        for tag in baseline:
            if tag.lower() not in existing:
                data.setdefault("tags", []).append(tag)
        return data
