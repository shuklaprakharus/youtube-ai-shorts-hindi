"""
script_agent.py
===============
Generates a Hindi YouTube Shorts script using Groq.

KEY CHANGES vs previous version:
1. Stricter "use the verified source" instruction — don't invent facts beyond
   what topic_agent gave us.
2. Image prompts now avoid trying to render specific named people (which
   Pollinations.ai cannot do well). Instead they describe CONTEXTUAL SCENES:
   stadiums, vintage objects, parades, locations, period-appropriate clothing,
   newspaper headlines, etc. — things image generators handle reliably.
"""

import json
import re
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL


_PROMPT_TEMPLATE = """
Write a YouTube Shorts script in HINDI (Devanagari script) for the topic:
"{topic}"

CRITICAL — FACT GROUNDING:
- The topic above includes a "verified_source" quote pulled directly from
  Wikipedia. ONLY write facts that are consistent with that source.
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

══════════════════════════════════════════════════════════════════════════════
CRITICAL IMAGE PROMPT RULES — these matter for production quality:
══════════════════════════════════════════════════════════════════════════════

❌ DO NOT try to depict specific real living/historical people by name.
   AI image generators cannot accurately render named individuals (Sachin
   Tendulkar, Modi, Bhagat Singh, Gandhi, etc.). Asking for "Sachin Tendulkar
   batting" will produce a generic cricketer that looks NOTHING like him.

✅ INSTEAD, describe the SCENE / CONTEXT / OBJECTS around the person:
   - For a cricketer's birthday → "vintage cricket bat and ball on green
     turf, Mumbai stadium in golden hour light, packed crowd in background"
   - For a freedom fighter's anniversary → "1940s Indian rally with
     thousands holding tricolor flags, sepia-toned vintage photograph"
   - For a scientific milestone → "telescope pointed at night sky over
     Indian Space Research building, control room illuminated"
   - For a battle/war event → "ancient Indian fort at sunset, sandstone
     walls, warriors' silhouettes on the ramparts"
   - For a festival → "diyas glowing in a temple courtyard at twilight,
     marigold garlands, traditional Indian architecture"
   - For a cultural figure (writer/musician) → "vintage typewriter and
     handwritten manuscript on wooden desk, soft window light"

✅ MAKE PROMPTS SPECIFIC. Mention era (1940s, 1980s, ancient), location
   (Indian temple, Mumbai stadium, Delhi fort, Himalayan mountains), mood
   (golden hour, dramatic stormy, festive), and 2-3 visual details
   (clothing era, objects, colors, lighting).

✅ EVERY image prompt should feel cinematic — like a frame from a movie
   trailer about that event, not a literal portrait.

══════════════════════════════════════════════════════════════════════════════

OUTPUT FORMAT — CRITICAL:
- Respond with ONLY a valid JSON object. No markdown fences, no preamble.
- Use double quotes everywhere. No trailing commas.

Return ONLY valid JSON in exactly this shape:
{{
  "slides": [
    {{
      "type":         "hook",
      "icon":         "🇮🇳",
      "main_text":    "MAX 4 WORD HINDI HOOK",
      "sub_text":     "Short Hindi sentence under 10 words।",
      "spoken_text":  "Hindi narration for this slide।",
      "image_prompt": "specific cinematic SCENE description in English, NO named people"
    }},
    {{
      "type":         "content",
      "icon":         "⚔️",
      "main_text":    "MAX 4 WORD HINDI",
      "sub_text":     "Short Hindi sentence under 10 words।",
      "spoken_text":  "Hindi narration for this slide।",
      "image_prompt": "specific cinematic SCENE description in English, NO named people"
    }},
    {{
      "type":         "content",
      "icon":         "🌟",
      "main_text":    "MAX 4 WORD HINDI",
      "sub_text":     "Short Hindi sentence under 10 words।",
      "spoken_text":  "Hindi narration for this slide।",
      "image_prompt": "specific cinematic SCENE description in English, NO named people"
    }},
    {{
      "type":         "content",
      "icon":         "✊",
      "main_text":    "MAX 4 WORD HINDI",
      "sub_text":     "Short Hindi sentence under 10 words।",
      "spoken_text":  "Hindi narration for this slide।",
      "image_prompt": "specific cinematic SCENE description in English, NO named people"
    }},
    {{
      "type":         "cta",
      "icon":         "🙌",
      "main_text":    "रोज़ नया इतिहास",
      "sub_text":     "हर दिन एक नई कहानी।",
      "spoken_text":  "अगर पसंद आया तो चैनल को सब्सक्राइब ज़रूर करना। कल फिर मिलेंगे एक नई कहानी के साथ।",
      "image_prompt": "warm sunrise over the Indian tricolor flag waving against blue sky, cinematic, 9:16 vertical"
    }}
  ]
}}
""".strip()


def _extract_json(raw: str) -> dict:
    if not raw or not raw.strip():
        raise ValueError("Empty response from LLM")

    cleaned = raw.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found. Raw output:\n{raw[:500]}")
    cleaned = match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as strict_err:
        print(f"⚠️  Strict JSON parse failed: {strict_err}. Trying json-repair...")

    try:
        from json_repair import repair_json
    except ImportError:
        raise ValueError(
            "JSON parse failed and json-repair is not installed.\n"
            f"Raw output:\n{raw[:1000]}"
        )

    repaired = repair_json(cleaned)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as repair_err:
        raise ValueError(
            f"JSON parse failed even after repair: {repair_err}\n"
            f"Raw output:\n{raw[:1000]}"
        )


def _validate_script(data: dict) -> None:
    if "slides" not in data or not isinstance(data["slides"], list):
        raise ValueError(f"Missing or invalid 'slides' array: {data}")
    if len(data["slides"]) < 3:
        raise ValueError(f"Too few slides ({len(data['slides'])}): {data}")
    required_keys = {"type", "icon", "main_text", "sub_text", "spoken_text", "image_prompt"}
    for i, slide in enumerate(data["slides"]):
        missing = required_keys - set(slide.keys())
        if missing:
            raise ValueError(f"Slide {i} missing keys {missing}: {slide}")


class ScriptAgent:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)

    def generate_script(self, topic: str, max_attempts: int = 3) -> dict:
        prompt = _PROMPT_TEMPLATE.format(topic=topic)
        last_error = None
        last_raw = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = self.client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a precise JSON generator who writes warm, "
                                "factually accurate Hindi for short-form video. "
                                "You only use facts provided in the topic source — "
                                "you never invent dates or details."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=2000,
                    temperature=0.7,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content.strip()
                last_raw = raw

                data = _extract_json(raw)
                _validate_script(data)

                data["full_script"] = " ".join(
                    slide["spoken_text"] for slide in data["slides"]
                )
                return data

            except Exception as e:
                last_error = e
                print(f"⚠️  Attempt {attempt}/{max_attempts} failed: {e}")
                if last_raw:
                    print(f"   Raw output (first 500 chars):\n{last_raw[:500]}")

        raise RuntimeError(
            f"ScriptAgent failed after {max_attempts} attempts. "
            f"Last error: {last_error}\n"
            f"Last raw output:\n{(last_raw or '')[:1000]}"
        )
