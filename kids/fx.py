"""2D overlays: text, bursts, bubbles, hearts, tears, sparkles, rainbow, sun, butterfly, lily pad, reeds."""
import math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
from pathlib import Path
FD = str(Path(__file__).resolve().parent.parent / 'assets' / 'fonts') + '/'
_fc = {}
def F(size, w=800, fam='Baloo2'):
    k = (size, w, fam)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(f'{FD}{fam}-{w}.ttf', size, layout_engine=ImageFont.Layout.RAQM)
    return _fc[k]

def ease(x):
    x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)
def pop_scale(dt, dur=0.28):
    if dt < 0: return 0.0
    if dt > dur: return 1.0
    x = dt / dur
    return 1.18 * math.sin(x * math.pi * 0.62) / math.sin(math.pi * 0.62) if x < 0.75 else 1.18 - 0.18 * (x - 0.75) / 0.25

_tc = {}
def text_img(s, size, fill, stroke=8, stroke_fill=(60, 30, 10), w=800, shadow=True):
    k = (s, size, fill, stroke, stroke_fill, w, shadow)
    if k in _tc: return _tc[k]
    f = F(size, w)
    bb = ImageDraw.Draw(Image.new('L', (10, 10))).textbbox((0, 0), s, font=f, stroke_width=stroke)
    tw, th = bb[2] - bb[0] + 24, bb[3] - bb[1] + 30
    im = Image.new('RGBA', (tw, th), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if shadow:
        sh = Image.new('RGBA', (tw, th), (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
        ds.text((12 - bb[0], 18 - bb[1]), s, font=f, fill=(0, 0, 0, 120), stroke_width=stroke, stroke_fill=(0, 0, 0, 120))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)))
    d.text((12 - bb[0], 12 - bb[1]), s, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    _tc[k] = im
    return im

def paste_scaled(frame, im, cx, cy, sc, alpha=1.0, rot=0.0, clamp=False):
    if sc <= 0.02 or alpha <= 0.01: return
    w, h = max(1, int(im.width * sc)), max(1, int(im.height * sc))
    t = im.resize((w, h), Image.BILINEAR)
    if rot: t = t.rotate(rot, Image.BILINEAR, expand=True)
    if clamp:   # keep text bursts / bubbles fully on screen
        cx = min(max(cx, t.width / 2 + 12), frame.width - t.width / 2 - 12)
        cy = min(max(cy, t.height / 2 + 12), frame.height - t.height / 2 - 12)
    if alpha < 1:
        a = t.getchannel('A').point(lambda v: int(v * alpha)); t.putalpha(a)
    frame.paste(t, (int(cx - t.width / 2), int(cy - t.height / 2)), t)

def burst(frame, s, cx, cy, dt, dur=1.3, size=96, fill=(255, 230, 60), stroke_fill=(150, 50, 0), rot=-6):
    if dt < 0 or dt > dur: return
    a = 1.0 if dt < dur - 0.25 else (dur - dt) / 0.25
    wob = 1 + 0.04 * math.sin(dt * 14)
    paste_scaled(frame, text_img(s, size, fill, 9, stroke_fill), cx, cy - 30 * ease(dt / dur), pop_scale(dt) * wob, a, rot, clamp=True)

_bc = {}
def bubble_img(s, size=64, tail='left'):
    k = (s, size, tail)
    if k in _bc: return _bc[k]
    f = F(size, 800)
    bb = ImageDraw.Draw(Image.new('L', (10, 10))).textbbox((0, 0), s, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pw, ph = tw + 70, th + 56
    im = Image.new('RGBA', (pw + 20, ph + 70), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    tx = 50 if tail == 'left' else pw - 50
    sh = Image.new('RGBA', im.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
    ds.rounded_rectangle([14, 16, pw + 14, ph + 16], 40, fill=(0, 0, 0, 90))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    d.polygon([(tx - 18, ph - 6), (tx + 18, ph - 6), (tx - 26 if tail == 'left' else tx + 26, ph + 50)], fill=(255, 255, 255, 255), outline=(60, 40, 30, 255))
    d.rounded_rectangle([4, 4, pw, ph], 40, fill=(255, 255, 255, 255), outline=(60, 40, 30, 255), width=5)
    d.polygon([(tx - 15, ph - 9), (tx + 15, ph - 9), (tx - 22 if tail == 'left' else tx + 22, ph + 42)], fill=(255, 255, 255, 255))
    d.text((4 + 35 - bb[0], 4 + 26 - bb[1]), s, font=f, fill=(40, 30, 30, 255))
    _bc[k] = im
    return im

def bubble(frame, s, x, y, dt, dur, tail='left', size=64):
    """x,y = tip of the tail (speaker's mouth). The tail side flips if the bubble would leave the screen."""
    if dt < 0 or dt > dur: return
    im = bubble_img(s, size, tail)
    full_cx = x + (im.width / 2 - (50 if tail == 'left' else im.width - 70) + (24 if tail == 'left' else -24))
    if tail == 'right' and full_cx - im.width / 2 < 10 and x + im.width < W - 10:
        tail = 'left'; im = bubble_img(s, size, tail)
    elif tail == 'left' and full_cx + im.width / 2 > W - 10 and x - im.width > 10:
        tail = 'right'; im = bubble_img(s, size, tail)
    a = 1.0 if dt < dur - 0.2 else (dur - dt) / 0.2
    sc = pop_scale(dt, 0.25)
    tx = 50 if tail == 'left' else im.width - 70
    cx = x + (im.width / 2 - tx + (24 if tail == 'left' else -24)) * sc
    cy = y - (im.height - 20) * sc + im.height / 2 * sc
    paste_scaled(frame, im, cx, cy, sc, a, clamp=True)

def heart_pts(cx, cy, r):
    pts = []
    for k in range(40):
        t = 2 * math.pi * k / 40
        x = 16 * math.sin(t) ** 3; y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * r / 16, cy + y * r / 16))
    return pts

def hearts(d, t, t0, x, y, n=7, seed=1):
    rng = random.Random(seed)
    for k in range(n):
        st = t0 + k * 0.28; dt = t - st
        if dt < 0 or dt > 2.4: continue
        xx = x + rng.uniform(-90, 90) + 22 * math.sin(dt * 4 + k); yy = y - dt * 150
        r = rng.uniform(22, 38) * min(1, dt / 0.25)
        a = int(255 * (1 if dt < 1.8 else (2.4 - dt) / 0.6))
        col = rng.choice([(255, 80, 120), (255, 110, 160), (255, 60, 90)])
        d.polygon(heart_pts(xx, yy, r), fill=col + (a,))
        d.ellipse([xx - r * 0.55, yy - r * 0.55, xx - r * 0.2, yy - r * 0.25], fill=(255, 255, 255, int(a * 0.7)))

def tear(d, x, y, r, a=230):
    pts = []
    for k in range(30):
        th = 2 * math.pi * k / 30
        rr = r * (1 - 0.5 * max(0, -math.sin(th)) ** 2)
        yy = y + rr * math.sin(th) - (r * 1.1 * max(0, -math.sin(th)) ** 8)
        pts.append((x + rr * math.cos(th) * 0.8, yy))
    d.polygon(pts, fill=(120, 200, 255, a))
    d.ellipse([x - r * 0.35, y - r * 0.2, x - r * 0.05, y + r * 0.15], fill=(255, 255, 255, a))

def sparkle(d, x, y, r, a=255, col=(255, 250, 210)):
    pts = []
    for k in range(8):
        th = math.pi * k / 4; rr = r if k % 2 == 0 else r * 0.28
        pts.append((x + rr * math.cos(th), y + rr * math.sin(th)))
    d.polygon(pts, fill=col + (a,))

def rings(d, x, y, t, rate=1.6, n=3, base=60, grow=120, squash=0.25, col=(255, 255, 255), amax=110, width=4):
    for k in range(n):
        ph = (t * rate + k / n) % 1.0
        rx = base + grow * ph; ry = rx * squash
        a = int(amax * (1 - ph) ** 1.5)
        d.ellipse([x - rx, y - ry, x + rx, y + ry], outline=col + (a,), width=width)

def sound_rings(d, x, y, dt, dirn=1, n=4):
    for k in range(n):
        ph = dt * 1.6 - k * 0.22
        if ph < 0 or ph > 1: continue
        r = 40 + 260 * ph; a = int(220 * (1 - ph))
        bb = [x - r, y - r, x + r, y + r]
        if dirn > 0: d.arc(bb, -55, 55, fill=(255, 255, 255, a), width=9)
        else: d.arc(bb, 125, 235, fill=(255, 255, 255, a), width=9)

_sun = None
def sun_img():
    global _sun
    if _sun is None:
        S = 900; y, x = np.mgrid[0:S, 0:S].astype(np.float32); c = S / 2
        r = np.sqrt((x - c) ** 2 + (y - c) ** 2)
        glow = np.clip(1 - r / (S / 2), 0, 1) ** 2.2
        ang = np.arctan2(y - c, x - c)
        rays = (0.5 + 0.5 * np.cos(ang * 14)) ** 6 * np.clip(1 - r / (S / 2), 0, 1) ** 1.5 * 0.35
        disk = np.clip((95 - r) / 3, 0, 1)
        a = np.clip(glow * 0.85 + rays + disk, 0, 1)
        col = np.stack([np.full_like(a, 255), 228 + 22 * disk, 150 + 70 * disk], -1)
        _sun = Image.fromarray(np.dstack([col, a * 255]).astype(np.uint8), 'RGBA')
    return _sun

def rainbow(frame, cx, cy, R, alpha, horizon=660):
    if alpha <= 0.01: return
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    cols = [(255, 70, 70), (255, 150, 50), (255, 225, 60), (90, 210, 90), (70, 160, 255), (110, 90, 230), (180, 90, 230)]
    bw = 26
    for i, c in enumerate(cols):
        r = R - i * bw
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c + (255,), width=bw + 2)
    lay = lay.filter(ImageFilter.GaussianBlur(5))
    a = np.asarray(lay.getchannel('A'), np.float32)
    yy = np.arange(H, dtype=np.float32)[:, None]
    fade = np.clip((horizon - 70 - yy) / 150, 0, 1)
    lay.putalpha(Image.fromarray((a * fade * alpha * 0.55).astype(np.uint8)))
    frame.alpha_composite(lay)

_bf = {}
def butterfly_img(size, phase_q):
    k = (size, phase_q)
    if k in _bf: return _bf[k]
    ss = 2; S = size * ss
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    c = S / 2
    def wing(cx, cy, rx, ry, rot, c1, c2):
        lay = Image.new('RGBA', (S, S), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        dl.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=c2 + (255,), outline=(90, 30, 60, 255), width=int(S * 0.012))
        dl.ellipse([cx - rx * 0.62, cy - ry * 0.62, cx + rx * 0.62, cy + ry * 0.62], fill=c1 + (255,))
        dl.ellipse([cx - rx * 0.18, cy - ry * 0.18, cx + rx * 0.18, cy + ry * 0.18], fill=(255, 255, 255, 230))
        return lay.rotate(rot, center=(c, c), resample=Image.BICUBIC)
    for sx in (-1, 1):
        im.alpha_composite(wing(c + sx * S * 0.20, c + S * 0.12, S * 0.15, S * 0.12, -sx * 30, (255, 210, 70), (255, 120, 60)))
        im.alpha_composite(wing(c + sx * S * 0.22, c - S * 0.08, S * 0.22, S * 0.16, sx * 25, (255, 200, 90), (255, 80, 150)))
    d = ImageDraw.Draw(im)
    d.ellipse([c - S * 0.035, c - S * 0.2, c + S * 0.035, c + S * 0.2], fill=(70, 40, 60, 255))
    d.ellipse([c - S * 0.05, c - S * 0.27, c + S * 0.05, c - S * 0.17], fill=(70, 40, 60, 255))
    for sx in (-1, 1):
        d.line([(c + sx * S * 0.02, c - S * 0.25), (c + sx * S * 0.12, c - S * 0.40)], fill=(70, 40, 60, 255), width=int(S * 0.012))
        d.ellipse([c + sx * S * 0.12 - S * 0.02, c - S * 0.42, c + sx * S * 0.12 + S * 0.02, c - S * 0.38], fill=(70, 40, 60, 255))
    f = 0.38 + 0.62 * abs(math.cos(phase_q / 12 * math.pi))
    half = int(c)
    L = im.crop((0, 0, half, S)).resize((max(1, int(half * f)), S), Image.BICUBIC)
    R = im.crop((half, 0, S, S)).resize((max(1, int((S - half) * f)), S), Image.BICUBIC)
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    out.paste(L, (half - L.width, 0), L); out.paste(R, (half, 0), R)
    body = im.crop((int(c - S * 0.06), 0, int(c + S * 0.06), S))
    out.alpha_composite(body, (int(c - S * 0.06), 0))
    out = out.resize((size, size), Image.LANCZOS)
    _bf[k] = out
    return out

def draw_butterfly(frame, x, y, t, size=110, rot=0):
    q = int((t * 4.5 * 12) % 12)
    im = butterfly_img(size, q)
    if rot: im = im.rotate(rot, Image.BILINEAR)
    frame.paste(im, (int(x - im.width / 2), int(y - im.height / 2)), im)

def lily_pad_big(d, x, y, w, h, rot=60, col=(70, 165, 72)):
    dark = tuple(int(c * 0.6) for c in col)
    d.ellipse([x - w * 1.08, y - h * 0.9, x + w * 1.08, y + h * 1.25], fill=(20, 80, 100, 70))
    d.pieslice([x - w, y - h + h * 0.18, x + w, y + h + h * 0.18], rot + 14, rot - 14 + 360, fill=dark + (255,))
    d.pieslice([x - w, y - h, x + w, y + h], rot + 14, rot - 14 + 360, fill=col + (255,))
    hl = tuple(min(255, int(c * 1.22)) for c in col)
    d.pieslice([x - w * 0.8, y - h * 0.85, x + w * 0.5, y + h * 0.4], rot + 14, rot - 14 + 360, fill=hl + (100,))
    for k in range(8):
        a = math.radians(rot + 30 + k * 300 / 7)
        d.line([(x, y), (x + w * 0.88 * math.cos(a), y + h * 0.88 * math.sin(a))], fill=dark + (130,), width=3)

def fg_reeds(d, t, side, n=5, seed=3, amp=1.0, base_y=1920, h0=900):
    rng = random.Random(seed)
    for k in range(n):
        x0 = (rng.uniform(-40, 140) if side < 0 else W - rng.uniform(-40, 140))
        hgt = h0 * rng.uniform(0.7, 1.1); w = rng.uniform(14, 24)
        sway = amp * (0.10 * math.sin(t * 1.3 + k * 1.7) + 0.05 * math.sin(t * 2.9 + k))
        bend = side * rng.uniform(0.1, 0.4) + sway
        left, right = [], []
        for i in range(13):
            s = i / 12
            xx = x0 + bend * s * s * hgt * 0.5; yy = base_y - hgt * s
            ww = w * (1 - s) ** 0.8 + 1
            left.append((xx - ww, yy)); right.append((xx + ww, yy))
        g = rng.uniform(0.8, 1.0)
        d.polygon(left + right[::-1], fill=(int(30 * g), int(88 * g), int(44 * g), 255))
        d.polygon(left[6:] + right[6:][::-1], fill=(int(60 * g), int(130 * g), int(58 * g), 255))


# ---------------- weather ----------------
def rain(d, t, intensity=1.0, seed=5):
    """Slanted rain streaks over the whole frame (positions move with t, so it animates)."""
    if intensity <= 0.01: return
    rng = random.Random(seed)
    for k in range(int(170 * intensity)):
        x0 = rng.uniform(-150, W + 250); sp = rng.uniform(1500, 2100); ln = rng.uniform(45, 85)
        y = (rng.uniform(0, H + 200) + t * sp) % (H + 200) - 100
        x = x0 - y * 0.20
        d.line([(x, y), (x + ln * 0.20, y - ln)], fill=(225, 238, 255, int(120 * intensity)), width=3)

def rain_ripples(d, t, y0, y1, intensity=1.0, seed=6):
    if intensity <= 0.01: return
    rng = random.Random(seed)
    for k in range(int(46 * intensity)):
        x = rng.uniform(0, W); y = rng.uniform(y0, y1); rate = rng.uniform(1.3, 2.2)
        ph = (t * rate + rng.random()) % 1.0
        r = (6 + 38 * ph) * (0.6 + 0.8 * (y - y0) / max(1.0, y1 - y0)); a = int(170 * (1 - ph) * intensity)
        d.ellipse([x - r, y - r * 0.28, x + r, y + r * 0.28], outline=(235, 245, 255, a), width=2)

def storm_sky(frame, sky_mask, amount):
    """Darken the sky (masked) toward slate grey for a rain-cloud look."""
    if amount <= 0.01: return
    lay = Image.new('RGBA', (W, H), (70, 78, 98, 0))
    a = sky_mask.point(lambda v: int(v * 0.66 * amount))
    lay.putalpha(a)
    frame.paste(lay, (0, 0), lay)

def flash(frame, amount):
    if amount <= 0.01: return frame
    return Image.blend(frame, Image.new('RGB', frame.size, (255, 255, 250)), min(0.45, amount * 0.45))

def bolt(d, x, y, length, a=255, seed=1):
    rng = random.Random(seed); pts = [(x, y)]
    for k in range(7):
        x += rng.uniform(-45, 45); y += length / 7; pts.append((x, y))
    d.line(pts, fill=(255, 250, 200, a), width=9, joint='curve')
    d.line(pts, fill=(255, 255, 255, a), width=4, joint='curve')
