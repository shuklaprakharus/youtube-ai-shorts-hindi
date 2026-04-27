"""
topic_agent.py
==============
Finds today's most significant date-anniversary or event tied to INDIA.

KEY CHANGE: Instead of asking the LLM "what happened on this date?" (which
hallucinates badly for specific calendar dates), we fetch the actual list of
events from Wikipedia's free "On this day" API, then ask the LLM to PICK the
most India-relevant one and write the headline.

This prevents the model from inventing dates like "Sachin Tendulkar's birthday
is today" when it's actually 3 days off.
"""

import json
import re
import datetime
import requests
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, TOPICS_FILE


# ─── Wikipedia "On this day" — free, no API key, factually accurate ──────────

def _fetch_wikipedia_on_this_day(target_date: datetime.date) -> dict:
    """
    Wikipedia's REST API returns curated lists of events, births, and deaths
    for a given calendar day. This is what powers the "On This Day" feature
    on Wikipedia's main page — meaning it's been editorially vetted by editors
    over the years.

    Endpoint:  https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/all/MM/DD
    """
    url = (
        "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/all/"
        f"{target_date.month:02d}/{target_date.day:02d}"
    )
    headers = {"User-Agent": "AajKaItihaas/1.0 (educational content)"}
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def _format_events_for_prompt(wiki_data: dict, max_per_section: int = 25) -> str:
    """
    Wikipedia returns sections: events, births, deaths, holidays, selected.
    We flatten them into a compact, prompt-friendly list for the LLM.
    """
    sections = ["events", "births", "deaths", "holidays", "selected"]
    lines: list[str] = []

    for section in sections:
        items = wiki_data.get(section, [])
        if not items:
            continue
        lines.append(f"\n--- {section.upper()} ---")
        for item in items[:max_per_section]:
            year = item.get("year", "")
            text = item.get("text", "").strip()
            # Mark items that mention India/Indian/Hindi for the LLM's convenience
            india_marker = " [INDIA]" if any(
                kw in text.lower()
                for kw in ["india", "indian", "hindi", "bharat", "delhi",
                           "mumbai", "bengal", "punjab", "tamil", "gandhi",
                           "nehru", "ambedkar", "tagore", "bose", "patel"]
            ) else ""
            if year:
                lines.append(f"  • {year}: {text}{india_marker}")
            else:
                lines.append(f"  • {text}{india_marker}")

    return "\n".join(lines) if lines else "(no events found)"


# ─── LLM picker ──────────────────────────────────────────────────────────────

_PICKER_PROMPT = """You are an Indian history content editor.

Below is the FACTUAL list of events that historically happened on {date_human}
(month {month}, day {day}), retrieved from Wikipedia. ONLY pick from this list.
Do NOT add events that are not in the list. Do NOT change dates. Do NOT
fabricate.

WIKIPEDIA EVENTS for this date:
{wiki_events}

ALSO AVOID these recently-covered events (don't repeat):
{recent}

YOUR JOB:
1. Scan the list and pick the SINGLE most compelling event for an Indian
   YouTube audience. Strong preference for items marked [INDIA].
2. If multiple India-tagged events exist, pick the one most likely to resonate
   with a typical Indian viewer (well-known names, major historical moments,
   national holidays, sports/scientific milestones).
3. If NO India-tagged events exist, pick the world event with the strongest
   India connection or broad cultural relevance.

Respond with STRICT JSON only — no markdown, no commentary:

{{
  "date_hindi":      "26 अप्रैल",
  "headline_hindi":  "एक 6-10 शब्दों का आकर्षक हिंदी हुक",
  "main_event_en":   "1-2 sentences describing the event in English (taken from the Wikipedia entry, not invented)",
  "year":            1986,
  "category":        "freedom_struggle | festival | birth_anniversary | death_anniversary | science | sports | culture | political",
  "wikipedia_quote": "the EXACT text from the Wikipedia list above that you picked, copy-pasted verbatim",
  "secondary_events_hindi": ["other notable event same date in Hindi", "another"]
}}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


# ─── Hindi date formatting ───────────────────────────────────────────────────

_HINDI_MONTHS = {
    1: "जनवरी", 2: "फ़रवरी", 3: "मार्च", 4: "अप्रैल", 5: "मई", 6: "जून",
    7: "जुलाई", 8: "अगस्त", 9: "सितंबर", 10: "अक्टूबर", 11: "नवंबर", 12: "दिसंबर"
}


def _format_hindi_date(target_date: datetime.date) -> str:
    return f"{target_date.day} {_HINDI_MONTHS[target_date.month]}"


# ─── TopicAgent ──────────────────────────────────────────────────────────────

class TopicAgent:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)

    def get_today_topic(self) -> str:
        today = datetime.date.today()
        history = self._load()

        # 1. Fetch verified events from Wikipedia
        print(f"     · Fetching Wikipedia events for {today.strftime('%d %B')}...")
        try:
            wiki_data = _fetch_wikipedia_on_this_day(today)
            wiki_events_text = _format_events_for_prompt(wiki_data)
        except Exception as e:
            raise RuntimeError(
                f"Wikipedia API request failed: {e}. "
                "Cannot proceed without verified events."
            ) from e

        # 2. Ask LLM to pick the best one
        recent = self._format_recent(history)
        prompt = _PICKER_PROMPT.format(
            date_human  = today.strftime("%d %B"),
            month       = today.month,
            day         = today.day,
            wiki_events = wiki_events_text,
            recent      = recent or "none",
        )

        response = self.client.chat.completions.create(
            model    = GROQ_MODEL,
            messages = [
                {"role": "system",
                 "content": (
                     "You are a precise JSON generator who only uses verified facts "
                     "provided to you. Never invent dates or events. Respond with "
                     "ONE valid JSON object."
                 )},
                {"role": "user", "content": prompt},
            ],
            max_tokens      = 800,
            temperature     = 0.3,
            response_format = {"type": "json_object"},
        )
        raw = _strip_fences(response.choices[0].message.content)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"TopicAgent — invalid JSON from Groq:\n{raw}") from e

        # 3. Validate that the picked event actually appears in Wikipedia data
        # (catches LLM hallucination as a safety net)
        quote = payload.get("wikipedia_quote", "").strip()
        if quote and quote.lower() not in wiki_events_text.lower():
            print(f"     ⚠️  WARNING: LLM-picked quote not found in Wikipedia data!")
            print(f"        Quote: {quote[:100]}")
            print(f"        Falling back to first India-tagged event...")
            # Best-effort fallback: use the first India-tagged event we can find
            india_lines = [
                line for line in wiki_events_text.splitlines()
                if "[INDIA]" in line
            ]
            if india_lines:
                fallback_text = india_lines[0].replace("[INDIA]", "").strip("• ")
                payload["main_event_en"] = fallback_text[:200]
                payload["wikipedia_quote"] = fallback_text

        # Always overwrite the Hindi date with our deterministic format
        payload["date_hindi"] = _format_hindi_date(today)

        # Stash for downstream agents
        self.context = payload
        self.context["date_iso"] = today.isoformat()

        # Append to history
        history.setdefault("history", []).append({
            "date":     today.isoformat(),
            "headline": payload.get("headline_hindi", ""),
            "event":    payload.get("main_event_en", ""),
            "year":     payload.get("year"),
            "category": payload.get("category"),
            "verified": payload.get("wikipedia_quote", "")[:300],
        })
        history["history"] = history["history"][-365:]
        self._save(history)

        topic_str = (
            f"{payload['date_hindi']} — {payload['headline_hindi']} "
            f"(English: {payload['main_event_en']}, "
            f"year: {payload.get('year', 'n/a')}, "
            f"category: {payload.get('category', 'general')}, "
            f"verified_source: \"{payload.get('wikipedia_quote', '')[:200]}\")"
        )
        return topic_str

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
