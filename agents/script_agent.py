"""
script_agent.py
===============
Generates a Hindi YouTube Shorts script using Groq.

Same slide schema as the English version (hook / content / cta) PLUS one new
field per slide: `image_prompt` — a vivid English prompt used to generate the
AI background image for that slide.
"""

import json
import re
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL


_PROMPT_TEMPLATE = """
Write a YouTube Shorts script in HINDI (Devanagari script) for the topic:
"{topic}"

The script tells Indian viewers WHY today's date is significant in Indian
history / culture. It will be narrated by a female Hindi voice and shown
on screen with AI-generated cinematic backgrounds.

LANGUAGE RULES:
- Pure conversational Hindi (Devanagari). Use simple everyday vocabulary
  a 16-year-old understands. Hinglish loanwords are fine if natural
  ("popular", "famous", "history" etc.).
- End every Hindi sentence with "।" or "?" or "!" — never an English period.
- No "namaste dosto" cliché unless it genuinely fits the hook.

LENGTH:
- Total spoken Hindi text across all slides ≈ 95-115 words.
  This becomes ~38-45 seconds of voiceover at default speed.

SLIDE STRUCTURE (5 slides total):
- Slide 1 — type "hook":     a surprising/curious opener.
- Slides 2-4 — type "content": each tells one fact / detail.
- Slide 5 — type "cta":      a "subscribe daily for itihaas" closer.

PER-SLIDE FIELDS:
  type:         "hook" | "content" | "cta"
  icon:         single relevant emoji (🇮🇳 🕉 ⚔️ 🎉 🌟 ✊ 🚀 etc.)
  main_text:    SHORT Hindi phrase, MAX 4 WORDS — shown big on screen overlay
  sub_text:     ONE Hindi sentence, max 10 words — shown smaller below main_text
  spoken_text:  the EXACT Hindi sentence(s) the narrator says for this slide
  image_prompt: cinematic ENGLISH prompt for AI image generation describing the
                visual scene for this slide. Photorealistic, dramatic lighting,
                4K, 9:16 vertical composition, NO text in image. Avoid named
                living people; describe historical figures generically (e.g.
                "an Indian freedom fighter in white khadi at a podium").

CONTENT GUARDRAILS:
- Stick to widely-accepted historical facts. Don't fabricate dates / numbers.
- Don't make politically charged commentary; report the event neutrally.
- Don't include offensive or discriminatory language.
- For religious festivals, be respectful and inclusive.
- For independence-era events, present them factually without jingoism.

OUTPUT FORMAT — CRITICAL:
- Respond with ONLY a valid JSON object. No markdown fences, no preamble.
- Use double quotes for all keys and string values.
- Escape any double quotes inside string values.
- No trailing commas.

Return ONLY valid JSON in exactly this shape:
{{
  "slides": [
    {{
      "type":         "hook",
      "icon":         "🇮🇳",
      "main_text":    "MAX 4 WORD HINDI HOOK",
      "sub_text":     "Short Hindi sentence under 10 words।",
      "spoken_text":  "The exact Hindi sentence(s) narrator speaks for this slide।",
      "image_prompt": "cinematic English image description for this scene"
    }},
    {{
      "type":         "content",
      "icon":         "⚔️",
      "main_text":    "MAX 4 WORD HINDI",
      "sub_text":     "Short Hindi sentence under 10 words।",
      "spoken_text":  "Hindi narration for this slide।",
      "image_prompt": "cinematic English image description"
    }},
    {{
      "type":         "content",
      "icon":         "🌟",
      "main_text":    "MAX 4 WORD HINDI",
      "sub_text":     "Short Hindi sentence under 10 words।",
      "spoken_text":  "Hindi narration for this slide।",
      "image_prompt": "cinematic English image description"
    }},
    {{
      "type":         "content",
      "icon":         "✊",
      "main_text":    "MAX 4 WORD HINDI",
      "sub_text":     "Short Hindi sentence under 10 words।",
      "spoken_text":  "Hindi narration for this slide।",
      "image_prompt": "cinematic English image description"
    }},
    {{
      "type":         "cta",
      "icon":         "🙌",
      "main_text":    "रोज़ नया इतिहास",
      "sub_text":     "हर दिन एक नई कहानी।",
      "spoken_text":  "अगर पसंद आया तो चैनल को सब्सक्राइब ज़रूर करना। कल फिर मिलेंगे एक नई कहानी के साथ।",
      "image_prompt": "warm sunrise over the Indian tricolor flag, cinematic, 9:16"
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
        raise ValueError(f"No JSON object found in response. Raw output:\n{raw[:500]}")
    cleaned = match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as strict_err:
        print(f"⚠️  Strict JSON parse failed: {strict_err}. Trying json-repair...")

    try:
        from json_repair import repair_json
    except ImportError:
        raise ValueError(
            "JSON parse failed and json-repair is not installed. "
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
                                "You are a precise JSON generator who writes "
                                "warm, accurate Hindi for short-form video. "
                                "Always respond with ONE valid JSON object."
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
