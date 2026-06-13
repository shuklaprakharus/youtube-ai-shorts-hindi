"""
config.py — Central configuration for Aaj Ka Itihaas (daily Hindi history Shorts).
All settings in one place. Tweak here, not deep in the code.
"""
import os

# ─── Gemini API ──────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

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

# ─── Background music bed (optional) ─────────────────────────────────────────
# Drop royalty-free instrumental MP3s into assets/music/ (optionally inside a
# genre subfolder). When present, one is looped and ducked under the voice.
# See assets/music/README.md for sources. No files → plain voiceover.
MUSIC_DIR    = "assets/music"
MUSIC_VOLUME = 0.22   # music level relative to voice (0.0–1.0)

# ─── AI background image provider ────────────────────────────────────────────
# "pollinations" → free, no API key (default)
# "dalle"        → requires OPENAI_API_KEY (~$0.04/image)
IMAGE_PROVIDER = "pollinations"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")  # only needed for dalle

# ─── Pexels stock footage/photos (free API key from pexels.com/api) ──────────
# When set, slides prefer vertical stock videos, then stock photos, before
# falling back to the AI image provider / procedural gradients.
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# Reject stock media containing identifiable human faces (likeness safety).
AVOID_FACES = os.environ.get("AVOID_FACES", "true").lower() == "true"

# ─── YouTube upload settings ─────────────────────────────────────────────────
YOUTUBE_CATEGORY_ID = "27"          # Education
YOUTUBE_PRIVACY     = "public"      # "public" | "private" | "unlisted"
YOUTUBE_LANGUAGE    = "hi"          # Hindi

# ─── Google Cloud Storage archive ────────────────────────────────────────────
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "")
GCS_PREFIX = os.environ.get("GCS_PREFIX", "youtube-ai-shorts-hindi")
REQUIRE_GCS_ARCHIVE = os.environ.get("REQUIRE_GCS_ARCHIVE", "false").lower() == "true"

# ─── File / folder paths ─────────────────────────────────────────────────────
OUTPUT_DIR  = "output"
SLIDES_DIR  = "output/slides"
BG_DIR      = "output/backgrounds"
AUDIO_FILE  = "output/voiceover.mp3"
VIDEO_FILE  = "output/final_video.mp4"
TOPICS_FILE = "topics.json"   # covered-events history file (dedup)

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
