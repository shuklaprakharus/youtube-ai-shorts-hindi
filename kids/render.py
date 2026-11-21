"""Data-driven shot renderer: turns an episode + its timeline into one mp4 per shot.
Shots: s0 title | s1-s2 family + event (wide) | s3-s5a Peelu at the reeds with frog & fish | s5b Mama comes |
s6 reunion + moral card | s7 bye-bye. Characters are 3D-shaded sprites (chars.py), cached on disk per pose."""
import hashlib
import math
import os
import pickle
import random
import subprocess

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import fx, settings
from .chars import duckling, fish, frog, mama, mango, render as crender
from .fx import H, W, ease

FPS = settings.FPS
BUILD = {"duck": duckling, "mama": mama, "frog": frog, "fish": fish, "mango": mango}
G = {}   # per-process state, filled by init()


def lerp(a, b, k): return a + (b - a) * k
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def q(v, n): return round(clamp(v) * (n - 1)) / (n - 1)


def init(work, ep, tl):
    G.clear()
    G.update(work=work, ep=ep, tl=tl, ev=tl["events"], total=tl["total"], out0=tl["out0"],
             L={i + 1: v for i, v in enumerate(tl["line0"])},
             mouth={k: np.array(v) for k, v in tl["mouth"].items()},
             pano=Image.open(work / "pano.png").convert("RGB"), skym=Image.open(work / "skymask.png").convert("L"),
             skyall=Image.open(work / "skyall.png").convert("L"),
             cache={}, lyr=[], lyr_img={}, card={}, sub=None)
    G["blur"] = G["pano"].filter(ImageFilter.GaussianBlur(5))
    (work / "spr").mkdir(exist_ok=True)
    keys = [f"L{i}" for i in range(1, settings.N_LINES + 1)] + ["outro"]
    starts = [G["L"][i] for i in range(1, settings.N_LINES + 1)] + [G["out0"]]
    for n, key in enumerate(keys):
        ws = [x for x in tl["words"] if x["key"] == key]
        words = []
        for j, x in enumerate(ws):
            w = x["w"]
            if x["who"] != "n":
                if j == 0 or ws[j - 1]["who"] != x["who"]: w = "“" + w
                if j == len(ws) - 1 or ws[j + 1]["who"] != x["who"]: w = w + "”"
            words.append((w, x["start"], x["end"]))
        G["lyr"].append({"t0": starts[n], "t1": starts[n + 1] if n + 1 < len(starts) else G["total"], "words": words})


def E(name, default=None):
    return G["ev"].get(name, default)


def seg(key, who):
    m = [s for s in G["tl"]["segs"] if s["key"] == key and s["who"] == who]
    return m[0] if m else None


# ---------------------------------------------------------------- sprites
def _floaty(img, anchor):
    a = np.array(img); ax, ay = anchor; cut = int(round(ay)) + 1
    a[cut:, :, 3] = 0
    for i, f in enumerate((0.9, 0.7, 0.4)):
        r = cut - 3 + i
        if 0 <= r < a.shape[0]: a[r, :, 3] = (a[r, :, 3] * f).astype(np.uint8)
    top = Image.fromarray(a, "RGBA")
    part = a[max(0, cut - int(img.height * 0.55)):cut][::-1].copy()
    rh = max(2, int(part.shape[0] * 0.5))
    part[..., :3] = (part[..., :3].astype(np.float32) * 0.55 + np.array([40, 135, 165], np.float32) * 0.45).astype(np.uint8)
    part[..., 3] = (part[..., 3] * 0.38).astype(np.uint8)
    refl = Image.fromarray(part, "RGBA").resize((img.width, rh), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))
    return top, refl


def sprite(kind, s, **kw):
    sq = max(12, int(round(s / 3.0)) * 3)
    key = (kind, sq, tuple(sorted(kw.items())))
    e = G["cache"].get(key)
    if e is None:
        fn = G["work"] / "spr" / (hashlib.md5(repr(key).encode()).hexdigest() + ".pkl")
        if fn.exists():
            with open(fn, "rb") as f: e = pickle.load(f)
        else:
            parts, dec, (w, h), anchor = BUILD[kind](sq, **kw)
            e = {"img": crender(parts, w, h, decals=dec), "anchor": anchor, "s": sq}
            tmp = str(fn) + f".{os.getpid()}.tmp"
            with open(tmp, "wb") as f: pickle.dump(e, f)
            os.replace(tmp, fn)
        if kind in ("duck", "mama"):
            e["top"], e["refl"] = _floaty(e["img"], e["anchor"])
        G["cache"][key] = e
    return e


def blink_at(t, seed):
    rng = random.Random(seed); tt = rng.uniform(0.3, 2.0)
    while tt <= t:
        if t - tt < 0.17: return 1.0
        tt += rng.uniform(2.0, 3.8)
    return 0.0


def mouth(who, t):
    m = G["mouth"].get(who)
    i = int(t * FPS)
    return float(m[i]) if m is not None and 0 <= i < len(m) else 0.0


# ---------------------------------------------------------------- camera
class Cam:
    def __init__(self, x0, y0, z):
        P = G["pano"]
        self.z = z
        self.x0 = min(max(x0, 0), P.width - W / z); self.y0 = min(max(y0, 0), P.height - H / z)
    def box(self): return (self.x0, self.y0, self.x0 + W / self.z, self.y0 + H / self.z)
    def bg(self, blur=False): return (G["blur"] if blur else G["pano"]).resize((W, H), Image.BILINEAR, box=self.box())
    def sky(self): return G["skym"].resize((W, H), Image.BILINEAR, box=self.box())
    def skyall(self): return G["skyall"].resize((W, H), Image.BILINEAR, box=self.box())
    def sx(self, x): return (x - self.x0) * self.z
    def sy(self, y): return (y - self.y0) * self.z
    def horizon(self): return self.sy(790)


def wpos(x0, y0, z, sx, sy): return x0 + sx / z, y0 + sy / z


# ---------------------------------------------------------------- drawing helpers
def draw_floater(frame, dr, kind, cam, wx, wy, s, t, phase=0.0, ripple=True, sqx=1.0, wake=0.0, dx=0.0, dy=0.0, **kw):
    e = sprite(kind, s * cam.z, **kw)
    sx, sy = cam.sx(wx) + dx, cam.sy(wy) + 3.5 * math.sin(t * 4.2 + phase) + dy
    top, refl, (ax, ay) = e["top"], e["refl"], e["anchor"]
    bw = e["s"]
    if sqx != 1.0:
        top = top.resize((max(1, int(top.width * sqx)), top.height)); refl = refl.resize((max(1, int(refl.width * sqx)), refl.height)); ax *= sqx
    frame.paste(refl, (int(sx - ax), int(sy + 2)), refl)
    if ripple:
        fx.rings(dr, sx, sy + 3, t + phase, rate=0.65, n=2, base=bw * 0.9, grow=bw * 0.8, squash=0.2, amax=80, width=3)
    if wake > 0:
        dirn = kw.get("d", 1)
        for k in range(3):
            ph = (t * 1.3 + k / 3) % 1
            bx = sx - dirn * bw * (1.0 + 2.2 * ph); spread = bw * 0.35 * (0.4 + ph); a = int(110 * min(1.0, wake) * (1 - ph))
            dr.line([(bx, sy + 4 - spread * 0.5), (bx - dirn * bw * 0.4, sy + 4 - spread)], fill=(255, 255, 255, a), width=4)
            dr.line([(bx, sy + 6 + spread * 0.5), (bx - dirn * bw * 0.4, sy + 6 + spread)], fill=(255, 255, 255, a), width=4)
    dr.ellipse([sx - bw * 0.85, sy - 3, sx + bw * 0.85, sy + 7], outline=(255, 255, 255, 110), width=3)
    frame.paste(top, (int(sx - ax), int(sy - ay)), top)
    return sx, sy, bw


def duck_head(sx, sy, s, d): return sx + 0.60 * s * d, sy - 1.20 * s
def duck_eye(sx, sy, s, d): return sx + 0.58 * s * d, sy - 1.27 * s
def duck_beak(sx, sy, s, d): return sx + 1.15 * s * d, sy - 1.10 * s


def draw_frog(frame, dr, cam, wx, wy, s, t, hop=0.0, **kw):
    sx, sy = cam.sx(wx), cam.sy(wy); ps = s * cam.z
    fx.lily_pad_big(dr, sx, sy + ps * 0.05, ps * 1.35, ps * 0.42, rot=-30)
    dr.ellipse([sx - ps * 0.85, sy - ps * 0.14, sx + ps * 0.85, sy + ps * 0.12], fill=(20, 60, 20, int(90 * (1 - min(1, hop / 60)))))
    e = sprite("frog", ps, **kw); ax, ay = e["anchor"]
    frame.paste(e["img"], (int(sx - ax), int(sy - ay - hop)), e["img"])
    return sx, sy - hop, e["s"]


def draw_fish(frame, dr, cam, wx, wy, s, t, cut_y=None, rot=0.0, **kw):
    e = sprite("fish", s * cam.z, **kw)
    img, (ax, ay) = e["img"], e["anchor"]
    sx, sy = cam.sx(wx), cam.sy(wy)
    if rot: img = img.rotate(rot, Image.BILINEAR, center=(ax, ay))
    if cut_y is not None:
        a = np.array(img); c = int(cut_y - (sy - ay))
        if c < a.shape[0]: a[max(0, c):, :, 3] = 0
        img = Image.fromarray(a, "RGBA")
    frame.paste(img, (int(sx - ax), int(sy - ay)), img)
    return sx, sy, e["s"]


def draw_mango(frame, x, y, size, t, rot=0.0, bob=True):
    e = sprite("mango", size)
    img, (ax, ay) = e["img"], e["anchor"]
    yy = y + (4 * math.sin(t * 3.3) if bob else 0)
    if rot: img = img.rotate(rot, Image.BILINEAR, center=(ax, ay), expand=False)
    frame.paste(img, (int(x - ax), int(yy - ay)), img)


def droplets(dr, x, y, dt, n=10, seed=0, power=1.0, scale=1.0):
    if dt < 0 or dt > 0.9: return
    rng = random.Random(seed)
    for k in range(n):
        vx = rng.uniform(-260, 260) * power; vy = -rng.uniform(250, 560) * power
        px = x + vx * dt * scale; py = y + (vy * dt + 900 * dt * dt) * scale
        r = rng.uniform(6, 12) * scale * (1 - dt / 0.9 * 0.5)
        if py > y + 10: continue
        dr.ellipse([px - r, py - r, px + r, py + r], fill=(235, 250, 255, int(230 * (1 - dt / 0.9))))


_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = (1 - 0.26 * np.clip(((_xx - W / 2) / (W * 0.75)) ** 2 + ((_yy - H * 0.47) / (H * 0.62)) ** 2, 0, 1) ** 1.4)[..., None].astype(np.float32)
del _yy, _xx


def grade_frame(frame, cool, warm=0.0, fade=1.0):
    a = np.asarray(frame, np.float32)
    g = np.array([lerp(1, 0.80, cool), lerp(1, 0.88, cool), lerp(1, 1.02, cool)], np.float32) * lerp(1, 0.86, cool)
    g = g * np.array([1 + 0.04 * warm, 1 + 0.02 * warm, 1.0], np.float32)
    return Image.fromarray(np.clip(a * (VIG * (g * fade)), 0, 255).astype(np.uint8))


BURST = {"yellow": ((255, 230, 60), (160, 60, 0)), "green": ((140, 240, 90), (20, 90, 20)), "blue": ((150, 225, 255), (20, 70, 150)),
         "pink": ((255, 150, 200), (150, 20, 80)), "white": ((255, 255, 255), (60, 50, 120)), "red": ((255, 90, 70), (110, 10, 10))}


def B(frame, s, x, y, t, t0, kind="yellow", size=96, dur=1.3, rot=-6):
    if not s or t0 is None: return
    f, st = BURST[kind]; fx.burst(frame, s, x, y, t - t0, dur, size, f, st, rot)


def bang(s):
    return s if (not s or s.endswith("!")) else s + "!"


# ---------------------------------------------------------------- lyrics, label, cards
def lyric_img(i, k):
    if (i, k) in G["lyr_img"]: return G["lyr_img"][(i, k)]
    f = fx.F(60, 800)
    ws = [w for w, a, b in G["lyr"][i]["words"]]
    dd = ImageDraw.Draw(Image.new("L", (10, 10))); sp = dd.textlength(" ", font=f)
    rows, cur, curw = [], [], 0
    for j, w in enumerate(ws):
        tw = dd.textlength(w, font=f)
        if cur and curw + sp + tw > 920:
            rows.append(cur); cur, curw = [], 0
        cur.append((j, w, tw)); curw += (sp if len(cur) > 1 else 0) + tw
    rows.append(cur)
    lh = 84; bw = max(sum(t for _, _, t in r) + sp * (len(r) - 1) for r in rows) + 70; bh = lh * len(rows) + 34
    im = Image.new("RGBA", (int(bw) + 30, int(bh) + 30), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle([12, 18, bw + 12, bh + 18], 36, fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([6, 6, bw + 6, bh + 6], 36, fill=(52, 30, 98, 200), outline=(255, 255, 255, 210), width=4)
    for r_i, r in enumerate(rows):
        rw = sum(t for _, _, t in r) + sp * (len(r) - 1); x = 6 + (bw - rw) / 2; y = 6 + 14 + r_i * lh
        for j, w, tw in r:
            d.text((x, y), w, font=f, fill=(255, 222, 60) if j < k else (255, 255, 255), stroke_width=4, stroke_fill=(40, 20, 70))
            x += tw + sp
    G["lyr_img"][(i, k)] = im
    return im


def draw_lyrics(frame, t):
    for i, ly in enumerate(G["lyr"]):
        if ly["t0"] <= t < ly["t1"]:
            k = sum(1 for w, a, b in ly["words"] if t >= a + 0.02)
            dt = t - ly["t0"]
            fx.paste_scaled(frame, lyric_img(i, k), W / 2, 1450, 0.92 + 0.08 * ease(dt / 0.2), ease(dt / 0.15))
            return


def ai_label(frame):
    d = ImageDraw.Draw(frame, "RGBA"); f = fx.F(34, 700, "Mukta"); s = "AI Generated"
    w = d.textlength(s, font=f); x1, y1 = W - 40, H - 44; x0, y0 = x1 - w - 36, y1 - 54
    d.rounded_rectangle([x0, y0, x1, y1], 14, fill=(0, 0, 0, 175), outline=(255, 255, 255, 200), width=2)
    d.text((x0 + 18, y0 + 6), s, font=f, fill=(255, 255, 255, 240))


def moral_card(k):
    if k in G["card"]: return G["card"][k]
    m = G["ep"]["moral"]
    im = Image.new("RGBA", (900, 470), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle([20, 26, 880, 450], 46, fill=(0, 0, 0, 120))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9)))
    d.rounded_rectangle([10, 10, 870, 440], 46, fill=(255, 248, 225, 245), outline=(255, 150, 40, 255), width=8)
    f1 = fx.F(70, 800); tw = d.textlength(m["title"], font=f1); d.text(((880 - tw) / 2, 34), m["title"], font=f1, fill=(200, 70, 20))
    for i, (n, txt, col) in enumerate([("1", m["rows"][0], (60, 170, 90)), ("2", m["rows"][1], (70, 130, 230))][:k]):
        y = 170 + i * 128
        d.rounded_rectangle([60, y, 820, y + 104], 52, fill=col + (255,))
        d.ellipse([72, y + 10, 156, y + 94], fill=(255, 255, 255, 255)); d.text((101, y + 8), n, font=fx.F(64, 800), fill=col)
        size = 70
        while size > 40 and d.textlength(txt, font=fx.F(size, 800)) > 600: size -= 4
        d.text((190, y + 6 + (70 - size) * 0.5), txt, font=fx.F(size, 800), fill=(255, 255, 255), stroke_width=3, stroke_fill=tuple(int(c * 0.6) for c in col))
    G["card"][k] = im
    return im


def sub_btn():
    if G["sub"] is None:
        im = Image.new("RGBA", (640, 170), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle([18, 26, 622, 156], 64, fill=(0, 0, 0, 120))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        d.rounded_rectangle([10, 10, 610, 140], 64, fill=(232, 28, 38, 255), outline=(255, 255, 255, 255), width=6)
        d.polygon([(60, 48), (60, 102), (106, 75)], fill=(255, 255, 255, 255))
        f = fx.F(64, 800); s = "सब्सक्राइब करें"; tw = d.textlength(s, font=f)
        d.text((130 + (480 - tw) / 2, 22), s, font=f, fill=(255, 255, 255))
        G["sub"] = im
    return G["sub"]


# ---------------------------------------------------------------- staging constants (world coords)
ZA, YA = 1.12, 206.0
def FAM():
    return {"mama": (*wpos(980, YA, ZA, 300, 1010), 100 / ZA, 0.0, 3), "sib1": (*wpos(980, YA, ZA, 520, 1095), 66 / ZA, 1.1, 4),
            "sib2": (*wpos(980, YA, ZA, 690, 1180), 74 / ZA, 2.3, 5), "peelu": (*wpos(980, YA, ZA, 860, 1275), 86 / ZA, 0.6, 9)}
ZB, YB, XB = 1.25, 316.0, 1500.0
PEELU_B = wpos(XB, YB, ZB, 560, 1230); S_PEELU_B = 140 / ZB
FROG_B = wpos(XB, YB, ZB, 190, 1311); S_FROG_B = 120 / ZB
FISH_B = wpos(XB, YB, ZB, 905, 1275); S_FISH_B = 110 / ZB
MAMA_B = wpos(XB, YB, ZB, 452, 1180); S_MAMA_B = 150 / ZB
SIBS_B = [(*wpos(XB, YB, ZB, 700, 1118), 64 / ZB, 1.7, 4), (*wpos(XB, YB, ZB, 798, 1132), 64 / ZB, 2.6, 5)]
MANGO_B = wpos(XB, YB, ZB, 760, 1262)
ZC, YC = 1.15, 222.0
MAMA_C = wpos(400, YC, ZC, 430, 1190); S_MAMA_C = 150 / ZC
SIBS_C = [(*wpos(400, YC, ZC, 170, 1120), 72 / ZC, 1.4, 4, 0.35), (*wpos(400, YC, ZC, 255, 1240), 80 / ZC, 2.2, 5, 0.2)]
ZD, YD, XD = 1.12, 206.0, 1450.0


def scenes():
    L, o = G["L"], G["out0"]
    return [("s0", 0.0, L[1]), ("s1", L[1], L[3]), ("s2", L[3], L[5]), ("s3", L[5], L[7]), ("s4", L[7], L[9]),
            ("s5a", L[9], L[10]), ("s5b", L[10], L[11]), ("s6", L[11], o), ("s7", o, G["total"])]


def fam_x(x0, t):
    L = G["L"]
    if t < L[3]: return x0 - 30 * (t - L[1])
    dt = t - L[3]
    return x0 - 30 * (L[3] - L[1]) - 30 * dt - 90 * max(0.0, dt - 0.75)


def swim_plan():
    """(turn time, swim start, swim duration) for Peelu's move to the reeds in shot s2."""
    L, ev = G["L"], G["ep"]["event"]
    if ev == "rain":
        th = E("thunder1", L[4] + 0.4)
        start = min(max(L[4] + 0.1, th + 0.35), L[5] - 1.4)
        return th + 0.05, start, (L[5] - 0.1) - start
    return L[3] + (1.6 if ev == "wander" else 1.0), L[4] + 0.1, 4.4


def peelu_A(t):
    """Peelu's world position/facing in shots s1-s2 (she ends at the reeds spot)."""
    L, ev = G["L"], G["ep"]["event"]
    x0, y0, s, _, _ = FAM()["peelu"]
    xL3 = x0 - 30 * (L[3] - L[1])
    turn, start, dur = swim_plan()
    if t < L[3]: return x0 - 30 * (t - L[1]), y0, -1
    hx, hy = xL3 - 18, y0
    if ev == "treat":
        hx, hy = xL3 + 70, y0 + 12
    if t < start:
        if ev == "treat" and E("mango_splash") and t >= E("mango_splash") + 0.2:
            k = ease((t - E("mango_splash") - 0.2) / 1.2)
            return lerp(xL3 - 18, hx, k), lerp(y0, hy, k), 1
        return xL3 - 18 * ease((t - L[3]) / 0.8), y0, (1 if t >= turn else -1)
    k = ease((t - start) / dur)
    return lerp(hx, PEELU_B[0], k), lerp(hy, PEELU_B[1], k), 1


def camA_x0(t):
    L = G["L"]
    if t < L[3]: return lerp(980, 700, (t - L[1]) / (L[3] - L[1]))
    _, start, _ = swim_plan()
    p0 = L[3] + 2.2 if G["ep"]["event"] != "rain" else start - 0.3
    return lerp(700, PEELU_B[0] - 620 / ZA, ease((t - p0) / (L[5] - p0)))


def butterfly_A(t):
    L = G["L"]
    w1 = 14 * math.sin(t * 7.0); w2 = 9 * math.cos(t * 5.3)
    px, py, _ = peelu_A(t); s = FAM()["peelu"][2]
    hx, hy = px + 20, py - 2.6 * s
    if t < L[3] + 1.5:
        k = ease((t - L[3]) / 1.5); return lerp(camA_x0(t) + 1150 / ZA, hx, k) + w1, lerp(YA + 640 / ZA, hy, k) + w2
    if t < L[4] + 0.2:
        a = (t - L[3] - 1.5) * math.pi; return hx + 70 * math.cos(a) + w1, hy + 35 * math.sin(a) + w2
    if t < L[4] + 4.0:
        k = ease((t - L[4] - 0.2) / 3.8); return lerp(hx + 90, 2120, k) + w1, lerp(hy, 1010, k) + w2
    k = ease((t - L[4] - 4.0) / 0.8); return lerp(2120, 2280, k) + w1, lerp(1010, 560, k) + w2


def rain_amount(t):
    if G["ep"]["event"] != "rain": return 0.0
    a, b = E("rain_start"), E("rain_end")
    return clamp((t - a) / 1.2) * clamp((b + 0.6 - t) / 1.2)


def thunder_flash(t):
    if G["ep"]["event"] != "rain": return 0.0
    f = 0.0
    for k in ("thunder1", "thunder2"):
        tt = E(k)
        if tt is not None:
            dt = t - tt
            if 0 <= dt < 0.10 or 0.18 <= dt < 0.26: f = max(f, 1.0 if dt < 0.10 else 0.6)
    return f


# ---------------------------------------------------------------- the frame
def frame_at(t):
    ep = G["ep"]; L = G["L"]; OUT0 = G["out0"]; TOTAL = G["total"]; event = ep["event"]
    sid = [s for s in scenes() if s[1] <= t < s[2]][0][0] if t < TOTAL else "s7"
    if sid == "s0":
        z = 1.5 + 0.06 * t / L[1]; cam = Cam(1320 - 540 / z, 1103 - 960 / z, z); frame = cam.bg(blur=True)
    elif sid in ("s1", "s2"):
        cam = Cam(camA_x0(t), YA, ZA); frame = cam.bg()
    elif sid in ("s3", "s4", "s5a", "s6"):
        x0 = lerp(XB + 12, XB - 10, clamp((t - L[5]) / (L[10] - L[5]))) if sid != "s6" else XB - 10
        cam = Cam(x0, YB, ZB); frame = cam.bg()
    elif sid == "s5b":
        cam = Cam(400 + 560 * ease(clamp((t - E("mama_go") - 0.2) / 2.4)), YC, ZC); frame = cam.bg()
    else:
        cam = Cam(XD + 8 * (t - OUT0), YD, ZD); frame = cam.bg()
    d = ImageDraw.Draw(frame, "RGBA")
    cool, warm = 0.0, 0.0
    ra = rain_amount(t)
    # ---- sky: sun / storm / rainbow (only where the panorama shows sky)
    if sid in ("s1", "s2", "s6", "s7") or ra > 0:
        skylay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if sid in ("s1", "s2"):
            sun_a = (1.0 if sid == "s1" else 1 - ease((t - (L[5] - 1.2)) / 1.2)) * (1 - ra)
            fx.paste_scaled(skylay, fx.sun_img(), 860, 300, 0.75, 0.9 * sun_a)
        elif sid in ("s6", "s7"):
            ka = ease((t - (L[11] + 0.4)) / 1.2) if sid == "s6" else 1.0
            ka *= (1 - ra)
            fx.paste_scaled(skylay, fx.sun_img(), 880, 250, 0.75, 0.9 * ka)
            fx.rainbow(skylay, 540, cam.horizon() + 330, 820, (ease((t - (L[11] + 1.0)) / 1.5) if sid == "s6" else 1.0), cam.horizon())
            warm = ka
        skylay.putalpha(ImageChops.multiply(skylay.getchannel("A"), cam.sky()))
        frame.paste(skylay, (0, 0), skylay)
        if ra > 0:
            fx.storm_sky(frame, cam.skyall(), ra)

    if ra > 0:
        fx.rain_ripples(d, t, max(cam.horizon() + 40, 700), 1880, ra)

    if sid == "s0":
        beak = 1.0 if 0.04 < t < 0.24 else (0.5 if 0.9 < t < 1.6 else 0.0)
        flap = q(0.5 + 0.5 * math.sin(2 * math.pi * 3 * (t - 0.35)), 3) if 0.35 < t < 1.35 else 0.0
        wx, wy = wpos(cam.x0, cam.y0, cam.z, 560, 1300)
        draw_floater(frame, d, "duck", cam, wx, wy, 200 / cam.z, t, d=1, bow=True, beak=q(beak, 3), flap=flap,
                     mood="happy" if 0.9 < t < 1.6 else "n", blink=blink_at(t, 1))
        for k in range(6):
            a = 0.5 + 0.5 * math.sin(t * 5 + k * 1.7)
            fx.sparkle(d, 200 + k * 140, 230 + 230 * (k % 2), 16 + 10 * a, int(200 * a * ease((t - 0.5) / 0.4)))
        fx.paste_scaled(frame, fx.text_img(ep["title"]["line1"], 160, (255, 222, 60), 10, (190, 70, 0)), 540, 340, fx.pop_scale(t - 0.5), 1.0)
        fx.paste_scaled(frame, fx.text_img(ep["title"]["line2"], 104, (255, 255, 255), 9, (200, 60, 120)), 540, 510, fx.pop_scale(t - 0.8), 1.0)

    elif sid in ("s1", "s2"):
        fam = FAM(); items = []
        for name in ("mama", "sib1", "sib2"):
            x0, y0, s, ph, sd = fam[name]; x = fam_x(x0, t)
            if cam.sx(x) < -400: continue
            items.append((y0, name, x, y0, s, ph, sd))
        px, py, pd = peelu_A(t)
        items.append((py, "peelu", px, py, fam["peelu"][2], 0.6, 9))
        sp0 = E("sfx_L2")
        carried = event == "treat" and E("mango_grab") is not None and t >= E("mango_grab")
        for _, name, x, y, s, ph, sd in sorted(items):
            if name != "peelu":
                draw_floater(frame, d, "mama" if name == "mama" else "duck", cam, x, y, s, t, phase=ph, wake=1.0, d=-1, blink=blink_at(t, sd))
                continue
            flap, beak, mood = 0.0, 0.0, "n"
            if sp0 is not None and sp0 - 0.1 < t < sp0 + 1.0:
                flap = q(0.5 + 0.5 * math.sin(2 * math.pi * 5 * (t - sp0)), 3); beak = 0.5; mood = "happy"
            if event == "rain" and t >= E("thunder1", 1e9): mood = "sad"
            if event == "treat" and E("mango_splash") and E("mango_splash") < t < L[5]: mood = "happy"
            turn_t, swim_t, _ = swim_plan()
            sqx = 0.7 if abs(t - turn_t) < 0.07 else 1.0
            swimming = t < L[3] + 0.8 or t > swim_t
            sx, sy, bw = draw_floater(frame, d, "duck", cam, x, y, s, t, phase=ph, sqx=sqx, wake=1.0 if swimming else 0.0,
                                      d=pd, bow=True, beak=q(beak, 3), flap=flap, mood=mood, blink=blink_at(t, sd) if mood != "happy" else 0.0)
            if sp0 is not None and sp0 < t < sp0 + 1.1:
                droplets(d, sx, sy, (t - sp0) % 0.55, 10, seed=int((t - sp0) // 0.55) + 3)
            B(frame, bang(ep["sound_words"].get("L2")), sx - 40, sy - bw * 2.9, t, sp0, "blue", 100)
            if event == "rain" and E("thunder1") is not None and t >= E("thunder1"):
                B(frame, "!", sx + 60, sy - bw * 2.5, t, E("thunder1") + 0.05, "red", 140, 1.2, 0)
            if carried:
                bx, by = duck_beak(sx, sy, bw, pd)
                draw_mango(frame, bx + pd * bw * 0.05, by + bw * 0.25, bw * 0.42, t, rot=-20 * pd, bob=False)
        if event == "wander" and t >= L[3]:
            bx, by = butterfly_A(t)
            if t < L[4] + 4.6: fx.draw_butterfly(frame, cam.sx(bx), cam.sy(by), t, 190)
            B(frame, bang(ep["sound_words"].get("L3")), cam.sx(bx) + 30, cam.sy(by) - 150, t, E("sfx_L3"), "pink", 92)
        if event == "treat" and E("mango_drop") is not None and t >= E("mango_drop") and not carried:
            xL3 = FAM()["peelu"][0] - 30 * (L[3] - L[1])
            mx, my = xL3 + 150, FAM()["peelu"][1] + 30
            td, tsp = E("mango_drop"), E("mango_splash")
            if t < tsp:
                k = (t - td) / (tsp - td)
                draw_mango(frame, cam.sx(mx), lerp(-150, cam.sy(my), k * k), 70, t, rot=360 * k, bob=False)
            else:
                draw_mango(frame, cam.sx(mx), cam.sy(my) - 25, 70, t)
                droplets(d, cam.sx(mx), cam.sy(my), t - tsp, 12, seed=11, power=1.1)
                fx.rings(d, cam.sx(mx), cam.sy(my) + 6, t, rate=0.9, n=2, base=50, grow=60, squash=0.25, amax=110, width=3)
            B(frame, bang(ep["sound_words"].get("L3")), cam.sx(mx), cam.sy(my) - 230, t, tsp, "yellow", 104)
        if event == "rain":
            B(frame, bang(ep["sound_words"].get("L3")), W / 2 + 140, 520, t, E("sfx_L3"), "blue", 100)
            B(frame, bang(ep["sound_words"].get("L4")), W / 2 - 100, 400, t, E("thunder1"), "white", 118, 1.4, 4)
            if E("thunder1") is not None and 0 <= t - E("thunder1") < 0.3:
                fx.bolt(d, 760, 120, 520, int(255 * (1 - (t - E("thunder1")) / 0.3)), seed=3)
        elif event == "wander":
            B(frame, bang(ep["sound_words"].get("L4")), cam.sx(2050), cam.sy(880), t, E("sfx_L4"), "green", 100)
        else:
            px_, py_, _ = peelu_A(t)
            B(frame, bang(ep["sound_words"].get("L4")), cam.sx(px_) - 60, cam.sy(py_) - 330, t, E("sfx_L4"), "blue", 96)
        if t >= L[4] - 0.3:
            shake = E("sfx_L4") if event == "wander" else None
            fx.fg_reeds(d, t, 1, n=4, seed=8, amp=1 + 2.5 * (1 if shake and shake - 0.1 < t < shake + 1.3 else 0), h0=820)

    elif sid in ("s3", "s4", "s5a"):
        cool = ease((t - L[5]) / 1.0)
        if t >= L[7] - 0.9: cool = lerp(1.0, 0.65, ease((t - (L[7] - 0.9)) / 4))
        if event == "rain": cool = max(cool, 0.75)
        fj0, fj1 = E("frog_jump") + 0.05, E("frog_land")
        items = [(PEELU_B[1], "peelu")]
        if t >= fj0: items.append((FROG_B[1], "frog"))
        if t >= L[9]: items.append((FISH_B[1], "fish"))
        if event == "treat": items.append((MANGO_B[1], "mango"))
        for _, kind in sorted(items):
            if kind == "mango":
                draw_mango(frame, cam.sx(MANGO_B[0]), cam.sy(MANGO_B[1]) - 22, 62, t)
                fx.rings(d, cam.sx(MANGO_B[0]), cam.sy(MANGO_B[1]) + 4, t, rate=0.7, n=2, base=40, grow=40, squash=0.25, amax=80, width=2)
            elif kind == "frog":
                if t < fj1:
                    k = (t - fj0) / (fj1 - fj0)
                    wx = lerp(cam.x0 - 200, FROG_B[0], k); wy = FROG_B[1] - 340 * 4 * k * (1 - k) / cam.z
                    e = sprite("frog", S_FROG_B * cam.z, blink=0.0)
                    fx.paste_scaled(frame, e["img"], cam.sx(wx), cam.sy(wy) - e["img"].height * 0.36, 1.0, 1.0, rot=14 * (1 - 2 * k))
                else:
                    m = mouth("frog", t)
                    croak = 1.0 if E("croak") < t < E("croak") + 0.42 else 0.0
                    pouch = q(max(croak, 0.8 * m, 0.12 + 0.1 * math.sin(t * 3)), 3)
                    fsx, fsy, fps = draw_frog(frame, d, cam, FROG_B[0], FROG_B[1], S_FROG_B, t, blink=blink_at(t, 21), pouch=pouch, mouth=q(m, 3))
                    if t < fj1 + 0.9: droplets(d, fsx, fsy, t - fj1, 9, seed=5, power=0.7)
                    B(frame, bang(ep["sound_words"].get("frog")), fsx + 50, fsy - fps * 2.85, t, E("frog_talk"), "green", 96)
                    fx.bubble(frame, ep["bubbles"]["frog"], fsx + 30, fsy - fps * 2.05, t - E("frog_bubble"), L[9] - 0.3 - E("frog_bubble"), "left", 70)
            elif kind == "fish":
                fx0 = E("fish_jump")
                if t < fx0 + 0.72:
                    k = clamp((t - fx0) / 0.70)
                    wx = lerp(FISH_B[0] + 95, FISH_B[0], k); wy = FISH_B[1] - (330 * 4 * k * (1 - k) + 30) / cam.z
                    draw_fish(frame, d, cam, wx, wy, S_FISH_B, t, cut_y=cam.sy(FISH_B[1]), rot=lerp(-40, 45, k), d=-1, wag=q(0.5 + 0.5 * math.sin(t * 25), 3))
                    droplets(d, cam.sx(FISH_B[0] + 95), cam.sy(FISH_B[1]), t - fx0, 11, seed=7, power=1.0)
                    droplets(d, cam.sx(FISH_B[0]), cam.sy(FISH_B[1]), t - (fx0 + 0.7), 11, seed=8, power=0.8)
                else:
                    m = mouth("fish", t)
                    wy = FISH_B[1] + (6 * math.sin(t * 3.1) - 26 * ease((t - fx0 - 0.7) / 0.4)) / cam.z
                    fsx, fsy, fss = draw_fish(frame, d, cam, FISH_B[0], wy, S_FISH_B, t, cut_y=cam.sy(FISH_B[1]) + 4, d=-1,
                                              wag=q(0.5 + 0.5 * math.sin(t * 6), 3), mouth=q(m, 3), blink=blink_at(t, 31))
                    fx.rings(d, cam.sx(FISH_B[0]), cam.sy(FISH_B[1]) + 4, t, rate=0.8, n=2, base=fss * 0.9, grow=fss * 0.7, squash=0.22, amax=90, width=3)
                    fx.bubble(frame, ep["bubbles"]["fish"], fsx - 10, 975, t - E("fish_bubble"), 2.0, "right", 66)
            else:
                # facing: wander looks around (turn1..3); others look back once; then frog (left), fish (right), call (left)
                flips = [E("turn1"), E("turn2"), E("turn3")] if event == "wander" else [E("turn1")]
                flips = [f for f in flips if f is not None]
                d_list = [1] + [(-1 if i % 2 == 0 else 1) for i in range(len(flips))]
                if event != "wander": d_list = [1, -1]
                dd = d_list[0]
                for i, f in enumerate(flips):
                    if t >= f: dd = d_list[i + 1]
                fl4 = L[9] + 0.3; fl5 = (E("peelu_call") - 0.6) if E("peelu_call") is not None and ep.get("peelu_calls") else None
                if t >= fl4: dd = 1
                if fl5 is not None and t >= fl5: dd = -1
                all_flips = flips + [fl4] + ([fl5] if fl5 else [])
                sqx = 0.7 if any(abs(t - f) < 0.07 for f in all_flips) else 1.0
                calm = E("frog_talk") + 0.8
                pmood = ep.get("peelu_mood", "sad")
                mood = pmood if (L[5] + (1.2 if event == "wander" else 0.0) <= t < calm) else "n"
                if event == "wander" and t < E("turn3", L[5] + 2.6): mood = "n"
                if pmood == "happy" and mood == "happy" and t > L[6]: mood = "n"
                pm = mouth("peelu", t); beak = pm if pm > 0.05 else 0.0
                flap = q(0.5 + 0.5 * math.sin(t * 30), 3) if (fl5 is not None and t >= fl5 + 0.5 and pm > 0.05) else 0.0
                jitter = 0.0
                if mood == "sad" and L[6] < t < E("frog_land"): jitter = 3 * math.sin(t * 13)
                dx = 3.0 * math.sin(t * 60) if mood == "scared" else 0.0
                dy_jump = 0.0
                if event == "rain" and E("thunder2") is not None and 0 <= t - E("thunder2") < 0.4:
                    dy_jump = -40 * math.sin(math.pi * (t - E("thunder2")) / 0.4)
                sx, sy, bw = draw_floater(frame, d, "duck", cam, PEELU_B[0], PEELU_B[1] + jitter / cam.z, S_PEELU_B, t, phase=0.6, sqx=sqx,
                                          dx=dx, dy=dy_jump, d=dd, bow=True, beak=q(beak, 3), flap=flap, mood="sad" if mood == "scared" else mood,
                                          blink=blink_at(t, 9) if mood not in ("sad", "scared", "happy") else 0.0)
                if mood == "sad" and L[6] + 0.2 < t < E("frog_land") + 0.3:
                    ex, ey = duck_eye(sx, sy, bw, dd)
                    for k in range(8):
                        dt = t - (L[6] + 0.2 + k * 0.5)
                        if 0 <= dt < 0.8:
                            yy = ey + bw * 0.18 + 300 * dt * dt + 50 * dt; xx = ex + dd * (bw * 0.06 + 20 * dt) + (k % 2) * bw * 0.36 * dd
                            if yy < sy: fx.tear(d, xx, yy, 21)
                if event == "wander" and E("turn1") < t < E("turn3", 0) + 0.6:
                    B(frame, "?", sx + 90, sy - bw * 2.35, t, E("turn1") + 0.05, "white", 130, 1.0, 8)
                    B(frame, "?", sx - 110, sy - bw * 2.45, t, E("turn2") + 0.05, "white", 120, 0.95, -8)
                hx, hy = duck_head(sx, sy, bw, dd)
                if ep["bubbles"].get("peelu"):
                    fx.bubble(frame, ep["bubbles"]["peelu"], hx + dd * bw * 0.45, hy - bw * 0.55, t - E("peelu_bubble"), E("peelu_bubble_dur", 2.5),
                              "left" if dd > 0 else "right", 66)
                if ep.get("peelu_calls") and E("peelu_call") is not None and t >= E("peelu_call") - 0.05:
                    bx_, by_ = duck_beak(sx, sy, bw, dd)
                    fx.sound_rings(d, bx_, by_, t - E("peelu_call"), dirn=dd)
                    B(frame, ep["bubbles"].get("peelu_call") or ep["mama_burst"], sx, sy - bw * 2.75, t, E("peelu_call"), "yellow", 118, 1.5)
        fx.fg_reeds(d, t, 1, n=4, seed=8, amp=1.0 + 1.5 * ra, h0=880)
        fx.fg_reeds(d, t, -1, n=3, seed=12, amp=1.0 + 1.5 * ra, h0=760)

    elif sid == "s5b":
        cool = 0.6 if event != "rain" else 0.75
        go, hear = E("mama_go"), E("mama_hear")
        k = clamp((t - go) / 2.4); kk = k * k * (1.6 - 0.6 * k)
        dd = -1 if t < hear + 0.25 else 1
        sqx = 0.7 if abs(t - (hear + 0.25)) < 0.07 else 1.0
        mbeak = 1.0 if (E("mama_q1") < t < E("mama_q1") + 0.2 or E("mama_q2") < t < E("mama_q2") + 0.2) else q(mouth("mama", t), 3)
        for (x0, y0, s, ph, sd, delay) in sorted(SIBS_C, key=lambda r: r[1]):
            kx = clamp((t - go - delay) / 2.4); kx = kx * kx * (1.6 - 0.6 * kx)
            draw_floater(frame, d, "duck", cam, x0 + 1100 * kx, y0, s, t, phase=ph, wake=1.0 if t > go else 0.0, d=-1 if t < hear + 0.45 else 1, blink=blink_at(t, sd))
        sx, sy, bw = draw_floater(frame, d, "mama", cam, MAMA_C[0] + 1150 * kk, MAMA_C[1], S_MAMA_C, t, phase=0.2, sqx=sqx,
                                  wake=1.5 if t > go else 0.0, d=dd, beak=q(mbeak, 3), blink=blink_at(t, 3), look=1.0 if t > hear else 0.0)
        if ep.get("peelu_calls") and t < hear + 0.6:
            fx.sound_rings(d, W + 60, 900, (t - L[10] - 0.1) % 1.2, dirn=-1)
        B(frame, "!", sx + 40, sy - bw * 2.55, t, hear, "red", 170, 1.4, 0)
        if t > go:
            for kline in range(6):
                yl = sy - bw * (0.2 + 0.25 * kline); xl = sx - dd * bw * (1.6 + 0.3 * (kline % 2))
                d.line([(xl, yl), (xl - dd * bw * 1.3, yl)], fill=(255, 255, 255, 150), width=7)
            droplets(d, sx + dd * bw, sy, (t - go) % 0.5, 7, seed=int((t - go) // 0.5), power=0.7)
        B(frame, ep.get("mama_burst"), min(sx, W - 330), sy - bw * 2.7, t, E("mama_q1"), "yellow", 110, 0.9)

    elif sid == "s6":
        cool = lerp(0.75 if event == "rain" else 0.6, 0.0, ease((t - (L[11] + 0.4)) / 1.2))
        hug = E("hug"); km = ease((t - L[11]) / 0.9); happy = t > hug
        items = [(MAMA_B[1], "mama"), (PEELU_B[1], "peelu"), (FROG_B[1], "frog"), (FISH_B[1], "fish")]
        items += [(y, "sib", x, s, ph, sd) for (x, y, s, ph, sd) in SIBS_B]
        if event == "treat": items.append((MANGO_B[1], "mango"))
        for it in sorted(items, key=lambda r: r[0]):
            kind = it[1]
            if kind == "sib":
                _, _, x, s, ph, sd = it
                ka = ease((t - (L[11] + 1.2)) / 1.4)
                if t < L[11] + 1.2: continue
                draw_floater(frame, d, "duck", cam, lerp(cam.x0 - 300, x, ka), it[0], s, t, phase=ph, wake=(1 - ka), d=1,
                             mood="happy" if ka > 0.95 else "n", blink=blink_at(t, sd))
            elif kind == "mama":
                draw_floater(frame, d, "mama", cam, lerp(cam.x0 - 380, MAMA_B[0], km), MAMA_B[1], S_MAMA_B, t, phase=0.2, wake=(1 - km) * 1.5, d=1,
                             mood="happy" if happy else "n", flap=1.0 if happy else 0.0,
                             beak=q(max(0.5 if happy else 0.0, mouth("mama", t)), 3), blink=blink_at(t, 3))
            elif kind == "peelu":
                sx, sy, bw = draw_floater(frame, d, "duck", cam, PEELU_B[0] - 12 * ease((t - hug) / 0.4), PEELU_B[1], S_PEELU_B, t, phase=0.6, d=-1,
                                          bow=True, mood="happy" if happy else "n", beak=0.5 if happy else 0.0, blink=blink_at(t, 9))
                fx.hearts(d, t, hug, sx - bw * 0.7, sy - bw * 2.2, n=10, seed=4)
            elif kind == "mango":
                sh = E("share", 1e9); k = ease((t - sh) / 1.0)
                mx = lerp(MANGO_B[0], SIBS_B[0][0] + 40, k)
                draw_mango(frame, cam.sx(mx), cam.sy(MANGO_B[1]) - 22, 62, t)
                if t > sh: fx.hearts(d, t, sh + 0.6, cam.sx(mx), cam.sy(MANGO_B[1]) - 140, n=5, seed=9)
            elif kind == "frog":
                hop = 0.0
                for h0 in (E("applause"), E("applause") + 0.6):
                    if 0 < t - h0 < 0.45: hop = 80 * math.sin(math.pi * (t - h0) / 0.45)
                draw_frog(frame, d, cam, FROG_B[0], FROG_B[1], S_FROG_B, t, hop=hop, blink=blink_at(t, 21), mood="happy" if happy else "n",
                          mouth=0.5 if hop > 0 else 0.0, pouch=0.0)
            else:
                jump = 0.0; h0 = E("applause") + 0.1
                if 0 < t - h0 < 0.5: jump = 100 * math.sin(math.pi * (t - h0) / 0.5)
                draw_fish(frame, d, cam, FISH_B[0], FISH_B[1] + (-26 + 6 * math.sin(t * 3.1) - jump) / cam.z, S_FISH_B, t, cut_y=cam.sy(FISH_B[1]) + 4,
                          d=-1, wag=q(0.5 + 0.5 * math.sin(t * 6), 3), mood="happy" if happy else "n", blink=blink_at(t, 31))
                fx.rings(d, cam.sx(FISH_B[0]), cam.sy(FISH_B[1]) + 4, t, rate=0.8, n=2, base=100, grow=70, squash=0.22, amax=90, width=3)
        if t > L[11] + 2.0:
            kb = ease((t - L[11] - 2.0) / 1.5)
            fx.draw_butterfly(frame, lerp(W + 100, W / 2 + 200 * math.cos(t * 1.5), kb), lerp(250, cam.horizon() + 150 + 60 * math.sin(t * 2.3), kb), t, 170)
        ap = E("applause")
        if ap < t < ap + 2.8:
            rng = random.Random(77)
            for k in range(50):
                dt = t - ap - rng.uniform(0, 0.6)
                if dt < 0: continue
                xx = rng.uniform(40, W - 40) + 40 * math.sin(dt * 3 + k); yy = -30 + dt * rng.uniform(300, 480)
                c = rng.choice([(255, 90, 90), (255, 210, 60), (90, 200, 255), (130, 230, 120), (255, 140, 220)])
                ang = dt * 6 + k
                d.polygon([(xx + 11 * math.cos(ang + a), yy + 6.6 * math.sin(ang + a)) for a in (0, 1.6, 3.14, 4.7)], fill=c + (230,))
        if t > E("moral"):
            kc = (1 if t > E("row1") else 0) + (1 if t > E("row2") else 0)
            fx.paste_scaled(frame, moral_card(kc), W / 2, lerp(-300, 300, ease((t - E("moral")) / 0.45)), 1.0, 1.0)

    else:   # s7 goodbye group shot
        cast = [("frog", 150, 1330, 105, 0.0, 21), ("sib1", 300, 1105, 64, 1.4, 4), ("mama", 470, 1165, 135, 0.2, 3),
                ("sib2", 800, 1118, 64, 2.2, 5), ("peelu", 640, 1240, 122, 0.6, 9), ("fish", 950, 1292, 100, 0.0, 31)]
        for name, sx0, sy0, ss_, ph, sd in sorted(cast, key=lambda r: r[2]):
            wx, wy = wpos(XD, YD, ZD, sx0, sy0); s = ss_ / ZD
            wv = q(0.5 + 0.5 * math.sin(t * 2 * math.pi * 1.6 + ph), 3)
            if name in ("sib1", "sib2"):
                draw_floater(frame, d, "duck", cam, wx, wy, s, t, phase=ph, d=1 if name == "sib1" else -1, mood="happy", flap=wv, beak=0.5, blink=blink_at(t, sd))
            elif name == "mama":
                draw_floater(frame, d, "mama", cam, wx, wy, s, t, phase=ph, d=1, mood="happy", flap=wv, beak=0.5, blink=blink_at(t, sd))
            elif name == "peelu":
                pbeak = 1.0 if E("bye_quack") < t < E("bye_quack") + 0.22 else 0.5
                draw_floater(frame, d, "duck", cam, wx, wy, s, t, phase=ph, d=-1, bow=True, mood="happy", flap=wv, beak=pbeak, blink=blink_at(t, sd))
            elif name == "frog":
                hop = 0.0
                for h0 in (OUT0 + 0.4, OUT0 + 1.6, OUT0 + 3.4):
                    if 0 < t - h0 < 0.45: hop = 70 * math.sin(math.pi * (t - h0) / 0.45)
                draw_frog(frame, d, cam, wx, wy, s, t, hop=hop, blink=blink_at(t, sd), mood="happy", mouth=0.5, pouch=0.0)
            else:
                yj = 90 * math.sin(math.pi * (t - OUT0 - 1.0) / 0.5) if 0 < t - (OUT0 + 1.0) < 0.5 else 0.0
                draw_fish(frame, d, cam, wx, wy + (-24 + 6 * math.sin(t * 3.1) - yj) / ZD, s, t, cut_y=cam.sy(wy) + 4, d=-1,
                          wag=q(0.5 + 0.5 * math.sin(t * 6), 3), mood="happy", blink=blink_at(t, sd))
        fx.draw_butterfly(frame, W / 2 + 230 * math.cos(t * 1.3), cam.horizon() + 120 + 50 * math.sin(t * 2.1), t, 160)
        fx.paste_scaled(frame, fx.text_img("बाय-बाय!", 170, (255, 255, 255), 11, (220, 60, 130)), 540, 300, fx.pop_scale(t - E("bye")), 1.0)
        if t > E("sub"):
            fx.paste_scaled(frame, sub_btn(), 540, 520, fx.pop_scale(t - E("sub")) * (1 + 0.04 * math.sin((t - OUT0) * 7)), 1.0)
        for k in range(8):
            a = 0.5 + 0.5 * math.sin(t * 5 + k * 1.3)
            fx.sparkle(d, 120 + k * 120, 150 + 260 * (k % 2), 14 + 10 * a, int(220 * a))

    if ra > 0:
        fx.rain(d, t, ra)
    fl = thunder_flash(t)
    if fl > 0: frame = fx.flash(frame, fl)
    if sid != "s0":
        draw_lyrics(frame, t)
    fade = max(0.0, (TOTAL - t) / 0.6) if t > TOTAL - 0.6 else 1.0
    frame = grade_frame(frame, cool, warm, fade)
    ai_label(frame)
    return frame


def render_scene(sid):
    s = [x for x in scenes() if x[0] == sid][0]
    f0, f1 = int(round(s[1] * FPS)), int(round(s[2] * FPS))
    out = G["work"] / f"{sid}.mp4"; tmp = G["work"] / f"{sid}.tmp.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    for i in range(f0, f1):
        p.stdin.write(frame_at(i / FPS).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {sid}")
    os.replace(tmp, out)
    return sid, f1 - f0
