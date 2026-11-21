"""1280x720 thumbnail: Peelu close-up in the reeds + up to three short Hindi lines + 'AI Generated' tag."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import fx
from .chars import duckling, mango, render as crender


def make(ep, work):
    TW, TH = 1280, 720
    pano = Image.open(work / "pano.png").convert("RGB")
    bg = pano.resize((TW, TH), Image.BILINEAR, box=(1330, 640, 2400, 640 + 1070 * TH / TW)).filter(ImageFilter.GaussianBlur(2.5))
    sad = ep.get("peelu_mood") in ("sad", "scared")
    tint = np.array([0.86, 0.93, 1.04]) * 0.92 if (sad or ep["event"] == "rain") else np.array([1.04, 1.0, 0.96])
    bg = Image.fromarray(np.clip(np.asarray(bg, np.float32) * tint, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(bg, "RGBA")
    s = 175
    parts, dec, (w, h), (ax, ay) = duckling(s, 1, bow=True, mood="sad" if sad else "happy", beak=0.5)
    im = crender(parts, w, h, decals=dec)
    a = np.array(im); a[int(ay) + 1:, :, 3] = 0; im = Image.fromarray(a, "RGBA")
    sx, sy = 330, 650
    for k in range(3):
        rx = s * (1.0 + 0.35 * k); d.ellipse([sx - rx, sy - rx * 0.2, sx + rx, sy + rx * 0.2], outline=(255, 255, 255, 90 - 25 * k), width=4)
    bg.alpha_composite(im, (int(sx - ax), int(sy - ay)))
    if ep.get("peelu_mood") == "sad":
        ex, ey = sx + 0.58 * s, sy - 1.27 * s
        fx.tear(d, ex + 0.06 * s, ey + 0.32 * s, 26); fx.tear(d, ex + 0.44 * s, ey + 0.30 * s, 20)
    if ep["event"] == "treat":
        mp, md, (mw, mh), (mx, my) = mango(70)
        bg.alpha_composite(crender(mp, mw, mh, decals=md), (int(sx + 1.2 * s - mx), int(sy - 0.8 * s - my)))
    if ep["event"] == "rain":
        lay = Image.new("RGBA", (TW, TH), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        import random
        rng = random.Random(3)
        for k in range(140):
            x, y = rng.uniform(0, TW + 100), rng.uniform(-50, TH)
            dl.line([(x, y), (x + 12, y - 60)], fill=(230, 240, 255, 110), width=3)
        bg.alpha_composite(lay)
    th = ep["thumb"]
    def T(txt, size, fill, stroke, cx, cy, rot):
        if txt: fx.paste_scaled(bg, fx.text_img(txt, size, fill, 12, stroke), cx, cy, 1.0, 1.0, rot)
    T(th.get("l1"), 150, (255, 225, 60), (150, 50, 0), 900, 175, -4)
    T(th.get("l2"), 165, (255, 255, 255), (200, 30, 60), 905, 365, -4)
    T(th.get("l3"), 92, (255, 170, 210), (110, 20, 70), 915, 540, -3)
    f = fx.F(30, 700, "Mukta"); lab = "AI Generated"
    wl = d.textlength(lab, font=f); x1, y1 = TW - 24, TH - 22; x0, y0 = x1 - wl - 30, y1 - 46
    d.rounded_rectangle([x0, y0, x1, y1], 12, fill=(0, 0, 0, 175), outline=(255, 255, 255, 200), width=2)
    d.text((x0 + 15, y0 + 5), lab, font=f, fill=(255, 255, 255, 240))
    out = work / "thumbnail.jpg"
    bg.convert("RGB").save(out, quality=92)
    return out
