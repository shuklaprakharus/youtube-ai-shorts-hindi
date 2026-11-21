"""Settings for the kids-rhyme pipeline. Every value can be overridden with an environment variable
(GitHub repository variables / workflow inputs), so nothing here needs editing for day-to-day use."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIDS_DIR = ROOT / "kids"
EPISODE_DIR = KIDS_DIR / "episodes"
HISTORY_FILE = KIDS_DIR / "history.json"
WORK = Path(os.environ.get("KIDS_WORKDIR", str(ROOT / "output" / "kids")))

# Song grid: intro bar + 12 lines x 2 bars + 2-bar outro at 100 BPM = 62.4 s (+ tail) -> 66 s Short
BPM = 100
BAR = 4 * 60 / BPM
N_LINES = 12
TOTAL = 66.0
FPS = 30
W, H = 1080, 1920
MAX_LINE_SECONDS = 4.55      # a sung/recited line must fit its 2-bar slot (4.8 s) with a breath
MAX_INTRO_SECONDS = 2.0
MAX_OUTRO_SECONDS = 4.4

# Where episodes come from: "auto" = Gemini new episode, else next unused library episode;
# "library" = library only; "gemini" = must be a new Gemini episode.
SOURCE = os.environ.get("KIDS_SOURCE", "auto").strip().lower()
FORCE_EPISODE = os.environ.get("KIDS_EPISODE", "").strip()      # e.g. ep02_baarish

# YouTube
UPLOAD = os.environ.get("KIDS_UPLOAD", "true").strip().lower() == "true"
PRIVACY = os.environ.get("KIDS_PRIVACY", "public").strip().lower()      # public | unlisted | private
CATEGORY_ID = os.environ.get("KIDS_CATEGORY_ID", "27")                  # 27 = Education
MADE_FOR_KIDS = os.environ.get("KIDS_MADE_FOR_KIDS", "true").strip().lower() == "true"

WORKERS = max(1, int(os.environ.get("KIDS_WORKERS", str(os.cpu_count() or 2))))

# Voices. Primary: edge-tts neural voices (free). Fallback: gTTS + pitch shift.
# (voice, rate, pitch) for edge-tts; (pitch ratio, tempo) for the gTTS fallback.
EDGE_VOICES = {
    "n":     ("hi-IN-SwaraNeural",  "+2%",  "+0Hz"),
    "peelu": ("hi-IN-SwaraNeural",  "+6%",  "+40Hz"),
    "mama":  ("hi-IN-SwaraNeural",  "-4%",  "-8Hz"),
    "frog":  ("hi-IN-MadhurNeural", "-2%",  "-10Hz"),
    "fish":  ("hi-IN-SwaraNeural",  "+8%",  "+25Hz"),
}
GTTS_VOICES = {"n": (1.06, 1.04), "peelu": (1.30, 1.06), "mama": (0.97, 1.0), "frog": (0.80, 1.0), "fish": (1.22, 1.08)}
TTS_PROVIDER = os.environ.get("KIDS_TTS", "edge").strip().lower()      # edge | gtts
