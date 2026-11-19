#!/usr/bin/env python3
"""Seasonal capsule themes for the SuccessBrian crossover format.

Brian's ruling (2026-11-18 23:41 CST): "starting soon we need to
have some thanksgiving themed content capsules -- then later
christmas themed ones, then 2027 themed ones, then valentines
day for early feb."

The crossover format's main content capsule is a variable
container: one frame, many interior layouts (the original
comparative-card format, charts, Facebook-type image+text posts,
relayed posts with Brian's thoughts beside them, and more). A
capsule THEME dresses those interiors. Themes are switchable
modules: a driver renders with a theme on or off per post, and
the rail, kicker pill, connect card, signature band and counter
never wear the season -- only the capsule interior does.

THE LIBRARY -- five commissioned families (all GO):

  Family 1 -- SEASONAL HOLIDAY SETS, in Brian's sequence:
      Thanksgiving (built first in this pass; Thanksgiving 2026
      is Thu Nov 26) -> Christmas -> 2027 -> Valentine's Day
      (for early February).
  Family 2 -- THE FOUR SEASONS as standing sets (Brian,
      2026-11-18 23:42 CST: "fall/spring/winter/summer too."):
      Fall -> Winter -> Spring -> Summer, built in their turn.
  Family 3 -- OTHER HOLIDAYS (Brian, 2026-11-18 23:42 CST:
      "maybe themes related to other holidays and current
      events" -- CORRECTED 23:43 CST: "these are not maybe --
      they are go go go."): COMMISSIONED. The wider holiday
      calendar beyond the named sets, built in calendar order
      on the pattern this module sets.
  Family 4 -- CURRENT EVENTS (same ruling, same correction):
      COMMISSIONED as a standing rapid-response pattern --
      designed and ready to fire on the day an event happens,
      not a pre-built set.
  Family 5 -- BLOG ARTICLE PROMOTION (Brian, 2026-11-18
      23:44 CST: "we have a 5th one, right? one that just
      promotes blog articles?"): COMMISSIONED. Evergreen
      capsules whose job is featuring and promoting a blog
      article; not seasonal.

THIS PASS BUILDS THANKSGIVING ONLY. The later sets and
families are recorded here as the plan and are built in their
turn -- no other season is implemented in this file yet.

THANKSGIVING TREATMENT: a harvest palette (deep amber,
cranberry -- kin to the format's garnet -- warm gold, sage,
cream, bark) and drawn motifs in the desk's supersampled
idiom (the five dishes below, dressed with leaf, pumpkin
and wheat -- no scraped clip-art), a seasonal header strip
for the capsule, and type dressing that follows the
format's case map: header and card labels ALL CAPS,
display words ALL CAPS on cards, quotes and notes in
sentence case.

THANKSGIVING IS THREE STRANDS (Brian's completion,
2026-11-18 23:50 CST: "well, it has gratitude,
thankfulness to GOD, and food !!"), completing his
23:49 CST ruling ("thanksgiving has TURKEY, pumpkin
pie -- cranberry, potatoes, stuffing"):
  1. FOOD -- the five dishes lead the original-card
     capsule, each drawn and named: TURKEY, PUMPKIN PIE,
     CRANBERRY, POTATOES, STUFFING -- plus a THANKSGIVING
     DINNER title card in the sixth slot.
  2. GRATITUDE -- the THANKFUL FOR register rides every
     card, and the quote capsule keeps its gratitude
     quote.
  3. THANKFULNESS TO GOD -- plain words, in Brian's own
     register (his public identity line carries FAITH):
     the quote capsule's subline thanks God for the
     table, and the title card's note does the same.
     Plain-spoken, never preachy, never denominational.
All three strands land in one look across the two proof
capsules: the grid is the table, the quote is the thanks.
"""

import math

import meme_template as mt
from PIL import Image, ImageDraw, ImageFilter

FB, FR, font = mt.FB, mt.FR, mt.font

# ------------------------------------------------------------------
# The documented plan (see module docstring for Brian's words).
# ------------------------------------------------------------------
LIBRARY_FAMILIES = (
    ("seasonal_holiday_sets", "commissioned",
     ("thanksgiving", "christmas", "new_year_2027", "valentines_day")),
    ("four_seasons", "commissioned",
     ("fall", "winter", "spring", "summer")),
    ("other_holidays", "commissioned",
     "the wider holiday calendar, built in calendar order"),
    ("current_events", "commissioned",
     "standing rapid-response pattern, ready to fire on the day"),
    ("blog_article_promotion", "commissioned",
     "evergreen capsules that feature and promote a blog article"),
)

SEASONAL_SEQUENCE = (
    "thanksgiving", "christmas", "new_year_2027", "valentines_day",
    "fall", "winter", "spring", "summer",
)

THANKSGIVING = {
    "name": "thanksgiving",
    "label": "THANKSGIVING",
    "amber": "#d9822b",
    "deep_amber": "#9a5410",
    "cranberry": "#a31621",
    "garnet": "#7e2e3f",
    "gold": "#d9a521",
    "sage": "#7d8c5c",
    "cream": "#fff3d6",
    "parchment": "#f7e3b8",
    "bark": "#2a1a12",
    "ink": "#2b1a10",
}

# Sample proof content -- season-true, in Brian's voice
# register, carrying the three strands: the food leads,
# gratitude rides every card's THANKFUL FOR tag, and the
# thanks to God is said in plain words. No promotions, no
# product claims. Drivers may pass their own content; these
# defaults exist so a proof render always has honest
# sample content.
SAMPLE_QUOTE_LINES = (
    "Gratitude turns",
    "ordinary days",
    "into blessings.",
)
SAMPLE_QUOTE_SUBLINE = \
    "Thank God for this table, this food, and the people around it."

THANKSGIVING_CARDS = (
    {"tag": "THANKFUL FOR", "title": "TURKEY",
     "note": "golden, carved, and gone", "frac": 0.95,
     "color": THANKSGIVING["deep_amber"], "glyph": "turkey"},
    {"tag": "THANKFUL FOR", "title": "PUMPKIN PIE",
     "note": "save room for a slice", "frac": 0.9,
     "color": THANKSGIVING["amber"], "glyph": "pumpkin_pie"},
    {"tag": "THANKFUL FOR", "title": "CRANBERRY",
     "note": "tart, bright, and red", "frac": 0.82,
     "color": THANKSGIVING["cranberry"], "glyph": "cranberry"},
    {"tag": "THANKFUL FOR", "title": "POTATOES",
     "note": "mashed, with butter on top", "frac": 0.88,
     "color": THANKSGIVING["gold"], "glyph": "potatoes"},
    {"tag": "THANKFUL FOR", "title": "STUFFING",
     "note": "everyone wants seconds", "frac": 0.93,
     "color": THANKSGIVING["sage"], "glyph": "stuffing"},
    {"tag": "THANKFUL FOR", "title": "THANKSGIVING DINNER",
     "note": "and thanks to God for it all", "frac": 1.0,
     "color": THANKSGIVING["garnet"], "glyph": "wheat"},
)


# ------------------------------------------------------------------
# Small helpers (the desk's drawn idiom: supersample, then scale).
# ------------------------------------------------------------------
def _rgba(color, alpha=255):
    return mt._hex(color) + (alpha,)


def _mix(c0, c1, f):
    a, b = mt._hex(c0), mt._hex(c1)
    return tuple(int(p + (q - p) * f) for p, q in zip(a, b))


def _vgrad(size, stops):
    """Vertical gradient through (fraction, color) stops."""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for yy in range(h):
        f = yy / max(1, h - 1)
        for i in range(len(stops) - 1):
            f0, c0 = stops[i]
            f1, c1 = stops[i + 1]
            if f0 <= f <= f1:
                g = (f - f0) / max(1e-6, f1 - f0)
                col = _mix(c0, c1, g)
                break
        else:
            col = mt._hex(stops[-1][1])
        d.line([(0, yy), (w, yy)], fill=col + (255,))
    return img


def _hgrad(size, stops):
    w, h = size
    img = _vgrad((h, w), stops).rotate(-90, expand=True)
    return img.resize((w, h))


def _fit(text, size, maxw, bold=True, floor=10):
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    path = FB if bold else FR
    s = size
    while s > floor and d.textlength(text, font=font(path, s)) > maxw:
        s -= 1
    return font(path, s), s


def _centered(d, cx, y, text, fnt, fill, tracking=0):
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


def _clip(img, tile, box, radius=18):
    """Paste tile into box through a rounded-corner mask."""
    x0, y0 = box[0], box[1]
    mask = Image.new("L", tile.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, tile.width - 1, tile.height - 1], radius, fill=255)
    out = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    out.alpha_composite(tile)
    out.putalpha(mask)
    img.alpha_composite(out, (x0, y0))


# ------------------------------------------------------------------
# Drawn glyphs -- the five dishes of the Thanksgiving table
# (turkey, pumpkin pie, cranberry, potatoes, stuffing),
# dressed with leaf, pumpkin, wheat. 4x supersampled.
# ------------------------------------------------------------------
def glyph(kind, size, color=None):
    S = 4
    s = size * S
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    P = THANKSGIVING
    if kind == "leaf":
        col = _rgba(color or P["amber"])
        dark = _rgba("#5f3405")
        # pointed-oval leaf along the diagonal, built from two
        # sine-weighted edges; stem and centre vein on top
        x0, y0, x1, y1 = s * 0.20, s * 0.80, s * 0.80, s * 0.20
        dx, dy = x1 - x0, y1 - y0
        px, py = -dy, dx
        norm = max(1.0, math.hypot(px, py))
        px, py = px / norm, py / norm
        side_a, side_b = [], []
        for i in range(25):
            t = i / 24
            wdt = math.sin(math.pi * t) * s * 0.20
            cxp, cyp = x0 + dx * t, y0 + dy * t
            side_a.append((cxp + px * wdt, cyp + py * wdt))
            side_b.append((cxp - px * wdt, cyp - py * wdt))
        d.polygon(side_a + side_b[::-1], fill=col)
        d.line([(x0, y0), (x1, y1)], fill=dark, width=max(2, 2 * S))
        d.line([(x0, y0), (x0 - s * 0.07, y0 + s * 0.07)],
               fill=dark, width=max(2, 2 * S))
    elif kind == "pumpkin":
        body = _rgba(color or P["amber"])
        deep = _rgba(P["deep_amber"])
        cx, cy = s / 2, s * 0.58
        rx, ry = s * 0.34, s * 0.27
        for f, wfrac in ((1.0, 1.0), (0.72, 0.78), (0.42, 0.52)):
            shade = tuple(int(c * (0.82 + 0.18 * f)) for c in body[:3])
            d.ellipse([cx - rx * wfrac, cy - ry, cx + rx * wfrac,
                       cy + ry], fill=shade + (255,))
        for f in (-0.55, 0.0, 0.55):
            d.arc([cx - rx * (0.35 + abs(f) * 0.55), cy - ry,
                   cx + rx * (0.35 + abs(f) * 0.55), cy + ry],
                  start=90 - 55, end=90 + 55, fill=deep, width=2 * S)
            d.arc([cx - rx * (0.35 + abs(f) * 0.55), cy - ry,
                   cx + rx * (0.35 + abs(f) * 0.55), cy + ry],
                  start=270 - 55, end=270 + 55, fill=deep, width=2 * S)
        d.polygon([(cx - s * 0.045, cy - ry + s * 0.02),
                   (cx + s * 0.015, cy - ry - s * 0.13),
                   (cx + s * 0.075, cy - ry - s * 0.10),
                   (cx + s * 0.045, cy - ry + s * 0.03)],
                  fill=_rgba("#5b6e35"))
    elif kind == "wheat":
        col = _rgba(color or P["gold"])
        dark = _rgba("#8a6414")
        cx = s / 2
        top, bot = s * 0.10, s * 0.92
        d.line([(cx, bot), (cx, top)], fill=dark, width=3 * S)
        # grain kernels: small rotated ovals alternating up the stalk
        for i in range(6):
            t = i / 5
            gy = bot - (bot - top) * (0.30 + 0.62 * t)
            for sgn in (-1, 1):
                tile = Image.new("RGBA", (int(s * 0.30), int(s * 0.16)),
                                 (0, 0, 0, 0))
                td = ImageDraw.Draw(tile)
                td.ellipse([4, 4, tile.width - 4, tile.height - 4],
                           fill=col)
                tile = tile.rotate(38 * sgn, expand=True,
                                   resample=Image.BICUBIC)
                im.alpha_composite(
                    tile, (int(cx + sgn * s * 0.10 - tile.width / 2),
                           int(gy - tile.height / 2)))
        d = ImageDraw.Draw(im)
        d.line([(cx, bot), (cx, top)], fill=dark, width=2 * S)
    elif kind == "turkey":
        # a roast turkey: two drumsticks up behind a plump
        # browned body, the bird resting on a platter
        body_c = _rgba("#b06a24")
        deep = _rgba("#7e4410")
        lite = _rgba("#d18f3e")
        bone = _rgba("#f7ecd4")
        cx, cy = s * 0.5, s * 0.60
        # platter (behind everything)
        d.ellipse([s * 0.05, s * 0.76, s * 0.95, s * 0.94],
                  fill=_rgba(P["sage"]))
        d.ellipse([s * 0.10, s * 0.775, s * 0.90, s * 0.915],
                  fill=_rgba("#a7b184"))
        # drumsticks: bone out to a knobbed tip, meat bulb
        # at its base, peeking past the body's shoulders
        for sgn in (-1, 1):
            tx, ty = cx + sgn * s * 0.40, cy - s * 0.40
            mx, my = cx + sgn * s * 0.30, cy - s * 0.20
            d.line([(mx, my), (tx, ty)], fill=bone,
                   width=max(2, int(s * 0.05)))
            for dx in (-0.032, 0.032):
                d.ellipse([tx + dx * s - s * 0.042, ty - s * 0.042,
                           tx + dx * s + s * 0.042, ty + s * 0.042],
                          fill=bone)
            d.ellipse([mx - s * 0.105, my - s * 0.09,
                       mx + s * 0.105, my + s * 0.09], fill=deep)
            d.ellipse([mx - s * 0.088, my - s * 0.078,
                       mx + s * 0.088, my + s * 0.068], fill=body_c)
        # the body: layered ellipses for roasted shading
        rx, ry = s * 0.355, s * 0.265
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=deep)
        d.ellipse([cx - rx * 0.95, cy - ry * 0.96,
                   cx + rx * 0.95, cy + ry * 0.86], fill=body_c)
        d.ellipse([cx - rx * 0.58, cy - ry * 0.80,
                   cx + rx * 0.28, cy + ry * 0.05], fill=lite)
        # platter front rim over the body's foot
        d.pieslice([s * 0.05, s * 0.76, s * 0.95, s * 0.94],
                   0, 180, fill=_rgba(P["sage"]))
        d.arc([s * 0.05, s * 0.76, s * 0.95, s * 0.94],
              0, 180, fill=_rgba("#5f6b41"),
              width=max(2, int(s * 0.02)))
    elif kind == "pumpkin_pie":
        # a slice of pumpkin pie on a plate: crimped crust
        # along the back edge, a whipped-cream dollop on top
        crust = _rgba("#a8702a")
        crust_dk = _rgba("#7e4f16")
        fill0 = _rgba("#d97b29")
        fill1 = _rgba("#e8933f")
        cream = _rgba("#fff8ec")
        cream_sh = _rgba("#eedfc2")
        # plate
        d.ellipse([s * 0.13, s * 0.815, s * 0.87, s * 0.915],
                  fill=_rgba("#e9dcbc"))
        d.ellipse([s * 0.17, s * 0.82, s * 0.83, s * 0.895],
                  fill=_rgba("#f7eeda"))
        # crust wedge, slightly proud of the filling
        d.polygon([(s * 0.14, s * 0.30), (s * 0.86, s * 0.30),
                   (s * 0.50, s * 0.86)], fill=crust)
        # filling, with a lit inner wedge
        d.polygon([(s * 0.20, s * 0.38), (s * 0.80, s * 0.38),
                   (s * 0.50, s * 0.80)], fill=fill0)
        d.polygon([(s * 0.26, s * 0.42), (s * 0.74, s * 0.42),
                   (s * 0.50, s * 0.72)], fill=fill1)
        # crimped crust rim along the back edge
        d.rounded_rectangle([s * 0.12, s * 0.24, s * 0.88, s * 0.38],
                            int(s * 0.05), fill=crust_dk)
        d.rounded_rectangle([s * 0.14, s * 0.25, s * 0.86, s * 0.35],
                            int(s * 0.04), fill=crust)
        # the dollop: lobes on a shaded base, peak on top
        for base, col in ((0.016, cream_sh), (0.0, cream)):
            for (dx, dy, r) in ((-0.10, 0.02, 0.085),
                                (0.10, 0.02, 0.085),
                                (0.0, -0.015, 0.105),
                                (0.0, -0.085, 0.055)):
                ccx, ccy = s * (0.5 + dx), s * (0.30 + dy + base)
                d.ellipse([ccx - r * s, ccy - r * s,
                           ccx + r * s, ccy + r * s], fill=col)
    elif kind == "cranberry":
        # a bowl of cranberry sauce, whole berries heaped
        # and glistening on top of the sauce's surface
        red = _rgba(P["cranberry"])
        red_lt = _rgba("#c92a38")
        berry = _rgba("#b81d2c")
        bowl = _rgba(P["cream"])
        bowl_dk = _rgba("#d9c491")
        # bowl foot, then the bowl's shaded under-edge
        d.rounded_rectangle([s * 0.42, s * 0.87, s * 0.58, s * 0.95],
                            int(s * 0.02), fill=bowl_dk)
        d.pieslice([s * 0.08, s * 0.06, s * 0.92, s * 0.94],
                   0, 180, fill=bowl_dk)
        d.pieslice([s * 0.08, s * 0.02, s * 0.92, s * 0.90],
                   0, 180, fill=bowl)
        # sauce surface (its rim sits at y .46)
        d.ellipse([s * 0.10, s * 0.35, s * 0.90, s * 0.57], fill=red)
        d.ellipse([s * 0.16, s * 0.355, s * 0.84, s * 0.50],
                  fill=red_lt)
        # the berries, each with a lit speck
        for (dx, dy, r) in ((-0.20, -0.02, 0.085),
                            (-0.07, -0.075, 0.095),
                            (0.07, -0.075, 0.095),
                            (0.20, -0.02, 0.085),
                            (0.0, -0.01, 0.09),
                            (-0.13, 0.015, 0.08),
                            (0.13, 0.015, 0.08)):
            ccx, ccy = s * (0.5 + dx), s * (0.36 + dy)
            d.ellipse([ccx - r * s, ccy - r * s,
                       ccx + r * s, ccy + r * s], fill=berry)
            d.ellipse([ccx - r * s * 0.45, ccy - r * s * 0.55,
                       ccx - r * s * 0.05, ccy - r * s * 0.15],
                      fill=_rgba("#e88a94"))
    elif kind == "potatoes":
        # a bowl of mashed potatoes: a creamy cloud of a
        # mound with a pat of butter melting on top
        bowl = _rgba(P["garnet"])
        bowl_dk = _rgba("#5e2432")
        mound = _rgba("#fff3d6")
        mound_sh = _rgba("#e0c48c")
        butter = _rgba("#f2c230")
        # bowl: shaded under-edge, body, gold rim (rim at y .46)
        d.rounded_rectangle([s * 0.42, s * 0.87, s * 0.58, s * 0.95],
                            int(s * 0.02), fill=bowl_dk)
        d.pieslice([s * 0.08, s * 0.06, s * 0.92, s * 0.94],
                   0, 180, fill=bowl_dk)
        d.pieslice([s * 0.08, s * 0.02, s * 0.92, s * 0.90],
                   0, 180, fill=bowl)
        # the mound: shaded lobes under lit ones
        lobes = ((0.30, 0.40, 0.15), (0.50, 0.33, 0.175),
                 (0.70, 0.40, 0.15), (0.40, 0.28, 0.12),
                 (0.60, 0.28, 0.12), (0.50, 0.43, 0.125))
        for (lx, ly, r) in lobes:
            d.ellipse([s * (lx - r), s * (ly - r + 0.025),
                       s * (lx + r), s * (ly + r + 0.025)],
                      fill=mound_sh)
        for (lx, ly, r) in lobes:
            d.ellipse([s * (lx - r), s * (ly - r),
                       s * (lx + r), s * (ly + r)], fill=mound)
        # the rim's front arc, tracing the bowl's mouth in
        # front of the mound's foot
        d.arc([s * 0.08, s * 0.35, s * 0.92, s * 0.57],
              0, 180, fill=_rgba(P["gold"]),
              width=max(2, int(s * 0.025)))
        # the butter pat, tilted, on the mound's peak
        bcx, bcy, bd = s * 0.5, s * 0.185, s * 0.075
        ca, sa = math.cos(0.35), math.sin(0.35)
        pts = []
        for (px, py) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            pts.append((bcx + (px * ca - py * sa) * bd,
                        bcy + (px * sa + py * ca) * bd))
        d.polygon(pts, fill=butter, outline=_rgba("#c9930a"))
    elif kind == "stuffing":
        # a baking dish heaped with stuffing: a crumbly
        # golden-brown mound, flecked with herb, in a
        # cream dish with a cranberry stripe
        dish = _rgba(P["cream"])
        dish_dk = _rgba("#d9c491")
        crumbs = ("#c98d3f", "#a96f27", "#e0aa54", "#b57e2f")
        # dish body, then its rim
        d.polygon([(s * 0.08, s * 0.50), (s * 0.92, s * 0.50),
                   (s * 0.86, s * 0.88), (s * 0.14, s * 0.88)],
                  fill=dish)
        d.polygon([(s * 0.095, s * 0.66), (s * 0.905, s * 0.66),
                   (s * 0.885, s * 0.76), (s * 0.115, s * 0.76)],
                  fill=_rgba(P["cranberry"]))
        d.ellipse([s * 0.06, s * 0.40, s * 0.94, s * 0.62],
                  fill=dish_dk)
        d.ellipse([s * 0.10, s * 0.425, s * 0.90, s * 0.595],
                  fill=_rgba("#c9b183"))
        # the mound: overlapping crumb circles along an arc,
        # roughed up with smaller crumbs in the gaps so it
        # reads crumbly, not like a row of rolls
        mound_pts = ((0.20, 0.44, 0.10), (0.32, 0.36, 0.115),
                     (0.47, 0.315, 0.125), (0.62, 0.36, 0.115),
                     (0.76, 0.44, 0.10), (0.38, 0.44, 0.10),
                     (0.58, 0.44, 0.10), (0.26, 0.40, 0.065),
                     (0.40, 0.315, 0.07), (0.55, 0.325, 0.06),
                     (0.69, 0.405, 0.065), (0.47, 0.42, 0.07))
        for i, (lx, ly, r) in enumerate(mound_pts):
            d.ellipse([s * (lx - r), s * (ly - r),
                       s * (lx + r), s * (ly + r)],
                      fill=_rgba(crumbs[i % len(crumbs)]))
        # flecks: dark crumb and sage herb specks
        for i, (fx, fy) in enumerate(((0.30, 0.38), (0.44, 0.33),
                                      (0.55, 0.40), (0.66, 0.35),
                                      (0.36, 0.46), (0.60, 0.46),
                                      (0.50, 0.29), (0.24, 0.45),
                                      (0.71, 0.44), (0.42, 0.40))):
            col = _rgba("#6d4a15") if i % 2 == 0 else _rgba(P["sage"])
            r = s * 0.017
            d.ellipse([s * fx - r, s * fy - r, s * fx + r,
                       s * fy + r], fill=col)
    else:
        raise ValueError(f"unknown glyph: {kind}")
    return im.resize((size, size), Image.LANCZOS)


# ------------------------------------------------------------------
# Seasonal surfaces.
# ------------------------------------------------------------------
def header_strip(width, height=40, label=None, skin="dark"):
    """The capsule's seasonal header strip: a cranberry ->
    amber -> gold band with a leaf and wheat glyph riding it
    and the season label in tracked ALL CAPS (the format's
    in-card label case)."""
    P = THANKSGIVING
    label = label or P["label"]
    strip = _hgrad((width, height),
                   ((0.0, P["garnet"]), (0.45, P["cranberry"]),
                    (0.78, P["amber"]), (1.0, P["gold"])))
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, width - 1, height - 1], height // 2, fill=255)
    strip.putalpha(mask)
    d = ImageDraw.Draw(strip)
    _centered(d, width / 2, (height - 15) // 2, label,
              font(FB, 15), _rgba(P["cream"]), tracking=3)
    # glyphs ride in the strip's own palette, contrasted
    # against the ground under them: cranberry leaf on the
    # gold end, gold wheat on the cranberry end
    g = glyph("leaf", 26, P["garnet"])
    strip.alpha_composite(g, (14, (height - 26) // 2))
    g = glyph("wheat", 26, P["gold"])
    strip.alpha_composite(g, (width - 14 - 26, (height - 26) // 2))
    return strip


def seasonal_background(width, height, skin="dark"):
    """The capsule interior ground in the season's palette,
    with soft harvest glows in the corners. `skin` follows the
    host template: 'dark' for the crypto desk, 'light' for the
    AI desk."""
    P = THANKSGIVING
    if skin == "light":
        tile = _vgrad((width, height),
                      ((0.0, "#fff8e7"), (0.55, P["cream"]),
                       (1.0, P["parchment"])))
    else:
        tile = _vgrad((width, height),
                      ((0.0, "#332216"), (0.55, "#241811"),
                       (1.0, "#180f0a")))
    for (gx, gy, col, alpha) in (
            (-90, -90, P["amber"], 52), (width - 130, -100,
                                         P["cranberry"], 44),
            (-100, height - 140, P["sage"], 30),
            (width - 120, height - 130, P["gold"], 36)):
        # mt._radial_glow fades to fully transparent at its
        # edges -- no seam where the glow tile meets the ground
        glow = mt._radial_glow(240, 240, mt._hex(col), alpha)
        tile.alpha_composite(glow, (gx, gy))
    return tile


def draw_quote_capsule(img, box, skin="dark", lines=None,
                       subline=None, label=None):
    """Quote-card interior: seasonal ground, header strip, a
    big gratitude quote in sentence case (the format's quoted-
    sentence case), a drawn glyph row, and a sentence-case
    subline. Fills `box` (x0, y0, x1, y1) inside the frame."""
    P = THANKSGIVING
    lines = tuple(lines) if lines else SAMPLE_QUOTE_LINES
    subline = subline if subline is not None else SAMPLE_QUOTE_SUBLINE
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    tile = seasonal_background(w, h, skin)
    d = ImageDraw.Draw(tile)
    strip = header_strip(w - 28, 40, label=label, skin=skin)
    tile.alpha_composite(strip, (14, 14))
    ink = P["ink"] if skin == "light" else P["cream"]
    muted = "#7a5a34" if skin == "light" else "#d8b98a"
    # the quote -- largest size at which every line fits
    size = 48
    while size > 20:
        f = font(FB, size)
        if all(d.textlength(t, font=f) <= w - 110 for t in lines):
            break
        size -= 1
    qf = font(FB, size)
    total_h = len(lines) * (size + 9) - 9
    qy = 78 + max(0, (h - 210 - total_h) // 2)
    for t in lines:
        _centered(d, w / 2, qy, t, qf, _rgba(ink) if isinstance(ink, tuple)
                  else ink)
        qy += size + 9
    d.line([(w / 2 - 90, h - 108), (w / 2 + 90, h - 108)],
           fill=_rgba(P["gold"]), width=2)
    if subline:
        sf, _ = _fit(subline, 17, w - 120, bold=False, floor=12)
        _centered(d, w / 2, h - 92, subline, sf,
                  _rgba(muted) if isinstance(muted, tuple) else muted)
    # the glyph row: the table itself, drawn and centred --
    # cranberry, potatoes, the turkey in the middle,
    # stuffing, pumpkin pie, all bottom-aligned
    kinds = ("cranberry", "potatoes", "turkey", "stuffing",
             "pumpkin_pie")
    sizes = (36, 40, 54, 40, 36)
    total_w = sum(sizes) + 12 * (len(sizes) - 1)
    gx = (w - total_w) // 2
    for kind, gs in zip(kinds, sizes):
        g = glyph(kind, gs)
        tile.alpha_composite(g, (gx, h - 12 - gs))
        gx += gs + 12
    _clip(img, tile, box, radius=18)
    return box


def draw_original_capsule(img, box, skin="dark", items=None,
                          label=None):
    """Original-card interior: the format's comparative-card
    grid (3 x 2) wearing the season -- seasonal ground and
    header strip, each card topped with its harvest accent,
    a drawn glyph riding the card, card labels and titles in
    ALL CAPS and notes in sentence case (the case map)."""
    P = THANKSGIVING
    items = list(items) if items else list(THANKSGIVING_CARDS)
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    tile = seasonal_background(w, h, skin)
    d = ImageDraw.Draw(tile)
    strip = header_strip(w - 28, 40, label=label, skin=skin)
    tile.alpha_composite(strip, (14, 14))
    gx0, gy0 = 16, 66
    gw, gh = w - 32, h - gy0 - 16
    gap = 8
    cw = (gw - 2 * gap) // 3
    ch = (gh - gap) // 2
    card_fill = (255, 250, 238, 255) if skin == "light" else (35, 29, 24, 255)
    title_ink = P["ink"] if skin == "light" else P["cream"]
    note_ink = "#7a5a34" if skin == "light" else "#cdb894"
    tag_ink = "#8a6a3a" if skin == "light" else "#a98f66"
    for i, item in enumerate(items[:6]):
        col, row = i % 3, i // 3
        x = gx0 + col * (cw + gap)
        y = gy0 + row * (ch + gap)
        ccx = x + cw / 2
        d.rounded_rectangle([x + 4, y + 6, x + cw + 4, y + ch + 6], 20,
                            fill=(0, 0, 0, 70))
        d.rounded_rectangle([x, y, x + cw, y + ch], 20,
                            fill=card_fill,
                            outline=_rgba(item["color"]), width=2)
        bar = _hgrad((cw - 16, 7),
                     ((0.0, item["color"]), (1.0, P["gold"])))
        bmask = Image.new("L", (cw - 16, 7), 0)
        ImageDraw.Draw(bmask).rounded_rectangle([0, 0, cw - 17, 6], 3,
                                                fill=255)
        bar.putalpha(bmask)
        tile.alpha_composite(bar, (x + 8, y + 7))
        g = glyph(item.get("glyph", "leaf"), 30, item["color"])
        tile.alpha_composite(g, (x + cw - 42, y + 16))
        d = ImageDraw.Draw(tile)
        _centered(d, ccx, y + 20, item["tag"], font(FB, 11),
                  _rgba(tag_ink) if isinstance(tag_ink, tuple) else tag_ink,
                  tracking=2)
        tf, _ = _fit(item["title"], 25, cw - 58)
        _centered(d, ccx, y + 40, item["title"], tf,
                  _rgba(title_ink) if isinstance(title_ink, tuple)
                  else title_ink)
        nf, _ = _fit(item["note"], 14, cw - 20, bold=False, floor=11)
        _centered(d, ccx, y + 76, item["note"], nf,
                  _rgba(note_ink) if isinstance(note_ink, tuple)
                  else note_ink)
        bx, bw, by, bh = x + 28, cw - 56, y + ch - 24, 12
        d.rounded_rectangle([bx, by, bx + bw, by + bh], 6,
                            fill=(214, 196, 160, 255) if skin == "light"
                            else (58, 46, 34, 255))
        frac = max(0.0, min(1.0, float(item.get("frac", 0.8))))
        if frac > 0:
            fb = _hgrad((max(2, int(bw * frac)), bh),
                        ((0.0, item["color"]), (1.0, P["gold"])))
            fm = Image.new("L", fb.size, 0)
            ImageDraw.Draw(fm).rounded_rectangle(
                [0, 0, fb.width - 1, fb.height - 1], 6, fill=255)
            fb.putalpha(fm)
            tile.alpha_composite(fb, (bx, by))
            d = ImageDraw.Draw(tile)
    _clip(img, tile, box, radius=18)
    return box
