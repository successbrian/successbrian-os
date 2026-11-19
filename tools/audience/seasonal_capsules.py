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
idiom (leaf, pumpkin, wheat -- no scraped clip-art), a
seasonal header strip for the capsule, and type dressing
that follows the format's case map: header and card labels
ALL CAPS, display words ALL CAPS on cards, quotes and notes
in sentence case.
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

# Sample proof content -- season-true, generic gratitude content
# in Brian's voice register. No promotions, no product claims.
# Drivers may pass their own content; these defaults exist so a
# proof render always has honest sample content.
SAMPLE_QUOTE_LINES = (
    "Gratitude turns",
    "ordinary days",
    "into blessings.",
)
SAMPLE_QUOTE_SUBLINE = "Thankful for family, friends, and the road ahead."

THANKSGIVING_CARDS = (
    {"tag": "THANKFUL FOR", "title": "FAMILY",
     "note": "the people at the table", "frac": 0.92,
     "color": THANKSGIVING["cranberry"], "glyph": "pumpkin"},
    {"tag": "THANKFUL FOR", "title": "FRIENDS",
     "note": "the ones who show up", "frac": 0.86,
     "color": THANKSGIVING["amber"], "glyph": "leaf"},
    {"tag": "THANKFUL FOR", "title": "HEALTH",
     "note": "strength for the season", "frac": 0.78,
     "color": THANKSGIVING["sage"], "glyph": "leaf"},
    {"tag": "THANKFUL FOR", "title": "WORK",
     "note": "the chance to build", "frac": 0.82,
     "color": THANKSGIVING["gold"], "glyph": "wheat"},
    {"tag": "THANKFUL FOR", "title": "COMMUNITY",
     "note": "neighbors who care", "frac": 0.88,
     "color": THANKSGIVING["garnet"], "glyph": "wheat"},
    {"tag": "THANKFUL FOR", "title": "TOMORROW",
     "note": "another day to begin", "frac": 0.95,
     "color": THANKSGIVING["deep_amber"], "glyph": "pumpkin"},
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
# Drawn harvest glyphs -- leaf, pumpkin, wheat. 4x supersampled.
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
    # the glyph row: leaf - pumpkin - wheat, drawn, centred
    kinds = ("leaf", "pumpkin", "wheat")
    sizes = (40, 52, 40)
    total_w = sum(sizes) + 28
    gx = (w - total_w) // 2
    for kind, gs in zip(kinds, sizes):
        g = glyph(kind, gs)
        tile.alpha_composite(g, (gx, h - 66 + (52 - gs) // 2))
        gx += gs + 14
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
