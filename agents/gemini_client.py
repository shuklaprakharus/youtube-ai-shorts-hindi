"""
Small Gemini wrapper used by the content agents.

The agents ask for strict JSON. This helper keeps the provider-specific code in
one place and validates that a configured API key exists before a workflow run
spends time creating media.
"""

import time

from google import genai
from google.genai import errors, types

from config import GEMINI_API_KEY, GEMINI_MODEL

_MAX_ATTEMPTS = 4
_RETRYABLE_CODES = {429, 500, 503}


def generate_json(prompt: str, system_instruction: str, max_tokens: int = 2000) -> str:
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it as a GitHub Secret named GEMINI_API_KEY."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)
    last_err = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    max_output_tokens=max_tokens,
                    temperature=0.7,
                    # Thinking tokens count against max_output_tokens on
                    # gemini-2.5-flash, which can truncate the JSON mid-object
                    # under load. These tasks don't need thinking — disable it.
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except errors.APIError as e:
            last_err = e
            if e.code in _RETRYABLE_CODES and attempt < _MAX_ATTEMPTS:
                wait = 5 * 2 ** (attempt - 1)
                print(f"⚠️  Gemini {e.code}, retrying in {wait}s "
                      f"(attempt {attempt}/{_MAX_ATTEMPTS}) …")
                time.sleep(wait)
                continue
            raise

        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return response.text.strip()

    raise RuntimeError(f"Gemini unavailable after {_MAX_ATTEMPTS} attempts: {last_err}")
