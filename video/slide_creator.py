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
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Pollinations failed after 3 attempts: {last_err}")


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


def _generate_bg_image(prompt: str, idx: int) -> Path:
    """Generate one background image. Returns Path to JPG file."""
    Path(BG_DIR).mkdir(parents=True, exist_ok=True)
    out = Path(BG_DIR) / f"bg_{idx:02d}.jpg"

    styled = (
        f"{prompt}, cinematic, photorealistic, dramatic lighting, "
        "rich colors, 4k highly detailed, vertical 9:16 composition, no text, no watermarks"
    )

    print(f"     → AI background {idx + 1}: {prompt[:60]}…")

    if IMAGE_PROVIDER == "dalle":
        return _gen_bg_dalle(styled, out)
    return _gen_bg_pollinations(styled, out, seed=idx * 1000 + datetime.date.today().toordinal())


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


# ───────────────────────── single slide ────────────────────────────────────

def _make_slide(slide_data: dict, idx: int, total: int,
                bg_image_path: Path, theme: dict) -> str:
    Path(SLIDES_DIR).mkdir(parents=True, exist_ok=True)
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT
    accent = theme["accent"]

    # ── 1. Load AI background and resize to fill canvas ──────────────────────
    bg = Image.open(bg_image_path).convert("RGBA")
    bg = _resize_cover(bg, W, H)

    # ── 2. Apply gradient overlays for legibility ────────────────────────────
    bg = _apply_top_caption_gradient(bg)
    bg = _apply_dark_gradient(bg, strength=0.6)

    img = bg.convert("RGBA")
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

    # ── 5. Bottom dark strip with sub_text (Hindi) ───────────────────────────
    sub_text = slide_data.get("sub_text", "").strip()
    strip_h = int(H * 0.24)
    strip_y = H - strip_h - 8
    draw.rectangle([(0, strip_y), (W, H - 8)], fill=(15, 13, 30, 220))

    if sub_text:
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

    # ── 6. Progress dots above the strip ─────────────────────────────────────
    dot_y = strip_y - 32
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

    # ── Save ──────────────────────────────────────────────────────────────────
    out = img.convert("RGB")
    path = os.path.join(SLIDES_DIR, f"slide_{idx:02d}.png")
    out.save(path, "PNG")
    return path


# ───────────────────────── public API ──────────────────────────────────────

def create_slides(slides: list) -> list:
    """
    Create all slide PNGs (with AI-generated backgrounds).
    Returns list of file paths in order.
    """
    theme_idx = datetime.date.today().toordinal() % len(THEMES)
    theme = THEMES[theme_idx]

    paths = []
    for i, slide_data in enumerate(slides):
        prompt = slide_data.get("image_prompt") or "warm cinematic Indian historical scene"
        bg_path = _generate_bg_image(prompt, i)
        slide_path = _make_slide(slide_data, i, len(slides), bg_path, theme)
        paths.append(slide_path)
        print(f"     → Slide {i + 1}/{len(slides)}: {slide_data.get('type', '?')}")
    return paths
