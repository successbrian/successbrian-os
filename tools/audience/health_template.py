"""Health-meme brand template for Brian's meme desk.

Same format as the AI and political templates (brand bar, kicker, gradient
3D headline, comparison cards, garnet punchline, curiosity CTA, shared
footer) with a health visual identity:

- deep saturated teal gradient canvas (Brian 2026-10-06: the old near-white
  base read as washed out — bold saturation now, clinical teal kept)
- strong EKG pulse-line pattern along the edges (the health signature, felt)
- kicker flanked by teal pulse glyphs
- Oliabo Prima capsule specimen badge top-right (REAL capsule photos,
  packet removed per Brian — the one emblem per meme)
- bright cyan vitality glow behind the headline
- electric green → cyan headline gradient with near-black teal 3D extrusion
- garnet punchline with a teal edge (garnet = Brian's January birthstone)
- tagline: "LIVED EXPERIENCE. REAL TALK." — the health desk's standing rule
  is lived experience, never prescription.
- hashtag: #SuccessBrianHealth (HEALTH_BRAND["hashtag"])

FORMAT RULE — Brian 2026-11-18 23:27 CST: kicker pills carry the
manufactured finish — gradient marks, soft shadow, 3D bevel, inner
highlight, sheen — on every template (the crypto kicker pill's
finish, propagated). At that hour this template's kicker was an
open assembly with no pill ground, so only the gradient pulse
glyphs and their shadow landed; the 23:38 CST chassis ruling
below supersedes that arrangement — the kicker is a real pill
now and carries the full finish.

FORMAT — CROSSOVER CHASSIS (Brian, 2026-11-18 23:38 CST: "the
other two templates need to carry these similar placements and
styles"): this template renders on the crossover chassis shared
with the AI and crypto templates —
  - full-height BLACK left rail (format rule, Brian 2026-11-18
    23:19 CST): photo + frame, BRIAN LATHE / SUCCESS BRIAN, the
    four nurture icons, a rail content section in the shared
    panel grammar (this template's: the EKG signature line,
    the desk's standing rule LIVED EXPERIENCE. REAL TALK., the
    content lanes — diabetes / GLP-1 / weight loss — and the
    stethoscope + glucometer medallions), and the standard CTA
    SLOT at the foot (rail panel width x 161 tall, swappable
    modules — this template ships the Spencer module);
  - a REAL kicker pill with the manufactured finish (gradient
    pulse glyphs, gloss, soft drop shadow, 3D bevel, inner
    highlight, top sheen);
  - the right side in the AI template's layout geometry and
    type system: headline via headline_3d at depth 4 (health's
    near-black teal extrusion kept), the framed card (444
    tall, holo ring + header band + garnet footer band — the
    garnet keeps its teal hairline, the health signature),
    the connect card in the shared rhythm, and the SIGNATURE
    BAND as a split row — branding left (BRIAN LATHE / LIVED
    EXPERIENCE. REAL TALK.), FOLLOW hashtag chip right
    (HEALTH_BRAND["hashtag"] = "FOLLOW #SuccessBrianHealth",
    on record in meme_template.py);
  - case balance per the AI case map (Brian, 2026-11-18
    23:21 CST): kicker sentence case, headline caps, in-card
    labels caps, ask caps, subline sentence case, chips caps,
    buttons Title Case, signature caps;
  - the Jensen Huang COUNTER STRIP at the foot of the column,
    764 x 86 like every template, the day derived in code
    from the Thu Nov 12, 2026 anchor (counters on all
    templates — Brian, 2026-11-18 22:40 CST).
The Oliabo Prima capsule emblem has no slot in the crossover
chassis and is not drawn by the chassis render (capsule_emblem
is retained; on alpha its photo files do not resolve in any
case — pre-existing). The headline divider and its flanking
icons retire with the old layout; the icons live on in the
rail panel's medallions.

FORMAT PRINCIPLE — THE CAPSULE IS A VARIABLE CONTAINER
(Brian, 2026-11-18 23:40 CST): the main content capsule (the
framed card) is ONE frame holding MANY interior layouts —
the original comparative-card format, charts, Facebook-type
image+text posts, relayed shared posts with Brian's thoughts
beside them, and others. The frame is the format; the
interior is variable. This template's comparative cards
(plus the optional series dots and counterpoint strip) ride
as the interior for now.

CONTENT contract mirrors meme_template.render_meme, plus the political
template's optional headline_size (starting point size, auto-shrinks).

WHY:
    Brian's health desk gives his lived-experience health content
    (diabetes/GLP-1/weight-loss — his standing content lane per 2026-10-04)
    a branded visual lane distinct from the AI and political desks. The
    Oliabo Prima capsule emblem ties the lane to his Oliabo business, and
    the tagline "LIVED EXPERIENCE. REAL TALK." encodes his standing rule:
    lived experience, never prescription.

CALLED BY:
    Imported via render_health_meme for health-desk renders; run directly
    as a script to self-render a proof card to /tmp/health_template_proof.png.

NOTES:
    The sys.path insert points at the /home/hatch/workspace/successbrian-os
    deployment checkout — leave it alone (deployment convention). The Prima
    emblem must use REAL capsule photos per Brian 2026-10-06 (packet removed,
    exactly one emblem per meme).
"""
import os
import sys
from datetime import date as _date
from pathlib import Path
sys.path.insert(0, "/home/hatch/workspace/successbrian-os/tools/audience")
import meme_template as mt
from meme_template import (headline_3d, photo_card,
                           font, _centered, grad_rounded, _gbar, icon,
                           BRAND,
                           HEALTH_BRAND as _HEALTH_BRAND,
                           INK, GRAY, FAINT, GARNET_BG, GARNET_EDGE,
                           YELLOW,
                           W, H, FB, FR)
from PIL import Image, ImageDraw, ImageFilter, ImageChops

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
    """Teal EKG glyph for flanking the kicker — manufactured
    finish (format rule, Brian 2026-11-18 23:27 CST): drawn at
    4x, the line filled with a vertical GRADIENT (lit mint at
    the top -> the glyph's own teal (0, 158, 110) at mid ->
    deep teal at the base) with a soft white SHEEN across its
    top, so the mark reads glossy and dimensional, not flat.
    The soft shadow rides at the kicker call site via the
    template's own _icon_shadow idiom."""
    from PIL import ImageChops
    S = 4
    w4, h4 = size * 2 * S, size * S
    sil = Image.new("L", (w4, h4), 0)
    ImageDraw.Draw(sil).line(
        _pulse_points(4 * S, 4 * S, (size * 2 - 8) * S,
                      (size - 8) * S),
        fill=255, width=max(3, size // 10) * S)
    stops = ((150, 255, 222), (0, 158, 110), (0, 92, 64))
    grad = Image.new("RGBA", (w4, h4), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for yy in range(h4):
        f = yy / max(1, h4 - 1)
        if f < 0.45:
            a, c, g = stops[0], stops[1], f / 0.45
        else:
            a, c, g = stops[1], stops[2], (f - 0.45) / 0.55
        gd.line([(0, yy), (w4, yy)],
                fill=tuple(int(p + (q - p) * g)
                           for p, q in zip(a, c)) + (255,))
    grad.putalpha(sil)
    # sheen: soft white light across the top of the line
    sa = Image.new("L", (w4, h4), 0)
    sd = ImageDraw.Draw(sa)
    for yy in range(h4):
        f = yy / max(1, h4 - 1)
        sd.line([(0, yy), (w4, yy)],
                fill=int(80 * max(0.0, 1 - f / 0.5)))
    sheen = Image.new("RGBA", (w4, h4), (255, 255, 255, 0))
    sheen.putalpha(ImageChops.darker(sa, sil))
    grad.alpha_composite(sheen)
    return grad.resize((size * 2, size), Image.LANCZOS)


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


def capsule_emblem(w=440, h=156):
    """Oliabo Prima capsules — REAL product photography, packet removed.

    Brian 2026-10-06: "i want just the capsules without the pillow pack"
    + each capsule IDENTIFIED. Four real capsule cutouts from Oliabo's own
    product photography on a horizontal white specimen badge:
      2 large dark-green softgels = HP-EVOO + rosemary  -> "HP-EVOO x2"
      green/white capsule         = OLIVECTIN (olive leaf + fruit)
      red/white capsule           = ROSSA (lycopene + grape seed)
    Gold ring + teal glow + drop shadow, same emblem language. Top-right,
    the one emblem per meme — sits above the kicker/headline, clear of
    both, and clear of the wordmark.
    """
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # teal glow behind (template glow language)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(
        [8, 8, w - 8, h - 8], radius=26, fill=(0, 255, 200, 90))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))

    # soft drop shadow under the badge
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [10, 14, w - 6, h - 2], radius=24, fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))

    # white specimen badge
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([6, 6, w - 6, h - 6], radius=24, fill=(255, 255, 255, 255))

    def load(name):
        for cand in (
            Path.home() / f"workspace/your_files/memes/proofs/capsule_{name}.png",
            Path(__file__).resolve().parent.parent.parent.parent
            / f"your_files/memes/proofs/capsule_{name}.png",
        ):
            if cand.exists():
                return Image.open(cand).convert("RGBA")
        print(f"WARNING capsule_emblem: capsule_{name}.png not found")
        return None

    evoo1, evoo2 = load("evoo"), load("evoo_b")
    oliv, rossa = load("olivectin"), load("rossa")
    if not all([evoo1, evoo2, oliv, rossa]):
        return im

    # scale: softgels to h=88, olivectin to w=88, rossa to h=72
    def scale(img, *, h=None, w=None):
        iw, ih = img.size
        s = (h / ih) if h else (w / iw)
        return img.resize((int(iw * s), int(ih * s)), Image.LANCZOS)

    evoo1, evoo2 = scale(evoo1, h=88), scale(evoo2, h=88)
    oliv, rossa = scale(oliv, w=88), scale(rossa, h=72)

    # baseline-align the capsules like specimens on a shelf
    cap_top, cap_bot = 16, 104
    items = [evoo1, evoo2, oliv, rossa]
    gap = 18
    total = sum(i.size[0] for i in items) + gap * (len(items) - 1)
    x = (w - total) // 2
    centers = []
    for it in items:
        iw, ih = it.size
        im.alpha_composite(it, (int(x), cap_bot - ih))
        centers.append(x + iw / 2)
        x += iw + gap

    # labels — dark green on white, must read at a glance
    d = ImageDraw.Draw(im)
    GREEN = "#14532d"
    f1, f2 = font(FB, 24), font(FB, 16)
    ly = cap_bot + 8
    # "HP-EVOO x2" spans the softgel pair
    t = "HP-EVOO \u00d72"
    tw = d.textlength(t, font=f1)
    d.text(((centers[0] + centers[1]) / 2 - tw / 2, ly), t, font=f1, fill=GREEN)
    # OLIVECTIN / ROSSA under their capsules — nudged apart so the long
    # OLIVECTIN label never touches ROSSA
    l_oliv, l_rossa = "OLIVECTIN\u2122", "ROSSA\u2122"
    tw_o = d.textlength(l_oliv, font=f2)
    tw_r = d.textlength(l_rossa, font=f2)
    xo, xr = centers[2] - tw_o / 2, centers[3] - tw_r / 2
    if xo + tw_o + 6 > xr:
        shift = (xo + tw_o + 6 - xr) / 2
        xo -= shift
        xr += shift
    d.text((xo, ly + 4), l_oliv, font=f2, fill=GREEN)
    d.text((xr, ly + 4), l_rossa, font=f2, fill=GREEN)

    # gold ring (Oliabo accent) defines the badge edge intentionally
    d.rounded_rectangle([6, 6, w - 6, h - 6], radius=24,
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
        # the finish's soft shadow, in the template's own
        # _icon_shadow idiom (dark teal, offset, blurred)
        sp = _icon_shadow(icon_pulse(36))
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




# ================= CROSSOVER CHASSIS =====================================
# Format convergence (Brian, 2026-11-18 23:38 CST — see the module
# docstring): this template renders on the crossover chassis shared
# with the AI and crypto templates. The helpers below follow the
# desk pattern — each driver carries its own copies (the crypto
# crossover driver is the reference build).
RAIL_W = 252
CX = (RAIL_W + W) // 2 + 14  # content-zone center
HUANG_COUNT_START = _date(2026, 11, 12)  # DAY 1 = Thu Nov 12, 2026
GOLD_TXT = "#d9a521"
RAIL_DIM = "#9aa7ba"

_HERE = os.path.dirname(os.path.abspath(__file__))
_SP = os.path.join(_HERE, "assets", "spencer-badge.webp")
if os.path.exists(_SP):
    mt.SPENCER_PHOTO = _SP


def _photo_resolved(p):
    """The caller's photo if it exists, else the desk's alpha asset
    (the legacy /home/hatch paths do not resolve on alpha)."""
    if p and os.path.exists(p):
        return p
    alt = os.path.join(_HERE, "assets", "brian-gina.jpg")
    return alt if os.path.exists(alt) else p


def cx_text(d, cx, y, text, fnt, fill, tracking=0):
    if tracking:
        tw = d.textlength(text, font=fnt) + tracking * (len(text) - 1)
        x = cx - tw / 2
        for ch in text:
            d.text((x, y), ch, font=fnt, fill=fill)
            x += d.textlength(ch, font=fnt) + tracking
        return tw
    tw = d.textlength(text, font=fnt)
    d.text((cx - tw / 2, y), text, font=fnt, fill=fill)
    return tw


def _lx_text(d, x, y, text, fnt, fill, tracking=0):
    """Left-aligned text with optional tracking; returns the x just
    past the last glyph."""
    if tracking:
        for ch in text:
            d.text((x, y), ch, font=fnt, fill=fill)
            x += d.textlength(ch, font=fnt) + tracking
        return x
    d.text((x, y), text, font=fnt, fill=fill)
    return x + d.textlength(text, font=fnt)


def _fit(text, size, maxw, floor=12):
    """Largest FB size (<= size) whose plain text width fits maxw."""
    _d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    s = size
    while s > floor and _d.textlength(text, font=font(FB, s)) > maxw:
        s -= 1
    return font(FB, s), s


def _vgrad(w, h, top, bot, radius):
    """Vertical two-stop gradient with rounded corners."""
    _g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _gd = ImageDraw.Draw(_g)
    _t, _b = mt._hex(top), mt._hex(bot)
    for _yy in range(h):
        _f = _yy / max(1, h - 1)
        _gd.line([(0, _yy), (w, _yy)],
                 fill=tuple(int(a + (c - a) * _f)
                            for a, c in zip(_t, _b)) + (255,))
    _mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(_mask).rounded_rectangle(
        [0, 0, w - 1, h - 1], radius, fill=255)
    _g.putalpha(_mask)
    return _g


def _kicker_finish(w, h, ground, radius, bevel_peak, sheen_peak,
                   hl_peak, bevel_w=3):
    """The manufactured finish core (the crypto/AI construction):
    soft SHEEN across the top of the ground, a 3D BEVEL ring
    (pale top edge rolling through a neutral mid to near-black
    at the bottom), and a fine INNER HIGHLIGHT line just inside
    the bevel. Built at 4x; `ground` is a 4x RGBA image."""
    S = 4
    W4, H4 = w * S, h * S
    R4 = radius * S
    pill = ground
    bw = bevel_w * S

    def _ring(inset, thick):
        _m = Image.new("L", (W4, H4), 0)
        _md = ImageDraw.Draw(_m)
        _md.rounded_rectangle([inset, inset, W4 - 1 - inset,
                               H4 - 1 - inset],
                              max(4, R4 - inset), fill=255)
        _inner = Image.new("L", (W4, H4), 0)
        ImageDraw.Draw(_inner).rounded_rectangle(
            [inset + thick, inset + thick,
             W4 - 1 - inset - thick, H4 - 1 - inset - thick],
            max(4, R4 - inset - thick), fill=255)
        return ImageChops.subtract(_m, _inner)

    def _vgrad_rgba(stops, alpha_mask, peak=255):
        _g = Image.new("RGBA", (W4, H4), (0, 0, 0, 0))
        _gd = ImageDraw.Draw(_g)
        for _yy in range(H4):
            _f = _yy / max(1, H4 - 1)
            for _i in range(len(stops) - 1):
                _f0, _c0 = stops[_i]
                _f1, _c1 = stops[_i + 1]
                if _f0 <= _f <= _f1:
                    _g2 = (_f - _f0) / max(1e-6, _f1 - _f0)
                    _col = tuple(int(p + (q - p) * _g2)
                                 for p, q in zip(_c0, _c1))
                    break
            else:
                _col = stops[-1][1]
            _gd.line([(0, _yy), (W4, _yy)], fill=_col + (255,))
        _g.putalpha(alpha_mask.point(lambda v: v * peak // 255))
        return _g

    _sa = Image.new("L", (W4, H4), 0)
    _sd = ImageDraw.Draw(_sa)
    for _yy in range(H4):
        _f = _yy / max(1, H4 - 1)
        _sd.line([(0, _yy), (W4, _yy)],
                 fill=int(sheen_peak * max(0.0, 1 - _f / 0.55)))
    _sa = _sa.filter(ImageFilter.GaussianBlur(3 * S))
    _interior = Image.new("L", (W4, H4), 0)
    ImageDraw.Draw(_interior).rounded_rectangle(
        [bw, bw, W4 - 1 - bw, H4 - 1 - bw], R4 - bw, fill=255)
    _sheen = Image.new("RGBA", (W4, H4), (255, 255, 255, 0))
    _sheen.putalpha(ImageChops.darker(_sa, _interior))
    pill.alpha_composite(_sheen)
    _bevel = _vgrad_rgba(
        ((0.0, (242, 250, 253)), (0.35, (158, 168, 178)),
         (0.65, (58, 64, 72)), (1.0, (6, 8, 12))),
        _ring(0, bw), peak=bevel_peak)
    pill.alpha_composite(_bevel)
    _ha = Image.new("L", (W4, H4), 0)
    _hd = ImageDraw.Draw(_ha)
    for _yy in range(H4):
        _f = _yy / max(1, H4 - 1)
        _hd.line([(0, _yy), (W4, _yy)],
                 fill=int(hl_peak * max(0.0, 1 - _f / 0.6)))
    _hl = Image.new("RGBA", (W4, H4), (255, 255, 255, 0))
    _hl.putalpha(ImageChops.darker(_ha, _ring(bw, 1 * S + 2)))
    pill.alpha_composite(_hl)
    return pill.resize((w, h), Image.LANCZOS)


def _kicker_pill(w, h, colors, base_alpha):
    """The kicker pill, manufactured: the holo gradient ground in
    the template's colors, finished with _kicker_finish at the
    format peaks (bevel 238, sheen 52, highlight 130). The soft
    drop shadow is cast by the caller."""
    S = 4
    ground = mt.holo_pill((w * S, h * S), colors=tuple(colors),
                          radius=26 * S, base_alpha=base_alpha)
    return _kicker_finish(w, h, ground, 26, 238, 52, 130)


def _polished_bar(w, h, stops, radius=14):
    """A bar with the manufactured finish: three-stop gradient
    ground finished with _kicker_finish at the bar peaks (bevel
    205, sheen 46, highlight 115). The caller casts the shadow."""
    S = 4
    W4, H4 = w * S, h * S
    cols = [mt._hex(s) for s in stops]
    bar = Image.new("RGBA", (W4, H4), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    for yy in range(H4):
        f = yy / max(1, H4 - 1)
        if f < 0.5:
            a, c, g = cols[0], cols[1], f / 0.5
        else:
            a, c, g = cols[1], cols[2], (f - 0.5) / 0.5
        bd.line([(0, yy), (W4, yy)],
                fill=tuple(int(p + (q - p) * g)
                           for p, q in zip(a, c)) + (255,))
    _mask = Image.new("L", (W4, H4), 0)
    ImageDraw.Draw(_mask).rounded_rectangle(
        [0, 0, W4 - 1, H4 - 1], radius * S, fill=255)
    bar.putalpha(_mask)
    return _kicker_finish(w, h, bar, radius, 205, 46, 115,
                          bevel_w=2)


def _bar_shadow(img, x, top, w, h, radius):
    _pad = 18
    _sh = Image.new("RGBA", (w + 2 * _pad, h + 2 * _pad),
                    (0, 0, 0, 0))
    ImageDraw.Draw(_sh).rounded_rectangle(
        [_pad, _pad, _pad + w - 1, _pad + h - 1], radius,
        fill=(0, 0, 0, 120))
    _sh = _sh.filter(ImageFilter.GaussianBlur(7))
    img.paste(_sh, (x - _pad, top + 4 - _pad), _sh)


_KEEP_CAPS = {"AI", "USA", "US", "MMN", "CVN", "EVOO"}


def _sentence_case(text):
    """The kicker role's case (format case map): sentence case.
    Tokens carrying digits, and the desk's standing acronyms
    (AI, USA, MMN, CVN, EVOO), keep their case — ordinary short
    words (IT, A, ON) lowercase like everything else."""
    out = []
    for w in text.split():
        core = w.strip("—–-•·\"'“”")
        if any(ch.isdigit() for ch in w) or (core.isupper()
                                             and core in _KEEP_CAPS):
            out.append(w)
        else:
            out.append(w.lower())
    s = " ".join(out)
    for i, ch in enumerate(s):
        if ch.isalpha():
            s = s[:i] + ch.upper() + s[i + 1:]
            break
    return s


def _ask_parts(content):
    """The connect card's ask + subline from the content's
    curiosity line (format case map: ask ALL CAPS, subline
    sentence case). An explicit content["ask"] wins."""
    if content.get("ask"):
        return content["ask"], content.get("ask_sub", "")
    cur = content.get("curiosity", "")
    if "?" in cur:
        a, _, rest = cur.partition("?")
        return (a + "?").upper(), (rest.strip()
                                   or "Drop your answer in the comments.")
    return cur.upper(), ""


def _yt_icon(size=26):
    _im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    _d = ImageDraw.Draw(_im)
    _d.rounded_rectangle([2, 2, size - 2, size - 2], size // 4,
                         fill=(235, 25, 35, 255))
    _d.polygon([(size * 0.40, size * 0.32), (size * 0.40, size * 0.68),
                (size * 0.70, size * 0.50)], fill=(255, 255, 255, 255))
    return _im


def _sharp_icon(kind, size=42):
    big = size * 4
    _b = _yt_icon(big) if kind == "youtube" else mt.icon(kind, big)
    return _b.resize((size, size), Image.LANCZOS)


def _panel_frame(img, outline):
    """The rail content section's frame (the shared panel
    grammar): one bordered panel, x14-238, y450-861."""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14, 450, RAIL_W - 14, 861], 18,
                        fill=(22, 23, 31, 255),
                        outline=mt._hex(outline) + (255,), width=2)
    return 450


def _panel_header(d, y0, text):
    cx_text(d, RAIL_W // 2, y0 + 20, text, font(FB, 18),
            GOLD_TXT, tracking=2)
    d.line([(40, y0 + 54), (RAIL_W - 40, y0 + 54)],
           fill=(217, 165, 33, 255), width=2)


def _medallion(img, mcx, top, glyph, color, size=58):
    """A drawn medallion in the shared grammar: dark disc ringed
    in the mark's color, the glyph centered inside."""
    S = 4
    m = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0))
    md = ImageDraw.Draw(m)
    c = size * S // 2
    r = c - 4 * S
    md.ellipse([c - r, c - r, c + r, c + r], fill=(35, 35, 46, 255),
               outline=mt._hex(color) + (255,), width=3 * S)
    m = m.resize((size, size), Image.LANCZOS)
    img.paste(m, (mcx - size // 2, top), m)
    g = glyph
    maxg = size - 16
    if g.width > maxg or g.height > maxg:
        if g.width >= g.height:
            g = g.resize((maxg, int(g.height * maxg / g.width)),
                         Image.LANCZOS)
        else:
            g = g.resize((int(g.width * maxg / g.height), maxg),
                         Image.LANCZOS)
    img.paste(g, (mcx - g.width // 2, top + (size - g.height) // 2), g)


def _spencer_cta(img, accent):
    """The Spencer CTA module in the standard slot (the AI
    crossover's geometry: gold rule 881, lines 895/914, badge
    935-1019, name 1027 — slot 881-1042, 161 tall)."""
    d = ImageDraw.Draw(img)
    d.line([(36, 881), (RAIL_W - 36, 881)],
           fill=(217, 165, 33, 255), width=3)
    for _i, _line in enumerate(mt.SPENCER_CTA):
        cx_text(d, RAIL_W // 2, 895 + _i * 19, _line, font(FB, 13),
                accent if _i else "#ffffff")
    _badge = mt.spencer_badge(84)
    img.paste(_badge, (RAIL_W // 2 - 42, 935), _badge)
    d = ImageDraw.Draw(img)
    cx_text(d, RAIL_W // 2, 1027, "SPENCER", font(FB, 15), "#ffffff")


def _rail(img, photo_path, edge_colors, brand_color, glow_color,
          panel_fn, cta_accent):
    """The full-height BLACK left rail (format rule): black
    ground, gradient edge, photo + frame + verified badge,
    BRIAN LATHE / SUCCESS BRIAN, the four nurture icons, the
    template's content section, the standard CTA slot."""
    rail = Image.new("RGBA", (RAIL_W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rail)
    for yy in range(H):
        t = yy / H
        col = tuple(int(a + (b - a) * t)
                    for a, b in zip((25, 27, 35), (15, 15, 20)))
        rd.line([(0, yy), (RAIL_W, yy)], fill=col + (255,))
    img.alpha_composite(rail, (0, 0))
    strip = grad_rounded((6, H), list(edge_colors), 3)
    img.paste(strip, (RAIL_W, 0), strip)
    glow = mt._radial_glow(300, 300, glow_color, 70)
    img.paste(glow, (RAIL_W // 2 - 150, -20), glow)
    pc = photo_card(_photo_resolved(photo_path), size=192)
    img.paste(pc, (RAIL_W // 2 - 96, 40), pc)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([RAIL_W // 2 - 102, 34, RAIL_W // 2 + 102, 238],
                        32, outline=(217, 165, 33, 255), width=4)
    d.rounded_rectangle([RAIL_W // 2 - 109, 27, RAIL_W // 2 + 109, 245],
                        36, outline=(217, 165, 33, 140), width=2)
    bx, by, br = RAIL_W // 2 + 74, 200, 20
    d.ellipse([bx - br, by - br, bx + br, by + br],
              fill=(10, 165, 224, 255),
              outline=(255, 255, 255, 255), width=3)
    d.line([(bx - 10, by), (bx - 3, by + 8), (bx + 11, by - 8)],
           fill=(255, 255, 255, 255), width=4)
    cx_text(d, RAIL_W // 2, 272, "BRIAN LATHE", font(FB, 32),
            "#ffffff", tracking=1)
    cx_text(d, RAIL_W // 2, 314, "SUCCESS BRIAN", font(FB, 17),
            brand_color, tracking=3)
    for _i, _kind in enumerate(("facebook", "instagram",
                                "youtube", "blog")):
        _ix = RAIL_W // 2 - 42 - 8 if _i % 2 == 0 else RAIL_W // 2 + 8
        _iy = 338 if _i < 2 else 338 + 42 + 12
        _ic = _sharp_icon(_kind, 42)
        img.paste(_ic, (_ix, _iy), _ic)
    panel_fn(img)
    _spencer_cta(img, cta_accent)


def _kicker(img, text, colors, base_alpha, text_fill, mark_l, mark_r):
    """The kicker as a REAL pill (format): AI proportions (y24,
    height 66, radius 26, text FB18), the manufactured finish,
    the template's own marks inside the pill ends, sentence
    case per the case map."""
    d = ImageDraw.Draw(img)
    kt = _sentence_case(text)
    kf = font(FB, 18)
    ktw = d.textlength(kt, font=kf) + 3 * (len(kt) - 1)
    pw, ph = int(ktw) + 120, 66
    px = int(CX - pw / 2)
    _pad = 32
    _shadow = Image.new("RGBA", (pw + 2 * _pad, ph + 2 * _pad),
                        (0, 0, 0, 0))
    ImageDraw.Draw(_shadow).rounded_rectangle(
        [_pad, _pad, _pad + pw - 1, _pad + ph - 1], 26,
        fill=(0, 0, 0, 165))
    _shadow = _shadow.filter(ImageFilter.GaussianBlur(11))
    img.paste(_shadow, (px - _pad, 24 + 7 - _pad), _shadow)
    _pill = _kicker_pill(pw, ph, colors, base_alpha)
    img.paste(_pill, (px, 24), _pill)
    if mark_l is not None:
        img.paste(mark_l, (px + 14, 24 + (66 - mark_l.height) // 2),
                  mark_l)
    if mark_r is not None:
        img.paste(mark_r, (px + pw - 14 - mark_r.width,
                           24 + (66 - mark_r.height) // 2), mark_r)
    d = ImageDraw.Draw(img)
    cx_text(d, CX, 24 + (66 - 18) // 2 - 1, kt, kf, text_fill,
            tracking=3)


def _headline(img, text, colors, start=96, extrusion=None):
    """The shared 3D headline treatment: headline_3d at depth 4,
    fitted from `start` on the TRUE rendered layer width (<= 814)
    and the format's layer height (<= 120), pasted at y94;
    returns the framed card's top (94 + layer height + 14)."""
    size = start
    _dummy = Image.new("RGBA", (10, 10))
    while size > 28:
        f_big = font(FB, size)
        kw = {"depth": 4}
        if extrusion:
            kw["extrusion"] = extrusion
        hl, (lw, lh) = headline_3d(_dummy, text, f_big,
                                   list(colors), **kw)
        if lw <= W - RAIL_W - 14 and lh <= 120:
            break
        size -= 1
    img.paste(hl, (int(CX - lw / 2), 94), hl)
    return 94 + lh + 14


def _framed(img, cy, colors, fill, outline):
    """THE CAPSULE — the framed card at the format's geometry
    (x286-1050, 444 tall, radius 24): holo ring outside, outline
    width 5, 14px holo header band flush inside the top. The
    interior is the caller's (variable container — see the
    module docstring); the garnet footer band closes it."""
    x0, x1 = RAIL_W + 34, W - 30
    _frame = mt.holo_pill((x1 - x0 + 6, 444 + 6),
                          colors=tuple(colors), radius=27,
                          base_alpha=255)
    img.paste(_frame, (x0 - 3, cy - 3), _frame)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, cy, x1, cy + 444], 24, fill=fill,
                        outline=outline, width=5)
    _bw = (x1 - 4) - (x0 + 4)
    _band = mt.holo_pill((_bw, 14), colors=tuple(colors), radius=1,
                         base_alpha=255)
    _bm = Image.new("L", (_bw * 3, 14 * 3), 0)
    ImageDraw.Draw(_bm).rounded_rectangle(
        [0, 0, _bw * 3 - 1, 14 * 3 + 60], radius=60, fill=255)
    _band.putalpha(_bm.resize((_bw, 14), Image.LANCZOS))
    img.paste(_band, (x0 + 4, cy + 4), _band)
    return x0, x1


def _garnet(img, cy, x0, x1, text, hairline=GARNET_EDGE):
    """The capsule's garnet footer band (48 tall, flush inside
    the bottom border): shaded garnet gradient, hairline on its
    top edge, the punchline in YELLOW at the format tier (FB23)."""
    _gbw = x1 - x0 - 8
    _gb = _vgrad(_gbw, 48, "#a83a50", "#7e2e3f", 1)
    _gm = Image.new("L", (_gbw * 3, 48 * 3), 0)
    ImageDraw.Draw(_gm).rounded_rectangle(
        [0, -60, _gbw * 3 - 1, 48 * 3 - 1], radius=60, fill=255)
    _gb.putalpha(_gm.resize((_gbw, 48), Image.LANCZOS))
    _gy = cy + 444 - 4 - 48
    img.paste(_gb, (x0 + 4, _gy), _gb)
    d = ImageDraw.Draw(img)
    d.line([x0 + 4, _gy, x1 - 4, _gy], fill=hairline, width=2)
    _pf, _psz = _fit(text.upper(), 23, _gbw - 40, floor=14)
    cx_text(d, (x0 + x1) // 2, _gy + (48 - _psz) // 2 - 1,
            text.upper(), _pf, YELLOW)


def _chip(img, cx_center, label, kind, top, fill, outline, ink):
    """A LIKE / COMMENT / SHARE chip (232x44) in the shared
    grammar, skinned by the caller."""
    chw, chh = 232, 44
    cx0 = int(cx_center - chw / 2)
    _s = Image.new("RGBA", (chw + 20, chh + 20), (0, 0, 0, 0))
    ImageDraw.Draw(_s).rounded_rectangle(
        [10, 10, chw + 10, chh + 10], 22, fill=(0, 0, 0, 90))
    _s = _s.filter(ImageFilter.GaussianBlur(6))
    img.paste(_s, (cx0 - 10, top - 6), _s)
    _cd = ImageDraw.Draw(img)
    _cd.rounded_rectangle([cx0, top, cx0 + chw, top + chh], 22,
                          fill=fill, outline=outline, width=2)
    if kind == "like":
        hx, hy = cx0 + 22, top + 10
        _cd.ellipse([hx, hy, hx + 12, hy + 12], fill="#e0245e")
        _cd.ellipse([hx + 11, hy, hx + 23, hy + 12], fill="#e0245e")
        _cd.polygon([(hx + 1, hy + 9), (hx + 22, hy + 9),
                     (hx + 11, hy + 24)], fill="#e0245e")
        ix = cx0 + 22 + 23 + 12
    elif kind == "share":
        nx, ny = cx0 + 22, top + 8
        _cd.line([(nx + 7, ny + 14), (nx + 24, ny + 5)], fill=ink,
                 width=3)
        _cd.line([(nx + 7, ny + 14), (nx + 24, ny + 23)], fill=ink,
                 width=3)
        for cxp, cyp in [(nx + 26, ny + 5), (nx + 5, ny + 14),
                         (nx + 26, ny + 23)]:
            _cd.ellipse([cxp - 5, cyp - 5, cxp + 5, cyp + 5],
                        outline=ink, width=3)
        ix = cx0 + 22 + 31 + 12
    else:
        bx0, by0 = cx0 + 22, top + 10
        _cd.rounded_rectangle([bx0, by0, bx0 + 30, by0 + 20], 6,
                              outline=ink, width=3)
        _cd.polygon([(bx0 + 6, by0 + 20), (bx0 + 6, by0 + 29),
                     (bx0 + 15, by0 + 20)], fill=ink)
        for _dx in (8, 15, 22):
            _cd.ellipse([bx0 + _dx - 2, by0 + 8, bx0 + _dx + 2,
                         by0 + 12], fill=ink)
        ix = cx0 + 22 + 30 + 12
    _cd.text((ix, top + 11), label, font=font(FB, 17), fill=ink)


def _cta(img, cx0, top, w, h, c_top, c_bot, line1, line2):
    _b = _vgrad(w, h, c_top, c_bot, 16)
    img.paste(_b, (cx0, top), _b)
    _bd = ImageDraw.Draw(img)
    _f1 = font(FB, 19)
    _w1 = _bd.textlength(line1, font=_f1)
    _bd.text((cx0 + (w - _w1) / 2, top + 9), line1, font=_f1,
             fill=(255, 255, 255, 255))
    _f2 = font(FB, 12)
    _w2 = _bd.textlength(line2, font=_f2)
    _bd.text((cx0 + (w - _w2) / 2, top + 35), line2, font=_f2,
             fill=(255, 255, 255, 235))


def _connect(img, T, *, card_fill, card_outline, strip_colors,
             ask, sub, ask_fill, sub_fill, chip_fill, chip_outline,
             chip_ink, band_stops, band_outline, band_line,
             hashtag, chip_stops, tag_ink):
    """THE CONNECT CARD in the shared rhythm (272 tall): ask
    (FB28, ALL CAPS) -> subline (FB18, sentence case) -> chips
    -> destinations (Substack polished bar + WhatsApp) -> the
    SIGNATURE BAND as a split row: branding LEFT, the FOLLOW
    hashtag chip RIGHT."""
    _csh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(_csh).rounded_rectangle(
        [RAIL_W + 34, T + 7, W - 30, T + 272 + 7], 24,
        fill=(0, 0, 0, 110))
    _csh = _csh.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(_csh)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([RAIL_W + 34, T, W - 30, T + 272], 24,
                        fill=card_fill, outline=card_outline,
                        width=3)
    _astrip = mt.holo_pill((W - 30 - (RAIL_W + 34) - 8, 7),
                           colors=tuple(strip_colors), radius=3,
                           base_alpha=220)
    img.paste(_astrip, (RAIL_W + 38, T + 6), _astrip)
    d = ImageDraw.Draw(img)
    _af, _asz = _fit(ask, 28, 724, floor=16)
    cx_text(d, CX, T + 16, ask, _af, ask_fill)
    if sub:
        cx_text(d, CX, T + 54, sub, font(FB, 18), sub_fill)
    _chip(img, 424, "LIKE", "like", T + 78, chip_fill,
          chip_outline, chip_ink)
    _chip(img, 668, "COMMENT", "comment", T + 78, chip_fill,
          chip_outline, chip_ink)
    _chip(img, 912, "SHARE", "share", T + 78, chip_fill,
          chip_outline, chip_ink)
    # destinations: the Substack bar, polished (Title Case name
    # + lowercase address), and the green WhatsApp pill
    _bar_shadow(img, 292, T + 126, 368, 58, 16)
    _sb = _polished_bar(368, 58, ("#ff9a4d", "#ff7a29", "#cf4300"),
                        16)
    img.paste(_sb, (292, T + 126), _sb)
    d = ImageDraw.Draw(img)
    _f1 = font(FB, 19)
    _w1 = d.textlength("Read My Blog", font=_f1)
    d.text((292 + (368 - _w1) / 2, T + 126 + 9), "Read My Blog",
           font=_f1, fill=(255, 255, 255, 255))
    _f2 = font(FB, 12)
    _url = BRAND["blog_url"]
    _w2 = d.textlength(_url, font=_f2)
    d.text((292 + (368 - _w2) / 2, T + 126 + 35), _url, font=_f2,
           fill=(255, 255, 255, 235))
    _cta(img, 676, T + 126, 368, 58, "#2fce6e", "#0f9d4c",
         "Message Me on WhatsApp",
         dict(BRAND["handles"])["whatsapp"])
    # THE SIGNATURE BAND — split row, polished navy-style bar in
    # the template's skin
    _bx0, _bx1 = RAIL_W + 46, W - 42
    _bw = _bx1 - _bx0
    _by, _bh = T + 198, 62
    _bar_shadow(img, _bx0, _by, _bw, _bh, 14)
    _pq = _polished_bar(_bw, _bh, band_stops, 14)
    img.paste(_pq, (_bx0, _by), _pq)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([_bx0, _by, _bx1, _by + _bh], 14,
                        outline=band_outline, width=2)
    _nend = _lx_text(d, _bx0 + 24, _by + 7, "BRIAN LATHE",
                     font(FB, 30), "white", tracking=1)
    _mend = _lx_text(d, _bx0 + 24, _by + 42, band_line,
                     font(FB, 13), "#f2cf7a", tracking=1)
    if hashtag:
        _tf, _tsz = _fit(hashtag, 15, 300, floor=11)
        _cw = int(d.textlength(hashtag, font=_tf) + 42)
        _ch = 34
        _cx1 = _bx1 - 20
        _cx0 = _cx1 - _cw
        _cy0 = _by + (_bh - _ch) // 2
        _lend = max(_nend, _mend)
        if _cx0 - _lend > 70:
            _dvx = (_lend + _cx0) // 2
            d.line([_dvx, _by + 14, _dvx, _by + _bh - 14],
                   fill=(70, 96, 138, 255), width=2)
        _bar_shadow(img, _cx0, _cy0, _cw, _ch, 18)
        _chipim = _polished_bar(_cw, _ch, chip_stops, 18)
        img.paste(_chipim, (_cx0, _cy0), _chipim)
        d = ImageDraw.Draw(img)
        cx_text(d, (_cx0 + _cx1) // 2, _cy0 + (_ch - _tsz) // 2 - 1,
                hashtag, _tf, tag_ink)


def _counter(img, T, edge_colors):
    """THE COUNTER STRIP — the format's counter slot at the foot
    of the column (764 x 86, the same size on every template):
    navy gradient block, blue outline, holo top edge in the
    template's colors, DAY n derived from the Thu Nov 12, 2026
    anchor — never hard-coded."""
    _day = (_date.today() - HUANG_COUNT_START).days + 1
    cs0, cs1 = T + 272 + 14, T + 272 + 14 + 86
    _sb = _vgrad(W - 30 - (RAIL_W + 34), cs1 - cs0,
                 "#1d2c49", "#131f36", 18)
    img.paste(_sb, (RAIL_W + 34, cs0), _sb)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([RAIL_W + 34, cs0, W - 30, cs1], 18,
                        outline="#0aa5e0", width=2)
    _edge = mt.holo_pill((W - 30 - (RAIL_W + 34) - 8, 5),
                         colors=tuple(edge_colors), radius=2,
                         base_alpha=200)
    img.paste(_edge, (RAIL_W + 38, cs0 + 3), _edge)
    d = ImageDraw.Draw(img)
    d.text((RAIL_W + 62, cs0 + 24), f"DAY {_day}",
           font=font(FB, 34), fill="white")
    _st = "JENSEN HUANG \u2022 DAYS SINCE HE RESIGNED"
    _sf = font(FB, 16)
    _sw = d.textlength(_st, font=_sf)
    d.text((W - 58 - _sw, cs0 + 18), _st, font=_sf, fill="#ffd23f")
    _ss = "COUNT STARTED THU NOV 12"
    _ssf = font(FB, 12)
    _ssw = d.textlength(_ss, font=_ssf)
    d.text((W - 58 - _ssw, cs0 + 44), _ss, font=_ssf,
           fill="#9fb4cc")


def _pulse_wide(w=184, h=46):
    """A wide EKG pulse line with icon_pulse's manufactured
    finish (vertical gradient — lit mint -> the glyph's teal ->
    deep teal — plus a top sheen), drawn at 4x."""
    S = 4
    w4, h4 = w * S, h * S
    sil = Image.new("L", (w4, h4), 0)
    ImageDraw.Draw(sil).line(
        _pulse_points(6 * S, 6 * S, (w - 12) * S, (h - 12) * S),
        fill=255, width=5 * S, joint="curve")
    stops = ((150, 255, 222), (0, 158, 110), (0, 92, 64))
    grad = Image.new("RGBA", (w4, h4), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for yy in range(h4):
        f = yy / max(1, h4 - 1)
        if f < 0.45:
            a, c, g = stops[0], stops[1], f / 0.45
        else:
            a, c, g = stops[1], stops[2], (f - 0.45) / 0.55
        gd.line([(0, yy), (w4, yy)],
                fill=tuple(int(p + (q - p) * g)
                           for p, q in zip(a, c)) + (255,))
    grad.putalpha(sil)
    sa = Image.new("L", (w4, h4), 0)
    sd = ImageDraw.Draw(sa)
    for yy in range(h4):
        f = yy / max(1, h4 - 1)
        sd.line([(0, yy), (w4, yy)],
                fill=int(80 * max(0.0, 1 - f / 0.5)))
    sheen = Image.new("RGBA", (w4, h4), (255, 255, 255, 0))
    sheen.putalpha(ImageChops.darker(sa, sil))
    grad.alpha_composite(sheen)
    return grad.resize((w, h), Image.LANCZOS)


def _health_panel(img):
    """The health rail section in the shared panel grammar:
    header + gold rule, the EKG signature line, the desk's
    standing rule as the panel's statement (LIVED EXPERIENCE.
    REAL TALK.), a hairline, the content lanes as lit rows,
    and the desk's two drawn instruments as medallions."""
    y0 = _panel_frame(img, TEAL_DARK)
    d = ImageDraw.Draw(img)
    _panel_header(d, y0, "HEALTH DESK")
    pw_ = _pulse_wide()
    img.paste(pw_, (RAIL_W // 2 - 92, y0 + 70), pw_)
    d = ImageDraw.Draw(img)
    cx_text(d, RAIL_W // 2, y0 + 138, "LIVED EXPERIENCE.",
            font(FB, 19), "#ffffff")
    cx_text(d, RAIL_W // 2, y0 + 166, "REAL TALK.",
            font(FB, 19), "#ffffff")
    d.line([(56, y0 + 204), (196, y0 + 204)],
           fill=(70, 74, 90, 255), width=2)
    cx_text(d, RAIL_W // 2, y0 + 220, "THE LANE", font(FB, 11),
            RAIL_DIM, tracking=3)
    for _i, _lane in enumerate(("DIABETES", "GLP-1", "WEIGHT LOSS")):
        _yy = y0 + 246 + _i * 30
        d.ellipse([44 - 9, _yy + 1, 44 + 9, _yy + 19],
                  fill=(0, 255, 170, 40))
        d.ellipse([44 - 4, _yy + 6, 44 + 4, _yy + 14],
                  fill=(64, 255, 170, 255))
        _lx_text(d, 62, _yy, _lane, font(FB, 14), "#ffffff",
                 tracking=1)
    _medallion(img, 56, y0 + 334, icon_stethoscope(34), TEAL_EDGE,
               size=52)
    _medallion(img, 196, y0 + 334, icon_glucometer(34), TEAL_EDGE,
               size=52)
    d = ImageDraw.Draw(img)
    cx_text(d, 56, y0 + 334 + 56, "STETHOSCOPE", font(FB, 9),
            "#ffffff")
    cx_text(d, 196, y0 + 334 + 56, "GLUCOMETER", font(FB, 9),
            "#ffffff")


def _health_interior(img, content, cy, x0, x1):
    """The health capsule interior (variable container — the
    desk's comparative cards ride as the interior for now),
    reflowed to the frame: cards across the interior width,
    the optional series dots above them, the optional
    counterpoint strip in the skeptics-strip position."""
    d = ImageDraw.Draw(img)
    cards = content["cards"]
    n = len(cards)
    ix0, ix1 = x0 + 20, x1 - 20
    top = cy + 26
    if content.get("series_day"):
        _sd = content["series_day"]
        _r, _gap = 7, 12
        _total = 5 * _r * 2 + 4 * _gap
        _sx = CX - _total / 2
        for _i in range(5):
            _cx = _sx + _r + _i * (_r * 2 + _gap)
            if _i < _sd:
                d.ellipse([_cx - _r, cy + 40 - _r, _cx + _r,
                           cy + 40 + _r], fill=TEAL_DARK)
            else:
                d.ellipse([_cx - _r, cy + 40 - _r, _cx + _r,
                           cy + 40 + _r], outline="#b9c4d6",
                          width=2)
        top = cy + 58
    cp = content.get("counterpoint")
    bot = cy + 322 if cp else cy + 392
    chh = bot - top
    gap = 24
    cw = (ix1 - ix0 - gap * (n - 1)) / n
    for i, c in enumerate(cards):
        x = ix0 + i * (cw + gap)
        tint = c.get("tint", "#ffffff")
        d.rounded_rectangle([x + 6, top + 10, x + cw + 6,
                             top + chh + 10], 26,
                            fill=(178, 188, 205, 255))
        d.rounded_rectangle([x, top, x + cw, top + chh], 26,
                            fill=tint,
                            outline=(210, 218, 230, 255), width=2)
        ccx = x + cw / 2
        for txt, fnt, col, fr_ in [
                (c["tag"], font(FB, 19), FAINT, 0.09),
                (c["title"], font(FB, 30), INK, 0.21),
                (c["price"], font(FB, c.get("price_size", 66)),
                 c["bar_color"], 0.37)]:
            tw = d.textlength(txt, font=fnt)
            d.text((ccx - tw / 2, top + chh * fr_), txt, font=fnt,
                   fill=col)
        t = c["sub"]
        tw = d.textlength(t, font=font(FR, 22))
        d.text((ccx - tw / 2, top + chh * 0.70), t,
               font=font(FR, 22), fill=GRAY)
        bx, bw, bh, by = x + 36, cw - 72, 24, top + chh * 0.85
        d.rounded_rectangle([bx, by, bx + bw, by + bh], 12,
                            fill=(226, 231, 241, 255))
        _gbar(img, [bx, by, bx + bw * c["bar_frac"], by + bh],
              c["bar_color"])
        d = ImageDraw.Draw(img)
    if cp:
        sy = cy + 334
        d.rounded_rectangle([x0 + 20, sy, x1 - 20, sy + 44], 14,
                            fill="#f0fdf9", outline=TEAL_EDGE,
                            width=2)
        cx_text(d, CX, sy + 5, cp["label"], font(FB, 12), FAINT,
                tracking=1)
        cx_text(d, CX, sy + 23, cp["quote"], font(FB, 17), INK)


def _pulse_mark():
    """The kicker's pulse mark: icon_pulse's gradient glyph on a
    deep-teal underlay grown from its own silhouette (the
    outline element of the manufactured finish, for a stroke
    glyph), finished with the template's soft-shadow idiom."""
    g = icon_pulse(22)
    a = g.split()[3].filter(ImageFilter.MaxFilter(5))
    under = Image.new("RGBA", g.size, (0, 38, 30, 255))
    under.putalpha(a)
    out = Image.new("RGBA", g.size, (0, 0, 0, 0))
    out.alpha_composite(under)
    out.alpha_composite(g)
    return _icon_shadow(out)


def render_health_meme(content, photo_path=None, out_path="meme.png",
                       brand=None, headline_size=None):
    """Render a health meme on the crossover chassis. The
    capsule interior is the desk's comparative cards (plus the
    optional series dots and counterpoint strip)."""
    b = brand or HEALTH_BRAND
    img = pulse_backdrop(health_background()).convert("RGBA")
    d = ImageDraw.Draw(img)

    _rail(img, photo_path, HL_COLORS, TEAL_EDGE, (0, 200, 160),
          _health_panel, "#22d3ee")

    # kicker: a real pill now, pulse glyphs inside as its marks
    _pm = _pulse_mark()
    _kicker(img, content["kicker"], HL_COLORS, 130,
            (235, 255, 248), _pm, _pm)

    # headline: electric gradient + the shared 3D treatment,
    # health's near-black teal extrusion
    cy = _headline(img, content["headline"],
                   content.get("grad_colors", HL_COLORS),
                   start=headline_size or 96,
                   extrusion=HL_EXTRUSION)

    # THE CAPSULE — the desk's cards are the interior
    x0, x1 = _framed(img, cy, HL_COLORS, "white", "#083f38")
    _health_interior(img, content, cy, x0, x1)
    _garnet(img, cy, x0, x1, content["punchline"],
            hairline=TEAL_EDGE)

    # connect card + counter strip
    T = cy + 444 + 26
    ask, sub = _ask_parts(content)
    _connect(img, T,
             card_fill="#0b3f38", card_outline=TEAL_EDGE,
             strip_colors=HL_COLORS,
             ask=ask, sub=sub, ask_fill="white",
             sub_fill="#bfe9df",
             chip_fill=(16, 84, 74), chip_outline=TEAL_EDGE,
             chip_ink="white",
             band_stops=("#14665a", "#0a4a41", "#052e29"),
             band_outline=TEAL_EDGE,
             band_line=b["tagline"],
             hashtag=content.get("hashtag") or b.get("hashtag"),
             chip_stops=("#8ff5d2", "#00c98a", "#009e6e"),
             tag_ink=(4, 43, 36))
    _counter(img, T, HL_COLORS)

    img.convert("RGB").save(out_path)
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
                 "bar_frac": 0.85, "bar_color": "#f59e0b",
                 "tint": "#fff8f0"},
                {"tag": "AFTER", "title": "98-109 CLUB",
                 "price": "STEADY", "sub": "nerves calming down",
                 "bar_frac": 0.35, "bar_color": "#00b894",
                 "tint": "#f0fdf9"},
            ],
            "punchline": "YOUR NUMBERS ARE A STORY. READ THEM.",
            "curiosity": "What changed first for you — the numbers or the symptoms?",
        },
        photo_path=PHOTO, out_path="/tmp/health_template_proof.png")
    print("wrote /tmp/health_template_proof.png")
