#!/usr/bin/env python3
"""SuccessBrian reusable meme template — 1080x1080 social cards (LIGHT edition).

PURPOSE:
    One branded layout for every @successbrian insight meme. Drop in new
    content (headline + chart cards + punchline) and render a fresh card.
    Brand = SuccessBrian. Light background for readability; headline ALWAYS
    renders as multi-color gradient with 3D extrusion. Keep it bold and
    simple — curiosity over complexity. The audience should think
    "wow, what is Brian telling me here?" and ask questions.

    AI-template signature visuals (built in): a neural-network
    constellation along the edges over holographic depth (blurred color
    orbs + diagonal sheen), Spencer the black Lab in a glowing badge with
    a holographic chrome ring and orbiting sparkles standing watch
    top-right — exactly one mascot per meme — the kicker
    on a holographic pill flanked by AI sparkles, iridescent chrome
    strips on the cards, and a glowing gradient divider.

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

CALLED BY:
    tools/audience/political_meme.py, health_template.py, crypto_template.py,
    war_on_oil.py — the template siblings import its shared primitives
    (background, headline_3d, photo_card, font, _centered, grad_rounded,
    _gbar, icon, BRAND constants) rather than reinventing them.

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

# Spencer's badge photo (face crop of his avatar). Brian 2026-10-11:
# Spencer replaces the generic robot as the AI template's top-right emblem.
SPENCER_PHOTO = "/home/hatch/workspace/avatars/spencer-chilling-chair.png"
SPENCER_CTA = ("Ask Brian about having", "your own FREE Muse AI Agent.")


def font(path, size):
    return ImageFont.truetype(path, size)


# ---------------- color helpers ----------------
def _radial_glow(w, h, color, max_alpha):
    """Elliptical glow with smooth radial falloff to transparent — a true
    glow with no visible edges (beauty pass 2026-10-11)."""
    glow = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    steps = 56
    for i in range(steps, 0, -1):
        t = i / steps
        a = int(max_alpha * (1 - t) ** 1.7)
        px = (w / 2) * t
        py = (h / 2) * t
        d.ellipse([px, py, w - px, h - py], fill=color + (a,))
    return glow


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


def spencer_badge(size=170, photo_path=None):
    """Spencer the black Lab in a rounded-rect badge — the one hero emblem
    per meme. Full face photo (never circle-cropped), holographic chrome
    frame, orbiting sparkles."""
    from PIL import Image as _Image
    s = size
    ph = _Image.open(photo_path or SPENCER_PHOTO).convert("RGB")
    side = min(ph.size)
    left = (ph.size[0] - side) // 2
    top = (ph.size[1] - side) // 2
    ph = ph.crop((left, top, left + side, top + side))
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cx = cy = s / 2
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle([6, 6, s - 6, s - 6], 26, fill=(56, 182, 255, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(max(4, int(s * 0.07))))
    im.alpha_composite(glow)
    # holographic chrome frame
    frame = holo_pill((s, s), radius=26, base_alpha=255)
    im.alpha_composite(frame)
    # face photo inset, rounded corners
    pad = 7
    fs = s - 2 * pad
    face = ph.resize((fs, fs), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (fs, fs), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, fs, fs], 20, fill=255)
    im.paste(face, (pad, pad), mask)
    # tiny orbiting sparkles on the glow field
    d = ImageDraw.Draw(im)
    for ang, scol in ((35, "#22d3ee"), (155, "#8b5cf6"), (275, "#e879f9")):
        a = math.radians(ang)
        ox = cx + math.cos(a) * s * 0.52
        oy = cy + math.sin(a) * s * 0.52
        sp = icon_spark(20, color=scol)
        im.paste(sp, (int(ox - 10), int(oy - 10)), sp)
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
    # holographic ring: the chrome shifts around the circle
    _holo_ring(d, cx, cy, s * 0.40, max(3, int(s * 0.028)))
    r2 = s * 0.345
    _holo_ring(d, cx, cy, r2, 2,
               ("#e879f9", "#8b5cf6", "#3b82f6", "#22d3ee"))
    # tiny orbiting sparkles on the glow field
    for ang, scol in ((35, "#22d3ee"), (155, "#8b5cf6"), (275, "#e879f9")):
        a = math.radians(ang)
        ox = cx + math.cos(a) * s * 0.47
        oy = cy + math.sin(a) * s * 0.47
        sp = icon_spark(20, color=scol)
        im.paste(sp, (int(ox - 10), int(oy - 10)), sp)
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


def holo_pill(size, colors=("#22d3ee", "#3b82f6", "#8b5cf6", "#e879f9"),
              radius=20, base_alpha=52):
    """Horizontal holographic gradient pill with rounded corners (RGBA).

    The AI template's iridescent chrome — used for the kicker pill, card
    top accents, and the punchline's iridescent edge."""
    w, h = size
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    n = len(colors)
    for x in range(w):
        t = x / max(1, w - 1)
        seg = t * (n - 1)
        i = int(seg)
        f = seg - i
        c1 = _hex(colors[i])
        c2 = _hex(colors[min(i + 1, n - 1)])
        gd.line([(x, 0), (x, h)],
                fill=tuple(int(a + (b - a) * f) for a, b in zip(c1, c2)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius,
                                           fill=base_alpha)
    grad.putalpha(mask)
    return grad.convert("RGBA")


def _holo_ring(d, cx, cy, r, width,
               colors=("#22d3ee", "#3b82f6", "#8b5cf6", "#e879f9")):
    """Badge ring drawn as arc segments colored by angle — the ring itself
    shifts cyan -> blue -> violet -> magenta around the circle."""
    n = 72
    for i in range(n):
        a0 = 360 * i / n
        a1 = 360 * (i + 1) / n + 1.5
        t = i / max(1, n - 1)
        seg = t * (len(colors) - 1)
        j = int(seg)
        f = seg - j
        col = _mix(colors[j], colors[min(j + 1, len(colors) - 1)], f)
        d.arc([cx - r, cy - r, cx + r, cy + r], start=a0, end=a1,
              fill=col, width=width)


def ai_backdrop(img):
    """Neural-network constellation + holographic depth — AI texture
    that stays off the readable middle. v2: denser nodes, blurred color
    orbs, and a faint diagonal holographic sheen for depth."""
    import random
    rnd = random.Random(73)
    w, h = img.size
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    pts = []
    for _ in range(14):
        pts.append((rnd.randint(24, 260), rnd.randint(60, h - 60)))
    for _ in range(14):
        pts.append((rnd.randint(w - 260, w - 24), rnd.randint(60, h - 60)))
    for i, (x1, y1) in enumerate(pts):
        for x2, y2 in pts[i + 1:]:
            if ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 < 320:
                d.line([(x1, y1), (x2, y2)], fill=(140, 150, 220, 85), width=2)
    for x, y in pts:
        r = rnd.randint(4, 9)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(130, 110, 220, 115))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    # holographic depth: large blurred color orbs
    orbs = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(orbs)
    od.ellipse([-160, 120, 320, 600], fill=(34, 211, 238, 56))
    od.ellipse([w - 320, -80, w + 160, 400], fill=(232, 121, 249, 52))
    od.ellipse([w - 420, h - 420, w + 60, h + 60], fill=(139, 92, 246, 54))
    od.ellipse([-200, h - 300, 200, h + 100], fill=(34, 211, 238, 44))
    orbs = orbs.filter(ImageFilter.GaussianBlur(60))
    img = Image.alpha_composite(img.convert("RGBA"), orbs).convert("RGB")
    # radiant burst behind the headline zone (beauty pass 2026-10-11):
    # true radial falloff so no edges ever show
    burst = _radial_glow(880, 720, (190, 232, 255), 60)
    img.paste(burst, (w // 2 - 440, -60), burst)
    burst2 = _radial_glow(480, 380, (255, 255, 255), 66)
    img.paste(burst2, (w // 2 - 240, 110), burst2)
    # faint diagonal holographic sheen
    sheen = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    sd.polygon([(w * 0.55, 0), (w * 0.85, 0), (w * 0.30, h), (w * 0.0, h)],
               fill=(255, 255, 255, 26))
    sd.polygon([(w * 0.88, 0), (w * 1.0, 0), (w * 0.45, h), (w * 0.33, h)],
               fill=(190, 220, 255, 30))
    sheen = sheen.filter(ImageFilter.GaussianBlur(30))
    img = Image.alpha_composite(img.convert("RGBA"), sheen).convert("RGB")
    # scattered micro-sparkles along the edges (beauty pass 2026-10-11)
    for sx, sy, ss, scol in ((70, 700, 18, "#22d3ee"),
                             (1010, 700, 18, "#e879f9"),
                             (60, 880, 14, "#8b5cf6"),
                             (1020, 880, 14, "#3b82f6"),
                             (90, 480, 14, "#e879f9"),
                             (990, 480, 14, "#22d3ee")):
        sp = icon_spark(ss, color=scol)
        img.paste(sp, (sx, sy), sp)
    return img


def kicker_ai(img, y, text, cx=None):
    """Kicker on a holographic pill, flanked by AI sparkles — the AI
    template signature. (Spencer appears exactly once per meme,
    as the badge top-right.) cx overrides the page-center default."""
    d = ImageDraw.Draw(img)
    kf = font(FB, 25)
    tw = d.textlength(text, font=kf) + 3 * (len(text) - 1)
    cx = cx if cx is not None else img.size[0] / 2
    pw, ph = int(tw) + 150, 52
    pill = holo_pill((pw, ph), radius=26, base_alpha=52)
    img.paste(pill, (int(cx - pw / 2), y - 8), pill)
    d = ImageDraw.Draw(img)
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
    gd.ellipse([W//2-460, -280, W//2+460, 360], fill=(120, 190, 255, 72))
    gd.ellipse([W-560, H-460, W+160, H+120], fill=(255, 196, 150, 54))
    gd.ellipse([-200, H-420, 420, H+80], fill=(196, 160, 255, 50))
    # richer holographic orbs for depth (beauty pass 2026-10-11)
    gd.ellipse([-320, 300, 180, 800], fill=(34, 211, 238, 52))
    gd.ellipse([W-180, 180, W+320, 680], fill=(232, 121, 249, 48))
    gd.ellipse([W//2-260, H-320, W//2+260, H+180], fill=(139, 92, 246, 46))
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
def headline_3d(base, text, fnt, colors, depth=7, extrusion=((26, 36, 80, 255),
               (16, 22, 54, 255))):
    """Multi-color vertical gradient face + 3D extrusion + soft shadow.
    Returns (layer, (w, h)) sized to the text.
    extrusion: (main, edge) RGBA fills for the 3D block — override for
    dark canvases (e.g. health's deep teal, crypto's charcoal)."""
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

    # 3D extrusion: dark block behind, offset down-right
    for i in range(depth, 0, -1):
        d.text((ox+i, oy+i), text, font=fnt, fill=extrusion[0])
    # darker edge on the extrusion for depth
    d.text((ox+depth, oy+depth), text, font=fnt, fill=extrusion[1])

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

    # brand bar: photo + wordmark. The kicker now lives up here too
    # (moved 2026-10-11 to free the content zone for the meat).
    pc = photo_card(photo_path)
    img.paste(pc, (48, 32), pc)
    x = 48 + 148 + 24
    wx = x
    for word, color in b["wordmark"]:
        f = font(FB, 46)
        d.text((wx, 36), word, font=f, fill=color)
        wx += d.textlength(word, font=f) + 10

    # Spencer standing watch, top right — the one mascot on the meme.
    # CTA above, his name below.
    _scx = W - 130
    for _i, _line in enumerate(SPENCER_CTA):
        _f = font(FB, 16)
        _tw = d.textlength(_line, font=_f)
        d.text((_scx - _tw / 2, 14 + _i * 22), _line, font=_f,
               fill="#0a7fd4" if _i else INK)
    badge = spencer_badge(120)
    img.paste(badge, (_scx - 60, 58), badge)
    _nf = font(FB, 18)
    _nw = d.textlength("SPENCER", font=_nf)
    d.text((_scx - _nw / 2, 182), "SPENCER", font=_nf, fill=INK)
    d = ImageDraw.Draw(img)

    # kicker up in the header now, centered on the page
    img = kicker_ai(img, 100, content["kicker"])
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
    # soft luminous halo behind the headline — radial falloff, no edges
    halo = _radial_glow(lw * 1.18, lh * 2.6, (255, 255, 255), 115)
    hx, hy0 = (W - lw) // 2, 196
    img.paste(halo, (int(hx + lw / 2 - halo.width / 2),
                     int(hy0 + lh / 2 - halo.height / 2)), halo)
    img.paste(hl, ((W-lw)//2, 196), hl)
    # colorful gradient divider under headline, with a soft holographic glow
    div = grad_rounded((440, 9), ["#22d3ee", "#3b82f6", "#8b5cf6", "#e879f9"], 4)
    glow = div.filter(ImageFilter.GaussianBlur(14))
    div_y = hy0 + lh + 10
    img.paste(glow, ((W-440)//2, div_y - 5), glow)
    img.paste(div, ((W-440)//2, div_y), div)
    # scattered AI sparkles flanking the divider (deterministic)
    for sx, sy, ss, scol in ((150, div_y - 8, 22, "#22d3ee"),
                             (238, div_y + 4, 16, "#8b5cf6"),
                             (842, div_y + 4, 16, "#e879f9"),
                             (930, div_y - 8, 22, "#3b82f6")):
        sp = icon_spark(ss, color=scol)
        img.paste(sp, (sx, sy), sp)
    d = ImageDraw.Draw(img)
    # series progress dots (optional): CONTENT["series_day"] = 1..5
    if content.get("series_day"):
        _sd = content["series_day"]
        _r, _gap = 7, 12
        _total = 5 * _r * 2 + 4 * _gap
        _sx = (W - _total) / 2
        _sy = div_y + 22
        for _i in range(5):
            _cx = _sx + _r + _i * (_r * 2 + _gap)
            if _i < _sd:
                d.ellipse([_cx - _r, _sy - _r, _cx + _r, _sy + _r],
                          fill="#0a7fd4")
            else:
                d.ellipse([_cx - _r, _sy - _r, _cx + _r, _sy + _r],
                          outline="#b9c4d6", width=2)

    # ---- content zone: sequential flow, cards scale to fill ----
    # CONTENT["hero"] = {"label": "SMALL CAPS", "image": "/path.png",
    #                    "caption": "Plain-English line."} — a diagram or
    # image depicting what the meme is about, for wide audiences.
    y = div_y + 28
    hero = content.get("hero")
    if hero:
        _centered(d, y + 4, hero["label"], font(FB, 17), FAINT)
        him = Image.open(hero["image"]).convert("RGBA")
        th = 104
        sc = th / him.height
        nw = max(1, int(him.width * sc))
        him = him.resize((nw, th), Image.LANCZOS)
        img.paste(him, (int((W - nw) / 2), y + 26), him)
        _centered(d, y + 136, hero["caption"], font(FB, 20), INK)
        d = ImageDraw.Draw(img)
        y += 180

    # cards: tinted, soft shadow, gradient bars; internals scale with ch
    cards = content["cards"]
    n = len(cards)
    gap, margin = 32, 48
    cw = (W - 2*margin - gap*(n-1)) / n
    ch = min(300, max(130, 700 - 12 - y))
    cy0 = y
    s = ch / 252
    for i, c in enumerate(cards):
        x = margin + i*(cw+gap)
        tint = c.get("tint", "#ffffff")
        # soft colored aura so the card lifts off the page (beauty 2026-10-11)
        ar, ag, ab = _hex(c["bar_color"])
        aura = Image.new("RGBA", (int(cw) + 72, ch + 72), (0, 0, 0, 0))
        ImageDraw.Draw(aura).rounded_rectangle(
            [0, 0, int(cw) + 72, ch + 72], 34, fill=(ar, ag, ab, 60))
        aura = aura.filter(ImageFilter.GaussianBlur(28))
        img.paste(aura, (int(x) - 36, int(cy0) - 36), aura)
        # soft drop shadow (blurred, not hard-offset)
        sh = Image.new("RGBA", (int(cw) + 40, ch + 40), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [20, 22, int(cw) + 20, ch + 22], 26, fill=(110, 122, 155, 105))
        sh = sh.filter(ImageFilter.GaussianBlur(13))
        img.paste(sh, (int(x) - 20, int(cy0) - 20), sh)
        d.rounded_rectangle([x, cy0, x+cw, cy0+ch], 26, fill=tint,
                            outline=(210, 218, 230, 255), width=2)
        # holographic chrome strip along the card top + corner sparkle
        strip = holo_pill((int(cw) - 8, 7), radius=3, base_alpha=220)
        img.paste(strip, (int(x) + 4, int(cy0) + 6), strip)
        csp = icon_spark(26, color="#8b5cf6")
        img.paste(csp, (int(x + cw) - 30, int(cy0) - 12), csp)
        d = ImageDraw.Draw(img)
        cx = x + cw/2
        for txt, fnt, col, yy in [
            (c["tag"], font(FB, max(11, int(19*s))), FAINT, cy0+24*s),
            (c["title"], font(FB, int(30*s)), INK, cy0+54*s),
            (c["price"], font(FB, int(66*s)), c["bar_color"], cy0+96*s),
        ]:
            tw = d.textlength(txt, font=fnt)
            d.text((cx-tw/2, yy), txt, font=fnt, fill=col)
        t = c["sub"]
        sf = font(FR, max(11, int(22*s)))
        tw = d.textlength(t, font=sf)
        d.text((cx-tw/2, cy0+178*s), t, font=sf, fill=GRAY)
        bx, bw, bh, by = x+36, cw-72, max(10, int(24*s)), cy0+214*s
        d.rounded_rectangle([bx, by, bx+bw, by+bh], 12, fill=(226, 231, 241, 255))
        _gbar(img, [bx, by, bx+bw*c["bar_frac"], by+bh], c["bar_color"])
        d = ImageDraw.Draw(img)
    y = cy0 + ch + 12

    # optional counterpoint strip: a slim outlined strip between the
    # cards and the punchline.
    # CONTENT["counterpoint"] = {"label": "SMALL CAPS",
    #                            "quote": "One plain-English line."}
    cp = content.get("counterpoint")
    if cp:
        cs0, cs1 = y, y + 68
        d.rounded_rectangle([48, cs0, W - 48, cs1], 16, fill="#eef2f7",
                            outline="#16213a", width=2)
        _centered(d, cs0 + 8, cp["label"], font(FB, 19), FAINT)
        _centered(d, cs0 + 34, cp["quote"], font(FB, 23), INK)
        y = cs1 + 12

    # punchline strip (garnet — Brian's birthstone) with iridescent top edge
    py0, py1 = y, y + 82
    d.rounded_rectangle([48, py0, W - 48, py1], 18, fill=GARNET_BG,
                        outline=GARNET_EDGE, width=2)
    edge = holo_pill((W - 96 - 8, 5), radius=2, base_alpha=200)
    img.paste(edge, (48 + 4, py0 + 3), edge)
    d = ImageDraw.Draw(img)
    _centered(d, py0+22, content["punchline"], font(FB, 29), YELLOW)
    y = py1 + 16

    # curiosity line (replaces technical callouts)
    if content.get("curiosity"):
        _centered(d, y, content["curiosity"], font(FB, 26), INK)

    # footer follows the flow
    img, d = footer(img, d, hashtag=content.get("hashtag"),
                    dy=y + 38 - 840, brand=b)

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
