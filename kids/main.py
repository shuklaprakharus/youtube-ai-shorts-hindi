#!/usr/bin/env python3
"""Kids nursery-rhyme Short pipeline (पीलू बतख series).

    episode (library or Gemini) → voices → music + SFX → 3D-style animation → MP4 → YouTube (made for kids)

Run:  python -m kids.main            (env: see kids/settings.py; KIDS_UPLOAD=false for a dry run)
"""
import datetime
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
import traceback

from . import audio, bg, episode, render, settings, thumb, tts


def banner(msg):
    print(f"\n{'─' * 60}\n  {msg}\n{'─' * 60}", flush=True)


def check_upload_env():
    raw = os.environ.get("YOUTUBE_CREDENTIALS")
    if not raw:
        raise EnvironmentError("YOUTUBE_CREDENTIALS secret is not set (run setup_auth.py once and save it as a GitHub "
                               "secret), or set KIDS_UPLOAD=false for a build-only run.")
    data = json.loads(raw)
    missing = [k for k in ("refresh_token", "client_id", "client_secret", "token_uri") if not data.get(k)]
    if missing:
        raise EnvironmentError("YOUTUBE_CREDENTIALS JSON is missing: " + ", ".join(missing))
    gcs = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if gcs:
        path = settings.ROOT / "output" / "google_application_credentials.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        json.loads(gcs); path.write_text(gcs, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)


def _init_worker(work, ep, tl):
    render.init(work, ep, tl)


def make_video(ep, work):
    t0 = time.time()
    print("\n🎙️  Voices …")
    voices = tts.build(ep, work)
    print(f"     → providers: {', '.join(voices['_providers'])}")
    print("\n🎵  Music, effects and timeline …")
    tl = audio.build(ep, voices, work)
    (work / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
    print("\n🏞️  Painting the pond …")
    seed = int(hashlib.md5(ep["id"].encode()).hexdigest()[:6], 16) % 1000
    pano, sky, skyall = bg.paint(seed=seed)
    pano.convert("RGB").save(work / "pano.png"); sky.save(work / "skymask.png"); skyall.save(work / "skyall.png")
    print(f"\n🎬  Rendering shots with {settings.WORKERS} workers …")
    render.init(work, ep, tl)
    order = ["s6", "s1", "s2", "s3", "s4", "s7", "s5a", "s5b", "s0"]      # heaviest first
    with mp.get_context("fork").Pool(settings.WORKERS, initializer=_init_worker, initargs=(work, ep, tl)) as pool:
        for sid, n in pool.imap_unordered(render.render_scene, order):
            print(f"     · {sid}: {n} frames", flush=True)
    names = [s[0] for s in render.scenes()]
    (work / "concat.txt").write_text("".join(f"file '{work / (n + '.mp4')}'\n" for n in names), encoding="utf-8")
    final = work / "final_video.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(work / "concat.txt"), "-c", "copy",
                    str(work / "video_only.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(work / "video_only.mp4"), "-i", str(work / "mix.wav"), "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    th = thumb.make(ep, work)
    print(f"     → {final} ({os.path.getsize(final) / 1e6:.1f} MB) in {time.time() - t0:.0f}s")
    return final, th, voices["_providers"]


def main():
    banner(f"🦆  Kids rhyme Short  ·  {datetime.date.today()}")
    work = settings.WORK; work.mkdir(parents=True, exist_ok=True)
    try:
        if settings.UPLOAD:
            check_upload_env()
        hist = episode.load_history()
        print("\n📖  Choosing the episode …")
        ep, source = episode.choose_episode(hist)
        for attempt in range(3):
            print(f"     → {ep['id']} ({source}, event={ep['event']}): {ep['title']['spoken']} — {ep['lesson']}")
            try:
                final, th, providers = make_video(ep, work)
                break
            except tts.LineTooLong as e:
                if source != "gemini" or attempt == 2:
                    raise
                print(f"     ⚠ {e}; asking Gemini for a shorter version")
                ep = episode.generate_with_gemini(hist, event=ep["event"], feedback=str(e))
        seo = ep["seo"]
        meta = {"date": datetime.date.today().isoformat(), "run_id": os.environ.get("GITHUB_RUN_ID", ""), "episode": ep,
                "source": source, "tts": providers, "youtube_url": None}
        if settings.UPLOAD:
            from uploader.youtube import upload_to_youtube
            print("\n📤  Uploading to YouTube (made for kids) …")
            tags = [h.lstrip("#") for h in seo["hashtags"]] + ["Hindi Rhymes", "बालगीत", "Kids Songs", "Peelu Duck"]
            url = upload_to_youtube(video_file=str(final), title=seo["titles"][0], description=seo["description"],
                                    tags=tags, channel_tags="#Shorts #HindiRhymes #बालगीत", privacy=settings.PRIVACY,
                                    category_id=settings.CATEGORY_ID, made_for_kids=settings.MADE_FOR_KIDS, thumbnail=str(th))
            meta["youtube_url"] = url
            if source == "gemini":
                gen = settings.EPISODE_DIR / "generated"; gen.mkdir(exist_ok=True)
                (gen / f"{ep['id']}.json").write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            episode.record(hist, ep, source, url)
            episode.save_history(hist)
            try:
                from uploader.storage import archive_run
                archive_run(str(final), meta, meta["run_id"] or datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S"))
            except Exception as e:      # archive is optional; never fail a published run on it
                print(f"     ⚠ archive skipped: {e}")
            banner(f"✅  Published → {url}")
        else:
            banner(f"✅  Built (no upload): {final}")
        (work / "run_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        banner(f"❌  Kids pipeline failed: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
