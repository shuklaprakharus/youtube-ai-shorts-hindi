"""Per-segment Hindi voices. Primary: edge-tts neural voices (free, used by the main pipeline too).
Fallback: gTTS + formant-preserving pitch shift (ffmpeg rubberband) for the character voices.
Every line must fit its 2-bar slot; lines that run long are sped up a little (max 1.15x)."""
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from . import settings
from .episode import EpisodeError


class LineTooLong(EpisodeError):
    pass


def _dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def _trim_to_wav(src, dst, extra_af=""):
    af = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
          "silenceremove=start_periods=1:start_threshold=-45dB,areverse")
    if extra_af:
        af += "," + extra_af
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", af, "-ar", "44100", "-ac", "1", str(dst)], check=True)


async def _edge(text, voice, rate, pitch, out):
    import edge_tts
    await edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch).save(str(out))


def segment(text, who, tts_dir):
    """Synthesize one segment; returns (wav path, seconds, provider). Cached by text+speaker."""
    tts_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(f"{settings.TTS_PROVIDER}|{who}|{text}".encode()).hexdigest()[:12]
    wav = tts_dir / f"{h}.wav"
    meta = tts_dir / f"{h}.json"
    if wav.exists() and meta.exists():
        return wav, _dur(wav), json.loads(meta.read_text())["provider"]
    provider = None
    if settings.TTS_PROVIDER == "edge":
        mp3 = tts_dir / f"{h}.edge.mp3"
        voice, rate, pitch = settings.EDGE_VOICES[who]
        try:
            asyncio.run(_edge(text, voice, rate, pitch, mp3))
            _trim_to_wav(mp3, wav)
            provider = f"edge:{voice}"
        except Exception as e:
            print(f"     ⚠ edge-tts failed for {who} ({e}); falling back to gTTS")
    if provider is None:
        from gtts import gTTS
        mp3 = tts_dir / f"{h}.gtts.mp3"
        gTTS(text, lang="hi", tld="co.in").save(str(mp3))
        p, tempo = settings.GTTS_VOICES[who]
        _trim_to_wav(mp3, wav, f"rubberband=pitch={p}:tempo={tempo}:formant=preserved:pitchq=quality")
        provider = "gtts"
    meta.write_text(json.dumps({"provider": provider, "who": who, "text": text}, ensure_ascii=False))
    return wav, _dur(wav), provider


def _speed(wav, factor):
    out = wav.with_name(wav.stem + f".x{factor:.3f}.wav")
    if not out.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", f"atempo={factor:.4f}", "-ar", "44100", "-ac", "1", str(out)], check=True)
    return out


GAP = 0.12


def build(ep, work):
    """Returns {key: {'segs': [{t, who, wav, dur}], 'total': s}} for intro, L1..L12, outro."""
    tts_dir = work / "tts"
    plan = [("intro", [{"t": ep["title"]["spoken"], "who": "n"}], settings.MAX_INTRO_SECONDS)]
    plan += [(f"L{i + 1}", segs, settings.MAX_LINE_SECONDS) for i, segs in enumerate(ep["lines"])]
    plan += [("outro", [{"t": ep["outro"], "who": "n"}], settings.MAX_OUTRO_SECONDS)]
    out, providers = {}, set()
    for key, segs, limit in plan:
        res = []
        for s in segs:
            wav, d, prov = segment(s["t"].strip(), s["who"], tts_dir)
            providers.add(prov)
            res.append({"t": s["t"].strip(), "who": s["who"], "wav": str(wav), "dur": round(d, 3)})
        total = sum(r["dur"] for r in res) + GAP * (len(res) - 1)
        if total > limit:
            factor = total / limit
            if factor > 1.15:
                raise LineTooLong(f"{key} needs {total:.2f}s but the slot allows {limit:.2f}s — shorten it")
            for r in res:
                w = _speed(Path(r["wav"]), factor)
                r["wav"], r["dur"] = str(w), round(_dur(w), 3)
            total = sum(r["dur"] for r in res) + GAP * (len(res) - 1)
        out[key] = {"segs": res, "total": round(total, 3)}
        print(f"     {key:6s} {total:4.2f}s  " + " | ".join(f"{r['who']}" for r in res))
    out["_providers"] = sorted(providers)
    return out
