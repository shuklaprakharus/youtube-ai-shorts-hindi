#!/usr/bin/env python3
"""
main.py — AI YouTube Shorts Generator
======================================
Fully automated daily pipeline:
  Topic → Script → Voiceover → Slides → Video → YouTube

Runs every day via GitHub Actions. Zero manual steps required.
"""

import os
import sys
import datetime
import json
import traceback
from pathlib import Path


def banner(msg: str):
    print(f"\n{'─'*60}")
    print(f"  {msg}")
    print(f"{'─'*60}")


def setup_dirs():
    Path("output/slides").mkdir(parents=True, exist_ok=True)


def main() -> int:
    banner(f"🤖  AI Shorts Generator  ·  {datetime.date.today()}")

    try:
        setup_dirs()

        # ── Late imports so missing deps give a clear error ──────────────────
        from agents.topic_agent  import TopicAgent
        from agents.script_agent import ScriptAgent
        from agents.seo_agent    import SEOAgent
        from video.tts           import generate_voiceover, get_audio_duration
        from video.slide_creator import create_slides
        from video.assembler     import assemble_video, calculate_slide_durations
        from uploader.youtube    import upload_to_youtube
        from uploader.storage    import archive_run
        from preflight           import validate_environment

        validate_environment(require_youtube=True)

        # ── 1. Pick today's topic ────────────────────────────────────────────
        print("\n📌  [1/6] Picking topic …")
        topic = TopicAgent().get_today_topic()
        print(f"     → {topic}")

        # ── 2. Write script ──────────────────────────────────────────────────
        print("\n📝  [2/6] Writing script …")
        script_data = ScriptAgent().generate_script(topic)
        print(f"     → {len(script_data['slides'])} slides | "
              f"{len(script_data['full_script'])} characters")

        # ── 3. Generate SEO metadata ─────────────────────────────────────────
        print("\n🔍  [3/6] Generating SEO metadata …")
        seo = SEOAgent().generate_seo(topic, script_data["full_script"])
        print(f"     → Title: {seo['title']}")

        # ── 4. Generate voiceover ────────────────────────────────────────────
        print("\n🎙️  [4/6] Generating voiceover …")
        audio_file = generate_voiceover(script_data["full_script"])
        duration   = get_audio_duration(audio_file)
        print(f"     → {duration:.1f}s of audio")

        # ── 5. Create slide images ───────────────────────────────────────────
        print("\n🖼️  [5/6] Creating slides …")
        slide_paths = create_slides(script_data["slides"])
        durations   = calculate_slide_durations(script_data["slides"], duration)

        # ── 6. Assemble video & upload ───────────────────────────────────────
        print("\n🎬  [6/6] Assembling video …")
        video_file = assemble_video(
            slide_paths = slide_paths,
            audio_file  = audio_file,
            durations   = durations,
            slides_data = script_data["slides"],   # for Ken Burns + subtitles
        )

        print("\n📤  Uploading to YouTube …")
        url = upload_to_youtube(
            video_file   = video_file,
            title        = seo["title"],
            description  = seo["description"],
            tags         = seo["tags"],
        )

        run_id = os.environ.get("GITHUB_RUN_ID") or datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        metadata = {
            "date": datetime.date.today().isoformat(),
            "run_id": run_id,
            "topic": json.loads(topic),
            "seo": seo,
            "youtube_url": url,
            "slides": script_data["slides"],
        }

        print("\n🪣  Archiving run artifacts …")
        archive_run(video_file, metadata, run_id)

        banner(f"✅  Published → {url}")
        return 0

    except Exception as exc:
        banner(f"❌  Pipeline failed: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
