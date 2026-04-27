"""
assembler.py
============
Stitches slide images + voiceover audio into a final MP4 with:
  • Ken Burns zoom/pan effect per slide
  • Word-timed SRT subtitles (Hindi, Devanagari) burned into the video
  • Full AAC audio from the edge-tts voiceover

Pipeline:
  1. For each slide → apply Ken Burns scale+crop → individual clip MP4
  2. Cross-fade clips together into a silent video
  3. Burn Hindi subtitles using a Devanagari font (libass)
  4. Mix in audio → final_video.mp4
"""

import os
import math
import subprocess
from pathlib import Path
from config import (
    VIDEO_WIDTH, VIDEO_HEIGHT, FPS,
    VIDEO_FILE, OUTPUT_DIR, MIN_SLIDE_DURATION,
    SUBTITLE_FONT_NAME,
)


# ─────────────────────────────────────────────────────────────────────────────
def calculate_slide_durations(slides_data: list, total_audio_sec: float) -> list:
    """
    Distribute total audio duration across slides proportionally by
    spoken_text character count. Enforces MIN_SLIDE_DURATION per slide.
    """
    char_counts = [max(1, len(s.get("spoken_text", ""))) for s in slides_data]
    total_chars = sum(char_counts)

    raw = [(c / total_chars) * total_audio_sec for c in char_counts]

    deficit = sum(max(0, MIN_SLIDE_DURATION - d) for d in raw)
    excess  = sum(max(0, d - MIN_SLIDE_DURATION) for d in raw)

    if deficit > 0 and excess > 0:
        scale = max(0, (excess - deficit) / excess)
        raw = [
            MIN_SLIDE_DURATION if d < MIN_SLIDE_DURATION
            else MIN_SLIDE_DURATION + (d - MIN_SLIDE_DURATION) * scale
            for d in raw
        ]

    total_raw = sum(raw)
    durations = [d * (total_audio_sec / total_raw) for d in raw]
    return durations


# ─────────────────────────────────────────────────────────────────────────────
def _build_srt(slides_data: list, durations: list) -> str:
    """
    Generate an SRT subtitle file from slide spoken_text fields.
    Each line holds ~5 Hindi words, timed proportionally within each slide.
    """
    srt_path = os.path.join(OUTPUT_DIR, "subs.srt")
    lines = []
    idx = 1
    t = 0.0

    WORDS_PER_LINE = 5  # Hindi words tend to be longer — fewer per line

    for slide, dur in zip(slides_data, durations):
        spoken = slide.get("spoken_text", "").strip()
        words  = spoken.split()
        if not words:
            t += dur
            continue

        chunks = []
        for i in range(0, len(words), WORDS_PER_LINE):
            chunks.append(" ".join(words[i:i + WORDS_PER_LINE]))

        chunk_dur = dur / len(chunks)
        for chunk in chunks:
            start = t
            end   = t + chunk_dur
            lines.append(
                f"{idx}\n"
                f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n"
                f"{chunk}\n"
            )
            idx += 1
            t = end

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return srt_path


def _fmt_srt_time(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds - math.floor(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ─────────────────────────────────────────────────────────────────────────────
def _encode_slide_clip(slide_path: str, duration: float,
                       clip_index: int, zoom_direction: str) -> str:
    clip_path = os.path.join(OUTPUT_DIR, f"_clip_{clip_index:03d}.mp4")

    PAD   = int(VIDEO_WIDTH  * 0.10)
    PAD_H = int(VIDEO_HEIGHT * 0.10)
    W_BIG = VIDEO_WIDTH  + PAD
    H_BIG = VIDEO_HEIGHT + PAD_H

    dur_expr = f"{duration:.4f}"

    if zoom_direction == "in":
        x_crop = f"'({PAD}/2)*(1 - t/{dur_expr})'"
        y_crop = f"'({PAD_H}/2)*(1 - t/{dur_expr})'"
    else:
        x_crop = f"'({PAD}/2)*(t/{dur_expr})'"
        y_crop = f"'({PAD_H}/2)*(t/{dur_expr})'"

    vf = (
        f"scale={W_BIG}:{H_BIG},"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:{x_crop}:{y_crop},"
        f"setsar=1,"
        f"fps={FPS}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-t", f"{duration:.4f}",
        "-i", os.path.abspath(slide_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        clip_path,
    ]
    _run(cmd, f"Ken Burns clip {clip_index + 1}")
    return clip_path


# ─────────────────────────────────────────────────────────────────────────────
def _xfade_clips(clip_paths: list, durations: list, output_path: str,
                 transition: str = "fade", trans_dur: float = 0.4):
    n = len(clip_paths)

    inputs = []
    for cp in clip_paths:
        inputs += ["-i", cp]

    filter_parts = []
    running_offset = 0.0
    prev_label = "[0:v]"

    for i in range(1, n):
        running_offset += durations[i - 1] - trans_dur
        curr_label = f"[v{i}]" if i < n - 1 else "[vout]"
        filter_parts.append(
            f"{prev_label}[{i}:v]xfade="
            f"transition={transition}:"
            f"duration={trans_dur}:"
            f"offset={running_offset:.4f}"
            f"{curr_label}"
        )
        prev_label = curr_label

    filter_complex = ";".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-c:v", "libx264",
            "-preset", "faster",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    )
    _run(cmd, f"xfade transitions ({transition})")


# ─────────────────────────────────────────────────────────────────────────────
def assemble_video(slide_paths: list,
                   audio_file:  str,
                   durations:   list,
                   slides_data: list = None) -> str:
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    print("     · Encoding Ken Burns clips …")
    clip_paths = []
    directions = ["in", "out"]
    for i, (path, dur) in enumerate(zip(slide_paths, durations)):
        direction = directions[i % 2]
        clip = _encode_slide_clip(path, dur, i, direction)
        clip_paths.append(clip)

    temp_silent = os.path.join(OUTPUT_DIR, "_temp_silent.mp4")
    if len(clip_paths) == 1:
        import shutil
        shutil.copy(clip_paths[0], temp_silent)
    else:
        _xfade_clips(clip_paths, durations, temp_silent)

    if slides_data:
        print("     · Building Hindi SRT subtitles …")
        srt_path = _build_srt(slides_data, durations)
    else:
        srt_path = None

    temp_subbed = os.path.join(OUTPUT_DIR, "_temp_subbed.mp4")

    if srt_path and os.path.exists(srt_path):
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        # Devanagari-capable font for Hindi subtitle rendering via libass
        sub_style = (
            f"FontName={SUBTITLE_FONT_NAME},"
            "FontSize=20,"
            "Bold=1,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BorderStyle=1,"
            "Outline=3,"
            "Shadow=1,"
            "Alignment=2,"
            "MarginV=140"
        )
        vf_subs = f"subtitles='{srt_escaped}':force_style='{sub_style}'"
        cmd_subs = [
            "ffmpeg", "-y",
            "-i", temp_silent,
            "-vf", vf_subs,
            "-c:v", "libx264",
            "-preset", "faster",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            temp_subbed,
        ]
        _run(cmd_subs, "Burning Hindi subtitles")
        video_before_audio = temp_subbed
    else:
        video_before_audio = temp_silent

    cmd_audio = [
        "ffmpeg", "-y",
        "-i", video_before_audio,
        "-i", audio_file,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        VIDEO_FILE,
    ]
    _run(cmd_audio, "Adding audio track")

    for f in [temp_silent, temp_subbed]:
        try:
            os.remove(f)
        except OSError:
            pass
    for cp in clip_paths:
        try:
            os.remove(cp)
        except OSError:
            pass

    print(f"     → Final video: {VIDEO_FILE}")
    return VIDEO_FILE


def _run(cmd: list, label: str):
    print(f"     · {label} …")
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")
        raise RuntimeError(f"FFmpeg failed ({label}):\n{stderr[-1500:]}")
