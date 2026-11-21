"""Paint the pond panorama once (sky, clouds, hills, 3D-shaded trees, water, lily pads, lotus, reeds)."""
import math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter
from .chars import P, render

PW, PH, HZ = 2400, 1920, 790      # panorama size, horizon (water starts) y

def lerp3(stops, t):
    t = np.clip(t, 0, 1); out = np.zeros(t.shape + (3,), np.float32)
    for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= t0) & (t <= t1); k = ((t - t0) / max(t1 - t0, 1e-6))[m][:, None]
        out[m] = np.array(c0) * (1 - k) + np.array(c1) * k
    return out

def cloud_layer(rng, n=7):
    lay = np.zeros((PH, PW, 4), np.float32); lay[..., :3] = 255
    yy = np.arange(900, dtype=np.float32)[:, None]
    for i in range(n):
        cx = 150 + i * (PW - 300) / (n - 1) + rng.uniform(-90, 90); cy = rng.uniform(170, 500); sc = rng.uniform(0.7, 1.25)
        mask = Image.new('L', (PW, 900), 0); d = ImageDraw.Draw(mask)
        for dx, dy, r in [(0, -20, 72), (-78, 4, 54), (80, 2, 58), (-36, -52, 56), (38, -58, 62), (-136, 22, 36), (134, 22, 40)]:
            r *= sc; d.ellipse([cx + dx * sc - r, cy + dy * sc - r, cx + dx * sc + r, cy + dy * sc + r], fill=255)
        d.ellipse([cx - 165 * sc, cy - 6 * sc, cx + 165 * sc, cy + 50 * sc], fill=255)
        m = np.asarray(mask.filter(ImageFilter.GaussianBlur(2.2)), np.float32) / 255
        hl = Image.new('L', (PW, 900), 0); dh = ImageDraw.Draw(hl)
        for dx, dy, r in [(0, -20, 72), (-78, 4, 54), (80, 2, 58), (-36, -52, 56), (38, -58, 62)]:
            r *= sc * 0.72; ox, oy = cx + (dx - 14) * sc, cy + (dy - 16) * sc
            dh.ellipse([ox - r, oy - r, ox + r, oy + r], fill=255)
        hlm = np.asarray(hl.filter(ImageFilter.GaussianBlur(22 * sc)), np.float32) / 255
        top, bot = cy - 125 * sc, cy + 50 * sc
        v = np.clip((yy - top) / (bot - top), 0, 1)
        tone = np.clip(0.93 - 0.15 * v ** 1.6 + 0.09 * hlm, 0, 1)
        col = np.stack([255 * tone, 252 * tone + 2, np.minimum(255, 248 * tone + 14)], -1) * np.ones((1, PW, 1), np.float32)
        a = m[..., None] * 0.97
        lay[:900, :, :3] = lay[:900, :, :3] * (1 - a) + col * a
        lay[:900, :, 3] = np.maximum(lay[:900, :, 3], a[..., 0])
    return lay

def hills(rng):
    out = []
    for k, (base, amp, col_top, col_bot, blur) in enumerate([(640, 70, (150, 196, 214), (185, 214, 222), 3),
                                                              (700, 45, (108, 170, 132), (140, 188, 150), 1.5)]):
        x = np.arange(PW)
        ph = rng.uniform(0, 6, 4)
        y = base - amp * (0.55 * np.sin(x / 410 + ph[0]) + 0.3 * np.sin(x / 170 + ph[1]) + 0.15 * np.sin(x / 63 + ph[2]))
        yy = np.arange(PH)[:, None]
        m = (yy >= y[None, :]) & (yy <= HZ + 5)
        t = np.clip((yy - y[None, :]) / 90, 0, 1)
        c = np.array(col_top, np.float32) * (1 - t[..., None]) + np.array(col_bot, np.float32) * t[..., None]
        a = gaussian_filter(m.astype(np.float32), blur)
        out.append((c, a))
    return out

def tree(scale, rng, hue=0):
    greens = [(52, 128, 62), (64, 145, 70), (46, 118, 70), (78, 150, 60)]
    g = greens[hue % 4]
    parts = []
    W, H = int(260 * scale), int(300 * scale)
    cx, base = W / 2, H - 8 * scale
    parts.append(P((cx, base - 40 * scale, 0), (14 * scale, 50 * scale, 14 * scale), (110, 78, 50), g=2))
    blobs = [(0, -150, 78), (-58, -118, 60), (60, -114, 62), (-26, -196, 56), (34, -192, 54), (0, -95, 60)]
    for bx, by, r in blobs:
        r *= scale * rng.uniform(0.9, 1.08)
        col = tuple(int(v * rng.uniform(0.93, 1.07)) for v in g)
        parts.append(P((cx + bx * scale, base + by * scale, rng.uniform(0, 20) * scale), (r, r * 0.92, r * 0.85), col, spec=0.08, g=1))
    return render(parts, W, H, ss=1, smooth=3), (cx, base)

def lotus(scale):
    W, H = int(160 * scale), int(130 * scale)
    cx, cy = W / 2, H * 0.70
    parts = []
    for k, ang in enumerate([-62, -40, -20, 0, 20, 40, 62]):
        a = math.radians(ang - 90)
        dist = 30 * scale
        z = 20 * scale if abs(ang) < 30 else 8 * scale
        parts.append(P((cx + dist * math.cos(a) * 0.9, cy + dist * math.sin(a), z), (16 * scale, 38 * scale, 12 * scale),
                       (255, 150 + int(abs(ang) * 0.6), 190), rot=ang, spec=0.35, shin=30))
    for ang in (-25, 25):
        a = math.radians(ang - 90)
        parts.append(P((cx + 22 * scale * math.cos(a), cy + 18 * scale * math.sin(a), 30 * scale), (13 * scale, 30 * scale, 10 * scale), (255, 175, 205), rot=ang * 0.6, spec=0.35))
    parts.append(P((cx, cy - 4 * scale, 26 * scale), (14 * scale, 9 * scale, 10 * scale), (255, 214, 70), spec=0.5))
    return render(parts, W, H, ss=2, smooth=2), (cx, cy + 10 * scale)

def lily_pad(d, x, y, w, rot, col=(64, 158, 72)):
    h = w * (0.30 + 0.28 * min(1, (y - HZ) / 1000))
    box = [x - w, y - h, x + w, y + h]
    gap0 = rot - 14; gap1 = rot + 14
    dark = tuple(int(c * 0.62) for c in col)
    d.pieslice([box[0], box[1] + h * 0.10, box[2], box[3] + h * 0.10], gap1, gap0 + 360, fill=dark + (255,))   # thickness
    d.pieslice(box, gap1, gap0 + 360, fill=col + (255,))
    hl = tuple(min(255, int(c * 1.25)) for c in col)
    d.pieslice([x - w * 0.78, y - h * 0.80, x + w * 0.55, y + h * 0.45], gap1, gap0 + 360, fill=hl + (110,))
    for k in range(7):
        a = math.radians(gap1 + 18 + k * (360 - 64) / 6)
        d.line([(x, y), (x + w * 0.85 * math.cos(a), y + h * 0.85 * math.sin(a))], fill=dark + (120,), width=max(1, int(w / 45)))

def reed_blade(d, x, ybase, hgt, bend, w, col_bot, col_top, steps=14):
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        xx = x + bend * t * t * hgt * 0.35; yy = ybase - hgt * t
        ww = w * (1 - t) ** 0.9 + 0.6
        left.append((xx - ww, yy)); right.append((xx + ww, yy))
    pts = left + right[::-1]
    mid = tuple(int(c0 * 0.5 + c1 * 0.5) for c0, c1 in zip(col_bot, col_top))
    d.polygon(pts, fill=mid + (255,))
    d.polygon(left[steps // 2:] + right[steps // 2:][::-1], fill=col_top + (255,))
    d.polygon(left[:steps // 3 + 1] + right[:steps // 3 + 1][::-1], fill=col_bot + (255,))

def cattail(scale):
    W, H = int(40 * scale), int(110 * scale)
    parts = [P((W / 2, H * 0.55, 0), (11 * scale, 36 * scale, 11 * scale), (122, 74, 44), spec=0.15, g=1),
             P((W / 2, H * 0.10, 0), (2.5 * scale, 14 * scale, 2.5 * scale), (150, 140, 70), g=0)]
    return render(parts, W, H, ss=2, smooth=2)

def reed_clump(lay, d, x, ybase, n, hmax, rng, cattails=True):
    for k in range(n):
        xx = x + rng.uniform(-70, 70); h = hmax * rng.uniform(0.55, 1.0); bend = rng.uniform(-0.6, 0.6)
        g = rng.uniform(0.85, 1.1)
        reed_blade(d, xx, ybase + rng.uniform(-10, 14), h, bend, rng.uniform(5, 9),
                   (int(40 * g), int(105 * g), int(52 * g)), (int(120 * g), int(185 * g), int(78 * g)))
    if cattails:
        for k in range(max(2, n // 4)):
            xx = x + rng.uniform(-50, 50); h = hmax * rng.uniform(0.7, 1.05)
            d.line([(xx, ybase), (xx + rng.uniform(-8, 8), ybase - h)], fill=(70, 120, 60, 255), width=5)
            ct = cattail(1.0 + rng.uniform(-0.1, 0.2))
            lay.alpha_composite(ct, (int(xx - ct.width / 2), int(ybase - h - ct.height * 0.35)))

def paint(seed=4):
    """Returns (panorama RGBA, open-sky mask, sky-incl-clouds mask). Deterministic for a given seed."""
    rng = random.Random(seed); nrng = np.random.default_rng(seed)
    yy = np.arange(PH, dtype=np.float32)[:, None] / HZ
    sky = lerp3([(0, (84, 160, 238)), (0.55, (146, 202, 248)), (0.9, (238, 222, 205)), (1.0, (255, 226, 190))], yy[:, 0])
    img = np.repeat(sky[:, None, :], PW, 1)
    cl = cloud_layer(nrng)
    img = img * (1 - cl[..., 3:]) + cl[..., :3] * cl[..., 3:]
    cloud_a = cl[..., 3].copy()
    occ = np.zeros((PH, PW), np.float32)          # land/trees/reeds (clouds handled separately)
    for c, a in hills(nrng):
        img = img * (1 - a[..., None]) + c * a[..., None]
        occ = np.maximum(occ, a)
    occ[HZ - 22:] = 1.0
    base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA')
    occ_im = Image.fromarray((occ * 255).astype(np.uint8), 'L')
    # far-shore trees + bushes
    xs = list(range(-60, PW + 60, 95))
    for i, x in enumerate(xs):
        if rng.random() < 0.18: continue
        sc = rng.uniform(0.45, 0.8)
        t, (ax, ay) = tree(sc, rng, hue=i)
        pos = (int(x - ax + rng.uniform(-25, 25)), int(HZ + 6 - ay))
        base.alpha_composite(t, pos)
        occ_im.paste(255, pos, t.getchannel('A'))
    d = ImageDraw.Draw(base)
    # grassy bank
    pts = [(x, HZ - 8 - 6 * math.sin(x / 37) - 4 * math.sin(x / 11)) for x in range(0, PW + 20, 20)]
    d.polygon(pts + [(PW, HZ + 16), (0, HZ + 16)], fill=(118, 182, 82, 255))
    d.rectangle([0, HZ + 6, PW, HZ + 16], fill=(84, 140, 70, 255))
    for k in range(160):
        x = rng.uniform(0, PW); y = HZ - rng.uniform(0, 8)
        col = rng.choice([(255, 230, 90), (255, 150, 190), (255, 255, 255)])
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col + (255,))
    arr = np.asarray(base, np.float32)[..., :3]
    # water
    t = np.clip((np.arange(PH, dtype=np.float32) - HZ) / (PH - HZ), 0, 1)
    water = lerp3([(0, (178, 222, 236)), (0.18, (120, 200, 214)), (0.55, (62, 166, 186)), (1.0, (28, 124, 152))], t)
    wimg = np.repeat(water[:, None, :], PW, 1)
    # reflection of shore/hills
    src = arr[HZ - 260:HZ + 14][::-1]
    rh = int(src.shape[0] * 0.85)
    refl = np.asarray(Image.fromarray(src.astype(np.uint8)).resize((PW, rh), Image.BILINEAR), np.float32)
    for r in range(rh):
        refl[r] = np.roll(refl[r], int(5 * math.sin(r * 0.35) * (r / rh + 0.3)), 0)
    refl = gaussian_filter(refl, (1.6, 3.5, 0))
    fade = (1 - np.arange(rh) / rh)[:, None, None] ** 1.3 * 0.62
    seg = wimg[HZ + 10:HZ + 10 + rh]
    wimg[HZ + 10:HZ + 10 + rh] = seg * (1 - fade) + (refl * 0.82 + seg * 0.18) * fade
    arr[HZ + 10:] = wimg[HZ + 10:]
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert('RGBA')
    lay = Image.new('RGBA', (PW, PH), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    # ripple streaks
    for k in range(700):
        y = HZ + 20 + (PH - HZ) * rng.random() ** 1.6; x = rng.uniform(0, PW)
        w = 10 + (y - HZ) * 0.10 * rng.uniform(0.5, 1.6); h = 1 + (y - HZ) * 0.004
        d.ellipse([x - w, y - h, x + w, y + h], fill=(220, 245, 255, rng.randint(25, 70)))
    base.alpha_composite(lay.filter(ImageFilter.GaussianBlur(1.0)))
    # lily pads (keep the swimming lane y 1030..1330 mostly clear)
    lay = Image.new('RGBA', (PW, PH), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    pads = []
    for k in range(70):
        y = HZ + 40 + (PH - HZ - 40) * rng.random() ** 1.1
        x = rng.uniform(-40, PW + 40); w = 26 + (y - HZ) * 0.115 * rng.uniform(0.8, 1.2)
        if 1040 - w * 0.4 < y < 1450 + w * 0.3 and 380 < x < PW + 60: continue
        if 1040 < y < 1450 and rng.random() < 0.6: continue
        pads.append((y, x, w))
    pads.sort()
    flowers = []
    for y, x, w in pads:
        col = rng.choice([(64, 158, 72), (74, 168, 70), (58, 146, 78), (86, 170, 66)])
        lily_pad(d, x, y, w, rng.uniform(0, 360), col)
        if rng.random() < 0.22 and not (y < 1500 and x > 380): flowers.append((x + rng.uniform(-0.2, 0.2) * w, y - w * 0.12, w))
    base.alpha_composite(lay)
    for x, y, w in flowers:
        fl, (ax, ay) = lotus(max(0.35, w / 95))
        base.alpha_composite(fl, (int(x - ax), int(y - ay)))
    # reeds: big clumps on the right side (the 'tall grass' Peelu wanders into) and a few on the left
    lay = Image.new('RGBA', (PW, PH), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for (x, yb, n, h) in [(1880, 1020, 16, 380), (2050, 1060, 22, 470), (2230, 1010, 18, 420), (2360, 1100, 20, 520),
                           (1700, 990, 9, 260), (120, 1040, 14, 400), (-20, 1110, 16, 500)]:
        reed_clump(lay, d, x, yb, n, h, rng)
        d = ImageDraw.Draw(lay)
    base.alpha_composite(lay)
    occ_im = Image.fromarray(np.maximum(np.asarray(occ_im), np.asarray(lay.getchannel('A'))))
    land = np.asarray(occ_im.filter(ImageFilter.GaussianBlur(1.5)), np.float32)
    sky = Image.fromarray((255 - np.maximum(land, cloud_a * 0.8 * 255)).astype(np.uint8), 'L')   # open sky, behind clouds
    skyall = Image.fromarray((255 - land).astype(np.uint8), 'L')                                # sky incl. clouds
    return base, sky, skyall
