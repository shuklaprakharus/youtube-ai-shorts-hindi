"""
Small Gemini wrapper used by the content agents.

The agents ask for strict JSON. This helper keeps the provider-specific code in
one place and validates that a configured API key exists before a workflow run
spends time creating media.
"""

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL


def generate_json(prompt: str, system_instruction: str, max_tokens: int = 2000) -> str:
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it as a GitHub Secret named GEMINI_API_KEY."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            max_output_tokens=max_tokens,
            temperature=0.7,
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    return response.text.strip()
