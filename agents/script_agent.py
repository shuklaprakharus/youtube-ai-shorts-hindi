"""
script_agent.py
===============
Generates a Hindi "today in history" YouTube Shorts script with Gemini.

Two production rules carried over from the original version:
1. Strict "use the verified source" instruction — don't invent facts beyond
   what topic_agent's Wikipedia quote establishes.
2. Image prompts avoid depicting specific named people (which image
   generators cannot render accurately). They describe CONTEXTUAL SCENES
   instead: stadiums, vintage objects, parades, locations, period clothing.
"""

import json
import re

from agents.gemini_client import generate_json


_PROMPT_TEMPLATE = """
Write a YouTube Shorts script in HINDI (Devanagari script) for this topic JSON:
{topic}

CRITICAL — FACT GROUNDING:
- The topic JSON includes a "wikipedia_quote" pulled directly from Wikipedia.
  ONLY write facts consistent with that source and "main_event_en".
- Do NOT invent additional dates, statistics, or details beyond what the
  source establishes.
- If the source doesn't specify a particular detail, don't fabricate it —
  describe the event in general terms instead.

The script tells Indian viewers WHY today's date matters in Indian history.
It will be narrated by a female Hindi voice and shown on screen with
AI-generated cinematic backgrounds.

LANGUAGE RULES:
- Pure conversational Hindi (Devanagari). Simple everyday vocabulary.
- End every Hindi sentence with "।" or "?" or "!" — never an English period.
- No "namaste dosto" cliché unless it genuinely fits the hook.

LENGTH:
- Total spoken Hindi text across all slides ≈ 95-115 words → ~38-45 seconds.

SLIDE STRUCTURE (5 slides total):
- Slide 1 — type "hook":     surprising/curious opener.
- Slides 2-4 — type "content": each tells one fact / detail.
- Slide 5 — type "cta":      a "subscribe daily for itihaas" closer.

PER-SLIDE FIELDS:
  type:         "hook" | "content" | "cta"
  icon:         single relevant emoji (🇮🇳 🕉 ⚔️ 🎉 🌟 ✊ 🚀 🏏 etc.)
  main_text:    SHORT Hindi phrase, MAX 4 WORDS — shown big on screen overlay
  sub_text:     ONE Hindi sentence, max 10 words — shown smaller
  spoken_text:  the EXACT Hindi sentence(s) the narrator says
  image_prompt: see CRITICAL IMAGE PROMPT RULES below

CRITICAL IMAGE PROMPT RULES:
❌ DO NOT try to depict specific real people by name. Image generators cannot
   accurately render named individuals — "Sachin Tendulkar batting" produces a
   generic cricketer that looks nothing like him.
✅ INSTEAD, describe the SCENE / CONTEXT / OBJECTS around the person:
   - cricketer's birthday → "vintage cricket bat and ball on green turf,
     Mumbai stadium in golden hour light, packed crowd in background"
   - freedom fighter's anniversary → "1940s Indian rally with thousands
     holding tricolor flags, sepia-toned vintage photograph"
   - scientific milestone → "telescope pointed at night sky over Indian Space
     Research building, control room illuminated"
   - battle/war event → "ancient Indian fort at sunset, sandstone walls,
     warriors' silhouettes on the ramparts"
   - festival → "diyas glowing in a temple courtyard at twilight, marigold
     garlands, traditional Indian architecture"
   - cultural figure → "vintage typewriter and handwritten manuscript on
     wooden desk, soft window light"
✅ MAKE PROMPTS SPECIFIC: era (1940s, ancient), location (Indian temple,
   Mumbai stadium, Delhi fort), mood (golden hour, dramatic, festive), and
   2-3 visual details (clothing era, objects, colors, lighting).
✅ Every image prompt should feel cinematic — like a frame from a movie
   trailer about that event, not a literal portrait. English only, vertical
   9:16, no text in image.

Return ONLY valid JSON:
{{
  "slides": [
    {{
      "type": "hook",
      "icon": "🇮🇳",
      "main_text": "MAX 4 WORD HINDI HOOK",
      "sub_text": "Short Hindi sentence under 10 words।",
      "spoken_text": "Hindi narration for this slide।",
      "image_prompt": "specific cinematic SCENE description in English, NO named people"
    }}
  ]
}}
""".strip()


def _extract_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found. Raw output:\n{raw[:500]}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        from json_repair import repair_json
        return json.loads(repair_json(match.group(0)))


def _validate_script(data: dict) -> None:
    if not isinstance(data.get("slides"), list) or len(data["slides"]) != 5:
        raise ValueError("Gemini must return exactly 5 slides.")
    required = {"type", "icon", "main_text", "sub_text", "spoken_text", "image_prompt"}
    for i, slide in enumerate(data["slides"]):
        missing = required - set(slide)
        if missing:
            raise ValueError(f"Slide {i + 1} missing keys: {sorted(missing)}")


class ScriptAgent:
    def generate_script(self, topic: str, max_attempts: int = 3) -> dict:
        prompt = _PROMPT_TEMPLATE.format(topic=topic)
        last_error = None
        last_raw = ""

        for attempt in range(1, max_attempts + 1):
            try:
                raw = generate_json(
                    prompt=prompt,
                    system_instruction=(
                        "You are a careful Hindi history scriptwriter. Use only the "
                        "verified facts provided. Return valid JSON only."
                    ),
                    max_tokens=2400,
                )
                last_raw = raw
                data = _extract_json(raw)
                _validate_script(data)
                data["full_script"] = " ".join(
                    slide["spoken_text"].strip() for slide in data["slides"]
                )
                return data
            except Exception as exc:
                last_error = exc
                print(f"⚠️  Script attempt {attempt}/{max_attempts} failed: {exc}")

        raise RuntimeError(
            f"ScriptAgent failed after {max_attempts} attempts: {last_error}\n"
            f"Last raw output:\n{last_raw[:1000]}"
        )
