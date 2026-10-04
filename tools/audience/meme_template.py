#!/usr/bin/env python3
"""SuccessBrian reusable meme template — 1080x1080 social cards (LIGHT edition).

PURPOSE:
    One branded layout for every @successbrian insight meme. Drop in new
    content (headline + chart cards + punchline) and render a fresh card.
    Brand = SuccessBrian. Light background for readability; headline ALWAYS
    renders as multi-color gradient with 3D extrusion. Keep it bold and
    simple — curiosity over complexity. The audience should think
    "wow, what is Brian telling me here?" and ask questions.

USAGE:
    from meme_template import render_meme
    render_meme(CONTENT, photo_path="/path/they.jpg", out_path="meme.png")

    CONTENT = {
        "kicker": "SMALL CAPS HOOK",
        "headline": "THE $620 RAM SCAM",   # gradient+3D applied automatically
        "grad_colors": ["#4dd8ff", "#2b7fff", "#8b2bff"],  # optional override
        "cards": [
            {"tag": "WHAT THEY SELL YOU", "title": "1x 32GB MACO",
             "price": "$1,099", "sub": "32GB total • 1 computer",
             "bar_frac": 0.58, "bar_color": "#ff5a5a"},
            ...
        ],
        "punchline": "+16GB MORE RAM • A SECOND COMPUTER • $141 LESS",
        "curiosity": "Curious how I figured this out? Ask me below.",
    }

BRAND defaults below are Brian's; override per user.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
}

INK = "#16213a"        # body text on light
GRAY = "#5b6474"
FAINT = "#8a93a3"
YELLOW = "#ffd23f"
MAROON_BG = "#6e1423"
MAROON_EDGE = "#c0392b"


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
        f = font(FB, int(size*0.55))
        t = "X"; tw = d.textlength(t, font=f)
        d.text(((size-tw)/2, size*0.20), t, font=f, fill="white")
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
    img = background()
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

    # kicker
    _centered(d, 216, content["kicker"], font(FB, 25), "#0a7fd4", tracking=3)

    # headline: gradient + 3D, always
    f_big = font(FB, 92)
    colors = content.get("grad_colors", ["#4dd8ff", "#2b7fff", "#8b2bff"])
    hl, (lw, lh) = headline_3d(img, content["headline"], f_big, colors)
    img.paste(hl, ((W-lw)//2, 254), hl)
    # colorful gradient divider under headline
    div = grad_rounded((440, 9), ["#4dd8ff", "#2b7fff", "#8b2bff", "#fd1d9d"], 4)
    img.paste(div, ((W-440)//2, 398), div)
    d = ImageDraw.Draw(img)

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

    # punchline strip (maroon — Brian's favorite)
    py0, py1 = 700, 782
    d.rounded_rectangle([48, py0, W-48, py1], 18, fill=MAROON_BG,
                        outline=MAROON_EDGE, width=2)
    _centered(d, py0+22, content["punchline"], font(FB, 29), YELLOW)

    # curiosity line (replaces technical callouts)
    if content.get("curiosity"):
        _centered(d, 804, content["curiosity"], font(FB, 26), INK)

    # footer
    d.line([(48, 862), (W-48, 862)], fill=(200, 208, 220, 255), width=2)
    items = [(icon(kind, 46), handle) for kind, handle in b["handles"]]
    widths = [46 + 12 + d.textlength(h, font=font(FR, 20)) for _, h in items]
    total_w = sum(widths) + 40*(len(items)-1)
    x = (W-total_w)/2; y_ic = 874
    for (ic, handle), wdt in zip(items, widths):
        img.paste(ic, (int(x), y_ic), ic)
        d.text((x+46+12, y_ic+8), handle, font=font(FR, 20), fill=INK)
        x += wdt + 40
    bic = icon("blog", 48)
    url = b["blog_url"]
    f_blog = font(FB, 30)
    tw = d.textlength(url, font=f_blog)
    bx = (W - (48 + 14 + tw))/2
    img.paste(bic, (int(bx), 930), bic)
    d.text((bx+48+14, 932), url, font=f_blog, fill=INK)

    img.save(out_path)
    return out_path


# ---------------- demo: the RAM SCAM card ----------------
RAM_SCAM = {
    "kicker": "MINI PC MAKERS DON'T WANT YOU DOING THIS MATH",
    "headline": "THE $620 RAM SCAM",
    "cards": [
        {"tag": "WHAT THEY SELL YOU", "title": "1x 32GB MACO", "price": "$1,099",
         "sub": "32GB total • 1 computer", "bar_frac": 2.91/5.01,
         "bar_color": "#ff5a5a", "tint": "#fff4f4"},
        {"tag": "WHAT I BOUGHT", "title": "2x 24GB MACO", "price": "$958",
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
