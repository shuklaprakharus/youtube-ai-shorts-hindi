"""Soundtrack: voice placed on the 100 BPM grid, an original synthesized kids tune with an emotional arc
(happy -> sad -> hope -> build -> joy), and synthesized sound effects. Also computes the shared timeline
(word timings, effect times, lip-sync envelopes) that the renderer follows."""
import hashlib
import subprocess
import wave

import numpy as np
from scipy.signal import butter, sosfilt

from . import settings

SR = 44100
BEAT = 60 / settings.BPM
BAR = settings.BAR
rng = np.random.default_rng(11)


def readwav(p):
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def writewav(p, x, ch=1):
    with wave.open(str(p), "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def add(buf, x, t, g=1.0):
    s = int(t * SR); e = min(len(buf), s + len(x))
    if 0 <= s < len(buf):
        buf[s:e] += g * x[:e - s]


def bp(x, lo, hi, order=2): return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)
def hp(x, f, order=2): return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)
def lp(x, f, order=2): return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


NOTE = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}
def hz(name, octv): return 440.0 * 2 ** ((NOTE[name] + 12 * (octv - 4)) / 12)
CH = {"D": ["D", "F#", "A"], "G": ["G", "B", "D"], "A": ["A", "C#", "E"], "Bm": ["B", "D", "F#"], "Em": ["E", "G", "B"]}


# ---------------- instruments ----------------
def pluck(f, dur=0.9, bright=1.0):
    n = int(dur * SR); t = np.arange(n) / SR; out = np.zeros(n)
    for k in range(1, 9):
        if f * k > 9000: break
        out += (1 / k ** 1.25) * np.exp(-t * (2.2 + 1.6 * k * bright)) * np.sin(2 * np.pi * f * k * t + k * 0.7)
    return out * np.minimum(1, t / 0.003)

def glock(f, dur=1.4):
    n = int(dur * SR); t = np.arange(n) / SR
    out = sum(a * np.exp(-t * d) * np.sin(2 * np.pi * f * r * t) for r, a, d in [(1, 1, 1.9), (2.76, 0.32, 5), (5.40, 0.14, 9), (8.93, 0.06, 14)])
    return out * np.minimum(1, t / 0.0015)

def musicbox(f, dur=1.6):
    n = int(dur * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 6)) * np.exp(-t * 2.2) * np.minimum(1, t / 0.002)

def bass(f, dur=0.55):
    n = int(dur * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 4.0) * np.minimum(1, t / 0.006)

def pad(freqs, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    out = sum(np.sin(2 * np.pi * f * t) + np.sin(2 * np.pi * f * 1.004 * t + 1) for f in freqs)
    return lp(out * np.minimum(1, t / 0.9) * np.minimum(1, (dur - t) / 0.8), 1800)

def kick():
    n = int(0.28 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * np.cumsum(45 + 85 * np.exp(-t * 30)) / SR) * np.exp(-t * 11)

def clap():
    n = int(0.18 * SR); t = np.arange(n) / SR
    e = sum(np.exp(-np.clip(t - o, 0, None) * 60) * (t >= o) for o in (0, 0.011, 0.022)) + 0.5 * np.exp(-t * 18)
    return bp(rng.standard_normal(n), 900, 3200) * e * 0.6

def shaker(acc=1.0):
    n = int(0.07 * SR); t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 6000) * np.minimum(1, t / 0.012) * np.exp(-t * 55) * acc


# ---------------- sound effects ----------------
def quack(f0=520, dur=0.22):
    n = int(dur * SR); t = np.arange(n) / SR
    ph = 2 * np.pi * np.cumsum(f0 * (1.0 + 0.10 * np.exp(-t * 25)) * (1 - 0.22 * t / dur)) / SR
    x = sum((1 / k ** 0.7) * np.sin(k * ph) for k in range(1, 14))
    x = bp(x, 700, 1500) * 1.4 + bp(x, 2000, 3200) * 0.8 + 0.15 * bp(rng.standard_normal(n), 1200, 4000)
    e = np.minimum(1, t / 0.015) * np.clip((dur - t) / (dur * 0.55), 0, 1) ** 0.8
    return x * e / (np.abs(x * e).max() + 1e-9)

def splash(dur=0.55, big=1.0):
    n = int(dur * SR); t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 500, 5000) * np.minimum(1, t / 0.006) * np.exp(-t * (7 / big))
    for k in range(5):
        o = rng.uniform(0.0, 0.25); fs = rng.uniform(500, 1100); m = t >= o; tt = t[m] - o
        x[m] += 0.25 * np.sin(2 * np.pi * np.cumsum(fs * np.exp(-tt * 9) + 250) / SR) * np.exp(-tt * 22)
    return x / (np.abs(x).max() + 1e-9)

def croak():
    n = int(0.42 * SR); t = np.arange(n) / SR
    ph = 2 * np.pi * np.cumsum(95 + 15 * np.sin(2 * np.pi * 3 * t)) / SR
    x = sum((1 / k ** 0.5) * np.sin(k * ph) for k in range(1, 18)) * (0.55 + 0.45 * np.sign(np.sin(2 * np.pi * 26 * t)))
    x = bp(x, 150, 1400) * np.minimum(1, t / 0.02) * np.clip((0.42 - t) / 0.15, 0, 1)
    return x / (np.abs(x).max() + 1e-9)

def flutter(dur=1.2):
    n = int(dur * SR); t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 1500, 6000) * (0.5 + 0.5 * np.sin(2 * np.pi * 18 * t)) ** 3
    return x * np.minimum(1, t / 0.2) * np.minimum(1, (dur - t) / 0.3)

def rustle(dur=1.0):
    n = int(dur * SR); t = np.arange(n) / SR; g = np.zeros(n)
    for k in range(60):
        o = int(rng.uniform(0, dur - 0.05) * SR); L = int(rng.uniform(0.01, 0.04) * SR)
        g[o:o + L] += rng.uniform(0.3, 1.0) * np.hanning(L)
    return bp(rng.standard_normal(n), 2500, 8000) * g * np.minimum(1, (dur - t) / 0.3)

def applause(dur=1.8):
    n = int(dur * SR); out = np.zeros(n)
    for k in range(70):
        c = clap() * rng.uniform(0.3, 0.9); o = int(rng.uniform(0, dur - 0.2) * SR)
        out[o:o + len(c)] += c[:n - o]
    t = np.arange(n) / SR
    return out * np.minimum(1, t / 0.15) * np.minimum(1, (dur - t) / 0.5)

def chime(notes=(("D", 6), ("F#", 6), ("A", 6), ("D", 7)), step=0.07):
    out = np.zeros(int((step * len(notes) + 1.5) * SR))
    for i, (nm, o) in enumerate(notes):
        g = glock(hz(nm, o), 1.4); s = int(i * step * SR); out[s:s + len(g)] += g * 0.6
    return out

def pop():
    n = int(0.09 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * np.cumsum(380 + 900 * t / 0.09) / SR) * np.exp(-t * 35)

def whoosh(dur=0.45):
    n = int(dur * SR); t = np.arange(n) / SR; x = rng.standard_normal(n); out = np.zeros(n); seg = 2048
    for i in range(0, n, seg):
        fc = 300 + 2500 * (i / n); out[i:i + seg] = bp(x[i:i + seg], fc * 0.7, fc * 1.4)[:min(seg, n - i)]
    return out * np.sin(np.pi * t / dur) ** 2

def boing():
    n = int(0.35 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * np.cumsum(260 + 220 * np.exp(-t * 9) * np.cos(2 * np.pi * 9 * t)) / SR) * np.exp(-t * 7)

def fall_whistle(dur=0.45):
    n = int(dur * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * np.cumsum(1500 - 1000 * t / dur) / SR) * np.minimum(1, t / 0.03) * 0.6

def rain_noise(dur):
    n = int(dur * SR); t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 900, 7000) * (0.7 + 0.3 * lp(np.abs(rng.standard_normal(n)), 3))
    drops = np.zeros(n)
    for k in range(int(dur * 14)):
        o = int(rng.uniform(0, dur - 0.03) * SR); L = int(0.012 * SR)
        drops[o:o + L] += rng.uniform(0.3, 1.0) * np.hanning(L) * np.sin(2 * np.pi * rng.uniform(1800, 3200) * np.arange(L) / SR)
    return (x * 0.5 + drops) * np.minimum(1, t / 1.2) * np.minimum(1, (dur - t) / 1.0)

def thunder(dur=2.2):
    n = int(dur * SR); t = np.arange(n) / SR
    x = lp(rng.standard_normal(n), 220) * 3 + lp(rng.standard_normal(n), 900) * 0.4 * np.exp(-t * 6)
    env = np.minimum(1, t / 0.02) * np.exp(-t * 1.6) * (0.7 + 0.3 * np.sin(2 * np.pi * 3.5 * t) ** 2)
    x = x * env
    return x / (np.abs(x).max() + 1e-9)


# ---------------- timeline + mix ----------------
def build(ep, tts, work):
    global rng
    rng = np.random.default_rng(int(hashlib.md5(ep["id"].encode()).hexdigest()[:8], 16))
    TOTAL = settings.TOTAL; N = int(SR * TOTAL)
    voice = np.zeros(N); segs = []
    voice_by = {w: np.zeros(N) for w in ("peelu", "frog", "fish", "mama")}

    def place(key, t0):
        t = t0
        for s in tts[key]["segs"]:
            a = readwav(s["wav"]); add(voice, a, t)
            if s["who"] in voice_by: add(voice_by[s["who"]], a, t)
            segs.append({"key": key, "who": s["who"], "t": s["t"], "start": round(t, 3), "dur": s["dur"]})
            t += s["dur"] + 0.12
    place("intro", 0.30)
    LINE0 = [round(BAR + 2 * BAR * i, 3) for i in range(settings.N_LINES)]
    for i in range(settings.N_LINES):
        place(f"L{i + 1}", LINE0[i] + 0.10)
    OUT0 = BAR + 2 * settings.N_LINES * BAR
    place("outro", OUT0 + 0.15)
    L = {i + 1: LINE0[i] for i in range(settings.N_LINES)}

    # word timings (characters spread over each segment)
    WORDS = []
    for s in segs:
        ws = s["t"].split(); wts = [len(w.strip(",.!?।—")) + 1 for w in ws]; tot = sum(wts); acc = s["start"]
        for w, k in zip(ws, wts):
            d = s["dur"] * k / tot
            WORDS.append({"key": s["key"], "who": s["who"], "w": w, "start": round(acc, 3), "end": round(acc + d, 3)}); acc += d

    def wt(key, sub, default=None):
        if not sub: return default
        sub = sub.strip("!").split("-")[0]
        m = [x for x in WORDS if x["key"] == key and sub in x["w"]]
        return m[0]["start"] if m else default

    def first_seg(keys, who):
        m = [s for s in segs if s["key"] in keys and s["who"] == who]
        return m[0] if m else None

    # ---------------- music ----------------
    mus = np.zeros(N); drums = np.zeros(N)
    sections = [(0, ["D"], "intro"), (1, ["D", "G", "A", "D", "D", "G", "A", "D"], "happy"), (9, ["Bm", "G", "Em", "A"], "sad"),
                (13, ["G", "D", "Em", "A"], "hope"), (17, ["Bm", "G", "D", "A"], "build"), (21, ["D", "G", "A", "D"], "joy"),
                (25, ["GA", "D"], "outro")]
    bars = [(b0 + k, c, mood) for b0, chords, mood in sections for k, c in enumerate(chords)]
    STRUM = [(0, "D", 1.0), (1, "D", 0.6), (1.5, "U", 0.5), (2.5, "U", 0.6), (3, "D", 0.8), (3.5, "U", 0.55)]
    for b, c, mood in bars:
        tb = b * BAR
        for ch, bo, bl in ([("G", 0, 2), ("A", 2, 2)] if c == "GA" else [(c, 0, 4)]):
            notes = CH[ch]
            if mood in ("happy", "hope", "build", "joy", "intro", "outro"):
                for beat, dirn, acc in STRUM:
                    if not (bo <= beat < bo + bl) or (mood == "hope" and beat % 1): continue
                    vs = [hz(notes[0], 4), hz(notes[1], 4), hz(notes[2], 4), hz(notes[0], 5)]
                    for j, f in enumerate(vs[::-1] if dirn == "U" else vs):
                        add(mus, pluck(f, 0.7), tb + beat * BEAT + j * 0.012, 0.050 * acc)
                for beat, mul in [(0, 1.0), (2, 1.5)]:
                    if bo <= beat < bo + bl:
                        add(mus, bass(hz(notes[0], 2) * mul), tb + beat * BEAT, 0.20)
            if mood == "sad":
                add(mus, pad([hz(n, 4) for n in notes], BAR), tb, 0.030)
                add(mus, bass(hz(notes[0], 2), 1.5), tb, 0.15)
                arp = [hz(notes[0], 5), hz(notes[1], 5), hz(notes[2], 5), hz(notes[1], 5)]
                for k in range(8):
                    add(mus, musicbox(arp[k % 4] * (2 if k == 4 else 1)), tb + k * BEAT / 2, 0.056)
            if mood == "hope":
                add(mus, pad([hz(n, 4) for n in notes], BAR), tb, 0.012)
        if mood in ("happy", "joy", "build", "outro"):
            lvl = 1.0 if mood != "build" else 0.6 + 0.4 * ((b - 17) / 3)
            for beat in range(4):
                if beat in (0, 2): add(drums, kick(), tb + beat * BEAT, 0.42 * lvl)
                if beat in (1, 3): add(drums, clap(), tb + beat * BEAT, 0.30 * lvl)
            for k in range(8):
                add(drums, shaker(1.0 if k % 2 else 0.6), tb + k * BEAT / 2, 0.22 * lvl)
            if mood == "joy":
                for k in range(16): add(drums, shaker(0.5), tb + k * BEAT / 4, 0.12)
        if mood == "hope":
            for beat in (0, 2): add(drums, kick(), tb + beat * BEAT, 0.20)
    def g(nm, o, t, v=0.10): add(mus, glock(hz(nm, o)), t, v)
    for k, (nm, o) in enumerate([("A", 5), ("F#", 5), ("A", 5), ("D", 6)]): g(nm, o, k * BEAT, 0.12)
    chord_at = {b: c for b, c, m in bars}; mood_at = {b: m for b, c, m in bars}
    for i in range(settings.N_LINES):
        endbar = 2 + 2 * i; c = chord_at.get(endbar, "D"); c = "A" if c == "GA" else c
        if mood_at.get(endbar) == "sad": continue
        for k, nm in enumerate(CH[c]):
            g(nm, 5 if NOTE[nm] >= NOTE["D"] else 6, endbar * BAR + 3 * BEAT + k * BEAT / 2, 0.075)
    for nm, o, b in [("D", 6, 0), ("B", 5, 1), ("D", 6, 2), ("C#", 6, 3), ("A", 5, 4), ("F#", 5, 5), ("A", 5, 6), ("D", 6, 8)]:
        g(nm, o, OUT0 + b * BEAT / 2 + (0 if b < 8 else BEAT * 2), 0.11)

    # ---------------- effects (times shared with the renderer) ----------------
    sfx = np.zeros(N); ev = {}
    def fx(name, t, gain=None, x=None):
        if t is None: return
        ev[name] = round(t, 3)
        if x is not None: add(sfx, x, t, gain)
    sw = ep.get("sound_words", {})
    fx("quack_title", 0.02, 0.32, quack(560)); fx("pop_title", 0.50, 0.25, pop())
    fx("sfx_L2", wt("L2", sw.get("L2")), 0.18, splash(0.45))
    if "sfx_L2" in ev: add(sfx, splash(0.4), ev["sfx_L2"] + 0.32, 0.16)
    fx("sfx_L3", wt("L3", sw.get("L3"), L[3] + 2.6))
    fx("sfx_L4", wt("L4", sw.get("L4"), L[4] + 2.6))
    event = ep["event"]
    if event == "wander":
        fx("butterfly_in", L[3] + 0.15, 0.22, chime()); add(sfx, flutter(3.5), L[3] + 0.3, 0.10)
        add(sfx, rustle(1.4), ev["sfx_L4"] - 0.1, 0.22)
        fx("turn1", L[5] + 0.15, 0.18, whoosh()); fx("turn2", L[5] + 1.45, 0.14, whoosh()); fx("turn3", L[5] + 2.6)
    elif event == "rain":
        fx("rain_start", L[3] + 0.6); fx("rain_end", L[11] + 0.6)
        add(sfx, rain_noise(ev["rain_end"] + 1.0 - ev["rain_start"]), ev["rain_start"], 0.16)
        fx("thunder1", wt("L4", sw.get("L4"), L[4] + 0.4), 0.42, thunder())
        fx("thunder2", L[5] + 2.3, 0.30, thunder(1.8))
        fx("turn1", L[5] + 0.9, 0.12, whoosh())
    elif event == "treat":
        fx("mango_drop", L[3] + 0.25, 0.20, fall_whistle()); fx("mango_splash", L[3] + 0.70, 0.26, splash(0.6, 1.3))
        fx("mango_grab", L[3] + 1.9, 0.18, chime((("A", 5), ("D", 6), ("F#", 6))))
        fx("turn1", L[5] + 0.9, 0.12, whoosh()); fx("share", L[11] + 1.7, 0.20, chime())
    pb = first_seg(("L5", "L6"), "peelu")
    fx("peelu_bubble", pb["start"] if pb else L[6] + 0.4); ev["peelu_bubble_dur"] = round((pb["dur"] + 0.5) if pb else 2.6, 3)
    fx("frog_jump", L[7] - 0.95, 0.22, boing()); fx("frog_land", L[7] - 0.45, 0.16, splash(0.35, 0.6))
    fx("croak", L[7] - 0.36, 0.22, croak())
    ft = first_seg(("L7", "L8"), "frog"); fx("frog_talk", ft["start"] if ft else L[7] + 1.5)
    f8 = first_seg(("L8",), "frog"); fx("frog_bubble", (f8["start"] if f8 else L[8]) + 1.1, 0.22, pop())
    fx("fish_jump", L[9] + 0.05, 0.26, splash(0.6, 1.3)); fx("fish_land", L[9] + 0.75, 0.18, splash(0.4))
    fs = first_seg(("L9",), "fish"); fx("fish_bubble", fs["start"] - 0.1 if fs else L[9] + 1.0, 0.20, pop())
    pc = first_seg(("L9",), "peelu")
    if pc: fx("peelu_call", pc["start"]); ev["peelu_call_dur"] = pc["dur"]
    fx("mama_hear", L[10] + 1.25, 0.18, pop()); fx("mama_go", L[10] + 2.0, 0.20, whoosh(0.6))
    fx("mama_q1", L[10] + 3.95, 0.30, quack(430, 0.24)); fx("mama_q2", L[10] + 4.25, 0.28, quack(410, 0.24))
    fx("hug", L[11] + 0.9, 0.24, chime((("A", 5), ("D", 6), ("F#", 6), ("A", 6), ("D", 7))))
    fx("applause", wt("L11", "ताली", L[11] + 2.7), 0.22, applause(2.0))
    rows = ep["moral"]["rows"]
    fx("moral", L[12] + 0.2, 0.20, chime())
    r1 = wt("L12", rows[0].split()[0], L[12] + 0.9); r2 = wt("L12", rows[1].split()[0], L[12] + 2.0)
    if r2 <= r1 + 0.4: r2 = r1 + 1.1
    fx("row1", max(r1, L[12] + 0.6), 0.16, pop()); fx("row2", r2, 0.16, pop())
    fx("bye", OUT0 + 0.2, 0.22, pop())
    fx("sub", wt("outro", "सब्सक्राइब", OUT0 + 2.2), 0.25, pop())
    oend = [s for s in segs if s["key"] == "outro"][-1]; oend = oend["start"] + oend["dur"]
    fx("bye_quack", oend + 0.1, 0.24, quack(560)); fx("end_chime", oend + 0.5, 0.18, chime())

    # ---------------- mix ----------------
    def env(x, win):
        k = int(win * SR); return np.sqrt(np.convolve(x ** 2, np.ones(k) / k, "same"))
    duck = 1 - 0.42 * np.clip(env(voice, 0.12) / 0.04, 0, 1)
    duck = np.convolve(duck, np.ones(int(0.15 * SR)) / int(0.15 * SR), "same")
    t = np.arange(N) / SR
    music = (mus + drums) * duck * np.minimum(1, (TOTAL - t) / 1.2)
    mix = voice + music * 0.85 + sfx * 0.9
    mix = np.tanh(mix * 1.1) / 1.1
    mix /= np.abs(mix).max() / 0.9
    writewav(work / "mix_raw.wav", mix)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(work / "mix_raw.wav"), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-ar", "44100", "-ac", "2", str(work / "mix.wav")], check=True)
    nf = int(TOTAL * settings.FPS); mouth = {}
    for who, v in voice_by.items():
        e = env(v, 0.04)
        fr = np.array([e[min(N - 1, int((i + 0.5) / settings.FPS * SR))] for i in range(nf)])
        mouth[who] = [round(float(x), 3) for x in np.clip(fr / (fr.max() + 1e-9) * 1.6, 0, 1)] if fr.max() > 0 else [0.0] * nf
    return {"bpm": settings.BPM, "bar": BAR, "total": TOTAL, "line0": LINE0, "out0": OUT0, "segs": segs,
            "events": ev, "words": WORDS, "mouth": mouth}
