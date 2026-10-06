"""Health-meme brand template for Brian's meme desk.

Same format as the AI and political templates (brand bar, kicker, gradient
3D headline, comparison cards, garnet punchline, curiosity CTA, shared
footer) with a health visual identity:

- deep saturated teal gradient canvas (Brian 2026-10-06: the old near-white
  base read as washed out — bold saturation now, clinical teal kept)
- strong EKG pulse-line pattern along the edges (the health signature, felt)
- kicker flanked by teal pulse glyphs
- Oliabo Prima pillow-pack emblem top-right (REAL product photo, not a
  drawing — the one emblem per meme)
- bright cyan vitality glow behind the headline
- electric green → cyan headline gradient with near-black teal 3D extrusion
- garnet punchline with a teal edge (garnet = Brian's January birthstone)
- tagline: "LIVED EXPERIENCE. REAL TALK." — the health desk's standing rule
  is lived experience, never prescription.
- hashtag: #SuccessBrianHealth (HEALTH_BRAND["hashtag"])

CONTENT contract mirrors meme_template.render_meme, plus the political
template's optional headline_size (starting point size, auto-shrinks).
"""
import sys
from pathlib import Path
sys.path.insert(0, "/home/hatch/workspace/successbrian-os/tools/audience")
from meme_template import (background, headline_3d, photo_card, footer,
                           font, _centered, grad_rounded, _gbar, icon,
                           HEALTH_BRAND as _HEALTH_BRAND,
                           INK, GRAY, FAINT, GARNET_BG, YELLOW,
                           W, H, FB, FR, BRAND)
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HEALTH_BRAND = dict(_HEALTH_BRAND)
HEALTH_BRAND.update({
    "tagline": "LIVED EXPERIENCE. REAL TALK.",
    "accent": "#00b894",
    # dark-canvas wordmark: white + bright cyan (deep teal base needs light type)
    "wordmark": [("SUCCESS", "#ffffff"), ("BRIAN", "#22d3ee")],
})

TEAL = "#00c98a"
TEAL_DARK = "#009e6e"
TEAL_EDGE = "#5eead4"
HL_COLORS = ["#00ffa3", "#00e5ff", "#38e1ff", "#5eead4"]  # electric green -> cyan
HL_EXTRUSION = ((3, 34, 30, 255), (1, 18, 16, 255))  # near-black teal depth


def _pulse_points(x0, y0, w, h):
    """Stylized EKG polyline in a w x h box at (x0, y0)."""
    return [(x0, y0 + h * 0.55), (x0 + w * 0.28, y0 + h * 0.55),
            (x0 + w * 0.34, y0 + h * 0.55), (x0 + w * 0.40, y0 + h * 0.20),
            (x0 + w * 0.48, y0 + h * 0.90), (x0 + w * 0.56, y0 + h * 0.55),
            (x0 + w * 0.64, y0 + h * 0.38), (x0 + w * 0.70, y0 + h * 0.55),
            (x0 + w, y0 + h * 0.55)]


def health_background():
    """Deep saturated teal gradient — the bold health canvas.

    Brian 2026-10-06: the old near-white clinical base read as washed out.
    This keeps the clinical teal identity but with saturation and presence:
    rich surgical-teal top melting into deep teal at the bottom, with bold
    cyan/emerald washes. White cards and the electric headline glow on it.

    Brian 2026-10-06 (v3): lighten a touch for contrast — lifted endpoints
    so the EKG lines, glows, and headline separate from the canvas more.
    Palette unchanged (his words: "i love the colors").
    """
    img = Image.new("RGB", (W, H), "#147a6e")
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        # saturated teal, lifted a touch: #20b8a4 top -> #105a54 bottom
        r = int(32 - 16 * t); g = int(184 - 94 * t); b = int(164 - 80 * t)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    # bright cyan vitality wash, top-center
    gd.ellipse([W // 2 - 480, -300, W // 2 + 480, 380],
               fill=(0, 229, 255, 90))
    # deep emerald pool, bottom
    gd.ellipse([W // 2 - 620, H - 560, W // 2 + 620, H + 160],
               fill=(0, 120, 95, 110))
    # mint sheen, upper-left diagonal
    gd.ellipse([-320, -160, 560, 560], fill=(94, 234, 212, 70))
    img = Image.alpha_composite(img.convert("RGBA"),
                                glow.filter(ImageFilter.GaussianBlur(60))).convert("RGB")
    return img


def pulse_backdrop(img):
    """Strong EKG lines along the left/right edges — the health signature.

    Brian 2026-10-06: make them FELT, not faint. Bright mint, high alpha,
    thicker strokes.
    """
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in (180, 420, 660, 900):
        d.line(_pulse_points(24, y, 150, 48), fill=(0, 255, 190, 125), width=4)
        d.line(_pulse_points(W - 174, y + 60, 150, 48),
               fill=(0, 255, 190, 125), width=4)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def icon_pulse(size=36):
    """Teal EKG glyph for flanking the kicker."""
    im = Image.new("RGBA", (size * 2, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.line(_pulse_points(4, 4, size * 2 - 8, size - 8),
           fill=(0, 158, 110, 255), width=max(3, size // 10))
    return im


def _icon_shadow(im):
    """Soft dark-teal drop shadow so white icons lift off the canvas."""
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    alpha = im.split()[3]
    solid = Image.new("RGBA", im.size, (5, 45, 40, 120))
    sh.paste(solid, (0, 3), alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(3))
    return Image.alpha_composite(sh, im)


def icon_stethoscope(size=48):
    """Hand-built stethoscope: binaural arc + tube + chestpiece.

    Brian 2026-10-06: relevant health icons, built in PIL like the
    packet emblem. White with a soft shadow — reads on the teal canvas.
    """
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(4, s // 12)
    ink = (255, 255, 255, 255)
    # binaural headset: top-half arc
    d.arc([s * 0.28, s * 0.06, s * 0.72, s * 0.50], start=180, end=360,
          fill=ink, width=w)
    # eartips
    r = w // 2 + 1
    for ex in (s * 0.28, s * 0.72):
        d.ellipse([ex - r, s * 0.28 - r, ex + r, s * 0.28 + r], fill=ink)
    # tube: straight stem from headset to chestpiece
    d.line([(s * 0.5, s * 0.28), (s * 0.5, s * 0.62)], fill=ink, width=w)
    # chestpiece: white disc with teal diaphragm dot
    cx, cy, cr = s * 0.5, s * 0.74, s * 0.12
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=ink)
    d.ellipse([cx - cr * 0.45, cy - cr * 0.45, cx + cr * 0.45, cy + cr * 0.45],
              fill=(10, 110, 95, 255))
    return _icon_shadow(im)


def icon_glucometer(size=48):
    """Hand-built blood-sugar meter: body + screen + test strip + blood drop.

    Brian 2026-10-06: relevant health icons, built in PIL like the
    packet emblem. White body, teal screen, red drop — reads instantly.
    """
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (255, 255, 255, 255)
    screen = (11, 110, 98, 255)
    # test strip sticking out the top
    d.rounded_rectangle([s * 0.43, s * 0.08, s * 0.57, s * 0.34],
                        radius=max(2, s // 24), fill=ink)
    # blood drop on the strip tip
    cx, cy, r = s * 0.5, s * 0.12, s * 0.055
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(230, 57, 70, 255))
    d.polygon([(cx - r * 0.9, cy - r * 0.2), (cx + r * 0.9, cy - r * 0.2),
               (cx, cy - r * 1.9)], fill=(230, 57, 70, 255))
    # meter body
    d.rounded_rectangle([s * 0.24, s * 0.30, s * 0.76, s * 0.96],
                        radius=int(s * 0.07), fill=ink)
    # screen
    d.rounded_rectangle([s * 0.33, s * 0.40, s * 0.67, s * 0.60],
                        radius=int(s * 0.035), fill=screen)
    # button
    br = s * 0.05
    d.ellipse([s * 0.5 - br, s * 0.78 - br, s * 0.5 + br, s * 0.78 + br],
              fill=screen)
    return _icon_shadow(im)


def packet_emblem(size=150):
    """Oliabo Prima pillow pack — REAL product photo.

    Brian 2026-10-06: "not a drawing. the actual high resolution image of
    it." The drawn sachet is gone. Loads oliabo-prima-packet.png (real
    Oliabo product photography: transparent daily sachet, 4 capsules
    visible inside), scales it into the emblem slot as a rounded product
    badge with a gold ring + teal glow + soft drop shadow so it sits
    naturally on the deep teal canvas — no white-box artifact. Top-right,
    the one emblem per meme.
    """
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    # teal glow behind (template glow language)
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([s * 0.08, s * 0.08, s * 0.92, s * 0.92],
                                 fill=(0, 255, 200, 90))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s * 0.08)))

    photo = None
    for cand in (
        Path.home() / "workspace/your_files/memes/proofs/oliabo-prima-packet.png",
        Path(__file__).resolve().parent.parent.parent.parent
        / "your_files/memes/proofs/oliabo-prima-packet.png",
    ):
        if cand.exists():
            photo = Image.open(cand).convert("RGB")
            break
    if photo is None:
        # Brian rejected the drawing — never fall back to it. Fail visibly.
        print("WARNING packet_emblem: oliabo-prima-packet.png not found")
        return im

    # fit the slot keeping aspect (photo is 335x265 landscape)
    max_side = int(s * 0.88)
    photo.thumbnail((max_side, max_side), Image.LANCZOS)
    pw, ph = photo.size
    bx, by = (s - pw) // 2, (s - ph) // 2

    # soft drop shadow under the badge
    rad = 22
    sh = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [bx + 5, by + 7, bx + pw + 5, by + ph + 7], radius=rad,
        fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))

    # rounded badge mask with a feathered edge — blends into the teal,
    # no hard white-box cut
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw, ph], radius=rad,
                                           fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.4))
    badge = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    badge.paste(photo, (bx, by), mask)
    im.alpha_composite(badge)

    # gold ring (Oliabo accent) defines the badge edge intentionally
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([bx, by, bx + pw, by + ph], radius=rad,
                        outline=(212, 160, 23, 255), width=4)
    return im


def kicker_health(img, y, text):
    """Kicker flanked by teal pulse glyphs — the health template signature.
    White type on the deep teal canvas (Brian 2026-10-06: no washed out)."""
    d = ImageDraw.Draw(img)
    kf = font(FB, 25)
    tw = d.textlength(text, font=kf) + 3 * (len(text) - 1)
    cx = img.size[0] / 2
    _centered(d, y, text, kf, "#ffffff", tracking=3)
    for sx in (int(cx - tw / 2 - 62), int(cx + tw / 2 + 16)):
        sp = icon_pulse(36)
        img.paste(sp, (sx, y - 2), sp)
    return ImageDraw.Draw(img)


def footer_health_dark(img, d, hashtag=None, dy=0, brand=None):
    """Footer recolored for the deep teal canvas: light handles, white blog
    URL, bright-teal hashtag line. Same rhythm as the shared footer()."""
    b = brand or HEALTH_BRAND
    tag = hashtag if hashtag is not None else b.get("hashtag")
    d.line([(48, 840 + dy), (W - 48, 840 + dy)], fill=(94, 234, 212, 255),
           width=3)
    items = [(icon(kind, 48), handle) for kind, handle in b["handles"]]
    widths = [48 + 12 + d.textlength(h, font=font(FR, 20)) for _, h in items]
    total_w = sum(widths) + 36 * (len(items) - 1)
    x = (W - total_w) / 2
    y_ic = 852 + dy
    for (ic, handle), wdt in zip(items, widths):
        img.paste(ic, (int(x), y_ic), ic)
        d.text((x + 48 + 12, y_ic + 9), handle, font=font(FR, 20),
               fill="#e8f4f1")
        x += wdt + 36
    d = ImageDraw.Draw(img)
    bic = icon("blog", 48)
    url = b["blog_url"]
    f_blog = font(FB, 30)
    tw = d.textlength(url, font=f_blog)
    bx = (W - (48 + 14 + tw)) / 2
    img.paste(bic, (int(bx), 910 + dy), bic)
    d.text((bx + 48 + 14, 912 + dy), url, font=f_blog, fill="#ffffff")
    if tag:
        _centered(d, 962 + dy, tag, font(FB, 28), "#5eead4")
    return img, ImageDraw.Draw(img)


def render_health_meme(content, photo_path=None, out_path="meme.png",
                       brand=None, headline_size=None):
    b = brand or HEALTH_BRAND
    img = pulse_backdrop(health_background())
    d = ImageDraw.Draw(img)

    # brand bar (light type on the deep teal canvas)
    pc = photo_card(photo_path)
    img.paste(pc, (48, 36), pc)
    x = 48 + 148 + 24
    wx = x
    for word, color in b["wordmark"]:
        f = font(FB, 46)
        d.text((wx, 44), word, font=f, fill=color)
        wx += d.textlength(word, font=f) + 10
    d.text((x, 104), b["tagline"], font=font(FR, 21), fill="#d7f5ee")

    # Prima pillow-pack emblem, top right — the one emblem on the meme
    emb = packet_emblem(150)
    img.paste(emb, (W - 30 - 150, 22), emb)
    d = ImageDraw.Draw(img)

    # strong cyan vitality glow behind the headline
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W / 2 - 360, 170, W / 2 + 360, 450],
                                 fill=(0, 229, 255, 85))
    img = Image.alpha_composite(img.convert("RGBA"),
                                glow.filter(ImageFilter.GaussianBlur(40))).convert("RGB")
    d = ImageDraw.Draw(img)

    # kicker with pulse glyphs
    d = kicker_health(img, 216, content["kicker"])

    # headline: gradient + 3D, always (auto-fit so the extrusion never clips)
    size = headline_size or 92
    _tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > 40:
        f_big = font(FB, size)
        tw = _tmp.textlength(content["headline"], font=f_big)
        if tw + 2 * 24 + 7 + 14 + 24 <= W - 24:
            break
        size -= 2
    colors = content.get("grad_colors", HL_COLORS)
    hl, (lw, lh) = headline_3d(img, content["headline"], f_big, colors,
                               extrusion=HL_EXTRUSION)
    img.paste(hl, ((W - lw) // 2, 254), hl)
    # colorful gradient divider under headline
    div = grad_rounded((440, 9), HL_COLORS, 4)
    img.paste(div, ((W - 440) // 2, 398), div)
    # relevant icons flanking the divider — stethoscope left, glucometer
    # right (Brian 2026-10-06). 48px, clear of EKG edges and card tops.
    _isz, _iy = 48, 374
    _st, _gm = icon_stethoscope(_isz), icon_glucometer(_isz)
    img.paste(_st, (236, _iy), _st)
    img.paste(_gm, (796, _iy), _gm)
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
                          fill=TEAL_DARK)
            else:
                d.ellipse([_cx - _r, 416 - _r, _cx + _r, 416 + _r],
                          outline="#b9c4d6", width=2)

    # cards: tinted, soft shadow, gradient bars (same as AI template)
    cards = content["cards"]
    n = len(cards)
    gap, margin = 32, 48
    cw = (W - 2 * margin - gap * (n - 1)) / n
    cy0, ch = 424, 252
    for i, c in enumerate(cards):
        x = margin + i * (cw + gap)
        tint = c.get("tint", "#ffffff")
        d.rounded_rectangle([x + 6, cy0 + 10, x + cw + 6, cy0 + ch + 10], 26,
                            fill=(178, 188, 205, 255))
        d.rounded_rectangle([x, cy0, x + cw, cy0 + ch], 26, fill=tint,
                            outline=(210, 218, 230, 255), width=2)
        cx = x + cw / 2
        _psz = c.get("price_size", 66)
        for txt, fnt, col, yy in [
            (c["tag"], font(FB, 19), FAINT, cy0 + 24),
            (c["title"], font(FB, 30), INK, cy0 + 54),
            (c["price"], font(FB, _psz), c["bar_color"], cy0 + 96),
        ]:
            tw = d.textlength(txt, font=fnt)
            d.text((cx - tw / 2, yy), txt, font=fnt, fill=col)
        t = c["sub"]
        tw = d.textlength(t, font=font(FR, 22))
        d.text((cx - tw / 2, cy0 + 178), t, font=font(FR, 22), fill=GRAY)
        bx, bw, bh, by = x + 36, cw - 72, 24, cy0 + 214
        d.rounded_rectangle([bx, by, bx + bw, by + bh], 12,
                            fill=(226, 231, 241, 255))
        _gbar(img, [bx, by, bx + bw * c["bar_frac"], by + bh], c["bar_color"])
        d = ImageDraw.Draw(img)

    # optional counterpoint strip (debate-style memes)
    cp = content.get("counterpoint")
    dy = 0
    if cp:
        cs0, cs1 = 688, 758
        d.rounded_rectangle([48, cs0, W - 48, cs1], 16, fill="#ffffff",
                            outline="#5eead4", width=3)
        _centered(d, cs0 + 8, cp["label"], font(FB, 19), FAINT)
        _centered(d, cs0 + 34, cp["quote"], font(FB, 23), INK)
        dy = 68

    # punchline strip (garnet — Brian's birthstone; strong teal edge for health)
    py0, py1 = 700 + dy, 782 + dy
    d.rounded_rectangle([48, py0, W - 48, py1], 18, fill=GARNET_BG,
                        outline=TEAL_EDGE, width=3)
    _centered(d, py0 + 22, content["punchline"], font(FB, 29), YELLOW)

    # curiosity line (replaces technical callouts)
    if content.get("curiosity"):
        _centered(d, 804 + dy, content["curiosity"], font(FB, 26), "#ffffff")

    img, d = footer_health_dark(img, d, hashtag=content.get("hashtag"), dy=dy,
                               brand=b)

    img.save(out_path)
    return out_path


if __name__ == "__main__":
    PHOTO = "/home/hatch/workspace/profile-images/brian-gina-together.jpg"
    render_health_meme(
        {
            "kicker": "THE HEALTH DESK IS OPEN",
            "headline": "LIVED IT. SHARING IT.",
            "cards": [
                {"tag": "BEFORE", "title": "BLOOD SUGAR",
                 "price": "HIGH", "sub": "nerves on fire",
                 "bar_frac": 0.85, "bar_color": "#f59e0b", "tint": "#fff8f0"},
                {"tag": "AFTER", "title": "98-109 CLUB",
                 "price": "STEADY", "sub": "nerves calming down",
                 "bar_frac": 0.35, "bar_color": "#00b894", "tint": "#f0fdf9"},
            ],
            "punchline": "YOUR NUMBERS ARE A STORY. READ THEM.",
            "curiosity": "What changed first for you — the numbers or the symptoms?",
        },
        photo_path=PHOTO, out_path="/tmp/health_template_proof.png")
    print("wrote /tmp/health_template_proof.png")
