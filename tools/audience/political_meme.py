#!/usr/bin/env python3
"""SuccessBrian POLITICAL meme renderer — 1080x1080 patriotic Navy edition.

PURPOSE:
    Brian's political-meme brand: patriotic, with U.S. Navy flair.
    He served as an MMN (Machinist's Mate, Nuclear) aboard
    USS George Washington (CVN-73). That identity is part of the brand.

    Same bones as meme_template.py (light background, gradient+3D headline,
    garnet punchline, curiosity CTA, standard footer) plus real Navy visuals:
      - red/white/blue ribbon across the top
      - Navy tagline under the wordmark (veteran • MMN • CVN-73)
      - carrier silhouette with 73 on the island, sailing by his name
      - Cherenkov reactor-blue glow behind the headline (nuke colors)
      - MM propeller rating badge + radiation trefoil flanking the kicker
        and standing watch on the punchline strip
      - patriotic headline gradient (navy -> blue -> red)

USAGE:
    from political_meme import render_political_meme
    render_political_meme(CONTENT, draw_content, out_path="meme.png")

    Optional kwargs:
      headline_size — starting point size for the headline (auto-shrinks to
        fit the 1080 width). Default 76; pass a larger number (e.g. 140)
        for a max-impact scroll-stopper headline.

    CONTENT = {
        "kicker": "SMALL CAPS HOOK",
        "headline": "90% BACK HER OPPONENT",
        "punchline": "HER OWN COMMENT SECTION HAS SPOKEN",
        "curiosity": "Think my count is off? Go read them yourself.",
    }
    # draw_content(img, draw, box) paints the middle zone (x0, y0, x1, y1).

WHY:
    Brian's political desk is his patriotic lane: Navy identity is
    non-negotiable (enlisted MMN, CVN-73 — propeller in enlisted silver,
    never officer's gold) and the standing hashtag is #MAGAUSNavyVet. The
    election_inset countdown rail auto-computes from the post date and
    retires itself after election day, so the template never ships stale
    urgency.

CALLED BY:
    tools/audience/war_on_oil.py (reference one-off render proving the
    chrome end to end). Future political meme scripts import
    render_political_meme with their own draw_content callback.

FORMAT RULE — Brian 2026-11-18 23:27 CST: kicker pills carry the
manufactured finish — gradient marks, soft shadow, 3D bevel, inner
highlight, sheen — on every template (the crypto kicker pill's
finish, propagated). At that hour this template's kicker was an
open assembly with no pill ground, so only the gradient anchors
and their shadows landed; the 23:38 CST chassis ruling below
supersedes that arrangement — the kicker is a real pill now and
carries the full finish.

FORMAT — CROSSOVER CHASSIS (Brian, 2026-11-18 23:38 CST: "the
other two templates need to carry these similar placements and
styles"): this template renders on the crossover chassis shared
with the AI and crypto templates —
  - full-height BLACK left rail (format rule, Brian 2026-11-18
    23:19 CST): photo + frame, BRIAN LATHE / SUCCESS BRIAN, the
    four nurture icons, a rail content section in the shared
    panel grammar (this template's: Brian's Navy service — the
    carrier, CVN-73, the MMN propeller and the trefoil as
    medallions), and the standard CTA SLOT at the foot (rail
    panel width x 161 tall, swappable modules — this template
    ships the Spencer module);
  - a REAL kicker pill with the manufactured finish (gradient
    anchors with near-black navy outlines, gloss, soft drop
    shadow, 3D bevel, inner highlight, top sheen);
  - the right side in the AI template's layout geometry and
    type system: headline via headline_3d at depth 4, the
    framed card (444 tall, holo ring + header band + garnet
    footer band), the connect card in the shared rhythm, and
    the SIGNATURE BAND as a split row — branding left
    (BRIAN LATHE / U.S. NAVY VETERAN), FOLLOW hashtag chip
    right (POL_BRAND["hashtag"], on record below);
  - case balance per the AI case map (Brian, 2026-11-18
    23:21 CST): kicker sentence case, headline caps, in-card
    labels caps, ask caps, subline sentence case, chips caps,
    buttons Title Case, signature caps;
  - the Jensen Huang COUNTER STRIP at the foot of the column,
    764 x 86 like every template, the day derived in code
    from the Thu Nov 12, 2026 anchor (counters on all
    templates — Brian, 2026-11-18 22:40 CST).
The full-width top ribbon does not survive the rail chassis
(it would cross the rail); the tricolor lives on in the
kicker pill ground, the framed card's holo ring and header
band, and the headline gradient. ribbon() is retained.

FORMAT PRINCIPLE — THE CAPSULE IS A VARIABLE CONTAINER
(Brian, 2026-11-18 23:40 CST): the main content capsule (the
framed card) is ONE frame holding MANY interior layouts —
the original comparative-card format, charts, Facebook-type
image+text posts, relayed shared posts with Brian's thoughts
beside them, and others. The frame is the format; the
interior is variable. This template's caller-painted content
(the draw_content callback, narrowed by the election inset
in season) rides as the interior for now.
"""

import math
import os
import sys
from datetime import date as _date

sys.path.insert(0, "/home/hatch/workspace/successbrian-os/tools/audience")
import meme_template as mt
from meme_template import (background, headline_3d, photo_card, BRAND,
                           font, _centered, ai_backdrop, footer,
                           grad_rounded,
                           INK, GRAY, GARNET_BG, GARNET_EDGE, YELLOW,
                           W, H, FB, FR)
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# Political template brand: same handles/blog as the AI brand, but its own
# hashtag slot — Brian will name the political hashtag later; until then the
# footer prints no hashtag line on political memes.
POL_BRAND = dict(BRAND)
POL_BRAND["hashtag"] = "FOLLOW #MAGAUSNavyVet"  # Brian's crowd, his flag (2026-10-06)

GOLD = "#d4af37"
NAVY = "#0a1f44"
FLAG_RED = "#b22234"
FLAG_BLUE = "#3c3b6e"
HEADLINE_COLORS = ["#1e3fae", "#2b7fff", "#e0393e"]  # navy -> blue -> red

POLITICAL_TAGLINE = "U.S. NAVY VETERAN"
PHOTO = "/home/hatch/workspace/profile-images/brian-gina-together.jpg"


def trefoil(size=44):
    """Radiation trefoil — the nuke's badge of honor."""
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = s / 2
    r = s / 2 - 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#ffd800",
              outline=NAVY, width=2)
    for a in (90, 210, 330):
        d.pieslice([cx - r, cy - r, cx + r, cy + r],
                   start=a - 30, end=a + 30, fill="#c400c4")
    d.ellipse([cx - r * 0.30, cy - r * 0.30, cx + r * 0.30, cy + r * 0.30],
              fill="#ffd800")
    d.ellipse([cx - r * 0.14, cy - r * 0.14, cx + r * 0.14, cy + r * 0.14],
              fill="#c400c4")
    return im


def propeller(size=44, color="#c7cedb"):
    """Three-bladed propeller — the Machinist's Mate rating badge.

    Rendered in enlisted silver steel, never officer's gold — Brian is
    enlisted (MMN), and the badge must read that way.
    """
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cx = cy = s / 2
    blade = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blade)
    bd.ellipse([cx - 9, cy - s * 0.44, cx + 9, cy - 10], fill=color)
    for ang in (0, 120, 240):
        im.alpha_composite(
            blade.rotate(ang, resample=Image.BICUBIC, center=(cx, cy)))
    d = ImageDraw.Draw(im)
    d.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=color,
              outline=NAVY, width=3)
    return im


def _jet(length=40, color=NAVY):
    """Side-view jet silhouette, nose to the right."""
    w, h = length, 20
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([2, 7, w - 8, 14], fill=color)                      # fuselage
    d.polygon([(w - 10, 7), (w - 1, 10.5), (w - 10, 14)], fill=color)  # nose
    d.polygon([(6, 7), (11, 0), (14, 7)], fill=color)             # tail fin
    d.polygon([(14, 11), (25, 11), (21, 16), (12, 16)], fill=color)    # wing
    d.ellipse([w - 21, 5, w - 14, 9], fill=(205, 225, 255, 255))  # canopy
    return im


def _helicopter(length=44, color=NAVY):
    """Side-view helicopter silhouette, nose to the left."""
    w, h = length, 27
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([1, 2, w - 8, 4.5], fill=color)                  # main rotor
    d.rectangle([w * 0.32, 4.5, w * 0.32 + 3, 10], fill=color)   # mast
    d.rounded_rectangle([w * 0.18, 9, w * 0.50, 19], 5, fill=color)  # body
    d.ellipse([w * 0.18, 10, w * 0.28, 16], fill=(205, 225, 255, 255))
    d.polygon([(w * 0.48, 11), (w * 0.90, 13), (w * 0.90, 15.5),
               (w * 0.48, 14)], fill=color)                      # tail boom
    d.polygon([(w * 0.88, 13), (w * 0.94, 4), (w * 0.97, 13)], fill=color)
    d.rectangle([w * 0.90, 6, w * 0.99, 8], fill=color)           # tail rotor
    d.rectangle([w * 0.20, 23, w * 0.48, 25], fill=color)        # skid
    d.rectangle([w * 0.26, 19, w * 0.28, 23], fill=color)
    d.rectangle([w * 0.42, 19, w * 0.44, 23], fill=color)
    return im


def icon_robot_futuristic(size=140, primary=NAVY, glow="#4dd8ff"):
    """Sleek futuristic robot bust — glowing visor, the political
    template's AI signature."""
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = s / 2
    # shoulders
    d.rounded_rectangle([cx - s * 0.32, s * 0.70, cx + s * 0.32, s * 0.98],
                        12, fill=primary)
    # chest light
    d.ellipse([cx - 9, s * 0.79, cx + 9, s * 0.93], fill=glow)
    # neck
    d.rectangle([cx - 11, s * 0.60, cx + 11, s * 0.72], fill=primary)
    # angular head
    d.polygon([(cx - s * 0.30, s * 0.30), (cx - s * 0.22, s * 0.12),
               (cx + s * 0.22, s * 0.12), (cx + s * 0.30, s * 0.30),
               (cx + s * 0.26, s * 0.58), (cx - s * 0.26, s * 0.58)],
              fill=primary)
    # glowing visor band
    d.rounded_rectangle([cx - s * 0.24, s * 0.27, cx + s * 0.24, s * 0.42],
                        9, fill=glow)
    d.rounded_rectangle([cx - s * 0.24, s * 0.27, cx + s * 0.24, s * 0.42],
                        9, outline=(255, 255, 255, 160), width=2)
    # antenna + tip light
    d.rectangle([cx - 2.5, s * 0.02, cx + 2.5, s * 0.12], fill=primary)
    d.ellipse([cx - 7, 0, cx + 7, 11], fill=glow)
    # ear discs
    d.ellipse([cx - s * 0.38, s * 0.32, cx - s * 0.25, s * 0.48],
              fill=primary, outline=glow, width=2)
    d.ellipse([cx + s * 0.25, s * 0.32, cx + s * 0.38, s * 0.48],
              fill=primary, outline=glow, width=2)
    return im


def anchor(size=44, color=NAVY):
    """Navy anchor — flanks the kicker on both sides.

    Manufactured finish (format rule, Brian 2026-11-18 23:27
    CST): drawn at 4x in the desk's supersampled idiom, the
    silhouette filled with a vertical GRADIENT (lit steel at
    the top -> the anchor's own navy at mid -> deep near-black
    navy at the base) with a soft gloss streak down the
    shank's upper left, so the mark reads glossy and
    dimensional, not flat. Same geometry as the flat anchor
    it replaces. The soft drop shadow is cast at the kicker
    call site."""
    import math
    S = 4
    s = size * S
    cx = s / 2
    w = max(3 * S, s // 12)

    def _shapes(d, fill):
        # ring
        rr = s * 0.10
        d.ellipse([cx - rr, s * 0.10 - rr, cx + rr, s * 0.10 + rr],
                  outline=fill, width=w)
        # shank
        d.rounded_rectangle([cx - w * 0.55, s * 0.18, cx + w * 0.55,
                             s * 0.74], w // 2 + 1, fill=fill)
        # stock (crossbar)
        d.rounded_rectangle([cx - s * 0.26, s * 0.24, cx + s * 0.26,
                             s * 0.24 + w * 1.1], w // 2 + 1, fill=fill)
        # arms (bottom arc)
        ax0, ay0, ax1, ay1 = cx - s * 0.30, s * 0.30, cx + s * 0.30, s * 0.94
        d.arc([ax0, ay0, ax1, ay1], 25, 155, fill=fill, width=w)
        # flukes: small barbs at the arc ends, angled outward
        for deg in (25, 155):
            a = math.radians(deg)
            ex = cx + s * 0.30 * math.cos(a)
            ey = (ay0 + ay1) / 2 + s * 0.32 * math.sin(a)
            L = s * 0.11
            d.polygon([(ex, ey - L), (ex - L * 0.7, ey + L * 0.5),
                       (ex + L * 0.7, ey + L * 0.5)], fill=fill)

    sil = Image.new("L", (s, s), 0)
    _shapes(ImageDraw.Draw(sil), 255)
    base = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    lit = tuple(int(c + (235 - c) * 0.55) for c in base)
    deep = tuple(int(c * 0.35) for c in base)
    stops = (lit, base, deep)
    grad = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for yy in range(s):
        f = yy / max(1, s - 1)
        if f < 0.45:
            a, c, g = stops[0], stops[1], f / 0.45
        else:
            a, c, g = stops[1], stops[2], (f - 0.45) / 0.55
        gd.line([(0, yy), (s, yy)],
                fill=tuple(int(p + (q - p) * g)
                           for p, q in zip(a, c)) + (255,))
    grad.putalpha(sil)
    # gloss: a soft white streak down the shank's upper left,
    # clipped to the silhouette
    ga = Image.new("L", (s, s), 0)
    ImageDraw.Draw(ga).rounded_rectangle(
        [cx - w * 0.42, s * 0.20, cx - w * 0.05, s * 0.52],
        w // 2, fill=85)
    ga = ga.filter(ImageFilter.GaussianBlur(1.5 * S))
    gloss = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gloss.putalpha(ImageChops.darker(ga, sil))
    grad.alpha_composite(gloss)
    # the outline (the manufactured finish's mark definition,
    # as on the crypto candles): the silhouette grown a breath,
    # in near-black navy, behind the gradient fill
    _rim_a = sil.filter(ImageFilter.MaxFilter(7))
    _rim = Image.new("RGBA", (s, s), (8, 12, 28, 255))
    _rim.putalpha(_rim_a)
    _out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    _out.alpha_composite(_rim)
    _out.alpha_composite(grad)
    return _out.resize((size, size), Image.LANCZOS)


def carrier_silhouette(width=300, color=NAVY):
    """Nimitz-style carrier: bow right, island with 73, jets + helo on deck.

    Rendered at 2x and downscaled with LANCZOS — crisp edges, no jaggies.
    """
    SS = 2  # supersample factor
    w = width * SS
    h = int(width * 0.44 * SS)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    deck_y0, deck_y1 = h * 0.36, h * 0.46
    mid = (deck_y0 + deck_y1) / 2
    # flight deck
    d.polygon([(4, deck_y0), (w * 0.96, deck_y0), (w - 2, mid),
               (w * 0.96, deck_y1), (4, deck_y1)], fill=color)
    # deck centerline dashes
    dx = 14
    while dx < w * 0.90:
        d.rectangle([dx, mid - 1, dx + 10, mid + 1],
                    fill=(255, 255, 255, 110))
        dx += 20
    # hull
    d.polygon([(w * 0.06, deck_y1), (w * 0.90, deck_y1),
               (w * 0.76, h * 0.90), (w * 0.22, h * 0.90)], fill=color)
    # pointed bow rising to the deck tip
    d.polygon([(w * 0.90, deck_y1), (w - 2, mid), (w * 0.84, h * 0.78)],
              fill=color)
    # island — bigger, with a proper bridge and readable hull number
    ix0, ix1 = w * 0.60, w * 0.75
    d.rectangle([ix0, h * 0.14, ix1, deck_y0], fill=color)
    d.rectangle([ix0 - 8, h * 0.18, ix1 + 8, h * 0.28], fill=color)
    d.rectangle([ix0 - 8, h * 0.205, ix1 + 8, h * 0.235],
                fill=(205, 225, 255, 255))
    mx = (ix0 + ix1) / 2
    d.rectangle([mx - 3, h * 0.04, mx + 3, h * 0.14], fill=color)
    d.rectangle([mx - 14, h * 0.06, mx + 14, h * 0.075], fill=color)
    d.ellipse([mx - 6, h * 0.012, mx + 6, h * 0.042], fill=color)
    # hull number on the island
    f = font(FB, max(16, int(w * 0.09)))
    t = "73"
    tw = d.textlength(t, font=f)
    d.text(((ix0 + ix1) / 2 - tw / 2, h * 0.30), t, font=f, fill="white")

    # air wing parked on deck — oversized so it reads at a glance
    for frac, make, ln in ((0.06, _helicopter, 60), (0.29, _jet, 56),
                           (0.46, _jet, 52)):
        ac = make(ln * SS)
        im.paste(ac, (int(w * frac), int(deck_y0 - ac.height + 3)), ac)

    # bow + stern wake
    wc = (130, 185, 235, 255)
    d.arc([w * 0.78, h * 0.84, w * 1.00, h * 1.02], 200, 340, fill=wc,
          width=3 * SS)
    d.arc([w * 0.00, h * 0.86, w * 0.22, h * 1.04], 200, 340, fill=wc,
          width=3 * SS)
    return im.resize((width, int(width * 0.44)), Image.LANCZOS)


def cherenkov_glow(img):
    """Reactor-blue (Cherenkov) glow behind the headline zone."""
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W / 2 - 520, 110, W / 2 + 520, 500], fill=(70, 150, 255, 95))
    gd.ellipse([W / 2 - 300, 180, W / 2 + 300, 420], fill=(120, 190, 255, 70))
    return Image.alpha_composite(
        img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(60))
    ).convert("RGB")


def ribbon(img):
    """Red/white/blue stripes across the very top."""
    d = ImageDraw.Draw(img)
    # red/white/blue frame: top reads red-white-blue, bottom reversed
    # (blue-white-red) — Brian's call, better visual appeal.
    for y0, order in ((0, [FLAG_RED, "white", FLAG_BLUE]),
                      (H - 24, [FLAG_BLUE, "white", FLAG_RED])):
        for i, col in enumerate(order):
            d.rectangle([0, y0 + i * 8, W, y0 + (i + 1) * 8], fill=col)


def _star_points(cx, cy, r_out, r_in, rot=-90):
    import math
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 36)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def political_backdrop(img):
    """Wavy stripes left, 3D stars right — patriotic texture, not a flag.

    Very faint by design: Brian's audience is global (Canada, UK, Australia
    and beyond), so this reads 'veteran' without shouting 'America-first'.
    The star emphasis ramps like a gradient: soft near the center,
    stronger toward the right edge.
    """
    import random
    rnd = random.Random(1776)
    w, h = img.size
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    # RIGHT: 3D stars with navy borders — distinctness ramps up left->right
    for _ in range(13):
        cx = rnd.randint(int(w * 0.56), w - 30)
        cy = rnd.randint(90, h - 90)
        r = rnd.randint(18, 44)
        t = (cx - w * 0.56) / (w * 0.44)  # 0 soft -> 1 distinct
        t = max(0.0, min(1.0, t))
        pts = _star_points(cx, cy, r, r * 0.42)
        sh = int(2 + t * 3)
        d.polygon([(x + sh, y + sh + 1) for x, y in pts],
                  fill=(90, 110, 165, int(50 + t * 60)))
        d.polygon(pts, fill=(178, 198, 235, int(110 + t * 70)),
                  outline=(30, 58, 138, int(60 + t * 120)),
                  width=1 + int(t * 2.5))

    # fireworks: soft multicolor bursts among the right-side stars —
    # deliberately fainter than the stars so they never steal the show;
    # colors weighted red/white/blue with a whisper of gold and teal
    fw_colors = [(178, 34, 52), (240, 240, 245), (60, 59, 110),
                 (178, 34, 52), (240, 240, 245), (60, 59, 110),
                 (212, 175, 55), (45, 212, 191)]
    for _ in range(8):
        cx = rnd.randint(int(w * 0.60), w - 40)
        cy = rnd.randint(110, h - 110)
        r = rnd.randint(13, 24)
        col = rnd.choice(fw_colors)
        for k in range(10):
            a = math.radians(k * 36 + rnd.randint(-8, 8))
            x2 = cx + r * math.cos(a)
            y2 = cy + r * math.sin(a)
            d.line([(cx, cy), (x2, y2)], fill=col + (30,), width=2)
            d.ellipse([x2 - 2, y2 - 2, x2 + 2, y2 + 2], fill=col + (36,))
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=col + (44,))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def political_stripes(img):
    """Soft red/white wavy stripes on the left — white is the bg showing
    through. Applied AFTER the Cherenkov glow so the blue wash doesn't
    bury them; alpha fades left -> right so they melt out past mid-canvas.
    """
    w, h = img.size
    waves = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    wd = ImageDraw.Draw(waves)
    for i, y_base in enumerate([130, 330, 530, 730, 930]):
        pts = [(x, y_base + 26 * math.sin(x / 130 + i * 1.3))
               for x in range(0, w + 1, 12)]
        wd.line(pts, fill=(178, 34, 52, 42), width=56)
    fade = Image.new("L", (w, 1), 0)
    fp = fade.load()
    for x in range(w):
        fp[x, 0] = int(255 * max(0.0, 1 - (x / w) * 1.35))
    fade = fade.resize((w, h))
    waves.putalpha(ImageChops.multiply(waves.split()[3], fade))
    return Image.alpha_composite(img.convert("RGBA"), waves).convert("RGB")


# --- Election-season inset: compact countdown + race tracker ---------------
# Standing until the midterms pass. One point per REAL published poll —
# never invented daily points.
ELECTION_DAY = "2026-11-03"
MN_SENATE_POLLS = [  # (date_label, dem_pct, gop_pct), chronological
    ("9/10", 48.9, 45.4),   # Quantus Insights
    ("9/14", 42.0, 42.0),   # KSTP/SurveyUSA
    ("9/15", 43.0, 42.0),   # co/efficient
    ("9/29", 46.0, 45.0),   # InsiderAdvantage
    ("9/30", 45.8, 43.6),   # Big Data Poll (with leaners)
    ("10/4", 53.0, 44.0),   # GQR (D), top-two ballot, Oct 1-4
    ("10/7", 48.0, 45.0),   # Rasmussen Reports, LV n=856, Oct 5-7
    ("10/7b", 45.0, 41.0),  # Morning Consult (D), RV n=1000, Oct 2-7
    ("10/7c", 47.0, 43.0),  # Mason-Dixon (Star Tribune Minnesota Poll), LV n=800, Oct 5-7, released 10/12; 9% undec
    ("10/12", 45.0, 42.0),   # KSTP/SurveyUSA, LV n=718, Oct 8-12, ±4.2; 4% other, 9% undec
]
MN_SENATE_DEM = "Flanagan (D)"
MN_SENATE_GOP = "Tafoya (R)"
MN_SENATE_FOOTER = "RCP AVG: FLANAGAN +2.2 • TOSS-UP"


def _days_until(post_date, election_day):
    from datetime import date as _date
    pd = post_date or _date.today()
    if isinstance(pd, str):
        pd = _date.fromisoformat(pd)
    return (_date.fromisoformat(election_day) - pd).days


def election_inset(img, d, box, post_date=None):
    """Small inclusion inset: election countdown + MN Senate trend tracker,
    drawn as a right-hand rail inside the content zone."""
    x0, y0, x1, y1 = box
    days_left = _days_until(post_date, ELECTION_DAY)

    # countdown card — big number, gold label
    ch = 118
    d.rounded_rectangle([x0, y0, x1, y0 + ch], 18, fill="#16213a")
    num = str(max(0, days_left))
    nf = font(FB, 62)
    nw = d.textlength(num, font=nf)
    d.text(((x0 + x1) / 2 - nw / 2, y0 + 4), num, font=nf, fill="white")
    lf = font(FB, 17)
    lab = ("DAY UNTIL ELECTION DAY" if days_left == 1
           else "DAYS UNTIL ELECTION DAY")
    lw = d.textlength(lab, font=lf)
    d.text(((x0 + x1) / 2 - lw / 2, y0 + 76), lab, font=lf, fill="#f5c518")
    d = ImageDraw.Draw(img)

    # trend tracker card — sparkline of real polls
    ty0 = y0 + ch + 12
    d.rounded_rectangle([x0, ty0, x1, y1], 18, fill="white",
                        outline="#1e3fae", width=3)
    d.text((x0 + 16, ty0 + 10), "MN SENATE TREND", font=font(FB, 19),
           fill=INK)
    sx0, sy0, sx1, sy1 = x0 + 16, ty0 + 46, x1 - 16, y1 - 54
    polls = MN_SENATE_POLLS
    vals = [v for _, a, b in polls for v in (a, b)]
    vmin, vmax = math.floor(min(vals) - 1), math.ceil(max(vals) + 1)
    n = len(polls)
    xs = [sx0 + i * (sx1 - sx0) / max(1, n - 1) for i in range(n)]

    def y_of(v):
        return sy1 - (v - vmin) / (vmax - vmin) * (sy1 - sy0)

    for col, idx in (("#2563eb", 1), ("#dc2626", 2)):
        pts = [(xs[i], y_of(p[idx])) for i, p in enumerate(polls)]
        d.line(pts, fill=col, width=3, joint="curve")
        for x, y in pts:
            d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=col)
    vf = font(FB, 16)
    dl = f"D {polls[-1][1]:.1f}%"
    d.text((x0 + 16, y1 - 42), dl, font=vf, fill="#2563eb")
    rl = f"R {polls[-1][2]:.1f}%"
    d.text((x1 - 16 - d.textlength(rl, font=vf), y1 - 42), rl, font=vf,
           fill="#dc2626")
    ff = font(FR, 12)
    fw = d.textlength(MN_SENATE_FOOTER, font=ff)
    d.text(((x0 + x1) / 2 - fw / 2, y1 - 22), MN_SENATE_FOOTER, font=ff,
           fill=GRAY)
    return img




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


def _pol_panel(img):
    """The political rail section: Brian's Navy service in the
    shared panel grammar — header + gold rule, the carrier
    (light steel on the black panel), CVN-73, a hairline, then
    the rating badges as medallions (enlisted-silver propeller
    = MMN; the trefoil = the nuke)."""
    y0 = _panel_frame(img, "#1e3fae")
    d = ImageDraw.Draw(img)
    _panel_header(d, y0, "U.S. NAVY")
    ship = carrier_silhouette(width=196, color="#7d94c4")
    img.paste(ship, (RAIL_W // 2 - 98, y0 + 64), ship)
    d = ImageDraw.Draw(img)
    cx_text(d, RAIL_W // 2, y0 + 162, "CVN-73", font(FB, 24),
            GOLD_TXT)
    cx_text(d, RAIL_W // 2, y0 + 196, "USS GEORGE WASHINGTON",
            font(FB, 11), RAIL_DIM, tracking=1)
    d.line([(56, y0 + 226), (196, y0 + 226)],
           fill=(70, 74, 90, 255), width=2)
    cx_text(d, RAIL_W // 2, y0 + 242, "THE RATING", font(FB, 11),
            RAIL_DIM, tracking=3)
    _medallion(img, 56, y0 + 266, propeller(40), "#c7cedb")
    _medallion(img, 196, y0 + 266, trefoil(40), "#ffd800")
    d = ImageDraw.Draw(img)
    cx_text(d, 56, y0 + 266 + 64, "MMN", font(FB, 11), "#ffffff",
            tracking=1)
    cx_text(d, 196, y0 + 266 + 64, "NUKE", font(FB, 11), "#ffffff",
            tracking=1)
    cx_text(d, RAIL_W // 2, y0 + 352, "MACHINIST'S MATE, NUCLEAR",
            font(FB, 10), RAIL_DIM, tracking=1)


def render_political_meme(content, draw_content, photo_path=None,
                          out_path="meme.png", brand=None,
                          headline_size=None, post_date=None,
                          election_day="2026-11-03", countdown=True):
    """Render a political meme on the crossover chassis.

    The capsule (framed card) interior is the caller's: the
    draw_content callback paints it, and in election season the
    countdown inset rail narrows it (the inset retires itself
    after election day, as before). headline_size is a starting
    point — the format's fitting loop still caps the headline
    layer to the shared box (width <= 814, height <= 120) so
    the chassis stack always lands on the canvas.
    """
    b = brand or POL_BRAND
    img = background()
    img = ai_backdrop(img)  # faint neural texture — more AI visuals
    img = political_backdrop(img)  # 3D stars + fireworks, subtle
    img = cherenkov_glow(img)  # reactor-blue glow, headline zone
    img = political_stripes(img)  # wavy red stripes, left
    img = img.convert("RGBA")
    d = ImageDraw.Draw(img)

    _rail(img, photo_path or PHOTO, HEADLINE_COLORS, "#6ea8ff",
          (70, 150, 255), _pol_panel, "#4d9fff")

    # kicker: a real pill now, anchors inside as its marks
    _kicker(img, content["kicker"], HEADLINE_COLORS, 120, NAVY,
            anchor(34), anchor(34))

    # headline: patriotic gradient + the shared 3D treatment
    cy = _headline(img, content["headline"], HEADLINE_COLORS,
                   start=headline_size or 96)

    # THE CAPSULE — the caller's content is the interior
    x0, x1 = _framed(img, cy, HEADLINE_COLORS, "white", INK)
    ix0, iy0, ix1, iy1 = x0 + 20, cy + 26, x1 - 20, cy + 392
    d = ImageDraw.Draw(img)
    content_box = (ix0, iy0, ix1, iy1)
    if countdown and _days_until(post_date, election_day) >= 0:
        rx0 = ix1 - 300
        election_inset(img, d, (rx0, iy0, ix1, iy1), post_date)
        d = ImageDraw.Draw(img)
        content_box = (ix0, iy0, rx0 - 16, iy1)
    if draw_content:
        draw_content(img, d, content_box)
    _garnet(img, cy, x0, x1, content["punchline"])

    # connect card + counter strip
    T = cy + 444 + 26
    ask, sub = _ask_parts(content)
    _connect(img, T,
             card_fill="white", card_outline="#1e3fae",
             strip_colors=HEADLINE_COLORS,
             ask=ask, sub=sub, ask_fill=INK, sub_fill=GRAY,
             chip_fill="white", chip_outline="#a0aac0",
             chip_ink=INK,
             band_stops=("#2c4a7c", "#0a1f44", "#060f24"),
             band_outline="#2b7fff",
             band_line=POLITICAL_TAGLINE,
             hashtag=b.get("hashtag"),
             chip_stops=("#a8c8ff", "#2b7fff", "#1e3fae"),
             tag_ink=(8, 24, 54))
    _counter(img, T, HEADLINE_COLORS)

    img.convert("RGB").save(out_path)
    return out_path
