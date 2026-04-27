"""
tts.py
======
Text-to-speech using Microsoft Edge Neural TTS (edge-tts).
  - 100% free, no API key needed
  - Excellent Hindi female voice: hi-IN-SwaraNeural (warm, friendly)
  - Falls back to gTTS Hindi if edge-tts is unavailable
"""

import os
import asyncio
from pathlib import Path
from config import (
    AUDIO_FILE, OUTPUT_DIR,
    HINDI_VOICE, VOICE_RATE, VOICE_PITCH, VOICE_VOLUME,
)


# ─────────────────────────────────────────────────────────────────────────────
async def _edge_tts_synthesize(text: str, output_path: str) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(
        text,
        voice  = HINDI_VOICE,
        rate   = VOICE_RATE,
        pitch  = VOICE_PITCH,
        volume = VOICE_VOLUME,
    )
    await communicate.save(output_path)


def generate_voiceover(text: str, lang: str = "hi") -> str:
    """
    Convert Hindi text to speech and save as MP3.
    Returns path to the audio file.

    `lang` arg kept for backward compatibility with the English version's
    main.py — ignored when using edge-tts (voice already encodes language).
    """
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    text = text.strip()

    # ── Primary: edge-tts (free, no key, best Hindi quality) ─────────────────
    try:
        asyncio.run(_edge_tts_synthesize(text, AUDIO_FILE))
        print(f"     → Saved (edge-tts / {HINDI_VOICE}): {AUDIO_FILE}")
        return AUDIO_FILE

    except Exception as edge_err:
        print(f"     ⚠ edge-tts failed ({edge_err}), trying gTTS Hindi …")

    # ── Fallback: gTTS Hindi ─────────────────────────────────────────────────
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="hi", slow=False)
        tts.save(AUDIO_FILE)
        print(f"     → Saved (gTTS hi): {AUDIO_FILE}")
        return AUDIO_FILE
    except Exception as gtts_err:
        raise RuntimeError(
            f"Both edge-tts and gTTS failed.\n"
            f"  edge-tts: {edge_err}\n"
            f"  gTTS:     {gtts_err}"
        )


# ─────────────────────────────────────────────────────────────────────────────
def get_audio_duration(audio_file: str) -> float:
    """Return the duration of an MP3 file in seconds."""
    from mutagen.mp3 import MP3
    return MP3(audio_file).info.length
