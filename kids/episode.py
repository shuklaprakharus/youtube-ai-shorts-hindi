"""Episodes: the hand-written library, Gemini-written new episodes, validation and history.

An episode is a JSON document (see kids/episodes/*.json). Every episode follows the same
song grid and beat sheet, so the renderer can stage it without any per-episode code:

  title bar  : title card, narrator says title.spoken
  L1-L2      : Peelu swims with Mama and her siblings (wide shot)
  L3-L4      : the event — "wander" (a butterfly lures her to the reeds), "rain" (rain + thunder,
               she hides in the reeds) or "treat" (a mango drops in the pond, she takes it to the reeds)
  L5-L6      : Peelu alone at the reeds, feeling peelu_mood (sad | scared | n | happy)
  L7-L8      : the frog hops onto a lily pad and gives advice (frog must speak in L7 or L8)
  L9         : the fish pops up with advice (fish must speak in L9); Peelu may answer/call
  L10        : far away, Mama notices and swims to Peelu (siblings follow)
  L11-L12    : hug, everyone cheers, rainbow; moral card on L12
  outro      : bye-bye + subscribe
"""
import datetime
import hashlib
import json
import os
import re

from . import settings

SPEAKERS = {"n", "peelu", "frog", "fish", "mama"}
EVENTS = ("wander", "rain", "treat")
MOODS = {"sad", "scared", "n", "happy"}
LATIN = re.compile(r"[A-Za-z]")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
BANNED_TOKENS = {"मार", "मारा", "मारो", "मारूँगा", "मारेगा", "खून", "मौत", "मरा", "मरी", "हत्या", "चाकू", "बंदूक",
                 "भूत", "चुड़ैल", "शराब", "सिगरेट", "जहर", "ज़हर", "बीमार", "चोट", "पिटाई", "थप्पड़"}
SLUG = re.compile(r"^[a-z0-9_]{3,48}$")


class EpisodeError(ValueError):
    pass


# ---------------------------------------------------------------- library / history
def load_library():
    eps = {}
    for root, _dirs, files in os.walk(settings.EPISODE_DIR):
        for fn in sorted(files):
            if fn.endswith(".json"):
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    ep = json.load(f)
                eps[ep["id"]] = ep
    return eps


def load_history():
    if settings.HISTORY_FILE.exists():
        with open(settings.HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"episodes": []}


def save_history(hist):
    with open(settings.HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
        f.write("\n")


def record(hist, ep, source, url):
    hist.setdefault("episodes", []).append({
        "date": datetime.date.today().isoformat(), "id": ep["id"], "title": ep["title"]["spoken"],
        "lesson": ep["lesson"], "event": ep["event"], "source": source, "youtube_url": url})


# ---------------------------------------------------------------- validation
def _line_text(segs):
    return " ".join(s["t"] for s in segs)


def _tokens(text):
    return [t for t in re.split(r"[\s,.!?।—\-“”\"'():;]+", text) if t]


def validate(ep):
    """Raise EpisodeError listing every problem; returns the (lightly normalised) episode."""
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    need(isinstance(ep, dict), "episode must be a JSON object")
    if errs:
        raise EpisodeError("; ".join(errs))
    need(bool(SLUG.match(str(ep.get("id", "")))), "id must be a lowercase slug")
    need(ep.get("event") in EVENTS, f"event must be one of {EVENTS}")
    need(ep.get("peelu_mood", "sad") in MOODS, f"peelu_mood must be one of {sorted(MOODS)}")
    need(isinstance(ep.get("lesson"), str) and 4 <= len(ep["lesson"]) <= 90, "lesson: 4-90 chars")
    t = ep.get("title") or {}
    need(1 <= len(t.get("line1", "")) <= 10, "title.line1: 1-10 chars")
    need(1 <= len(t.get("line2", "")) <= 12, "title.line2: 1-12 chars")
    need(4 <= len(t.get("spoken", "")) <= 30, "title.spoken: 4-30 chars")
    lines = ep.get("lines")
    need(isinstance(lines, list) and len(lines) == settings.N_LINES, f"lines: exactly {settings.N_LINES}")
    all_text = [t.get("line1", ""), t.get("line2", ""), t.get("spoken", ""), ep.get("outro", "")]
    if isinstance(lines, list) and len(lines) == settings.N_LINES:
        for i, segs in enumerate(lines, 1):
            if not (isinstance(segs, list) and 1 <= len(segs) <= 4):
                errs.append(f"L{i}: 1-4 segments"); continue
            for s in segs:
                if not (isinstance(s, dict) and s.get("who") in SPEAKERS and isinstance(s.get("t"), str) and s["t"].strip()):
                    errs.append(f"L{i}: each segment needs who in {sorted(SPEAKERS)} and text"); break
            else:
                txt = _line_text(segs)
                need(14 <= len(txt) <= 62, f"L{i}: line length {len(txt)} (want 14-62 chars)")
                all_text.append(txt)
        whos = lambda i: {s.get("who") for s in lines[i - 1] if isinstance(s, dict)}
        need("frog" in whos(7) | whos(8), "the frog must speak in L7 or L8")
        need("fish" in whos(9), "the fish must speak in L9")
    need(isinstance(ep.get("outro"), str) and 6 <= len(ep.get("outro", "")) <= 60, "outro: 6-60 chars")
    b = ep.get("bubbles") or {}
    for k, mx in (("peelu", 16), ("frog", 14), ("fish", 14), ("peelu_call", 14)):
        if b.get(k):
            need(len(b[k]) <= mx, f"bubbles.{k}: max {mx} chars")
            all_text.append(b[k])
    need(bool(b.get("frog")) and bool(b.get("fish")), "bubbles.frog and bubbles.fish are required")
    sw = ep.get("sound_words") or {}
    for k, v in sw.items():
        need(k in ("L2", "L3", "L4", "frog"), f"sound_words.{k}: only L2, L3, L4, frog")
        need(isinstance(v, str) and len(v) <= 14, f"sound_words.{k}: max 14 chars")
        if k in ("L2", "L3", "L4") and isinstance(lines, list) and len(lines) == settings.N_LINES and isinstance(v, str):
            head = v.split("-")[0].strip("!")
            need(head in _line_text(lines[int(k[1:]) - 1]), f"sound_words.{k} '{v}' must appear in {k}")
    m = ep.get("moral") or {}
    need(2 <= len(m.get("title", "")) <= 16, "moral.title: 2-16 chars")
    rows = m.get("rows") or []
    need(len(rows) == 2 and all(2 <= len(r) <= 16 for r in rows), "moral.rows: exactly 2 rows of 2-16 chars")
    all_text += [m.get("title", "")] + list(rows)
    th = ep.get("thumb") or {}
    need(1 <= len(th.get("l1", "")) <= 8 and 1 <= len(th.get("l2", "")) <= 10 and len(th.get("l3", "")) <= 12,
         "thumb: l1<=8, l2<=10, l3<=12 chars")
    all_text += [th.get("l1", ""), th.get("l2", ""), th.get("l3", "")]
    if ep.get("mama_burst"):
        need(len(ep["mama_burst"]) <= 14, "mama_burst: max 14 chars")
    seo = ep.get("seo") or {}
    titles = seo.get("titles") or []
    need(len(titles) >= 1 and all(10 <= len(x) <= 95 for x in titles), "seo.titles: 1-2 titles of 10-95 chars")
    need(isinstance(seo.get("description"), str) and 40 <= len(seo["description"]) <= 900, "seo.description: 40-900 chars")
    tags = seo.get("hashtags") or []
    need(4 <= len(tags) <= 10 and all(isinstance(x, str) and x.startswith("#") and " " not in x for x in tags),
         "seo.hashtags: 4-10 items like #HindiRhymes")
    for s in all_text:
        if not isinstance(s, str):
            continue
        if LATIN.search(s):
            errs.append(f"Latin letters not allowed in on-screen/spoken text: {s[:30]}")
        bad = BANNED_TOKENS.intersection(_tokens(s))
        if bad:
            errs.append(f"not suitable for little kids: {sorted(bad)}")
    if errs:
        raise EpisodeError("; ".join(dict.fromkeys(errs)))
    ep.setdefault("peelu_mood", "sad")
    ep.setdefault("sound_words", {})
    ep.setdefault("peelu_calls", any(s["who"] == "peelu" for s in ep["lines"][8]))
    ep.setdefault("mama_burst", "क्वैक-क्वैक!")
    return ep


# ---------------------------------------------------------------- Gemini
SYSTEM = """You write ORIGINAL Hindi nursery rhymes (बालगीत) for children aged 2-6 for a YouTube Shorts series
called "पीलू बतख". Everything you write must be new: never reuse or adapt lyrics of existing songs, poems,
film songs or other channels' rhymes, and never mention brands, real people, religion, politics, scary
things, violence, illness or injuries. Simple, warm, everyday Hindi in Devanagari only (no English letters).

FIXED CAST (only these may speak): narrator "n"; "peelu" — a little yellow duckling girl with a pink bow;
"mama" — her white mother duck; "frog" — a friendly frog on a lotus leaf; "fish" — a cheerful golden fish.
Peelu also has two duckling siblings (they never speak). Setting: a lotus pond with tall reeds.

FIXED SONG GRID (the animation is built from this, so follow it exactly):
- 12 lines, rhyming in couplets (L1/L2, L3/L4, ... L11/L12), rhythmic, 14-50 characters each (about 14-18
  syllables), each line said in under 4.5 seconds. A line is a list of segments {"t": text, "who": speaker};
  split a line into segments only where a character speaks their own words (no quote marks in "t").
- L1-L2: Peelu swims happily with Mama and siblings; introduce her by name.
- L3-L4: the EVENT you are given:
    wander = a colourful butterfly appears and Peelu follows it into the tall reeds, away from her family;
    rain   = clouds come, rain starts (टप-टप) and thunder rumbles (गड़-गड़); Peelu gets scared and hides in the reeds;
    treat  = a ripe mango falls into the pond (छपाक); Peelu grabs it and swims into the reeds to keep it to herself.
- L5-L6: Peelu alone at the reeds with a clear feeling (peelu_mood: sad | scared | n | happy); she may say a short line.
- L7-L8: the frog arrives and gives the first piece of advice. The frog MUST speak in L7 or L8.
- L9: the fish pops up with the second piece of advice (the fish MUST speak in L9); Peelu may reply or call out.
- L10: Mama, far away, notices/hears and comes swimming to Peelu (siblings follow).
- L11: happy reunion, hug, everyone claps; L12: the lesson in one simple line.
The two pieces of advice must together teach ONE gentle, practical lesson for small children, and the moral
card repeats it as a short question plus two short answers.

Return ONLY a JSON object with exactly these keys (see the example for style):
id (lowercase slug), event, lesson, peelu_mood, title {line1 (<=10 chars), line2 (<=12), spoken (<=30)},
lines (12 lists of segments), outro (<=60 chars, bye-bye + subscribe), sound_words {L2, L3, L4, frog: short
reduplicated sound words like छप-छप that literally appear in that line; frog e.g. टर्र-टर्र!},
bubbles {peelu (<=16), frog (<=14), fish (<=14), peelu_call (<=14, only if Peelu calls out in L9)},
peelu_calls (true if Peelu calls out loudly in L9), mama_burst (<=14, e.g. क्वैक-क्वैक!),
moral {title (<=16), rows [2 items, each <=16]}, thumb {l1 (<=8), l2 (<=10), l3 (<=12)},
seo {titles [2 YouTube titles <=95 chars, Hindi + "Hindi Rhymes for Kids" style keywords allowed, end with #Shorts],
description (Hindi, 2-3 sentences, may mention "मूल (original) कविता और संगीत"), hashtags [6-8 items]}.
English is allowed ONLY inside seo.titles, seo.description and seo.hashtags."""


def _prompt(event, history, feedback=""):
    used = [f"- {h.get('title')} — {h.get('lesson')}" for h in history.get("episodes", [])][-40:]
    lib = load_library()
    example = lib.get("ep01_khoi_peelu") or next(iter(lib.values()))
    p = (f"Write a NEW episode. EVENT = {event}.\n"
         f"Choose a lesson that is different from all of these earlier episodes:\n" + ("\n".join(used) or "- none") +
         f"\n\nExample episode (format and quality reference only — do not copy its lines):\n"
         f"{json.dumps(example, ensure_ascii=False)}\n")
    if feedback:
        p += f"\nYour previous attempt was rejected: {feedback}\nFix these problems.\n"
    return p


def generate_with_gemini(history, event=None, feedback="", attempts=3):
    from agents.gemini_client import generate_json
    import json_repair
    if event is None:
        recent = [h.get("event") for h in history.get("episodes", [])]
        event = min(EVENTS, key=lambda e: (recent.count(e), -max([i for i, x in enumerate(recent) if x == e], default=-1)))
    last = None
    for k in range(attempts):
        raw = generate_json(_prompt(event, history, feedback), SYSTEM, max_tokens=8000)
        try:
            ep = json_repair.loads(raw)
            ep["event"] = event
            day = datetime.date.today().strftime("%Y%m%d")
            stem = re.sub(r"[^a-z0-9_]", "", str(ep.get("id", "")).lower())[:30] or "episode"
            ep["id"] = f"g{day}_{stem}_{hashlib.md5(raw.encode()).hexdigest()[:4]}"
            ep["source"] = "gemini"
            return validate(ep)
        except Exception as e:      # validation problems are fed back to the model
            last = e
            feedback = str(e)[:600]
            print(f"     ⚠ Gemini episode rejected (attempt {k + 1}/{attempts}): {feedback}")
    raise EpisodeError(f"Gemini could not produce a valid episode: {last}")


def choose_episode(history):
    """Returns (episode, source). Raises if nothing new is available."""
    lib = load_library()
    if settings.FORCE_EPISODE:
        if settings.FORCE_EPISODE not in lib:
            raise EpisodeError(f"KIDS_EPISODE={settings.FORCE_EPISODE} not found in kids/episodes")
        return validate(lib[settings.FORCE_EPISODE]), "library"
    if settings.SOURCE in ("auto", "gemini") and os.environ.get("GEMINI_API_KEY"):
        try:
            return generate_with_gemini(history), "gemini"
        except Exception as e:
            if settings.SOURCE == "gemini":
                raise
            print(f"     ⚠ Gemini episode unavailable ({e}); using the library")
    used = {h["id"] for h in history.get("episodes", [])}
    for eid in sorted(lib):
        if eid not in used and lib[eid].get("source", "library") == "library":
            return validate(lib[eid]), "library"
    raise EpisodeError("No unused library episode left. Set the GEMINI_API_KEY secret (new episodes are then "
                       "written automatically) or add episode JSON files to kids/episodes/.")
