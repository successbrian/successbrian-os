"""Health-meme brand template for Brian's meme desk.

Same format as the AI and political templates (brand bar, kicker, gradient
3D headline, comparison cards, garnet punchline, curiosity CTA, shared
footer) with a health visual identity:

- faint EKG pulse-line pattern along the edges (the health backdrop)
- kicker flanked by teal pulse glyphs
- heart-with-pulse emblem standing watch top-right (the one emblem per meme)
- soft teal glow behind the headline (vitality, not Cherenkov)
- teal → sky → green headline gradient
- garnet punchline with a teal edge (garnet = Brian's January birthstone)
- tagline: "LIVED EXPERIENCE. REAL TALK." — the health desk's standing rule
  is lived experience, never prescription.
- hashtag: #SuccessBrianHealth (HEALTH_BRAND["hashtag"])

CONTENT contract mirrors meme_template.render_meme, plus the political
template's optional headline_size (starting point size, auto-shrinks).
"""
import sys
sys.path.insert(0, "/home/hatch/workspace/successbrian-os/tools/audience")
from meme_template import (background, headline_3d, photo_card, footer,
                           font, _centered, grad_rounded, _gbar,
                           HEALTH_BRAND as _HEALTH_BRAND,
                           INK, GRAY, FAINT, GARNET_BG, YELLOW,
                           W, H, FB, FR, BRAND)
from PIL import Image, ImageDraw, ImageFilter

HEALTH_BRAND = dict(_HEALTH_BRAND)
HEALTH_BRAND.update({
    "tagline": "LIVED EXPERIENCE. REAL TALK.",
    "accent": "#00b894",
})

TEAL = "#00c98a"
TEAL_DARK = "#009e6e"
TEAL_EDGE = "#5eead4"
HL_COLORS = ["#00e69a", "#00d9c0", "#22d3ee", "#38bdf8"]  # green -> turquoise -> cyan -> slight blue


def _pulse_points(x0, y0, w, h):
    """Stylized EKG polyline in a w x h box at (x0, y0)."""
    return [(x0, y0 + h * 0.55), (x0 + w * 0.28, y0 + h * 0.55),
            (x0 + w * 0.34, y0 + h * 0.55), (x0 + w * 0.40, y0 + h * 0.20),
            (x0 + w * 0.48, y0 + h * 0.90), (x0 + w * 0.56, y0 + h * 0.55),
            (x0 + w * 0.64, y0 + h * 0.38), (x0 + w * 0.70, y0 + h * 0.55),
            (x0 + w, y0 + h * 0.55)]


def pulse_backdrop(img):
    """Faint EKG lines along the left/right edges — the health backdrop."""
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in (180, 420, 660, 900):
        d.line(_pulse_points(28, y, 130, 44), fill=(0, 205, 140, 50), width=3)
        d.line(_pulse_points(W - 158, y + 60, 130, 44),
               fill=(0, 205, 140, 50), width=3)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def icon_pulse(size=36):
    """Teal EKG glyph for flanking the kicker."""
    im = Image.new("RGBA", (size * 2, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.line(_pulse_points(4, 4, size * 2 - 8, size - 8),
           fill=(0, 158, 110, 255), width=max(3, size // 10))
    return im


def health_emblem(size=150):
    """Heart-with-pulse badge standing watch top-right. The one emblem."""
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # soft teal glow
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([s * 0.08, s * 0.08, s * 0.92, s * 0.92],
                                 fill=(0, 217, 192, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.08))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)
    # white badge, teal edge
    d.rounded_rectangle([s * 0.10, s * 0.10, s * 0.90, s * 0.90], s * 0.22,
                        fill="white", outline=TEAL, width=max(3, s // 36))
    # heart: two circles + triangle
    cx, cy = s / 2, s * 0.46
    hr = s * 0.20
    d.ellipse([cx - hr - hr * 0.55, cy - hr * 0.9, cx - hr * 0.45, cy + hr * 0.2],
              fill=TEAL)
    d.ellipse([cx + hr * 0.45, cy - hr * 0.9, cx + hr + hr * 0.55, cy + hr * 0.2],
              fill=TEAL)
    d.polygon([(cx - hr * 1.42, cy - hr * 0.25), (cx + hr * 1.42, cy - hr * 0.25),
               (cx, cy + hr * 1.35)], fill=TEAL)
    # white pulse line across the heart
    d.line(_pulse_points(cx - hr * 1.1, cy - hr * 0.35, hr * 2.2, hr * 0.9),
           fill="white", width=max(3, s // 40))
    return im


def kicker_health(img, y, text):
    """Kicker flanked by teal pulse glyphs — the health template signature."""
    d = ImageDraw.Draw(img)
    kf = font(FB, 25)
    tw = d.textlength(text, font=kf) + 3 * (len(text) - 1)
    cx = img.size[0] / 2
    _centered(d, y, text, kf, TEAL_DARK, tracking=3)
    for sx in (int(cx - tw / 2 - 62), int(cx + tw / 2 + 16)):
        sp = icon_pulse(36)
        img.paste(sp, (sx, y - 2), sp)
    return ImageDraw.Draw(img)


def render_health_meme(content, photo_path=None, out_path="meme.png",
                       brand=None, headline_size=None):
    b = brand or HEALTH_BRAND
    img = pulse_backdrop(background())
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

    # health emblem standing watch, top right — the one emblem on the meme
    emb = health_emblem(150)
    img.paste(emb, (W - 30 - 150, 22), emb)
    d = ImageDraw.Draw(img)

    # soft teal vitality glow behind the headline
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W / 2 - 330, 180, W / 2 + 330, 430],
                                 fill=(34, 211, 238, 42))
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
    hl, (lw, lh) = headline_3d(img, content["headline"], f_big, colors)
    img.paste(hl, ((W - lw) // 2, 254), hl)
    # colorful gradient divider under headline
    div = grad_rounded((440, 9), HL_COLORS, 4)
    img.paste(div, ((W - 440) // 2, 398), div)
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
        for txt, fnt, col, yy in [
            (c["tag"], font(FB, 19), FAINT, cy0 + 24),
            (c["title"], font(FB, 30), INK, cy0 + 54),
            (c["price"], font(FB, 66), c["bar_color"], cy0 + 96),
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
        d.rounded_rectangle([48, cs0, W - 48, cs1], 16, fill="#eef2f7",
                            outline="#16213a", width=2)
        _centered(d, cs0 + 8, cp["label"], font(FB, 19), FAINT)
        _centered(d, cs0 + 34, cp["quote"], font(FB, 23), INK)
        dy = 68

    # punchline strip (garnet — Brian's birthstone; teal edge for health)
    py0, py1 = 700 + dy, 782 + dy
    d.rounded_rectangle([48, py0, W - 48, py1], 18, fill=GARNET_BG,
                        outline=TEAL_EDGE, width=2)
    _centered(d, py0 + 22, content["punchline"], font(FB, 29), YELLOW)

    # curiosity line (replaces technical callouts)
    if content.get("curiosity"):
        _centered(d, 804 + dy, content["curiosity"], font(FB, 26), INK)

    img, d = footer(img, d, hashtag=content.get("hashtag"), dy=dy, brand=b)

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
