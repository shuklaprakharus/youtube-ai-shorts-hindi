"""
config.py — Central configuration for AI YouTube Shorts Generator (Hindi / India edition)
All settings in one place. Tweak here, not deep in the code.
"""
import os

# ─── Groq API (free tier, no quota issues) — reused from English version ─────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"   # better Hindi quality than 8b-instant

# ─── Video dimensions (YouTube Shorts = 9:16 vertical) ───────────────────────
VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920
FPS          = 30
MIN_SLIDE_DURATION = 3.0   # seconds — no slide shorter than this

# ─── Hindi female voice (edge-tts — free, no API key) ────────────────────────
# Pleasant Hindi female options:
#   hi-IN-SwaraNeural   — warm, friendly  (recommended)
#   hi-IN-AnanyaNeural  — youthful
#   hi-IN-KavyaNeural   — calm narrator
HINDI_VOICE  = "hi-IN-SwaraNeural"
VOICE_RATE   = "+0%"     # speed: -50% .. +100%
VOICE_PITCH  = "+0Hz"    # pitch shift
VOICE_VOLUME = "+0%"

# ─── AI background image provider ────────────────────────────────────────────
# "pollinations" → free, no API key (default)
# "dalle"        → requires OPENAI_API_KEY (~$0.04/image)
IMAGE_PROVIDER = "pollinations"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")  # only needed for dalle

# ─── YouTube upload settings ─────────────────────────────────────────────────
YOUTUBE_CATEGORY_ID = "27"          # Education (changed from 28 = Science/Tech)
YOUTUBE_PRIVACY     = "public"      # "public" | "private" | "unlisted"
YOUTUBE_LANGUAGE    = "hi"          # Hindi

# ─── File / folder paths ─────────────────────────────────────────────────────
OUTPUT_DIR  = "output"
SLIDES_DIR  = "output/slides"
BG_DIR      = "output/backgrounds"
AUDIO_FILE  = "output/voiceover.mp3"
VIDEO_FILE  = "output/final_video.mp4"
TOPICS_FILE = "topics.json"   # repurposed as a date/event history file

# ─── Hindi font for slide overlays + subtitles ───────────────────────────────
# Searched in order; first match wins. Workflow installs Noto Devanagari via apt.
HINDI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/Library/Fonts/NotoSansDevanagari-Bold.ttf",                  # macOS
    "/System/Library/Fonts/Supplemental/NotoSansDevanagari.ttc",   # macOS
    "assets/fonts/NotoSansDevanagari-Bold.ttf",                    # bundled fallback
]

# Subtitle name passed to ffmpeg's libass — must match an installed font family
SUBTITLE_FONT_NAME = "Noto Sans Devanagari"

# Optional: keep these if you want to tint AI backgrounds slightly
THEMES = [
    {"accent": (255, 153,  51)},   # saffron
    {"accent": ( 19, 136,   8)},   # India green
    {"accent": (  0,   0, 128)},   # navy (Ashoka Chakra blue)
    {"accent": (255, 200,   0)},   # gold
    {"accent": (200,  16,  46)},   # crimson
]
