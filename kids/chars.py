"""Tiny 2.5D renderer: z-buffered ellipsoids with soft 'animated-film' shading, plus character and prop builders."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter

L = np.array([-0.50, -0.72, 0.60], np.float32); L /= np.linalg.norm(L)
V = np.array([0, 0, 1.0], np.float32)
HV = (L + V) / np.linalg.norm(L + V)
KEY = np.array([1.00, 0.95, 0.86], np.float32)     # warm key
FILL = np.array([0.50, 0.62, 0.86], np.float32)    # cool sky fill
RIMC = np.array([1.00, 0.93, 0.78], np.float32)

class P:
    __slots__ = ('c', 'r', 'col', 'rot', 'spec', 'shin', 'fuzz', 'emis', 'g')
    def __init__(self, c, r, col, rot=0.0, spec=0.25, shin=30, fuzz=0.0, emis=False, g=0):
        self.g = g
        self.c, self.r, self.col, self.rot = c, r, col, rot
        self.spec, self.shin, self.fuzz, self.emis = spec, shin, fuzz, emis

_noise_cache = {}
def _noise(h, w):
    k = (h, w)
    if k not in _noise_cache:
        rng = np.random.default_rng(3)
        n = gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 2.2)
        _noise_cache[k] = n / (n.std() + 1e-6)
    return _noise_cache[k]

def render(parts, W, H, ss=2, decals=None, ao_strength=0.55, grade=None, smooth=5.0):
    """parts: list of P in output pixel coords (x right, y down, z toward viewer). Returns RGBA PIL image W x H."""
    Ws, Hs = W * ss, H * ss
    Z = np.full((Hs, Ws), -1e9, np.float32)
    N = np.zeros((Hs, Ws, 3), np.float32)
    A = np.zeros((Hs, Ws, 3), np.float32)
    SP = np.zeros((Hs, Ws), np.float32); SH = np.ones((Hs, Ws), np.float32)
    FZ = np.zeros((Hs, Ws), np.float32); EM = np.zeros((Hs, Ws), bool); G = np.zeros((Hs, Ws), np.int8)
    for p in parts:
        cx, cy, cz = p.c[0] * ss, p.c[1] * ss, p.c[2] * ss
        a, b, c = max(p.r[0] * ss, 0.5), max(p.r[1] * ss, 0.5), max(p.r[2] * ss, 0.5)
        th = math.radians(p.rot); ct, st = math.cos(th), math.sin(th)
        hx = math.sqrt((a * ct) ** 2 + (b * st) ** 2); hy = math.sqrt((a * st) ** 2 + (b * ct) ** 2)
        x0, x1 = max(0, int(cx - hx) - 1), min(Ws, int(cx + hx) + 2)
        y0, y1 = max(0, int(cy - hy) - 1), min(Hs, int(cy + hy) + 2)
        if x0 >= x1 or y0 >= y1:
            continue
        xs = np.arange(x0, x1, dtype=np.float32) + 0.5 - cx
        ys = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - cy
        u = xs * ct + ys * st; v = -xs * st + ys * ct
        s = 1 - (u / a) ** 2 - (v / b) ** 2
        sq = np.sqrt(np.clip(s, 0, None))
        z = cz + c * sq
        zr = Z[y0:y1, x0:x1]
        upd = (s > 0) & (z > zr)
        if not upd.any():
            continue
        nu, nv, nw = u / (a * a), v / (b * b), sq / c
        nx = nu * ct - nv * st; ny = nu * st + nv * ct
        ln = np.sqrt(nx * nx + ny * ny + nw * nw) + 1e-9
        zr[upd] = z[upd]
        Nr = N[y0:y1, x0:x1]
        Nr[..., 0][upd] = (nx / ln)[upd]; Nr[..., 1][upd] = (ny / ln)[upd]; Nr[..., 2][upd] = (nw / ln)[upd]
        A[y0:y1, x0:x1][upd] = np.array(p.col, np.float32) / 255.0
        SP[y0:y1, x0:x1][upd] = p.spec; SH[y0:y1, x0:x1][upd] = p.shin
        FZ[y0:y1, x0:x1][upd] = p.fuzz; EM[y0:y1, x0:x1][upd] = p.emis; G[y0:y1, x0:x1][upd] = p.g
    valid = Z > -1e8
    if not valid.any():
        return Image.new('RGBA', (W, H), (0, 0, 0, 0))
    # crop to used box for speed
    rows = np.where(valid.any(1))[0]; cols = np.where(valid.any(0))[0]
    pad = 24 * ss
    ry0, ry1 = max(0, rows[0] - pad), min(Hs, rows[-1] + pad + 1)
    rx0, rx1 = max(0, cols[0] - pad), min(Ws, cols[-1] + pad + 1)
    sl = (slice(ry0, ry1), slice(rx0, rx1))
    Zc, Nc, Ac, vc = Z[sl], N[sl].copy(), A[sl], valid[sl]
    Gc = G[sl]
    hh, ww = Zc.shape
    def _down(a): return a[::2, ::2]
    def _up(a): return np.repeat(np.repeat(a, 2, 0), 2, 1)[:hh, :ww]
    if smooth > 0:
        Nd, Gd, vd = _down(Nc), _down(Gc), _down(vc)
        for g in np.unique(Gc[vc]):
            if g <= 0: continue
            Mg = (Gc == g) & vc; Mgd = (Gd == g) & vd
            wsum = gaussian_filter(Mgd.astype(np.float32), smooth * ss / 2)
            for k in range(3):
                ch = gaussian_filter(np.where(Mgd, Nd[..., k], 0), smooth * ss / 2) / np.maximum(wsum, 1e-4)
                Nc[..., k] = np.where(Mg, _up(ch), Nc[..., k])
        ln = np.sqrt((Nc ** 2).sum(-1, keepdims=True)) + 1e-9
        Nc = Nc / ln
    nx, ny, nz = Nc[..., 0], Nc[..., 1], Nc[..., 2]
    ndl = nx * L[0] + ny * L[1] + nz * L[2]
    diff = np.clip((ndl + 0.28) / 1.28, 0, 1) ** 1.15
    # screen-space AO from depth
    M = _down(vc).astype(np.float32); sig = 7 * ss / 2
    bZ = gaussian_filter(np.where(_down(vc), _down(Zc), 0), sig); bM = gaussian_filter(M, sig)
    avg = _up(bZ / np.maximum(bM, 1e-3))
    occ = np.clip((avg - Zc) / (16 * ss), 0, 1)
    ao = 1 - ao_strength * occ
    up = np.clip(0.5 - 0.5 * ny, 0, 1)
    fill = (0.30 + 0.22 * up)
    ndh = np.clip(nx * HV[0] + ny * HV[1] + nz * HV[2], 0, 1)
    spec = SP[sl] * ndh ** SH[sl]
    rimd = np.clip(0.35 + 0.65 * (0.55 * nx - 0.6 * ny), 0, 1)
    rim = np.clip(1 - nz, 0, 1) ** 2.6 * rimd * 0.55
    alb = Ac * (1 + (FZ[sl] * _noise(ry1 - ry0, rx1 - rx0))[..., None])
    # warm 'subsurface' at the terminator
    sss = np.clip(1 - np.abs(ndl - 0.05) / 0.45, 0, 1) * 0.10
    sat = np.clip(alb, 0, 1) ** 1.6
    col = alb * KEY * (diff * ao)[..., None] + sat * FILL * 1.25 * (fill * ao)[..., None] + alb * sss[..., None] * np.array([1.0, 0.45, 0.25], np.float32)
    col = col + spec[..., None] * 0.95 + rim[..., None] * RIMC * (0.35 + 0.65 * alb)
    col = np.where(EM[sl][..., None], Ac, col)
    # gentle filmic shoulder
    col = col / (1 + 0.18 * col)
    col = np.clip(col * 1.12, 0, 1)
    if grade is not None:
        col = np.clip(col * np.array(grade, np.float32), 0, 1)
    out = np.zeros((Hs, Ws, 4), np.uint8)
    out[sl][..., :3] = (col * 255).astype(np.uint8)
    out[sl][..., 3] = (vc * 255).astype(np.uint8)
    im = Image.fromarray(out, 'RGBA')
    if decals:
        for fn in decals:
            fn(im, ss)
    return im.resize((W, H), Image.LANCZOS)

# ---------------- decal helpers (work in supersampled space) ----------------
def d_ellipse(cx, cy, rx, ry, fill, blur=0):
    def f(im, ss):
        lay = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.ellipse([(cx - rx) * ss, (cy - ry) * ss, (cx + rx) * ss, (cy + ry) * ss], fill=fill)
        if blur: lay = lay.filter(ImageFilter.GaussianBlur(blur * ss))
        im.alpha_composite(lay)
    return f

def d_arc(cx, cy, rx, ry, a0, a1, col, w):
    def f(im, ss):
        d = ImageDraw.Draw(im)
        d.arc([(cx - rx) * ss, (cy - ry) * ss, (cx + rx) * ss, (cy + ry) * ss], a0, a1, fill=col, width=max(1, int(w * ss)))
    return f

def d_line(pts, col, w):
    def f(im, ss):
        d = ImageDraw.Draw(im)
        d.line([(x * ss, y * ss) for x, y in pts], fill=col, width=max(1, int(w * ss)), joint='curve')
        for x, y in (pts[0], pts[-1]):
            r = w * ss / 2; d.ellipse([x * ss - r, y * ss - r, x * ss + r, y * ss + r], fill=col)
    return f

def d_poly(pts, fill, blur=0):
    def f(im, ss):
        lay = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.polygon([(x * ss, y * ss) for x, y in pts], fill=fill)
        if blur: lay = lay.filter(ImageFilter.GaussianBlur(blur * ss))
        im.alpha_composite(lay)
    return f

def tear_pts(x, y, s):
    pts = []
    for k in range(24):
        a = 2 * math.pi * k / 24
        r = s * (1 - 0.55 * max(0, -math.sin(a)) ** 3)
        pts.append((x + r * math.cos(a) * 0.75, y + r * math.sin(a) - s * 0.9 * max(0, -math.sin(a)) ** 6))
    return pts

# ---------------- characters ----------------
YEL = (255, 202, 40); YEL2 = (255, 214, 72); YELD = (246, 182, 28)
ORG = (255, 140, 30); ORGD = (238, 112, 24)

def surf_z(head, dx, dy):
    """z on the front of an (unrotated) head ellipsoid at offset dx,dy (pixels) from its centre."""
    (hx, hy, hz), (a, b, c) = head
    s = 1 - (dx / a) ** 2 - (dy / b) ** 2
    return hz + c * math.sqrt(max(s, 0))

def duckling(s, d=1, blink=0.0, beak=0.0, flap=0.0, tilt=0.0, mood='n', bow=False, look=0.0):
    """Returns (parts, decals, size, anchor). Anchor = waterline centre in sprite coords.
    s = body half-width in px. d = +1 faces right, -1 faces left. mood: n|happy|sad."""
    Wd, Hd = int(s * 3.6), int(s * 3.3)
    ox, oy = Wd / 2, Hd * 0.80
    def X(x): return ox + x * s * d
    def Y(y): return oy + y * s
    parts, dec = [], []
    parts.append(P((X(0), Y(-0.32), 0), (1.0 * s, 0.66 * s, 0.82 * s), YEL, rot=-6 * d, fuzz=0.02, g=1))
    parts.append(P((X(0.42), Y(-0.48), 0.22 * s), (0.56 * s, 0.50 * s, 0.56 * s), YEL, fuzz=0.02, g=1))
    parts.append(P((X(-0.92), Y(-0.62), 0), (0.30 * s, 0.17 * s, 0.24 * s), YEL, rot=-40 * d, g=1))
    wr = (-14 - 55 * flap) * d
    parts.append(P((X(-0.12 - 0.05 * flap), Y(-0.44 - 0.18 * flap), 0.56 * s), (0.50 * s, 0.30 * s, 0.24 * s), YELD, rot=wr, fuzz=0.02, g=2))
    # head (tilt shifts it a little)
    hxo, hyo = 0.60 + 0.05 * tilt, -1.20 + 0.04 * abs(tilt)
    head = ((X(hxo), Y(hyo), 0.16 * s), (0.60 * s, 0.58 * s, 0.58 * s))
    parts.append(P(head[0], head[1], YEL, fuzz=0.02, g=1))
    # tuft
    for (tx, ty, rx, ry, rr) in [(-0.06, -0.57, 0.09, 0.20, -22), (0.07, -0.60, 0.08, 0.18, 12), (0.18, -0.52, 0.07, 0.14, 38)]:
        hx_, hy_ = head[0][0] + tx * s * d, head[0][1] + ty * s
        parts.append(P((hx_, hy_, surf_z(head, tx * s, max(ty, -0.5) * s) - 0.05 * s), (rx * s, ry * s, 0.08 * s), YEL, rot=rr * d, g=1))
    # beak
    bx, by = head[0][0] + 0.50 * s * d, head[0][1] + 0.10 * s
    bz = head[0][2] + 0.30 * s
    parts.append(P((bx + 0.02 * s * d, by - 0.01 * s + 0.02 * beak * s, bz - 0.05 * s), (0.22 * s, (0.05 + 0.07 * beak) * s, 0.12 * s), (120, 28, 40)))
    parts.append(P((bx + 0.04 * s * d, by - 0.04 * s, bz), (0.30 * s, 0.10 * s, 0.20 * s), ORG, rot=5 * d, spec=0.45, shin=40))
    parts.append(P((bx - 0.02 * s * d, by + (0.06 + 0.12 * beak) * s, bz - 0.02 * s), (0.24 * s, 0.08 * s, 0.16 * s), ORGD, rot=(6 + 30 * beak) * d, spec=0.35))
    # eyes
    eyes = [(-0.02 + 0.05 * look, -0.07, 0.15, 0.20, 1.0), (0.38 + 0.04 * look, -0.09, 0.10, 0.18, 0.7)]
    for i, (ex, ey, erx, ery, k) in enumerate(eyes):
        cx_, cy_ = head[0][0] + ex * s * d, head[0][1] + ey * s
        if mood == 'happy' or blink > 0.75:
            dec.append(d_arc(cx_, cy_ + (0.04 if mood == 'happy' else -0.02) * s, erx * s * 0.95, ery * s * 0.6,
                             200 if mood == 'happy' else 20, 340 if mood == 'happy' else 160, (40, 25, 20, 255), 0.055 * s * k))
            continue
        sy = ery * (1 - 0.8 * blink)
        z = surf_z(head, ex * s, ey * s) - 0.035 * s
        parts.append(P((cx_, cy_, z), (erx * s, sy * s, 0.10 * s), (22, 16, 24), spec=1.4, shin=90))
        if blink < 0.4:
            dec.append(d_ellipse(cx_ - 0.045 * s * d, cy_ - 0.075 * s, 0.055 * s * k, 0.06 * s * k, (255, 255, 255, 245)))
            dec.append(d_ellipse(cx_ + 0.04 * s * d, cy_ + 0.07 * s, 0.025 * s * k, 0.025 * s * k, (255, 255, 255, 220)))
            if mood == 'sad':
                dec.append(d_ellipse(cx_ + 0.03 * s * d, cy_ - 0.02 * s, 0.04 * s * k, 0.035 * s * k, (255, 255, 255, 200)))
    # blush
    dec.append(d_ellipse(head[0][0] + 0.16 * s * d, head[0][1] + 0.16 * s, 0.13 * s, 0.07 * s, (255, 120, 120, 120), blur=0.03 * s))
    if mood == 'sad':
        for (ex, ey, k) in [(-0.02, -0.07, 1.0), (0.38, -0.09, 0.7)]:
            cx_, cy_ = head[0][0] + ex * s * d, head[0][1] + ey * s
            inner = 1 if ex < 0.2 else -1   # inner end points toward the other eye
            p_in = (cx_ + inner * 0.11 * s * d * k, cy_ - 0.34 * s)
            p_out = (cx_ - inner * 0.11 * s * d * k, cy_ - 0.25 * s)
            dec.append(d_line([p_out, p_in], (165, 105, 20, 235), 0.045 * s * k))
    if bow:
        bxh, byh = head[0][0] - 0.22 * s * d, head[0][1] - 0.50 * s
        zb = head[0][2] + 0.42 * s
        parts.append(P((bxh - 0.15 * s, byh - 0.02 * s, zb), (0.17 * s, 0.11 * s, 0.09 * s), (255, 92, 150), rot=-28, spec=0.5))
        parts.append(P((bxh + 0.15 * s, byh - 0.02 * s, zb), (0.17 * s, 0.11 * s, 0.09 * s), (255, 92, 150), rot=28, spec=0.5))
        parts.append(P((bxh, byh, zb + 0.04 * s), (0.07 * s, 0.07 * s, 0.07 * s), (240, 60, 120), spec=0.6))
    return parts, dec, (Wd, Hd), (ox, oy)

def mama(s, d=1, blink=0.0, beak=0.0, flap=0.0, mood='n', look=0.0):
    Wd, Hd = int(s * 3.8), int(s * 3.7)
    ox, oy = Wd / 2, Hd * 0.80
    def X(x): return ox + x * s * d
    def Y(y): return oy + y * s
    W1, W3 = (250, 248, 242), (232, 229, 222)
    parts, dec = [], []
    parts.append(P((X(-0.05), Y(-0.30), 0), (1.08 * s, 0.64 * s, 0.84 * s), W1, rot=-5 * d, fuzz=0.015, g=1))
    parts.append(P((X(0.45), Y(-0.45), 0.2 * s), (0.55 * s, 0.48 * s, 0.55 * s), W1, fuzz=0.015, g=1))
    parts.append(P((X(-1.02), Y(-0.62), 0), (0.34 * s, 0.17 * s, 0.26 * s), W1, rot=-40 * d, g=1))
    wr = (-12 - 60 * flap) * d
    parts.append(P((X(-0.18 - 0.08 * flap), Y(-0.48 - 0.22 * flap), 0.58 * s), (0.62 * s, 0.33 * s, 0.26 * s), W3, rot=wr, fuzz=0.015, g=2))
    parts.append(P((X(0.62), Y(-0.92), 0.12 * s), (0.25 * s, 0.42 * s, 0.25 * s), W1, rot=14 * d, g=1))
    head = ((X(0.80), Y(-1.40), 0.14 * s), (0.48 * s, 0.46 * s, 0.46 * s))
    parts.append(P(head[0], head[1], W1, fuzz=0.015, g=1))
    bx, by = head[0][0] + 0.42 * s * d, head[0][1] + 0.08 * s
    bz = head[0][2] + 0.22 * s
    parts.append(P((bx + 0.02 * s * d, by + 0.02 * beak * s, bz - 0.05 * s), (0.22 * s, (0.05 + 0.07 * beak) * s, 0.1 * s), (120, 28, 40)))
    parts.append(P((bx + 0.06 * s * d, by - 0.03 * s, bz), (0.30 * s, 0.09 * s, 0.17 * s), ORG, rot=4 * d, spec=0.45, shin=40))
    parts.append(P((bx, by + (0.06 + 0.12 * beak) * s, bz - 0.02 * s), (0.24 * s, 0.07 * s, 0.14 * s), ORGD, rot=(5 + 28 * beak) * d, spec=0.35))
    for ex, ey, erx, ery, k in [(0.02 + 0.05 * look, -0.06, 0.11, 0.15, 1.0), (0.32 + 0.04 * look, -0.08, 0.075, 0.13, 0.7)]:
        cx_, cy_ = head[0][0] + ex * s * d, head[0][1] + ey * s
        if mood == 'happy' or blink > 0.75:
            dec.append(d_arc(cx_, cy_ + (0.03 if mood == 'happy' else -0.02) * s, erx * s, ery * s * 0.6,
                             200 if mood == 'happy' else 20, 340 if mood == 'happy' else 160, (40, 25, 20, 255), 0.05 * s * k))
        else:
            z = surf_z(head, ex * s, ey * s) - 0.03 * s
            parts.append(P((cx_, cy_, z), (erx * s, ery * (1 - 0.8 * blink) * s, 0.08 * s), (22, 16, 24), spec=1.4, shin=90))
            if blink < 0.4:
                dec.append(d_ellipse(cx_ - 0.035 * s * d, cy_ - 0.055 * s, 0.042 * s * k, 0.045 * s * k, (255, 255, 255, 245)))
                dec.append(d_ellipse(cx_ + 0.03 * s * d, cy_ + 0.05 * s, 0.02 * s * k, 0.02 * s * k, (255, 255, 255, 220)))
        # lashes
        for kk in (-1, 0, 1):
            ax = cx_ - 0.03 * s * d + kk * 0.045 * s * d * k
            dec.append(d_line([(ax, cy_ - ery * s * 0.85), (ax - 0.04 * s * d + kk * 0.03 * s * d, cy_ - ery * s * 1.25)], (40, 30, 30, 230), 0.03 * s * k))
    dec.append(d_ellipse(head[0][0] + 0.12 * s * d, head[0][1] + 0.15 * s, 0.11 * s, 0.06 * s, (255, 130, 140, 110), blur=0.03 * s))
    # pink lotus clip on head
    fx, fy = head[0][0] - 0.18 * s * d, head[0][1] - 0.36 * s
    fz = head[0][2] + 0.36 * s
    for k in range(5):
        a = math.radians(-90 + (k - 2) * 32)
        parts.append(P((fx + 0.13 * s * math.cos(a), fy + 0.13 * s * math.sin(a), fz), (0.07 * s, 0.13 * s, 0.05 * s), (255, 130, 175), rot=math.degrees(a) + 90, spec=0.4))
    parts.append(P((fx, fy, fz + 0.04 * s), (0.06 * s, 0.05 * s, 0.05 * s), (255, 215, 80), spec=0.5))
    return parts, dec, (Wd, Hd), (ox, oy)

def frog(s, blink=0.0, pouch=0.0, mouth=0.0, mood='n', look=0.0):
    Wd, Hd = int(s * 2.8), int(s * 2.6)
    ox, oy = Wd / 2, Hd * 0.86
    def X(x): return ox + x * s
    def Y(y): return oy + y * s
    G, G2, BEL = (92, 188, 70), (78, 168, 58), (206, 236, 150)
    parts, dec = [], []
    for sx in (-1, 1):
        parts.append(P((X(0.78 * sx), Y(-0.26), 0.05 * s), (0.40 * s, 0.26 * s, 0.32 * s), G2, rot=-10 * sx))
        parts.append(P((X(0.98 * sx), Y(-0.06), 0.25 * s), (0.30 * s, 0.10 * s, 0.2 * s), G2))
    body = ((X(0), Y(-0.58), 0), (0.92 * s, 0.58 * s, 0.70 * s))
    parts.append(P(body[0], body[1], G, spec=0.35, shin=25, g=1))
    parts.append(P((X(0), Y(-0.40), 0.35 * s), (0.62 * s, 0.40 * s, 0.40 * s), BEL, g=1))
    parts.append(P((X(0), Y(-0.50 + 0.04 * pouch), 0.30 * s), ((0.26 + 0.20 * pouch) * s, (0.16 + 0.16 * pouch) * s, (0.30 + 0.12 * pouch) * s), (246, 238, 175), spec=0.6, shin=50))
    for sx in (-1, 1):
        parts.append(P((X(0.46 * sx), Y(-0.16), 0.48 * s), (0.15 * s, 0.22 * s, 0.14 * s), G))
        parts.append(P((X(0.52 * sx), Y(-0.02), 0.56 * s), (0.17 * s, 0.07 * s, 0.10 * s), G2))
    for sx in (-1, 1):
        ec = (X(0.40 * sx), Y(-1.06), 0.22 * s)
        parts.append(P(ec, (0.31 * s, 0.30 * s, 0.30 * s), G, spec=0.35, shin=25, g=1))
        if blink > 0.75 or mood == 'happy':
            dec.append(d_arc(ec[0], ec[1] + 0.02 * s, 0.18 * s, 0.12 * s, 200 if mood == 'happy' else 20, 340 if mood == 'happy' else 160, (30, 50, 20, 255), 0.06 * s))
            continue
        parts.append(P((ec[0], ec[1] - 0.02 * s, ec[2] + 0.18 * s), (0.22 * s, 0.22 * s * (1 - 0.8 * blink), 0.14 * s), (252, 252, 248), spec=0.8, shin=60))
        parts.append(P((ec[0] + 0.04 * s * look, ec[1] + 0.0 * s, ec[2] + 0.28 * s), (0.11 * s, 0.13 * s * (1 - 0.8 * blink), 0.07 * s), (20, 18, 20), spec=1.4, shin=90))
        if blink < 0.4:
            dec.append(d_ellipse(ec[0] - 0.04 * s + 0.04 * s * look, ec[1] - 0.06 * s, 0.045 * s, 0.045 * s, (255, 255, 255, 240)))
    # mouth: wide smile, opens when talking
    mx, my = X(0), Y(-0.76)
    if mouth > 0.15:
        dec.append(d_ellipse(mx, my + 0.02 * s, 0.34 * s, 0.05 * s + 0.12 * s * mouth, (110, 30, 40, 255)))
        dec.append(d_ellipse(mx, my + 0.06 * s + 0.08 * s * mouth, 0.16 * s, 0.04 * s + 0.04 * s * mouth, (235, 110, 120, 255)))
    dec.append(d_arc(mx, my - 0.14 * s, 0.42 * s, 0.18 * s, 25, 155, (40, 90, 30, 255), 0.05 * s))
    for sx in (-1, 1):
        dec.append(d_ellipse(X(0.52 * sx), Y(-0.78), 0.12 * s, 0.06 * s, (255, 120, 120, 110), blur=0.03 * s))
        dec.append(d_ellipse(X(0.14 * sx), Y(-0.98), 0.025 * s, 0.018 * s, (40, 80, 30, 200)))
    # spots
    for (px, py, pr) in [(-0.55, -0.62, 0.07), (0.62, -0.70, 0.06), (-0.20, -0.95, 0.045)]:
        dec.append(d_ellipse(X(px), Y(py), pr * s, pr * 0.8 * s, (70, 150, 50, 160), blur=0.01 * s))
    return parts, dec, (Wd, Hd), (ox, oy)

def fish(s, d=1, blink=0.0, wag=0.0, mouth=0.0, mood='n'):
    Wd, Hd = int(s * 3.4), int(s * 2.2)
    ox, oy = Wd / 2 - 0.15 * s * d, Hd / 2
    def X(x): return ox + x * s * d
    def Y(y): return oy + y * s
    O1, O2, O3 = (255, 150, 38), (255, 196, 88), (255, 112, 48)
    parts, dec = [], []
    for sy in (-1, 1):
        parts.append(P((X(-1.10 + 0.05 * wag * sy), Y(0.24 * sy + 0.1 * wag), -0.1 * s), (0.42 * s, 0.17 * s, 0.07 * s), O3, rot=(35 * sy + 18 * wag) * d, spec=0.5))
    parts.append(P((X(-0.15), Y(-0.55), -0.05 * s), (0.45 * s, 0.18 * s, 0.06 * s), O3, rot=-12 * d, spec=0.4))
    body = ((X(0), Y(0), 0), (1.0 * s, 0.60 * s, 0.46 * s))
    parts.append(P(body[0], body[1], O1, spec=0.7, shin=60, g=1))
    parts.append(P((X(0.1), Y(0.22), 0.16 * s), (0.72 * s, 0.34 * s, 0.30 * s), O2, spec=0.5, shin=50, g=1))
    parts.append(P((X(0.18), Y(0.18), 0.40 * s), (0.26 * s, 0.10 * s, 0.07 * s), O3, rot=(28 + 25 * math.sin(wag * 3)) * d, spec=0.5))
    parts.append(P((X(0.98), Y(0.10), 0.05 * s), (0.10 * s, (0.07 + 0.05 * mouth) * s, 0.08 * s), (255, 105, 125), spec=0.6))
    ex, ey = X(0.55), Y(-0.14)
    if blink > 0.75 or mood == 'happy':
        dec.append(d_arc(ex, ey + 0.03 * s, 0.13 * s, 0.09 * s, 200, 340, (60, 30, 20, 255), 0.05 * s))
    else:
        parts.append(P((ex, ey, 0.30 * s), (0.20 * s, 0.22 * s * (1 - 0.8 * blink), 0.12 * s), (252, 252, 250), spec=0.8, shin=60))
        parts.append(P((ex + 0.04 * s * d, ey + 0.01 * s, 0.40 * s), (0.10 * s, 0.13 * s * (1 - 0.8 * blink), 0.05 * s), (20, 18, 24), spec=1.4, shin=90))
        if blink < 0.4:
            dec.append(d_ellipse(ex + 0.0 * s, ey - 0.06 * s, 0.045 * s, 0.045 * s, (255, 255, 255, 240)))
    dec.append(d_ellipse(X(0.62), Y(0.16), 0.11 * s, 0.06 * s, (255, 110, 120, 110), blur=0.03 * s))
    for k in range(3):
        for j in range(2):
            cx_, cy_ = X(-0.45 + k * 0.28), Y(-0.15 + j * 0.28)
            dec.append(d_arc(cx_, cy_, 0.13 * s, 0.13 * s, 300 if d > 0 else 120, 60 if d > 0 else 240, (255, 205, 120, 90), 0.025 * s))
    return parts, dec, (Wd, Hd), (ox, oy)

def make(builder, *a, **k):
    parts, dec, (w, h), anchor = builder(*a, **k)
    return render(parts, w, h, decals=dec), anchor


def mango(s, rot=0.0):
    """A ripe mango with a leaf. s = half-length in px. Anchor = centre of the fruit."""
    Wd, Hd = int(s * 2.8), int(s * 2.8)
    cx, cy = Wd / 2, Hd / 2 + 0.15 * s
    parts = [P((cx, cy, 0), (1.0 * s, 0.76 * s, 0.68 * s), (255, 182, 38), rot=rot - 18, spec=0.55, shin=40, g=1),
             P((cx - 0.62 * s, cy - 0.58 * s, 0.05 * s), (0.07 * s, 0.17 * s, 0.07 * s), (110, 75, 40), rot=rot + 25),
             P((cx - 0.18 * s, cy - 0.86 * s, 0.25 * s), (0.46 * s, 0.13 * s, 0.05 * s), (70, 165, 62), rot=rot - 28, spec=0.45)]
    dec = [d_ellipse(cx + 0.30 * s, cy - 0.12 * s, 0.55 * s, 0.42 * s, (255, 90, 60, 120), blur=0.18 * s),
           d_ellipse(cx - 0.35 * s, cy - 0.30 * s, 0.16 * s, 0.09 * s, (255, 255, 230, 120), blur=0.05 * s)]
    return parts, dec, (Wd, Hd), (cx, cy)
