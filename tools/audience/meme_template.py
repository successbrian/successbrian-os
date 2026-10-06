#!/usr/bin/env python3
"""SuccessBrian reusable meme template — 1080x1080 social cards (LIGHT edition).

PURPOSE:
    One branded layout for every @successbrian insight meme. Drop in new
    content (headline + chart cards + punchline) and render a fresh card.
    Brand = SuccessBrian. Light background for readability; headline ALWAYS
    renders as multi-color gradient with 3D extrusion. Keep it bold and
    simple — curiosity over complexity. The audience should think
    "wow, what is Brian telling me here?" and ask questions.

    AI-template signature visuals (built in): a faint neural-network
    constellation along the edges, the android emblem (glowing badge with
    the humanoid android) standing watch top-right — exactly one robot
    per meme — plus the kicker flanked by AI sparkles.

WHY:
    Brian's standing design rules: light background because readability
    comes first — a card that can't be read in one glance gets scrolled
    past. The headline renders as multi-color gradient with 3D extrusion
    and drop shadow because that is the hook — bold, simple, built to
    spark curiosity so people ask questions in the comments. Cards stay
    comparative and plain-worded so casual observers relate without
    knowing brand names. Every render is 1080x1080 square, no exceptions;
    one format keeps the feed consistent and the template code simple.

USAGE:
    from meme_template import render_meme
    render_meme(CONTENT, photo_path="/path/they.jpg", out_path="meme.png")

    CONTENT = {
        "kicker": "SMALL CAPS HOOK",
        "headline": "THE $620 RAM SCAM",   # gradient+3D applied automatically
        "grad_colors": ["#22d3ee", "#3b82f6", "#8b5cf6", "#e879f9"],  # optional override (holographic)
        "cards": [
            {"tag": "WHAT THEY SELL YOU", "title": "1x 32GB MACO",
             "price": "$1,099", "sub": "32GB total • 1 computer",
             "bar_frac": 0.58, "bar_color": "#ff5a5a"},
            ...
        ],
        "punchline": "+16GB MORE RAM • A SECOND COMPUTER • $141 LESS",
        "curiosity": "Curious how I figured this out? Ask me below.",
        # optional debate strip between cards and punchline:
        # "counterpoint": {"label": "THE OTHER SIDE — SOURCE, DATE",
        #                  "quote": "Their verdict, in their words."},
        # optional series progress dots: "series_day": 1..5
        # optional hashtag CTA: CONTENT["hashtag"] overrides the brand default
        # (the AI brand default is "FOLLOW #SuccessBrianAI"; each topic
        # template carries its own hashtag in its brand dict),
    }

BRAND defaults below are Brian's; override per user.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
try:
    import qrcode
except ImportError:
    qrcode = None
import math
import os

W = H = 1080
FB = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"

BRAND = {
    "wordmark": [("SUCCESS", "#16213a"), ("BRIAN", "#0aa5e0")],
    "tagline": "AI INSIGHTS THAT SAVE YOU REAL MONEY",
    "accent": "#0aa5e0",
    "handles": [
        ("facebook", "@successbrian"),
        ("instagram", "@successbrian"),
        ("x", "@MAGAUSNavyVet"),
        ("whatsapp", "+1 952 657 9982"),
    ],
    "blog_url": "successbrianhub.substack.com",
    # per-topic hashtag CTA — each template gets its own; the footer prints
    # CONTENT["hashtag"] if given, else this brand default, else nothing.
    "hashtag": "FOLLOW #SuccessBrianAI",
}

# Health desk brand: same handles/blog as the AI brand, own hashtag.
# (Dedicated health visuals are a future build; health memes render on the
# AI template chrome for now.)
HEALTH_BRAND = dict(BRAND)
HEALTH_BRAND["hashtag"] = "FOLLOW #SuccessBrianHealth"

INK = "#16213a"        # body text on light
GRAY = "#5b6474"
FAINT = "#8a93a3"
YELLOW = "#ffd23f"
GARNET_BG = "#7e2e3f"   # soft garnet — Brian's January birthstone
GARNET_EDGE = "#b3566a"


def font(path, size):
    return ImageFont.truetype(path, size)


# ---------------- color helpers ----------------
def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))


def _mix(h1, h2, f):
    a, b = _hex(h1), _hex(h2)
    return "#%02x%02x%02x" % tuple(int(x+(y-x)*f) for x, y in zip(a, b))


def grad_rounded(size, colors, radius):
    """Horizontal multi-color gradient with rounded corners (RGBA)."""
    w, h = size
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    n = len(colors)
    for x in range(w):
        t = x/max(1, w-1); seg = t*(n-1); i = int(seg); f = seg-i
        c1 = _hex(colors[i]); c2 = _hex(colors[min(i+1, n-1)])
        gd.line([(x, 0), (x, h)],
                fill=tuple(int(a+(b-a)*f) for a, b in zip(c1, c2)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def _gbar(base, box, color):
    """Vertical-gradient rounded bar pasted onto base image."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = max(1, x1-x0), max(1, y1-y0)
    light = _mix(color, "#ffffff", 0.45)
    bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    for yy in range(h):
        t = yy/max(1, h-1)
        a, b = _hex(color), _hex(light)
        bd.line([(0, yy), (w, yy)],
                fill=tuple(int(p+(q-p)*t) for p, q in zip(a, b))+(255,))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], h//2, fill=255)
    base.paste(bar, (x0, y0), mask)


# ---------------- social icons (simple, recognizable) ----------------
def _rr(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def icon(kind, size=56):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = 2
    if kind == "facebook":
        _rr(d, [pad, pad, size-pad, size-pad], size//4, "#1877f2")
        f = font(FB, int(size*0.62))
        t = "f"; tw = d.textlength(t, font=f)
        d.text(((size-tw)/2, size*0.16), t, font=f, fill="white")
    elif kind == "instagram":
        # colorful IG: purple -> pink -> orange gradient + white camera glyph
        sq = grad_rounded((size, size), ["#833ab4", "#fd1d1d", "#fcb045"], size//4)
        im.alpha_composite(sq)
        d = ImageDraw.Draw(im)
        pad2 = int(size*0.20)
        d.rounded_rectangle([pad2, pad2, size-pad2, size-pad2], int(size*0.14),
                            outline="white", width=max(3, int(size*0.075)))
        r = size*0.115
        d.ellipse([size/2-r, size/2-r, size/2+r, size/2+r],
                  outline="white", width=max(3, int(size*0.075)))
        dr = size*0.05; cx, cy = size*0.685, size*0.315
        d.ellipse([cx-dr, cy-dr, cx+dr, cy+dr], fill="white")
    elif kind == "x":
        _rr(d, [pad, pad, size-pad, size-pad], size//4, "#000000", None, 1)
        # subtle light outline so the black tile reads on light backgrounds
        d.rounded_rectangle([pad-1, pad-1, size-pad+1, size-pad+1], size//4,
                            outline=(205, 212, 224, 255), width=2)
        # thick-stroked X, drawn not typed — unmistakable at any size
        m = size * 0.26
        w = max(5, int(size * 0.15))
        d.line([(m, m), (size-m, size-m)], fill="white", width=w)
        d.line([(size-m, m), (m, size-m)], fill="white", width=w)
    elif kind == "blog":
        _rr(d, [pad, pad, size-pad, size-pad], size//4, "#ff6719")
        for i, yy in enumerate([0.30, 0.47, 0.64]):
            ww = size*(0.52 if i < 2 else 0.34)
            d.rounded_rectangle([size/2-ww/2, size*yy-3, size/2+ww/2, size*yy+3],
                                3, fill="white")
    elif kind == "whatsapp":
        d.ellipse([pad, pad, size-pad, size-pad], fill="#25d366")
        bw, bh = size*0.52, size*0.42
        bx, by = (size-bw)/2, (size-bh)/2 - 2
        _rr(d, [bx, by, bx+bw, by+bh], 10, "white")
        d.polygon([(bx+bw*0.30, by+bh-2), (bx+bw*0.22, by+bh+10), (bx+bw*0.48, by+bh-2)],
                  fill="white")
    return im


# ---------------- photo slot ----------------
def photo_card(photo_path, size=148):
    """Rounded photo of Brian & Gina together; placeholder if none provided."""
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    im = None
    if photo_path and os.path.exists(photo_path):
        try:
            im = Image.open(photo_path).convert("RGB")
        except Exception:
            im = None
    if im is not None:
        s = min(im.size)
        im = im.crop(((im.width-s)//2, (im.height-s)//2,
                      (im.width+s)//2, (im.height+s)//2)).resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], 28, fill=255)
        card.paste(im, (0, 0), mask)
        d.rounded_rectangle([0, 0, size, size], 28, outline=(10, 165, 224, 255), width=4)
    else:
        d.rounded_rectangle([0, 0, size, size], 28, fill=(232, 237, 245, 255),
                            outline=(140, 150, 168, 255), width=3)
        for a in range(0, 360, 18):
            d.arc([8, 8, size-8, size-8], a, a+10, fill=(10, 165, 224, 200), width=3)
        f = font(FB, 20)
        for i, t in enumerate(["YOUR", "PHOTO", "HERE"]):
            tw = d.textlength(t, font=f)
            d.text(((size-tw)/2, size/2-34+i*26), t, font=f, fill=(120, 132, 150, 255))
    return card


# ---------------- AI visuals (the AI template's signature) ----------------
def _head_path(cx, cyc, rx, ry, jaw_drop, n=28):
    """Smooth head silhouette: elliptical cranium flowing into a soft jaw."""
    pts = []
    for i in range(n + 1):  # over the top, left -> right
        a = math.pi - i * math.pi / n
        pts.append((cx + rx * math.cos(a), cyc - ry * math.sin(a)))
    jaw = [(0.88, 0.35), (0.72, 0.60), (0.50, 0.80), (0.28, 0.93),
           (0.10, 1.0), (0.0, 1.0)]
    for fx, fy in jaw:  # right side down to the chin
        pts.append((cx + rx * fx, cyc + jaw_drop * fy))
    for fx, fy in reversed(jaw[1:]):  # mirror up the left side
        pts.append((cx - rx * fx, cyc + jaw_drop * fy))
    pts.append((cx - rx * 0.94, cyc + jaw_drop * 0.38))
    return pts


def _vgrad_masked(size, top_rgb, bot_rgb, poly):
    """Vertical RGB gradient masked by a polygon — metallic fills."""
    s = size
    strip = Image.new("RGB", (1, s))
    px = strip.load()
    for y in range(s):
        t = y / max(1, s - 1)
        px[0, y] = (round(top_rgb[0] + (bot_rgb[0] - top_rgb[0]) * t),
                    round(top_rgb[1] + (bot_rgb[1] - top_rgb[1]) * t),
                    round(top_rgb[2] + (bot_rgb[2] - top_rgb[2]) * t))
    grad = strip.resize((s, s)).convert("RGBA")
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    grad.putalpha(mask)
    return grad


def icon_robot(size=120, dark="#16213a", glow="#4dd8ff"):
    """Humanoid android bust — metallic, glowing eyes. The AI mascot."""
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cx = s / 2

    # shoulders: chamfered plate, metallic
    sh = [(cx - s * 0.30, s * 0.99), (cx - s * 0.30, s * 0.85),
          (cx - s * 0.21, s * 0.78), (cx + s * 0.21, s * 0.78),
          (cx + s * 0.30, s * 0.85), (cx + s * 0.30, s * 0.99)]
    im.alpha_composite(_vgrad_masked(s, (228, 235, 246), (155, 172, 197), sh))
    d = ImageDraw.Draw(im)
    d.polygon(sh, outline=dark, width=3)
    # chest core
    cr = s * 0.030
    d.ellipse([cx - cr * 2.2, s * 0.885 - cr * 2.2,
               cx + cr * 2.2, s * 0.885 + cr * 2.2],
              fill=(77, 216, 255, 90))
    d.ellipse([cx - cr, s * 0.885 - cr, cx + cr, s * 0.885 + cr],
              fill=glow, outline=dark, width=2)

    # neck
    nk = [(cx - s * 0.085, s * 0.58), (cx + s * 0.085, s * 0.58),
          (cx + s * 0.085, s * 0.79), (cx - s * 0.085, s * 0.79)]
    im.alpha_composite(_vgrad_masked(s, (232, 238, 248), (165, 180, 202), nk))
    d = ImageDraw.Draw(im)
    d.polygon(nk, outline=dark, width=2)
    d.line([(cx - s * 0.085, s * 0.66), (cx + s * 0.085, s * 0.66)],
           fill=dark, width=2)

    # head: metallic gradient under a smooth cranium-to-jaw silhouette
    head = _head_path(cx, s * 0.30, s * 0.27, s * 0.25, s * 0.30)
    im.alpha_composite(_vgrad_masked(s, (240, 244, 251), (164, 181, 204), head))
    d = ImageDraw.Draw(im)
    d.polygon(head, outline=dark, width=3)
    # face plate: lighter inset
    face = _head_path(cx, s * 0.305, s * 0.225, s * 0.205, s * 0.25)
    im.alpha_composite(_vgrad_masked(s, (249, 251, 254), (212, 222, 235), face))
    d = ImageDraw.Draw(im)
    # cranium seam
    d.line([(cx, s * 0.205), (cx, s * 0.075)], fill=(118, 134, 160), width=2)
    # forehead sensor
    r = s * 0.018
    d.ellipse([cx - r, s * 0.175 - r, cx + r, s * 0.175 + r],
              fill=glow, outline=dark, width=2)
    # soft brows
    bw = max(2, int(s * 0.022))
    d.line([(cx - s * 0.150, s * 0.298), (cx - s * 0.055, s * 0.306)],
           fill=dark, width=bw)
    d.line([(cx + s * 0.055, s * 0.306), (cx + s * 0.150, s * 0.298)],
           fill=dark, width=bw)
    # glowing human-like eyes
    ey = s * 0.365
    for ex in (cx - s * 0.105, cx + s * 0.105):
        er = s * 0.055
        d.ellipse([ex - er * 1.4, ey - er * 1.0, ex + er * 1.4, ey + er * 1.0],
                  fill=(77, 216, 255, 70))
        d.ellipse([ex - er, ey - er * 0.60, ex + er, ey + er * 0.60],
                  fill="white", outline=dark, width=2)
        ir = s * 0.026
        d.ellipse([ex - ir, ey - ir, ex + ir, ey + ir], fill=glow)
        pr = s * 0.011
        d.ellipse([ex - pr, ey - pr, ex + pr, ey + pr], fill=dark)
        hx, hy = ex - ir * 0.75, ey - ir * 0.85
        d.ellipse([hx, hy, hx + s * 0.016, hy + s * 0.016], fill="white")
    # nose ridge
    d.line([(cx, s * 0.415), (cx, s * 0.475)], fill=dark,
           width=max(2, int(s * 0.018)))
    # mouth - calm, slight smile
    d.arc([cx - s * 0.06, s * 0.50, cx + s * 0.06, s * 0.585],
          25, 155, fill=dark, width=max(2, int(s * 0.02)))
    # ear discs
    for ex in (cx - s * 0.27, cx + s * 0.27):
        r = s * 0.042
        d.ellipse([ex - r, s * 0.355 - r, ex + r, s * 0.355 + r],
                  fill=dark, outline=glow, width=2)
    return im


def android_emblem(size=170, ring="#38b6ff"):
    """The android inside a glowing badge - the one hero emblem per meme."""
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cx = cy = s / 2
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([cx - s * 0.47, cy - s * 0.47, cx + s * 0.47, cy + s * 0.47],
               fill=(56, 182, 255, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(max(4, int(s * 0.07))))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)
    d.ellipse([cx - s * 0.40, cy - s * 0.40, cx + s * 0.40, cy + s * 0.40],
              fill=(241, 246, 253, 255), outline="#c3d2e8", width=2)
    d.ellipse([cx - s * 0.40, cy - s * 0.40, cx + s * 0.40, cy + s * 0.40],
              outline=ring, width=max(3, int(s * 0.028)))
    r2 = s * 0.345
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
              outline=(56, 182, 255, 170), width=2)
    bot = icon_robot(int(s * 0.60))
    im.paste(bot, (int(cx - bot.width / 2),
                   int(cy - bot.height / 2 - s * 0.015)), bot)
    return im


def icon_spark(size=44, color="#8b2bff"):
    """Four-point AI sparkle."""
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = s / 2
    r = s / 2 - 2
    k = r * 0.22
    d.polygon([(cx, cy - r), (cx + k, cy - k), (cx + r, cy),
               (cx + k, cy + k), (cx, cy + r), (cx - k, cy + k),
               (cx - r, cy), (cx - k, cy - k)], fill=color)
    return im


def ai_backdrop(img):
    """Faint neural-network constellation along the edges — AI texture
    that never touches the readable middle."""
    import random
    rnd = random.Random(73)
    w, h = img.size
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    pts = []
    for _ in range(9):
        pts.append((rnd.randint(24, 190), rnd.randint(60, h - 60)))
    for _ in range(9):
        pts.append((rnd.randint(w - 190, w - 24), rnd.randint(60, h - 60)))
    for i, (x1, y1) in enumerate(pts):
        for x2, y2 in pts[i + 1:]:
            if ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 < 300:
                d.line([(x1, y1), (x2, y2)], fill=(160, 170, 225, 60), width=2)
    for x, y in pts:
        r = rnd.randint(4, 8)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(150, 130, 220, 85))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def kicker_ai(img, y, text):
    """Kicker flanked by AI sparkles — the AI template signature.
    (The android appears exactly once per meme, as the emblem top-right.)"""
    d = ImageDraw.Draw(img)
    kf = font(FB, 25)
    tw = d.textlength(text, font=kf) + 3 * (len(text) - 1)
    cx = img.size[0] / 2
    _centered(d, y, text, kf, "#0a7fd4", tracking=3)
    for sx in (int(cx - tw / 2 - 58), int(cx + tw / 2 + 20)):
        sp = icon_spark(36)
        img.paste(sp, (sx, y - 6), sp)
    return img


def footer(img, d, hashtag=None, dy=0, brand=None):
    """Bottom branding, shared by the AI and political templates.

    Cleaner rhythm: stronger divider, 48px social icons with 20px handles,
    generous row spacing, then the blog row and an explicit hashtag CTA.
    dy shifts the whole stack (counterpoint memes). The hashtag resolves as:
    explicit `hashtag` arg wins, else brand["hashtag"], else no line.
    Each topic template carries its own hashtag in its brand dict.
    """
    b = brand or BRAND
    tag = hashtag if hashtag is not None else b.get("hashtag")
    d.line([(48, 840 + dy), (W-48, 840 + dy)], fill=(190, 200, 214, 255),
           width=3)
    items = [(icon(kind, 48), handle) for kind, handle in b["handles"]]
    widths = [48 + 12 + d.textlength(h, font=font(FR, 20)) for _, h in items]
    total_w = sum(widths) + 36 * (len(items) - 1)
    x = (W - total_w) / 2
    y_ic = 852 + dy
    for (ic, handle), wdt in zip(items, widths):
        img.paste(ic, (int(x), y_ic), ic)
        d.text((x + 48 + 12, y_ic + 9), handle, font=font(FR, 20), fill=INK)
        x += wdt + 36
    d = ImageDraw.Draw(img)
    bic = icon("blog", 48)
    url = b["blog_url"]
    f_blog = font(FB, 30)
    tw = d.textlength(url, font=f_blog)
    bx = (W - (48 + 14 + tw)) / 2
    img.paste(bic, (int(bx), 910 + dy), bic)
    d.text((bx + 48 + 14, 912 + dy), url, font=f_blog, fill=INK)
    if tag:
        _centered(d, 962 + dy, tag, font(FB, 28), "#0a7fd4")
    return img, ImageDraw.Draw(img)


# ---------------- light background ----------------
def background():
    img = Image.new("RGB", (W, H), "#f4f6fb")
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        # very light cool gradient: #fbfcfe -> #e9eef6
        r = int(251 - 14*t); g = int(252 - 12*t); b = int(254 - 8*t)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    # soft blue glow top + faint warm/cool washes for color
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W//2-460, -280, W//2+460, 360], fill=(120, 190, 255, 60))
    gd.ellipse([W-560, H-460, W+160, H+120], fill=(255, 196, 150, 44))
    gd.ellipse([-200, H-420, 420, H+80], fill=(196, 160, 255, 40))
    img = Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(70))).convert("RGB")
    return img


def _centered(d, y, text, fnt, fill, tracking=0):
    if tracking:
        tw = d.textlength(text, font=fnt) + tracking*(len(text)-1)
        x = (W-tw)/2
        for ch in text:
            d.text((x, y), ch, font=fnt, fill=fill)
            x += d.textlength(ch, font=fnt) + tracking
        return
    d.text(((W-d.textlength(text, font=fnt))/2, y), text, font=fnt, fill=fill)


# ---------------- gradient + 3D headline ----------------
def headline_3d(base, text, fnt, colors, depth=7):
    """Multi-color vertical gradient face + 3D extrusion + soft shadow.
    Returns (layer, (w, h)) sized to the text."""
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    bbox = tmp.textbbox((0, 0), text, font=fnt)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    pad = 24
    lw, lh = tw + pad*2 + depth + 14, th + pad*2 + depth + 18
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ox, oy = pad - bbox[0], pad - bbox[1]

    # soft drop shadow
    sh = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((ox+5, oy+9), text, font=fnt, fill=(20, 30, 60, 110))
    layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(layer)

    # 3D extrusion: dark navy block behind, offset down-right
    for i in range(depth, 0, -1):
        d.text((ox+i, oy+i), text, font=fnt, fill=(26, 36, 80, 255))
    # darker edge on the extrusion for depth
    d.text((ox+depth, oy+depth), text, font=fnt, fill=(16, 22, 54, 255))

    # gradient face
    n = len(colors)
    face = Image.new("RGBA", (tw+8, th+8), (0, 0, 0, 0))
    fd = ImageDraw.Draw(face)
    mask = Image.new("L", (tw+8, th+8), 0)
    ImageDraw.Draw(mask).text((4-bbox[0], 4-bbox[1]), text, font=fnt, fill=255)
    for yy in range(th+8):
        t = yy / max(1, th+7)
        seg = t*(n-1); i = int(seg); f = seg-i
        c1 = _hex(colors[i]); c2 = _hex(colors[min(i+1, n-1)])
        col = tuple(int(a+(b-a)*f) for a, b in zip(c1, c2))
        fd.line([(0, yy), (tw+8, yy)], fill=col+(255,))
    face.putalpha(mask)
    # subtle top highlight on the face
    hi = Image.new("RGBA", (tw+8, th+8), (0, 0, 0, 0))
    ImageDraw.Draw(hi).text((4-bbox[0], 4-bbox[1]), text, font=fnt, fill=(255, 255, 255, 70))
    himask = mask.point(lambda v: int(v*0.35) if True else v)
    hi.putalpha(himask)
    face = Image.alpha_composite(face, hi)

    layer.alpha_composite(face, (ox-4+bbox[0], oy-4+bbox[1]))
    return layer, (lw, lh)


# ---------------- main render ----------------
def render_meme(content, photo_path=None, out_path="meme.png", brand=None):
    b = brand or BRAND
    img = ai_backdrop(background())
    d = ImageDraw.Draw(img)

    # brand bar
    pc = photo_card(photo_path)
    img.paste(pc, (48, 36), pc)
    x = 48 + 148 + 24
    wx = x
    for word, color in b["wordmark"]:
        f = font(FB, 46)
        d.text((wx, 44), word, font=f, fill=color)
        wx += d.textlength(word, font=f) + 10
    d.text((x, 104), b["tagline"], font=font(FR, 21), fill=GRAY)

    # android emblem standing watch, top right — the one robot on the meme
    emb = android_emblem(150)
    img.paste(emb, (W - 30 - 150, 22), emb)
    d = ImageDraw.Draw(img)

    # kicker with AI emblems (robot + spark)
    img = kicker_ai(img, 216, content["kicker"])
    d = ImageDraw.Draw(img)

    # headline: gradient + 3D, always (auto-fit so the extrusion never clips)
    size = 92
    _tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > 40:
        f_big = font(FB, size)
        tw = _tmp.textlength(content["headline"], font=f_big)
        if tw + 2 * 24 + 7 + 14 + 24 <= W - 24:
            break
        size -= 2
    colors = content.get("grad_colors", ["#22d3ee", "#3b82f6", "#8b5cf6", "#e879f9"])
    hl, (lw, lh) = headline_3d(img, content["headline"], f_big, colors)
    img.paste(hl, ((W-lw)//2, 254), hl)
    # colorful gradient divider under headline
    div = grad_rounded((440, 9), ["#22d3ee", "#3b82f6", "#8b5cf6", "#e879f9"], 4)
    img.paste(div, ((W-440)//2, 398), div)
    d = ImageDraw.Draw(img)
    # series progress dots (optional): CONTENT["series_day"] = 1..5
    if content.get("series_day"):
        _sd = content["series_day"]
        _r, _gap = 7, 12
        _total = 5 * _r * 2 + 4 * _gap
        _sx = (W - _total) / 2
        for _i in range(5):
            _cx = _sx + _r + _i * (_r * 2 + _gap)
            if _i < _sd:
                d.ellipse([_cx - _r, 416 - _r, _cx + _r, 416 + _r],
                          fill="#0a7fd4")
            else:
                d.ellipse([_cx - _r, 416 - _r, _cx + _r, 416 + _r],
                          outline="#b9c4d6", width=2)

    # cards: tinted, soft shadow, gradient bars
    cards = content["cards"]
    n = len(cards)
    gap, margin = 32, 48
    cw = (W - 2*margin - gap*(n-1)) / n
    cy0, ch = 424, 252
    for i, c in enumerate(cards):
        x = margin + i*(cw+gap)
        tint = c.get("tint", "#ffffff")
        d.rounded_rectangle([x+6, cy0+10, x+cw+6, cy0+ch+10], 26, fill=(178, 188, 205, 255))
        d.rounded_rectangle([x, cy0, x+cw, cy0+ch], 26, fill=tint,
                            outline=(210, 218, 230, 255), width=2)
        cx = x + cw/2
        for txt, fnt, col, yy in [
            (c["tag"], font(FB, 19), FAINT, cy0+24),
            (c["title"], font(FB, 30), INK, cy0+54),
            (c["price"], font(FB, 66), c["bar_color"], cy0+96),
        ]:
            tw = d.textlength(txt, font=fnt)
            d.text((cx-tw/2, yy), txt, font=fnt, fill=col)
        t = c["sub"]; tw = d.textlength(t, font=font(FR, 22))
        d.text((cx-tw/2, cy0+178), t, font=font(FR, 22), fill=GRAY)
        bx, bw, bh, by = x+36, cw-72, 24, cy0+214
        d.rounded_rectangle([bx, by, bx+bw, by+bh], 12, fill=(226, 231, 241, 255))
        _gbar(img, [bx, by, bx+bw*c["bar_frac"], by+bh], c["bar_color"])
        d = ImageDraw.Draw(img)

    # optional counterpoint strip (debate-style memes): a slim outlined
    # strip between the cards and the punchline; shifts everything below.
    # CONTENT["counterpoint"] = {"label": "SMALL CAPS SOURCE",
    #                            "quote": "The other side, in their words."}
    cp = content.get("counterpoint")
    dy = 0
    if cp:
        cs0, cs1 = 688, 758
        d.rounded_rectangle([48, cs0, W - 48, cs1], 16, fill="#eef2f7",
                            outline="#16213a", width=2)
        _centered(d, cs0 + 8, cp["label"], font(FB, 19), FAINT)
        _centered(d, cs0 + 34, cp["quote"], font(FB, 23), INK)
        dy = 68

    # punchline strip (garnet — Brian's birthstone)
    py0, py1 = 700 + dy, 782 + dy
    d.rounded_rectangle([48, py0, W-48, py1], 18, fill=GARNET_BG,
                        outline=GARNET_EDGE, width=2)
    _centered(d, py0+22, content["punchline"], font(FB, 29), YELLOW)

    # curiosity line (replaces technical callouts)
    if content.get("curiosity"):
        _centered(d, 804 + dy, content["curiosity"], font(FB, 26), INK)

    img, d = footer(img, d, hashtag=content.get("hashtag"), dy=dy, brand=b)

    # optional QR badge (top-right): the link survives screenshots/forwards.
    # On the feed itself it's unscannable, so keep it small and clearly
    # labeled; it earns its place when the image circulates on WhatsApp.
    if content.get("qr_url") and qrcode is not None:
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(content["qr_url"]); qr.make(fit=True)
        qim = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        q = qim.resize((116, 116), Image.LANCZOS)
        bs, bh = 144, 176
        badge = Image.new("RGBA", (bs, bh), (0, 0, 0, 0))
        db = ImageDraw.Draw(badge)
        db.rounded_rectangle([0, 0, bs, bh], 18, fill="white",
                             outline=(210, 218, 230, 255), width=2)
        badge.paste(q, ((bs-116)//2, 10), q)
        t = "SCAN FOR FULL STORY"
        fs = 14
        while fs > 8:
            f = font(FB, fs)
            if db.textlength(t, font=f) <= bs-16:
                break
            fs -= 1
        tw = db.textlength(t, font=f)
        db.text(((bs-tw)/2, 134), t, font=f, fill=INK)
        img.paste(badge, (W-bs-28, 36), badge)
        d = ImageDraw.Draw(img)

    img.save(out_path)
    return out_path


# ---------------- demo: the RAM SCAM card ----------------
RAM_SCAM = {
    "kicker": "MINI PC MAKERS DON'T WANT YOU DOING THIS MATH",
    "headline": "THE $620 RAM SCAM",
    "cards": [
        {"tag": "WHAT THEY SELL YOU", "title": "1x 32GB mini PC", "price": "$1,099",
         "sub": "32GB total • 1 computer", "bar_frac": 2.91/5.01,
         "bar_color": "#ff5a5a", "tint": "#fff4f4"},
        {"tag": "WHAT I BOUGHT", "title": "2x 24GB mini PC", "price": "$958",
         "sub": "48GB total • 2 computers", "bar_frac": 1.0,
         "bar_color": "#22b573", "tint": "#f0faf5"},
    ],
    "punchline": "+16GB MORE RAM • A SECOND COMPUTER • $141 LESS",
    "curiosity": "Curious how I figured this out? Ask me below.",
}

if __name__ == "__main__":
    import sys
    photo = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else "meme.png"
    print(render_meme(RAM_SCAM, photo_path=photo, out_path=out))
