"""
topic_agent.py
==============
Finds today's most significant date-anniversary or event tied to INDIA,
using Groq (no extra credentials needed — reuses the English pipeline's GROQ_API_KEY).

Returns a structured topic string used by ScriptAgent + SEOAgent.

topics.json is repurposed as a HISTORY file. We keep a record of past picks so
that on dates with multiple notable events, we can pick a different one next year
instead of repeating ourselves.
"""

import json
import re
import datetime
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, TOPICS_FILE


_PROMPT = """You are an Indian historian and content researcher.

Today's date is {date_human} (day {day}, month {month}).

Find the SINGLE most compelling date-anniversary or event tied to INDIA that
falls on this calendar day. A typical Indian YouTube viewer should immediately
recognise it or find it interesting.

Selection priority (highest first):
  1. Major Indian festivals or national observances falling on this date.
     IMPORTANT: only include festivals if you are confident they fall on this
     specific date THIS year. Lunar-calendar festivals shift each year — when
     in doubt, skip them.
  2. Pivotal moments in the Indian freedom struggle / political history
     (e.g. Jallianwala Bagh — 13 April 1919; Quit India — 9 August 1942).
  3. Birth or death anniversaries of widely-known Indians (Bhagat Singh,
     Sachin Tendulkar, Lata Mangeshkar, A.P.J. Abdul Kalam, etc.).
  4. Major Indian scientific / sporting / cultural achievements
     (e.g. Pokhran nuclear test — 11 May 1998; Chandrayaan-3 landing —
     23 August 2023).
  5. Significant world events with strong India connection.

AVOID dates already covered recently. Recent picks: {recent}

Respond with STRICT JSON only — no markdown, no commentary:

{{
  "date_hindi":      "26 अप्रैल",
  "headline_hindi":  "एक 6-10 शब्दों का आकर्षक हुक",
  "main_event_en":   "concise English description of the event, 1-2 sentences",
  "year":            1986,
  "category":        "freedom_struggle | festival | birth_anniversary | death_anniversary | science | sports | culture | political",
  "secondary_events_hindi": ["other notable event same date in Hindi", "another"]
}}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


class TopicAgent:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)

    # ── public API used by main.py ──────────────────────────────────────────
    def get_today_topic(self) -> str:
        """
        Returns a single string topic that ScriptAgent + SEOAgent will use.
        Also stashes the full structured payload on `self.context` so
        downstream agents can access richer info.
        """
        today = datetime.date.today()
        history = self._load()

        recent = self._format_recent(history)

        prompt = _PROMPT.format(
            date_human = today.strftime("%d %B"),
            day        = today.day,
            month      = today.month,
            recent     = recent or "none",
        )

        response = self.client.chat.completions.create(
            model       = GROQ_MODEL,
            messages    = [
                {"role": "system",
                 "content": "You are a precise JSON generator. Respond with ONE valid JSON object only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens     = 600,
            temperature    = 0.3,
            response_format = {"type": "json_object"},
        )
        raw = _strip_fences(response.choices[0].message.content)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"TopicAgent — invalid JSON from Groq:\n{raw}") from e

        # Stash the full context for ScriptAgent / SEOAgent
        self.context = payload
        self.context["date_iso"] = today.isoformat()

        # Append to history file
        history.setdefault("history", []).append({
            "date":      today.isoformat(),
            "headline":  payload.get("headline_hindi", ""),
            "event":     payload.get("main_event_en", ""),
            "year":      payload.get("year"),
            "category":  payload.get("category"),
        })
        # Keep last 365 entries
        history["history"] = history["history"][-365:]
        self._save(history)

        # Return a single rich string — ScriptAgent reads it directly
        topic_str = (
            f"{payload['date_hindi']} — {payload['headline_hindi']} "
            f"(English: {payload['main_event_en']}, "
            f"year: {payload.get('year', 'n/a')}, category: {payload.get('category', 'general')})"
        )
        return topic_str

    # ── helpers ─────────────────────────────────────────────────────────────
    def _format_recent(self, history: dict) -> str:
        items = history.get("history", [])[-30:]
        if not items:
            return ""
        return "; ".join(
            f"{h.get('date', '?')}: {h.get('event', '')[:80]}" for h in items
        )

    def _load(self) -> dict:
        try:
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"history": []}

    def _save(self, data: dict):
        with open(TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
