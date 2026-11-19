"""FrontLines Maps renderer: a battle, day by day, with moving front lines.
Usage: python render.py battles/<id>.json out.mp4 [--short] [--fps 25]
The battle file lists places with dated control changes; the front line is drawn where the
two sides' zones of control meet (a smooth field built from the places), clipped to land."""
import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
SERIF = os.path.join(FONTS, "Lora-Variable.ttf")
BOLD = os.path.join(FONTS, "Poppins-Bold.ttf")
MED = os.path.join(FONTS, "Poppins-Medium.ttf")
CREAM = (250, 245, 235)
GOLD = (255, 214, 90)
DARK = (8, 10, 14)
NEUTRAL = np.array([96, 93, 86], np.float32)


def font(p, s, bold=False):
    f = ImageFont.truetype(p, s)
    if bold:
        try:
            f.set_variation_by_name("Bold")
        except Exception:
            pass
    return f


def parse(d):
    return dt.date.fromisoformat(d)


ap = argparse.ArgumentParser()
ap.add_argument("battle")
ap.add_argument("out")
ap.add_argument("--short", action="store_true")
ap.add_argument("--fps", type=int, default=25)
ap.add_argument("--data", default=os.path.join(HERE, "data"))
ap.add_argument("--part", default="", help="key of B['parts'] to render only a date window, e.g. 'b'")
ap.add_argument("--thumb", default="", help="write a 1280x720 thumbnail PNG and exit")
ap.add_argument("--preview", type=int, default=0, help="only render N evenly spaced frames to PNG")
a = ap.parse_args()
B = json.load(open(a.battle))

SHORT = a.short
W, H = (1080, 1920) if SHORT else (1920, 1080)
FPS = a.fps
start, end = parse(B["start"]), parse(B["end"])
ndays = (end - start).days + 1
D0, D1 = 0, ndays - 1
PART = (B.get("parts") or {}).get(a.part) if a.part else None
if PART:
    D0, D1 = (parse(PART["from"]) - start).days, (parse(PART["to"]) - start).days
    B = dict(B, title=PART.get("title", B["title"]), subtitle=PART.get("subtitle", B.get("subtitle", "")))
vdays = D1 - D0 + 1
# pacing: long video about 1.8-3 s per day (capped to ~6 min), Short about 55 s total
if SHORT:
    sec_per_day = max(0.35, min(1.6, 50.0 / vdays))
else:
    sec_per_day = max(1.2, min(3.0, 330.0 / vdays))
INTRO, OUTRO = (2.5, 3.0) if SHORT else (5.0, 5.0)
main_len = vdays * sec_per_day
TOTAL = INTRO + main_len + OUTRO
NF = int(TOTAL * FPS)

# ---------- map projection (equirectangular, cos(lat) corrected) ----------
lon0, lat0, lon1, lat1 = B["bbox"]
latc = (lat0 + lat1) / 2
kx = math.cos(math.radians(latc))
# fit bbox into frame keeping aspect; pad the shorter side
bw, bh = (lon1 - lon0) * kx, (lat1 - lat0)
scale = min(W / bw, H / bh) * (0.98 if not SHORT else 1.0)
if SHORT:  # fill the tall frame: use the height, crop width
    scale = H / bh
cx, cy = (lon0 + lon1) / 2, latc
if SHORT and B.get('short_center'):
    cx, cy = B['short_center']


def P(lon, lat):
    return (W / 2 + (lon - cx) * kx * scale, H / 2 - (lat - cy) * scale)


def inv(x, y):
    return (cx + (x - W / 2) / (kx * scale), cy - (y - H / 2) / scale)


# ---------- land and borders from historical-basemaps ----------
gj = json.load(open(os.path.join(a.data, f"world_{B.get('basemap_year', 1938)}.geojson")))
land = Image.new("L", (W, H), 0)
bord = Image.new("L", (W, H), 0)
dl, db = ImageDraw.Draw(land), ImageDraw.Draw(bord)
for f in gj["features"]:
    g = f.get("geometry") or {}
    polys = g.get("coordinates", []) if g.get("type") == "MultiPolygon" else [g.get("coordinates", [])]
    for poly in polys:
        for k, ring in enumerate(poly):
            pts = [P(c[0], c[1]) for c in ring]
            if len(pts) > 2:
                dl.polygon(pts, fill=255 if k == 0 else 0)
                db.line(pts, fill=150, width=2)
LAND = np.asarray(land, np.float32)[..., None] / 255
gy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
OCEAN = np.array([10, 14, 22], np.float32) * (1 - gy) + np.array([20, 28, 40], np.float32) * gy
rng = np.random.default_rng(5)
NZ = np.asarray(Image.fromarray(((rng.normal(0, 1, (H // 12 + 1, W // 12 + 1)) + 3) * 36).clip(0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32)[..., None] / 255
BASE = OCEAN * (1 - LAND) + (NEUTRAL * (0.88 + 0.24 * NZ)) * LAND
BORD = np.asarray(bord, np.float32)[..., None] / 255 * 0.45

# rivers / extra lines (optional): [{"name":..., "points":[[lat,lon],...]}]
riv = Image.new("L", (W, H), 0)
dr = ImageDraw.Draw(riv)
for r in B.get("rivers", []):
    dr.line([P(p[1], p[0]) for p in r["points"]], fill=255, width=4 if not SHORT else 5, joint="curve")
RIV = np.asarray(riv.filter(ImageFilter.GaussianBlur(1)), np.float32)[..., None] / 255 * 0.8
RIVC = np.array([40, 70, 110], np.float32)

# ---------- control field ----------
sides = B["sides"]
COL = {k: np.array(v["color"], np.float32) for k, v in sides.items()}
GW, GH = W // 4, H // 4
gx, gyy = np.meshgrid(np.arange(GW) * 4 + 2, np.arange(GH) * 4 + 2)
glon, glat = inv(gx, gyy)
places = B["places"] + [dict(p, label=False) for p in B.get("anchors", [])]
sigma = B.get("sigma_deg", 1.2)
Wt = []
for p in places:
    dx = (glon - p["lon"]) * kx
    dyy = glat - p["lat"]
    Wt.append(np.exp(-(dx * dx + dyy * dyy) / (2 * sigma * sigma)) * p.get("weight", 1.0))
Wt = np.stack(Wt).astype(np.float32)  # K x GH x GW
INFL = 1 - np.exp(-(Wt.sum(0)) * 3)
Wt = Wt ** 4  # close to nearest-place ownership, keeps small pockets
Wsum = Wt.sum(0) + 1e-12  # how much a pixel is "in" the war zone


def owner_at(p, day):
    """0 = side A, 1 = side B, blended over 1 day after each change."""
    ctrl = sorted(p["control"], key=lambda c: c[0])
    val = None
    for i, (d, s) in enumerate(ctrl):
        di = (parse(d) - start).days
        v = 0.0 if s == "A" else 1.0
        if val is None:
            val = v
            if day < di:
                break
            continue
        if day >= di + 1:
            val = v
        elif day > di:
            val = val + (v - val) * (day - di)
    return val if val is not None else 0.5


def field(day):
    o = np.array([owner_at(p, day) for p in places], np.float32)
    v = (Wt * o[:, None, None]).sum(0) / Wsum
    im = Image.fromarray((v * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))
    v = np.asarray(im, np.float32)[..., None] / 255
    return 1 / (1 + np.exp(-(v - 0.5) * 55))  # crisp zones with a soft 1-2 px edge


INF = np.asarray(Image.fromarray((INFL * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6)), np.float32)[..., None] / 255

# ---------- text ----------
FS = 1.0 if not SHORT else 1.35
f_date = font(SERIF, int(64 * FS), True)
f_day = font(BOLD, int(30 * FS))
f_evt = font(MED, int(40 * FS))
f_city = font(BOLD, int(22 * FS))
f_leg = font(BOLD, int(24 * FS))
f_title = font(SERIF, int(96 * FS), True)
f_sub = font(MED, int(40 * FS))
events = sorted(B.get("events", []), key=lambda e: e["date"])
MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]


def wrap(d, text, f, maxw):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def arrow(d, p0, p1, col, w, frac):
    x0, y0 = p0
    x1, y1 = x0 + (p1[0] - x0) * frac, y0 + (p1[1] - y0) * frac
    d.line([(x0, y0), (x1, y1)], fill=col, width=w)
    ang = math.atan2(y1 - y0, x1 - x0)
    L = w * 3
    d.polygon([(x1, y1), (x1 - L * math.cos(ang - 0.5), y1 - L * math.sin(ang - 0.5)), (x1 - L * math.cos(ang + 0.5), y1 - L * math.sin(ang + 0.5))], fill=col)


def frame(t):
    if t < INTRO:
        day = float(D0)
    elif t < INTRO + main_len:
        day = D0 + (t - INTRO) / sec_per_day
    else:
        day = float(D1)
    v = field(day)
    inf = INF
    colz = COL["A"] * (1 - v) + COL["B"] * v
    landc = BASE * (1 - inf * 0.8) + colz * (inf * 0.8) * (0.9 + 0.2 * NZ)
    img = BASE * (1 - LAND) + landc * LAND
    img = img * (1 - RIV * LAND) + RIVC * (RIV * LAND)
    edge = (4 * v * (1 - v)) ** 2.5 * np.clip((inf - 0.55) / 0.3, 0, 1) * LAND * 0.95
    img = img * (1 - edge) + np.array(GOLD, np.float32) * edge
    img = img * (1 - BORD) + np.array([18, 18, 22], np.float32) * BORD
    pic = Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    # cities
    for p in B["places"]:
        if not p.get("label", True):
            continue
        x, y = P(p["lon"], p["lat"])
        if not (0 <= x <= W and 0 <= y <= H):
            continue
        if p.get("side_label") != "left" and x + 9 * FS + 6 + d.textlength(p["name"], font=f_city) > W - 8:
            p = dict(p, side_label="left")
        if p.get("side_label") == "left" and x - 9 * FS - 6 - d.textlength(p["name"], font=f_city) < 8:
            continue
        o = owner_at(p, day)
        c = tuple(int(q) for q in (COL["A"] * (1 - o) + COL["B"] * o))
        r = 9 * FS if p.get("big") else 6 * FS
        d.ellipse((x - r, y - r, x + r, y + r), fill=c + (255,), outline=(255, 255, 255, 255), width=2)
        if p.get("side_label") == "left":
            d.text((x - r - 6, y), p["name"], font=f_city, fill=CREAM, anchor="rm", stroke_width=3, stroke_fill=DARK)
        else:
            d.text((x + r + 6, y), p["name"], font=f_city, fill=CREAM, anchor="lm", stroke_width=3, stroke_fill=DARK)
    # event arrows and caption
    cur = None
    for e in events:
        ed = (parse(e["date"]) - start).days
        if ed - 0.2 <= day <= ed + max(2.5, 3.5 / sec_per_day):
            cur = e
            if e.get("arrow"):
                fr, to = e["arrow"]["from"], e["arrow"]["to"]
                frac = min(1.0, max(0.05, (day - ed + 0.2) / 1.5))
                col = tuple(int(q) for q in COL[e["arrow"].get("side", "B")]) + (255,)
                arrow(d, P(fr[1], fr[0]), P(to[1], to[0]), (255, 255, 255, 235), int(14 * FS), frac)
                arrow(d, P(fr[1], fr[0]), P(to[1], to[0]), col, int(8 * FS), frac)
    # top-left date + day counter
    dd = start + dt.timedelta(days=int(min(day, ndays - 1)))
    m = int(24 * FS)
    box_w = int(560 * FS) if not SHORT else W - 2 * m
    d.rounded_rectangle((m, m, m + box_w, m + int(150 * FS)), radius=18, fill=(0, 0, 0, 150))
    d.text((m + 24, m + int(52 * FS)), f"{dd.day} {MONTHS[dd.month - 1]} {dd.year}", font=f_date, fill=CREAM, anchor="lm")
    d.text((m + 26, m + int(118 * FS)), f"DAY {int(min(day, ndays - 1)) + 1} OF {ndays}", font=f_day, fill=GOLD, anchor="lm")
    # legend
    ly = m + int(150 * FS) + 16 if SHORT else m
    lx = m if SHORT else W - m - int(380 * FS)
    d.rounded_rectangle((lx, ly, lx + int(380 * FS), ly + int(100 * FS)), radius=16, fill=(0, 0, 0, 150))
    for i, (k, s) in enumerate(sides.items()):
        yy = ly + int(30 * FS) + i * int(40 * FS)
        d.rectangle((lx + 20, yy - 12, lx + 50, yy + 12), fill=tuple(s["color"]) + (255,))
        d.text((lx + 64, yy), s["name"], font=f_leg, fill=CREAM, anchor="lm")
    # caption
    if cur and t <= INTRO + main_len and not a.thumb:
        lines = wrap(d, cur["text"], f_evt, W - 2 * m - 60)
        hh = int(56 * FS) * len(lines) + 30
        y0 = H - m - hh - (int(260) if SHORT else 30)
        d.rounded_rectangle((m, y0, W - m, y0 + hh), radius=18, fill=(0, 0, 0, 175))
        for i, ln in enumerate(lines):
            d.text((W / 2, y0 + 15 + int(56 * FS) * (i + 0.5)), ln, font=f_evt, fill=CREAM, anchor="mm")
    d.text((W - 14, H - 10), "Borders: historical-basemaps (A. Ourednik, GPL-3.0). Front lines approximate.", font=font(MED, 16), fill=(220, 220, 220, 170), anchor="rd")
    # intro / outro cards
    if t < INTRO:
        al = 1.0 if t < INTRO - 0.7 else (INTRO - t) / 0.7
        card = Image.new("RGBA", (W, H), (0, 0, 0, int(170 * al)))
        cd = ImageDraw.Draw(card)
        tl = wrap(cd, B["title"].upper(), f_title, W - 160)
        for i, ln in enumerate(tl):
            cd.text((W / 2, H * 0.42 + (i - (len(tl) - 1) / 2) * int(110 * FS)), ln, font=f_title, fill=CREAM + (int(255 * al),), anchor="mm", stroke_width=6, stroke_fill=DARK + (int(255 * al),))
        cd.text((W / 2, H * 0.42 + len(tl) * int(62 * FS) + 30), B.get("subtitle", ""), font=f_sub, fill=GOLD + (int(255 * al),), anchor="mm")
        over = Image.alpha_composite(over, card)
    if t > INTRO + main_len:
        al = min(1.0, (t - INTRO - main_len) / 0.8)
        card = Image.new("RGBA", (W, H), (0, 0, 0, int(185 * al)))
        cd = ImageDraw.Draw(card)
        tl = wrap(cd, B.get("outro", "WHICH BATTLE NEXT?"), f_title, W - 140)
        lh = int(115 * FS)
        y0 = H * 0.42 - (len(tl) - 1) * lh / 2
        for i, ln in enumerate(tl):
            cd.text((W / 2, y0 + i * lh), ln, font=f_title, fill=CREAM + (int(255 * al),), anchor="mm", stroke_width=6, stroke_fill=DARK + (int(255 * al),))
        sub = ["Comment below", "Subscribe to FrontLines Maps"] if SHORT else ["Comment below  •  Subscribe to FrontLines Maps"]
        for i, ln in enumerate(sub):
            cd.text((W / 2, y0 + (len(tl) - 1) * lh + int(110 * FS) + i * int(60 * FS)), ln, font=f_sub, fill=GOLD + (int(255 * al),), anchor="mm")
        over = Image.alpha_composite(over, card)
    return Image.alpha_composite(pic, over).convert("RGB")


if a.thumb:
    # thumbnail: the map at the battle's turning point, big title, day badge
    tday = (parse(B.get("thumb_date", B["end"])) - start).days
    im = frame(INTRO + (tday - D0 + 0.5) * sec_per_day).resize((1280, int(1280 * H / W)))
    if im.height != 720:
        top = (im.height - 720) // 2
        im = im.crop((0, top, 1280, top + 720))
    dd = ImageDraw.Draw(im, "RGBA")
    dd.rectangle((0, 470, 1280, 720), fill=(0, 0, 0, 150))
    words = B.get("thumb_text", B["title"].split(":")[0]).upper()
    ft = font(SERIF, 120, True)
    while dd.textlength(words, font=ft) > 1200:
        ft = font(SERIF, ft.size - 6, True)
    dd.text((640, 560), words, font=ft, fill=CREAM, anchor="mm", stroke_width=6, stroke_fill=DARK)
    dd.text((640, 665), f"DAY BY DAY  •  {ndays} DAYS", font=font(BOLD, 48), fill=GOLD, anchor="mm", stroke_width=3, stroke_fill=DARK)
    im.save(a.thumb)
    sys.exit(0)

if a.preview:
    for i in range(a.preview):
        t = INTRO + 0.5 + (main_len - 1) * i / max(1, a.preview - 1)
        frame(t).save(f"{a.out}.{i}.png")
    sys.exit(0)

# ---------- music: original slow Ottoman war track (music/styles.py) ----------
mw = a.out + ".music.wav"
subprocess.run([sys.executable, os.path.join(HERE, "music", "styles.py"), B.get("music", "ottoman_slow"), mw, f"{TOTAL:.2f}"], check=True)

ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                       "-i", mw, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                       "-shortest", "-movflags", "+faststart", a.out], stdin=subprocess.PIPE)
for i in range(NF):
    ff.stdin.write(frame(i / FPS).tobytes())
    if i % (FPS * 20) == 0:
        print(f"frame {i}/{NF}", flush=True)
ff.stdin.close()
ff.wait()
os.remove(mw)
print("done", a.out, f"{TOTAL:.1f}s")
