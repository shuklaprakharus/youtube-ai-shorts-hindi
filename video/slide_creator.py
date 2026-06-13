"""
slide_creator.py
================
Creates 1080×1920 (9:16) slide PNGs for Hindi YouTube Shorts.

Pipeline per slide:
  1. Generate an AI background image relevant to the slide's content via
     Pollinations.ai (free, no API key) using the slide's `image_prompt` field.
  2. Apply a vertical darkening gradient at the bottom for text legibility.
  3. Overlay the existing on-screen UI elements:
        • caption pill at top (main_text)
        • dark text strip near bottom with Hindi sub_text
        • coloured progress dots
        • thin India-themed accent bars top + bottom
"""

import os
import math
import random
import re
import time
import urllib.parse
import datetime
import textwrap
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import (
    VIDEO_WIDTH, VIDEO_HEIGHT,
    SLIDES_DIR, BG_DIR, THEMES,
    HINDI_FONT_CANDIDATES,
    IMAGE_PROVIDER, OPENAI_API_KEY,
    PEXELS_API_KEY, AVOID_FACES,
)


# ───────────────────────── font loader ─────────────────────────────────────

def _load_hindi_font(size: int) -> ImageFont.FreeTypeFont:
    """Find first available Devanagari TTF and return a sized font."""
    for path in HINDI_FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Last-resort fallback — won't render Devanagari correctly
    print(
        "⚠️  No Devanagari font found! Slides will look broken. "
        "Install via: sudo apt install fonts-noto-core libraqm-dev"
    )
    return ImageFont.load_default()


# ───────────────────────── AI background generation ───────────────────────

def _pollinations_url(prompt: str, seed: int) -> str:
    encoded = urllib.parse.quote(prompt)
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1024&height=1820&seed={seed}&nologo=true&enhance=true&model=flux"
    )


def _gen_bg_pollinations(prompt: str, out_path: Path, seed: int) -> Path:
    url = _pollinations_url(prompt, seed=seed)
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=180)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
            return out_path
        except requests.RequestException as e:
            last_err = e
            status = getattr(e.response, "status_code", None)
            # 4xx (except 429) won't resolve by retrying — e.g. 402 paywall
            if status and status != 429 and 400 <= status < 500:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Pollinations failed: {last_err}")


def _gen_bg_dalle(prompt: str, out_path: Path) -> Path:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set; cannot use DALL-E provider.")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}",
               "Content-Type": "application/json"}
    body = {
        "model": "dall-e-3", "prompt": prompt, "n": 1,
        "size": "1024x1792", "quality": "standard",
    }
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers=headers, json=body, timeout=120,
    )
    resp.raise_for_status()
    img_url = resp.json()["data"][0]["url"]
    img_data = requests.get(img_url, timeout=60)
    img_data.raise_for_status()
    out_path.write_bytes(img_data.content)
    return out_path


def _gen_bg_fallback(out_path: Path, idx: int) -> Path:
    """
    Procedural themed background — vertical gradient in the day's theme
    colour with soft glow circles. Used when the AI image provider fails,
    so a third-party outage or paywall can never kill the daily run.
    """
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    accent = THEMES[datetime.date.today().toordinal() % len(THEMES)]["accent"]
    rng = random.Random(idx * 7919 + datetime.date.today().toordinal())

    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    top = tuple(int(c * 0.15) for c in accent)
    bottom = tuple(min(255, int(c * 0.6) + 25) for c in accent)
    for y in range(h):
        t = y / (h - 1)
        draw.line(
            [(0, y), (w, y)],
            fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)),
        )

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    tint = tuple(min(255, c + 80) for c in accent)
    for _ in range(4):
        r = rng.randint(180, 420)
        cx, cy = rng.randint(0, w), rng.randint(0, h)
        odraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*tint, 70))
    overlay = overlay.filter(ImageFilter.GaussianBlur(120))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    img.save(out_path, "JPEG", quality=90)
    return out_path


def _generate_bg_image(prompt: str, idx: int) -> Path:
    """Generate one background image. Returns Path to JPG file."""
    Path(BG_DIR).mkdir(parents=True, exist_ok=True)
    out = Path(BG_DIR) / f"bg_{idx:02d}.jpg"

    styled = (
        f"{prompt}, cinematic, photorealistic, dramatic lighting, "
        "rich colors, 4k highly detailed, vertical 9:16 composition, no text, no watermarks"
    )

    print(f"     → AI background {idx + 1}: {prompt[:60]}…")

    try:
        if IMAGE_PROVIDER == "dalle":
            return _gen_bg_dalle(styled, out)
        return _gen_bg_pollinations(styled, out, seed=idx * 1000 + datetime.date.today().toordinal())
    except Exception as e:
        print(f"     ⚠️  AI background failed ({e}); using themed fallback background.")
        return _gen_bg_fallback(out, idx)


# ───────────────────────── face detection (avoid likeness issues) ──────────
# We never show identifiable human faces in stock media: it's a likeness/
# personality-rights risk and generic stock people rarely fit an AI track.
# OpenCV's Haar cascade rejects any candidate that contains a face, so the
# selectors fall through to a face-free clip/photo (or the gradient).

_FACE_CASCADE = None
_FACE_CASCADE_READY = False


def _face_cascade():
    global _FACE_CASCADE, _FACE_CASCADE_READY
    if _FACE_CASCADE_READY:
        return _FACE_CASCADE
    _FACE_CASCADE_READY = True
    try:
        import cv2
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        if cascade.empty():
            raise RuntimeError("cascade file failed to load")
        _FACE_CASCADE = cascade
    except Exception as e:
        print(f"     ⚠️  Face detection unavailable ({e}); face filter disabled.")
        _FACE_CASCADE = None
    return _FACE_CASCADE


def _gray_has_face(gray) -> bool:
    cascade = _face_cascade()
    if cascade is None:
        return False
    import cv2
    h, w = gray.shape[:2]
    scale = 720 / max(h, w) if max(h, w) > 720 else 1.0
    if scale < 1.0:
        gray = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))))
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=6, minSize=(36, 36)
    )
    return len(faces) > 0


def _image_has_face(path: str) -> bool:
    if not AVOID_FACES or _face_cascade() is None:
        return False
    try:
        import cv2
        img = cv2.imread(path)
        if img is None:
            return False
        return _gray_has_face(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    except Exception:
        return False


def _video_has_face(path: str, samples: int = 6) -> bool:
    if not AVOID_FACES or _face_cascade() is None:
        return False
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
            if frame_count > 0:
                points = [int(frame_count * (k + 0.5) / samples) for k in range(samples)]
                for p in points:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, p)
                    ok, frame = cap.read()
                    if ok and _gray_has_face(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)):
                        return True
            else:
                for _ in range(samples):           # unknown length → read serially
                    ok, frame = cap.read()
                    if not ok:
                        break
                    if _gray_has_face(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)):
                        return True
        finally:
            cap.release()
    except Exception:
        return False
    return False


# ───────────────────────── Pexels stock footage/photos ─────────────────────

def _stock_query(slide_data: dict) -> str:
    query = (slide_data.get("stock_query") or "").strip()
    if query:
        return query
    # Fall back to the first few English words of the image prompt
    words = re.findall(r"[A-Za-z]+", slide_data.get("image_prompt", ""))
    return " ".join(words[:5]) or "cinematic india"


def _pexels_get(url: str, params: dict) -> dict:
    resp = requests.get(
        url,
        headers={"Authorization": PEXELS_API_KEY},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _pexels_video(query: str, idx: int) -> str | None:
    """Download a vertical stock video clip for the slide, or None."""
    if not PEXELS_API_KEY:
        return None
    try:
        data = _pexels_get(
            "https://api.pexels.com/videos/search",
            {"query": query, "orientation": "portrait", "per_page": 12},
        )
        videos = data.get("videos") or []
        rng = random.Random(datetime.date.today().toordinal() * 31 + idx)
        rng.shuffle(videos)
        Path(BG_DIR).mkdir(parents=True, exist_ok=True)
        tmp = Path(BG_DIR) / f"_tmp_bgv_{idx:02d}.mp4"
        out = Path(BG_DIR) / f"bgv_{idx:02d}.mp4"
        downloads = 0
        for video in videos:
            files = [
                f for f in video.get("video_files", [])
                if f.get("link") and f.get("width") and f.get("height")
                and f["height"] > f["width"]            # portrait only
                and 960 <= f["height"] <= 2200          # enough pixels, sane size
            ]
            if not files:
                continue
            if downloads >= 6:                          # bound bandwidth/time
                break
            best = max(files, key=lambda f: f["height"])
            blob = requests.get(best["link"], timeout=120)
            blob.raise_for_status()
            tmp.write_bytes(blob.content)
            downloads += 1
            if _video_has_face(str(tmp)):
                print("     · stock video has a face — trying another clip")
                tmp.unlink(missing_ok=True)
                continue
            tmp.replace(out)
            return str(out)
        tmp.unlink(missing_ok=True)
    except Exception as e:
        print(f"     ⚠️  Pexels video search failed ({e})")
    return None


def _pexels_photo(query: str, idx: int) -> str | None:
    """Download a vertical stock photo for the slide, or None."""
    if not PEXELS_API_KEY:
        return None
    try:
        data = _pexels_get(
            "https://api.pexels.com/v1/search",
            {"query": query, "orientation": "portrait", "per_page": 12},
        )
        photos = data.get("photos") or []
        rng = random.Random(datetime.date.today().toordinal() * 31 + idx)
        rng.shuffle(photos)
        Path(BG_DIR).mkdir(parents=True, exist_ok=True)
        tmp = Path(BG_DIR) / f"_tmp_bg_{idx:02d}.jpg"
        out = Path(BG_DIR) / f"bg_{idx:02d}.jpg"
        for photo in photos:
            src = (photo.get("src") or {}).get("portrait") or (photo.get("src") or {}).get("large2x")
            if not src:
                continue
            blob = requests.get(src, timeout=60)
            blob.raise_for_status()
            tmp.write_bytes(blob.content)
            if _image_has_face(str(tmp)):
                print("     · stock photo has a face — trying another photo")
                tmp.unlink(missing_ok=True)
                continue
            tmp.replace(out)
            return str(out)
        tmp.unlink(missing_ok=True)
    except Exception as e:
        print(f"     ⚠️  Pexels photo search failed ({e})")
    return None


# ───────────────────────── compositing helpers ────────────────────────────

def _resize_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize image to cover target box (crop excess), preserving aspect."""
    iw, ih = img.size
    scale = max(target_w / iw, target_h / ih)
    new_w, new_h = int(iw * scale + 0.5), int(ih * scale + 0.5)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    # Centre-crop
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _apply_dark_gradient(img: Image.Image, strength: float = 0.55) -> Image.Image:
    """
    Add a vertical gradient that darkens the bottom 40% of the image so the
    text strip remains readable on top of any background.
    """
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = overlay.load()

    grad_start = int(h * 0.45)  # gradient begins ~45% down
    for y in range(grad_start, h):
        # alpha rises from 0 → strength*255 over the bottom 55%
        progress = (y - grad_start) / (h - grad_start)
        a = int(strength * 255 * progress)
        for x in range(w):
            px[x, y] = (0, 0, 0, a)

    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _apply_top_caption_gradient(img: Image.Image, strength: float = 0.35) -> Image.Image:
    """A subtle gradient at the top so the caption pill stands out."""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = overlay.load()

    grad_end = int(h * 0.18)
    for y in range(0, grad_end):
        progress = 1 - (y / grad_end)
        a = int(strength * 255 * progress)
        for x in range(w):
            px[x, y] = (0, 0, 0, a)

    return Image.alpha_composite(img.convert("RGBA"), overlay)


# ───────────────────────── text rendering ──────────────────────────────────

def _draw_text_centered(draw, text, font, y, color, max_width):
    """Render single-line text centered horizontally at y. Returns new y."""
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = (VIDEO_WIDTH - tw) // 2
    draw.text((x, y), text, font=font, fill=color)
    return y + th


def _draw_wrapped_text(draw, text, font, y, color, max_width, line_gap=14):
    """Wrap Hindi text to multiple lines and draw each centered. Returns new y."""
    if not text:
        return y

    # Hindi text — wrap by character width since words can be long
    avg_char = font.getbbox("क")[2] or 30
    chars_per_line = max(8, int(max_width / avg_char))
    lines = textwrap.wrap(text, width=chars_per_line) or [text]

    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        x = (VIDEO_WIDTH - tw) // 2
        draw.text((x, y), line, font=font, fill=color)
        y += th + line_gap
    return y


# ───────────────────────── slide overlay + compositing ─────────────────────

def _render_overlay(slide_data: dict, idx: int, total: int, theme: dict) -> str:
    """
    Render every UI element (legibility scrims, accent bars, caption pill,
    text strip, progress dots) on a TRANSPARENT canvas. Composited over photo
    backgrounds in Python and over stock-video backgrounds by ffmpeg.
    """
    Path(SLIDES_DIR).mkdir(parents=True, exist_ok=True)
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT
    accent = theme["accent"]

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img = _apply_top_caption_gradient(img)
    img = _apply_dark_gradient(img, strength=0.6)
    draw = ImageDraw.Draw(img)

    # ── 3. Top accent bar (India-themed) ─────────────────────────────────────
    draw.rectangle([(0, 0), (W, 12)], fill=(*accent, 255))

    # ── 4. Caption pill at top with main_text (Hindi) ────────────────────────
    main_text = slide_data.get("main_text", "").strip()
    if main_text:
        cap_font = _load_hindi_font(58)
        bb = draw.textbbox((0, 0), main_text, font=cap_font)
        cw, ch = bb[2] - bb[0], bb[3] - bb[1]
        cap_pad_x, cap_pad_y = 32, 18
        py_top = 56
        px_left = (W - cw) // 2
        # Dark pill behind text
        draw.rounded_rectangle(
            [px_left - cap_pad_x, py_top - cap_pad_y,
             px_left + cw + cap_pad_x, py_top + ch + cap_pad_y],
            radius=20, fill=(20, 18, 35, 220)
        )
        draw.text((px_left, py_top), main_text, font=cap_font, fill=(255, 255, 255))

    # ── 5. Bottom dark strip with sub_text (omitted when slide has none) ─────
    sub_text = slide_data.get("sub_text", "").strip()
    strip_h = int(H * 0.24)
    strip_y = H - strip_h - 8
    if sub_text:
        draw.rectangle([(0, strip_y), (W, H - 8)], fill=(15, 13, 30, 220))
        sub_font = _load_hindi_font(64)
        # Vertical-center the sub_text in the strip
        avg_char = sub_font.getbbox("क")[2] or 32
        chars_per_line = max(8, int((W - 100) / avg_char))
        lines = textwrap.wrap(sub_text, width=chars_per_line) or [sub_text]
        line_h = sub_font.getbbox("कख")[3] + 18
        block_h = line_h * len(lines)
        text_y = strip_y + (strip_h - block_h) // 2

        for line in lines:
            bb = draw.textbbox((0, 0), line, font=sub_font)
            tw = bb[2] - bb[0]
            x = (W - tw) // 2
            draw.text((x, text_y), line, font=sub_font, fill=(255, 235, 180))  # warm gold
            text_y += line_h
        dot_anchor = strip_y
    else:
        dot_anchor = H - 80   # no strip — dots sit near the bottom edge

    # ── 6. Progress dots above the strip (or bottom edge) ────────────────────
    dot_y = dot_anchor - 32
    dot_r = 9
    dot_gap = 32
    total_w = total * (dot_r * 2) + (total - 1) * (dot_gap - dot_r * 2)
    dot_x = (W - total_w) // 2
    for i in range(total):
        cx_d = dot_x + i * dot_gap + dot_r
        if i == idx:
            draw.ellipse(
                [cx_d - dot_r - 3, dot_y - dot_r - 3,
                 cx_d + dot_r + 3, dot_y + dot_r + 3],
                fill=(*accent, 255)
            )
        else:
            draw.ellipse(
                [cx_d - dot_r, dot_y - dot_r, cx_d + dot_r, dot_y + dot_r],
                fill=(220, 220, 220, 200)
            )

    # ── 7. Bottom accent bar ─────────────────────────────────────────────────
    draw.rectangle([(0, H - 8), (W, H)], fill=(*accent, 255))

    path = os.path.join(SLIDES_DIR, f"overlay_{idx:02d}.png")
    img.save(path, "PNG")
    return path


def _compose_slide(bg_image_path: str, overlay_path: str, idx: int) -> str:
    """Static slide: background photo under the transparent UI overlay."""
    bg = Image.open(bg_image_path).convert("RGBA")
    bg = _resize_cover(bg, VIDEO_WIDTH, VIDEO_HEIGHT)
    overlay = Image.open(overlay_path).convert("RGBA")
    out = Image.alpha_composite(bg, overlay).convert("RGB")
    path = os.path.join(SLIDES_DIR, f"slide_{idx:02d}.png")
    out.save(path, "PNG")
    return path


# ───────────────────────── public API ──────────────────────────────────────

def create_slides(slides: list) -> list:
    """
    Create one background per slide. Preference order:
      1. Pexels stock VIDEO  (needs PEXELS_API_KEY)
      2. Pexels stock photo  (needs PEXELS_API_KEY)
      3. AI image provider   (pollinations/dalle)
      4. Procedural themed gradient
    Returns a list of entries for assemble_video:
      str  → finished slide PNG (static background, Ken Burns motion)
      dict → {"video": stock_clip_path, "overlay": transparent_ui_png}
    """
    theme_idx = datetime.date.today().toordinal() % len(THEMES)
    theme = THEMES[theme_idx]

    entries = []
    total = len(slides)
    for i, slide_data in enumerate(slides):
        overlay = _render_overlay(slide_data, i, total, theme)
        query = _stock_query(slide_data)

        video = _pexels_video(query, i)
        if video:
            entries.append({"video": video, "overlay": overlay})
            print(f"     → Slide {i + 1}/{total}: {slide_data.get('type', '?')} (stock video: {query})")
            continue

        bg_path = _pexels_photo(query, i)
        kind = "stock photo"
        if not bg_path:
            prompt = slide_data.get("image_prompt") or "warm cinematic Indian scene"
            bg_path = _generate_bg_image(prompt, i)
            kind = "generated"
        entries.append(_compose_slide(bg_path, overlay, i))
        print(f"     → Slide {i + 1}/{total}: {slide_data.get('type', '?')} ({kind})")
    return entries
