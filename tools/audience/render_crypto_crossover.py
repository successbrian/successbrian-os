#!/usr/bin/env python3
"""Crypto desk in the CROSSOVER format — Brian's ruling 2026-11-18
21:49 CST: "make this look more like the one we developed today."

The format is the AI crossover meme of 2026-11-18 (full-height left
rail + kicker pill + gradient-3D headline + framed central card with
the garnet punchline joined inside it + the unified connect card),
wearing the crypto desk's identity: near-black charcoal, candlestick
texture, Kaspa teal / Cardano blue / BNB gold.

Machinery: everything renders through the existing desk machinery —
meme_template.py primitives (photo_card, spencer_badge, holo_pill,
grad_rounded, icons, _gbar) and crypto_template.py (dark backdrop,
headline_3d_dark, candle glyphs, the branded-six DEFAULT_CONTENT).
The rail/rack block is carried verbatim from render_crossover_graph.py
(the crossover format master) — the desk pattern until the Format
Library extraction (FORMAT_LIBRARY_SPEC.md Module 2, staged in the
PM queue) lands it in the library. NO new layout was created.

Content (the crypto desk as rebranded, commit 25e4179): headline
"BUY FEAR. SELL GREED.", the six coins as comparative cards, the
skeptics strip, punchline "SUPPORT IS WHERE YOU BUY. RESISTANCE IS
WHERE YOU SELL.", the curiosity line as the connect card's ask,
FOLLOW #SuccessBrianCrypto. The AI piece's DAY/Huang counter strip
is AI-meme content and is NOT carried over.

Open items flagged for Brian (not decided here):
- D1 (rail brand line per-theme vs global) is UNRULED. The rail's
  two-line brand slot carries the crypto desk's own tagline, split
  at its bullet: "BUY SUPPORT • SELL RESISTANCE" / "HOLD LONG".
- The signature plaque's second line: the AI version reads "AI
  INSIGHTS THAT SAVE YOU REAL MONEY". The crypto theme's materials
  supply no insights-parallel line, so the plaque carries the desk's
  own line in full — "BUY SUPPORT • SELL RESISTANCE • HOLD LONG" —
  agent-placed, awaiting Brian's ruling on the wording.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meme_template as mt
import crypto_template as ct
from PIL import Image, ImageDraw, ImageFilter

mt.SPENCER_PHOTO = ("/home/successbrian/successbrian-os/tools/audience/"
                    "assets/spencer-badge.webp")
PHOTO = ("/home/successbrian/successbrian-os/tools/audience/"
         "assets/brian-gina.jpg")
OUT = ("/home/successbrian/successbrian-os/tools/audience/out/"
       "crypto-crossover-six-coins-2026-11-18.png")

W = H = 1080
RAIL_W = 252
CX = (RAIL_W + W) // 2 + 14  # content-zone center
INK_D = ct.INK_D
DIM_D = ct.DIM_D
GOLD = "#d9a521"
HL = tuple(ct.HL_COLORS)     # Kaspa teal -> Cardano blue -> BNB gold

font, FB, FR = mt.font, mt.FB, mt.FR


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


def _fit(text, size, maxw, floor=12):
    """Largest FB size (<= size) whose plain text width fits maxw."""
    _d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    s = size
    while s > floor and _d.textlength(text, font=font(FB, s)) > maxw:
        s -= 1
    return font(FB, s), s


def _vgrad(w, h, top, bot, radius):
    """Vertical two-stop gradient with rounded corners (from the
    crossover driver — gives flat bars shaded depth)."""
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


# ---------------- 3D rack (verbatim from render_crossover_graph.py,
# the crossover format master; Format Library Module 2 will extract
# it into the library — see the spec's staging table) ----------------
def draw_rack(base, x, y, w, units):
    """Brian's home-lab rack as an OPEN-FRAME rack, drawn on a 4x
    canvas and downscaled for real resolution. Front posts with
    cage-nut holes, bolted faceplates, uniform left-aligned work
    labels, one green light per unit. Alpha and Bravo are two
    GMKtec K11 mini PCs inside a custom 3D-printed enclosure labeled
    AI INFERENCE; a printed nameplate rides the top bar. The rack
    carries Brian's fleet only — Gamma is rented and is never on it."""
    S = 4  # supersample factor for the rack render
    gap = 3
    heights = [25 if k == "slim" else 46 if k == "pcs" else 32
               for _, _, k in units]
    top_bar, bot_bar = 16, 12
    h = top_bar + sum(heights) + gap * (len(units) - 1) + bot_bar
    dx, dy = 22, -18
    pad_l, pad_t = 34, 44
    cv = Image.new("RGBA", ((w + pad_l + 64) * S, (h + pad_t + 72) * S),
                   (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    X = (pad_l) * S          # rack front-left, hi-res px
    Y = (pad_t) * S          # rack front-top
    Wd = w * S
    Hd = h * S

    def R(a, b, c, e, r=0, **kw):
        d.rounded_rectangle([a, b, c, e], r, **kw)

    def screw(cx, cy, r=5):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(168, 186, 210, 255))
        d.ellipse([cx - r + 2, cy - r + 2, cx + r - 3, cy + r - 3],
                  fill=(210, 224, 244, 255))
        d.line([(cx - r + 2, cy), (cx + r - 2, cy)], fill=(90, 105, 130, 255), width=2)
        d.line([(cx, cy - r + 2), (cx, cy + r - 2)], fill=(90, 105, 130, 255), width=2)

    def led(cx, cy, col=(64, 255, 150), r=4):
        d.ellipse([cx - r * 3, cy - r * 3, cx + r * 3, cy + r * 3], fill=col + (46,))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,))
        d.ellipse([cx - 1, cy - 2, cx + 1, cy], fill=(235, 255, 244, 255))

    def vgrad(a, b, c, e, top, bot):
        steps = int(e - b)
        for i in range(steps):
            t = i / max(1, steps - 1)
            col = tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3))
            d.line([(a, b + i), (c, b + i)], fill=col + (255,))

    def label(tx, ty, text, size=13, fill=(255, 255, 255, 255)):
        f = font(FB, size * S)
        d.text((tx + 1, ty + 2), text, font=f, fill=(0, 0, 0, 110))
        d.text((tx, ty), text, font=f, fill=fill)

    d = ImageDraw.Draw(cv)

    DX, DY = dx * S, dy * S
    # top face + right side face (the frame's depth)
    d.polygon([(X, Y), (X + DX, Y + DY), (X + Wd + DX, Y + DY), (X + Wd, Y)],
              fill=(66, 80, 108, 255))
    d.line([(X, Y), (X + DX, Y + DY), (X + Wd + DX, Y + DY), (X + Wd, Y)],
           fill=(140, 165, 200, 255), width=2)
    d.polygon([(X + Wd, Y), (X + Wd + DX, Y + DY), (X + Wd + DX, Y + DY + Hd),
               (X + Wd, Y + Hd)], fill=(26, 34, 54, 255))
    for i in range(10):
        yy = Y + DY + 26 * S + i * (Hd - 40 * S) // 10
        d.line([(X + Wd + 6 * S, yy + 8 * S), (X + Wd + DX - 4 * S, yy)],
               fill=(80, 102, 138, 255), width=3)
    # dark cavity behind the units
    R(X + 11 * S, Y + 4 * S, X + Wd - 11 * S, Y + Hd - 4 * S, 6, fill=(8, 11, 18, 255))

    post_w = 13 * S
    uy = Y + top_bar * S
    for (name, spec, kind), uh1 in zip(units, heights):
        uh = uh1 * S
        ux0, ux1 = X + post_w, X + Wd - post_w
        # faceplate with a brushed vertical gradient
        vgrad(ux0, uy, ux1, uy + uh, (58, 74, 102), (33, 43, 64))
        d.line([(ux0, uy), (ux1, uy)], fill=(190, 210, 235, 90), width=2)
        d.line([(ux0, uy + uh - 2), (ux1, uy + uh - 2)], fill=(0, 0, 0, 130), width=2)
        mid_y = uy + uh // 2
        if kind == "slim":
            # network switch: dark face, 8 ports, link lights, LAN label
            vgrad(ux0, uy, ux1, uy + uh, (40, 52, 76), (22, 30, 46))
            for px in range(8):
                pxx = ux0 + 12 * S + px * 15 * S
                R(pxx, mid_y - 6 * S, pxx + 10 * S, mid_y + 4 * S, 2 * S,
                  fill=(14, 20, 32, 255), outline=(96, 116, 148, 255), width=2)
                d.ellipse([pxx + 3 * S, mid_y + 6 * S, pxx + 5 * S, mid_y + 8 * S],
                          fill=(64, 255, 150, 255))
                d.ellipse([pxx + 6 * S, mid_y + 6 * S, pxx + 8 * S, mid_y + 8 * S],
                          fill=(255, 190, 64, 255))
            tw = d.textlength(name, font=font(FB, 13 * S))
            label(ux1 - 14 * S - tw, mid_y - 9 * S, name)
        elif kind == "pcs":
            # 3D-printed enclosure (matte charcoal, visible print
            # layer lines) holding the two K11 mini PCs
            R(ux0 + 2 * S, uy + 2 * S, ux1 - 2 * S, uy + uh - 2 * S, 6 * S,
              fill=(36, 38, 44, 255))
            for ly2 in range(uy + 5 * S, uy + uh - 4 * S, 3 * S):
                d.line([(ux0 + 4 * S, ly2), (ux1 - 4 * S, ly2)], fill=(255, 255, 255, 14), width=1)
            # printed corner brackets in accent filament
            for bx2 in (ux0 + 2 * S, ux1 - 8 * S):
                R(bx2, uy + 2 * S, bx2 + 6 * S, uy + 9 * S, 2 * S, fill=(16, 132, 196, 255))
                R(bx2, uy + uh - 9 * S, bx2 + 6 * S, uy + uh - 2 * S, 2 * S, fill=(16, 132, 196, 255))
            bw2 = (ux1 - ux0 - 26 * S) // 2
            for i, nm in enumerate(("ALPHA", "BRAVO")):
                bx2 = ux0 + 8 * S + i * (bw2 + 10 * S)
                by2, bh2 = uy + 4 * S, uh - 16 * S
                # K11 front face: metal edge frame, glossy dark panel
                R(bx2, by2, bx2 + bw2, by2 + bh2, 5 * S, fill=(22, 24, 30, 255),
                  outline=(158, 168, 186, 255), width=3)
                R(bx2 + 3 * S, by2 + 3 * S, bx2 + bw2 - 3 * S, by2 + bh2 - 3 * S, 4 * S,
                  outline=(255, 255, 255, 30), width=1)
                # the K11's LED illumination strip across the upper face
                d.line([(bx2 + 6 * S, by2 + 6 * S), (bx2 + bw2 - 6 * S, by2 + 6 * S)],
                       fill=(96, 220, 255, 255), width=2)
                d.line([(bx2 + 6 * S, by2 + 8 * S), (bx2 + bw2 - 6 * S, by2 + 8 * S)],
                       fill=(96, 220, 255, 60), width=2)
                # micro badge with the machine's name, lower-left
                f6 = font(FB, 6 * S)
                d.text((bx2 + 6 * S, by2 + bh2 - 15 * S), nm, font=f6,
                       fill=(150, 162, 182, 255))
                # front ports row: power, audio, USB-A x2, USB4-C, OCuLink
                py = by2 + bh2 - 8 * S
                pcx = bx2 + 9 * S
                d.ellipse([pcx - 3 * S, py - 3 * S, pcx + 3 * S, py + 3 * S],
                          outline=(190, 200, 216, 255), width=2)
                d.ellipse([pcx - 1 * S, py - 1 * S, pcx + 1 * S, py + 1 * S],
                          fill=(64, 255, 150, 255))
                ax = pcx + 8 * S
                d.ellipse([ax - 2 * S, py - 2 * S, ax + 2 * S, py + 2 * S],
                          fill=(10, 12, 16, 255), outline=(140, 150, 168, 255), width=1)
                ux2 = ax + 7 * S
                for k in range(2):
                    R(ux2, py - 2 * S, ux2 + 7 * S, py + 2 * S, 1 * S,
                      fill=(28, 32, 42, 255), outline=(130, 140, 158, 255), width=1)
                    d.line([(ux2 + 1 * S, py), (ux2 + 6 * S, py)], fill=(90, 100, 118, 255), width=1)
                    ux2 += 10 * S
                R(ux2, py - 1 * S, ux2 + 6 * S, py + 2 * S, 1 * S,
                  fill=(28, 32, 42, 255), outline=(130, 140, 158, 255), width=1)
                ux2 += 9 * S
                R(ux2, py - 2 * S, ux2 + 8 * S, py + 2 * S, 1 * S,
                  fill=(28, 32, 42, 255), outline=(130, 140, 158, 255), width=1)
            # the enclosure's printed front lip carries the work label
            label(ux0 + 10 * S, uy + uh - 12 * S, name, size=10)
            led(ux1 - 12 * S, uy + uh - 7 * S, r=3)
        else:
            # a work unit: uniform left-aligned label, vent field, LED
            label(ux0 + 11 * S, mid_y - 9 * S, name)
            vx0 = ux0 + 23 * S + d.textlength(name, font=font(FB, 13 * S))
            for vx in range(6):
                for vy in range(2):
                    cxp = vx0 + vx * 8 * S
                    cyp = uy + 9 * S + vy * 9 * S
                    if cxp < ux1 - 34 * S:
                        d.ellipse([cxp, cyp, cxp + 3 * S, cyp + 3 * S], fill=(16, 22, 36, 160))
            led(ux1 - 12 * S, mid_y, r=4)
        # faceplate bolts, both ends
        screw(ux0 + 6 * S, mid_y, r=4)
        screw(ux1 - 6 * S, mid_y, r=4)
        uy += uh + gap * S

    # front posts with cage-nut holes, over the unit edges
    for px0 in (X, X + Wd - post_w):
        vgrad(px0, Y, px0 + post_w, Y + Hd, (74, 92, 124), (40, 52, 78))
        d.line([(px0, Y), (px0, Y + Hd)], fill=(170, 195, 225, 120), width=2)
        hy = Y + 10 * S
        while hy < Y + Hd - 8 * S:
            R(px0 + 4 * S, hy, px0 + 9 * S, hy + 5 * S, 1 * S, fill=(10, 14, 22, 255),
              outline=(150, 170, 200, 160), width=1)
            hy += 11 * S
    # top + bottom crossbars
    vgrad(X, Y, X + Wd, Y + top_bar * S, (84, 104, 138), (52, 66, 94))
    vgrad(X, Y + Hd - bot_bar * S, X + Wd, Y + Hd, (52, 66, 94), (34, 44, 66))
    d.rounded_rectangle([X, Y, X + Wd, Y + Hd], 8 * S, outline=(140, 165, 200, 255), width=3)
    # 3D-printed nameplate on the top bar, screwed on
    plate_w = 152 * S
    px0 = X + (Wd - plate_w) // 2
    R(px0, Y + 2 * S, px0 + plate_w, Y + top_bar * S - 2 * S, 3 * S,
      fill=(22, 96, 148, 255), outline=(120, 200, 245, 255), width=2)
    _psz = 10 * S
    while _psz > 6 * S and d.textlength("SUCCESSBRIAN ECOSYSTEM", font=font(FB, _psz)) > plate_w - 16 * S:
        _psz -= S
    f9 = font(FB, _psz)
    tw = d.textlength("SUCCESSBRIAN ECOSYSTEM", font=f9)
    d.text((px0 + (plate_w - tw) / 2, Y + (top_bar * S - _psz) // 2), "SUCCESSBRIAN ECOSYSTEM", font=f9,
           fill=(240, 250, 255, 255))
    screw(px0 + 6 * S, Y + top_bar * S // 2, r=3)
    screw(px0 + plate_w - 6 * S, Y + top_bar * S // 2, r=3)

    rack = cv.resize((cv.width // S, cv.height // S), Image.LANCZOS)
    base.alpha_composite(rack, (x - pad_l, y - pad_t))
    return h


def main():
    content = ct.DEFAULT_CONTENT
    img = ct.crypto_backdrop(ct.dark_background()).convert("RGBA")
    d = ImageDraw.Draw(img)

    # ---- left rail panel (dark-charcoal edition of the crossover
    # rail: same geometry, crypto tones) ----
    rail = Image.new("RGBA", (RAIL_W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rail)
    for yy in range(H):
        t = yy / H
        col = tuple(int(a + (b - a) * t) for a, b in zip((26, 27, 35), (15, 15, 20)))
        rd.line([(0, yy), (RAIL_W, yy)], fill=col + (255,))
    img.alpha_composite(rail, (0, 0))
    # gradient right edge of the rail, in the crypto palette
    strip = mt.grad_rounded((6, H), list(HL), 3)
    img.paste(strip, (RAIL_W, 0), strip)
    d = ImageDraw.Draw(img)

    # ---- Brian branding, rail top (identical placement to the
    # crossover; colors adapted to the dark rail) ----
    glow = mt._radial_glow(300, 300, (112, 199, 186), 70)
    img.paste(glow, (RAIL_W // 2 - 150, -30), glow)
    pc = mt.photo_card(PHOTO, size=168)
    img.paste(pc, (RAIL_W // 2 - 84, 24), pc)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([RAIL_W // 2 - 90, 18, RAIL_W // 2 + 90, 198], 30,
                        outline=(217, 165, 33, 255), width=4)
    d.rounded_rectangle([RAIL_W // 2 - 97, 11, RAIL_W // 2 + 97, 205], 34,
                        outline=(217, 165, 33, 140), width=2)
    bx, by, br = RAIL_W // 2 + 66, 162, 19
    d.ellipse([bx - br, by - br, bx + br, by + br], fill=(10, 165, 224, 255),
              outline=(255, 255, 255, 255), width=3)
    d.line([(bx - 9, by), (bx - 3, by + 7), (bx + 10, by - 7)],
           fill=(255, 255, 255, 255), width=4)
    cx_text(d, RAIL_W // 2, 218, "BRIAN LATHE", font(FB, 30), INK_D, tracking=1)
    cx_text(d, RAIL_W // 2, 256, "SUCCESS BRIAN", font(FB, 16), ct.KASPA, tracking=3)

    def _yt_icon(size=26):
        _im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        _d = ImageDraw.Draw(_im)
        _d.rounded_rectangle([2, 2, size - 2, size - 2], size // 4,
                             fill=(235, 25, 35, 255))
        _d.polygon([(size * 0.40, size * 0.32), (size * 0.40, size * 0.68),
                    (size * 0.70, size * 0.50)], fill=(255, 255, 255, 255))
        return _im

    def _sharp_icon(kind, size=36):
        big = size * 4
        _b = _yt_icon(big) if kind == "youtube" else mt.icon(kind, big)
        return _b.resize((size, size), Image.LANCZOS)
    _isz, _hgap, _vgap, _iy0 = 36, 14, 8, 282
    for _i, _kind in enumerate(("facebook", "instagram", "youtube", "blog")):
        _ix = RAIL_W // 2 - _isz - _hgap // 2 if _i % 2 == 0 else RAIL_W // 2 + _hgap // 2
        _iy = _iy0 if _i < 2 else _iy0 + _isz + _vgap
        _ic = _sharp_icon(_kind, _isz)
        img.paste(_ic, (_ix, _iy), _ic)
    d = ImageDraw.Draw(img)
    d.line([(36, 376), (RAIL_W - 36, 376)], fill=(217, 165, 33, 255), width=3)

    # Rail brand lines — D1 UNRULED (per-theme vs global). Until Brian
    # rules, the slot carries the crypto desk's own tagline, split at
    # its bullet (see the module docstring).
    cx_text(d, RAIL_W // 2, 390, "BUY SUPPORT \u2022 SELL RESISTANCE",
            font(FB, 11), DIM_D, tracking=1)
    cx_text(d, RAIL_W // 2, 411, "HOLD LONG", font(FB, 11), DIM_D, tracking=2)

    # ---- the rack (Brian's fleet by JOB; identical to crossover) ----
    units = [
        ("LAN", "", "slim"),
        ("AI INFERENCE", "", "pcs"),
        ("SUCCESSBRIAN OS", "", "cmp"),
        ("BLOG WRITER", "", "cmp"),
        ("VIDEO AND IMAGE", "", "cmp"),
        ("WEB HOSTING", "", "cmp"),
        ("SAAS HOSTING", "", "cmp"),
        ("BLOG SERVING", "", "cmp"),
        ("SOCIAL MEDIA", "", "cmp"),
        ("DATABASE", "", "cmp"),
        ("AI TRAINING", "", "cmp"),
    ]
    draw_rack(img, 22, 448, RAIL_W - 52, units)
    d = ImageDraw.Draw(img)
    d.line([(36, 881), (RAIL_W - 36, 881)], fill=(217, 165, 33, 255), width=3)
    for _i, _line in enumerate(mt.SPENCER_CTA):
        cx_text(d, RAIL_W // 2, 895 + _i * 19, _line, font(FB, 13),
                "#0a7fd4" if _i else INK_D)
    _badge = mt.spencer_badge(84)
    img.paste(_badge, (RAIL_W // 2 - 42, 935), _badge)
    d = ImageDraw.Draw(img)
    cx_text(d, RAIL_W // 2, 1027, "SPENCER", font(FB, 15), INK_D)

    # ---- kicker pill (crossover pill, crypto palette, candle
    # glyphs instead of sparkles — the crypto kicker signature) ----
    _kt = content["kicker"]  # "THE CRYPTO DESK IS OPEN"
    _kf = font(FB, 17)
    _ktw = d.textlength(_kt, font=_kf) + 3 * (len(_kt) - 1)
    _pw, _ph = int(_ktw) + 150, 56
    _pill = mt.holo_pill((_pw, _ph), colors=HL, radius=26, base_alpha=130)
    img.paste(_pill, (int(CX - _pw / 2), 24), _pill)
    d = ImageDraw.Draw(img)
    cx_text(d, CX, 24 + (56 - 17) // 2 - 1, _kt, _kf, (234, 252, 247), tracking=3)
    for _up, _gx in ((True, int(CX - _pw / 2 + 18)), (False, int(CX + _pw / 2 - 48))):
        _g = ct.icon_candle(30, up=_up)
        img.paste(_g, (_gx, 24 + 13), _g)
    d = ImageDraw.Draw(img)

    # ---- headline (dark 3D variant, crypto gradient, fitted on the
    # TRUE rendered layer width like the crossover) ----
    size = 96
    _dummy = Image.new("RGBA", (10, 10))
    while size > 28:
        f_big = font(FB, size)
        hl, (lw, lh) = ct.headline_3d_dark(_dummy, content["headline"],
                                           f_big, list(HL), depth=4)
        if lw <= W - RAIL_W - 14:
            break
        size -= 1
    img.paste(hl, (int(CX - lw / 2), 92), hl)
    d = ImageDraw.Draw(img)
    cy = 92 + lh + 12

    # ---- THE CENTRAL CARD: framed like the crossover graph card
    # (gradient ring + header band + garnet footer band joined
    # inside), dark-filled; inside it, the six coin cards and the
    # skeptics strip ----
    x0, x1 = RAIL_W + 34, W - 30
    card_h = 548
    _frame = mt.holo_pill((x1 - x0 + 6, card_h + 6), colors=HL,
                          radius=27, base_alpha=255)
    img.paste(_frame, (x0 - 3, cy - 3), _frame)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, cy, x1, cy + card_h], 24,
                        fill=mt._hex(ct.CARD_BG) + (255,),
                        outline=mt._hex(ct.KASPA_DK) + (255,), width=4)
    _bw = (x1 - 4) - (x0 + 4)
    _band = mt.holo_pill((_bw, 14), colors=HL, radius=1, base_alpha=255)
    _bm = Image.new("L", (_bw * 3, 14 * 3), 0)
    ImageDraw.Draw(_bm).rounded_rectangle(
        [0, 0, _bw * 3 - 1, 14 * 3 + 60], radius=60, fill=255)
    _band.putalpha(_bm.resize((_bw, 14), Image.LANCZOS))
    img.paste(_band, (x0 + 4, cy + 4), _band)
    d = ImageDraw.Draw(img)

    # the six coin cards — the crypto desk's vertical terminal cards,
    # 3 x 2 inside the frame
    cards = content["cards"]
    cw, chh, cgap = 233, 188, 12
    for i, c in enumerate(cards):
        col, row = i % 3, i // 3
        x = x0 + 20 + col * (cw + cgap)
        y = cy + 30 + row * (chh + cgap)
        ccx = x + cw / 2
        d.rounded_rectangle([x + 5, y + 8, x + cw + 5, y + chh + 8], 22,
                            fill=(0, 0, 0, 160))
        d.rounded_rectangle([x, y, x + cw, y + chh], 22,
                            fill=(35, 35, 46, 255),
                            outline=(120, 84, 30, 255), width=2)
        _strip = mt.grad_rounded((cw - 16, 7), [c["bar_color"], c["bar_color"]], 3)
        img.paste(_strip, (x + 8, y + 7), _strip)
        d = ImageDraw.Draw(img)
        cx_text(d, ccx, y + 24, c["tag"], font(FB, 12), DIM_D, tracking=2)
        _tf = ct._fit_font(d, c["title"], FB, 26, cw - 16)
        cx_text(d, ccx, y + 46, c["title"], _tf, INK_D)
        _pf = ct._fit_font(d, c["price"], FB, 42, cw - 16)
        cx_text(d, ccx, y + 82, c["price"], _pf, c["bar_color"])
        _sf = ct._fit_font(d, c["sub"], FR, 15, cw - 16)
        _stw = d.textlength(c["sub"], font=_sf)
        d.text((ccx - _stw / 2, y + 140), c["sub"], font=_sf, fill=DIM_D)
        bx, bw2, by2, bh2 = x + 30, cw - 60, y + 162, 15
        d.rounded_rectangle([bx, by2, bx + bw2, by2 + bh2], 7,
                            fill=(42, 42, 54, 255))
        mt._gbar(img, [bx, by2, bx + bw2 * c["bar_frac"], by2 + bh2],
                 c["bar_color"])
        d = ImageDraw.Draw(img)

    # skeptics strip (the crypto counterpoint, in its own dark idiom)
    cp = content["counterpoint"]
    sy = cy + 430
    d.rounded_rectangle([x0 + 20, sy, x1 - 20, sy + 54], 14,
                        fill=(32, 32, 42, 255),
                        outline=mt._hex(ct.KASPA) + (255,), width=2)
    cx_text(d, CX, sy + 7, cp["label"], font(FB, 12), DIM_D, tracking=1)
    cx_text(d, CX, sy + 27, cp["quote"], font(FB, 18), INK_D)

    # garnet punchline band — the card's footer, flush inside the
    # bottom border exactly as in the crossover
    _gbw = x1 - x0 - 8
    _gb = _vgrad(_gbw, 48, "#ad5f71", "#9a475c", 1)
    _gm = Image.new("L", (_gbw * 3, 48 * 3), 0)
    ImageDraw.Draw(_gm).rounded_rectangle(
        [0, -60, _gbw * 3 - 1, 48 * 3 - 1], radius=60, fill=255)
    _gb.putalpha(_gm.resize((_gbw, 48), Image.LANCZOS))
    _gby = cy + card_h - 4 - 48
    img.paste(_gb, (x0 + 4, _gby), _gb)
    d = ImageDraw.Draw(img)
    d.line([x0 + 4, _gby, x1 - 4, _gby], fill="#c0788a", width=2)
    _plf, _plsz = _fit(content["punchline"], 23, _gbw - 40, floor=14)
    cx_text(d, (x0 + x1) // 2, _gby + (48 - _plsz) // 2 - 1,
            content["punchline"], _plf, mt.YELLOW)
    cy = cy + card_h + 12

    # ---- THE CONNECT CARD (the crossover's unified card, dark
    # edition): ask -> chips -> CTA pills -> signature plaque ->
    # hashtag line. NO scorecard strip — that is AI-meme content. ----
    T = cy + 2
    _card_h = 284
    _csh2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(_csh2).rounded_rectangle(
        [RAIL_W + 34, T + 7, W - 30, T + _card_h + 7], 24, fill=(0, 0, 0, 110))
    _csh2 = _csh2.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(_csh2)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([RAIL_W + 34, T, W - 30, T + _card_h], 24,
                        fill=mt._hex(ct.CARD_BG) + (255,),
                        outline=mt._hex(ct.KASPA_DK) + (255,), width=3)
    _astrip = mt.holo_pill((W - 30 - (RAIL_W + 34) - 8, 7), colors=HL,
                           radius=3, base_alpha=255)
    img.paste(_astrip, (RAIL_W + 38, T + 6), _astrip)
    d = ImageDraw.Draw(img)
    # the ask — Brian's curiosity line, split across the format's
    # ask + subline exactly as written
    _af, _asz = _fit("Which coin are you stacking right now?", 26, 724, floor=16)
    cx_text(d, CX, T + 16, "Which coin are you stacking right now?",
            _af, INK_D)
    cx_text(d, CX, T + 52, "Drop it below.", font(FB, 17), DIM_D)

    def _mchip(cx_center, label, kind, top):
        chw, chh = 232, 44
        cx0 = int(cx_center - chw / 2)
        _s = Image.new("RGBA", (chw + 20, chh + 20), (0, 0, 0, 0))
        ImageDraw.Draw(_s).rounded_rectangle([10, 10, chw + 10, chh + 10], 22,
                                             fill=(0, 0, 0, 90))
        _s = _s.filter(ImageFilter.GaussianBlur(6))
        img.paste(_s, (cx0 - 10, top - 6), _s)
        _cd = ImageDraw.Draw(img)
        _cd.rounded_rectangle([cx0, top, cx0 + chw, top + chh], 22,
                              fill=(32, 32, 42, 255),
                              outline=(96, 96, 116, 255), width=2)
        if kind == "like":
            hx, hy = cx0 + 22, top + 10
            _cd.ellipse([hx, hy, hx + 12, hy + 12], fill="#e0245e")
            _cd.ellipse([hx + 11, hy, hx + 23, hy + 12], fill="#e0245e")
            _cd.polygon([(hx + 1, hy + 9), (hx + 22, hy + 9), (hx + 11, hy + 24)],
                        fill="#e0245e")
            ix = cx0 + 22 + 23 + 12
        elif kind == "share":
            nx, ny = cx0 + 22, top + 8
            _cd.line([(nx + 7, ny + 14), (nx + 24, ny + 5)], fill=INK_D, width=3)
            _cd.line([(nx + 7, ny + 14), (nx + 24, ny + 23)], fill=INK_D, width=3)
            for cxp, cyp in [(nx + 26, ny + 5), (nx + 5, ny + 14), (nx + 26, ny + 23)]:
                _cd.ellipse([cxp - 5, cyp - 5, cxp + 5, cyp + 5], outline=INK_D, width=3)
            ix = cx0 + 22 + 31 + 12
        else:
            bx0, by0 = cx0 + 22, top + 10
            _cd.rounded_rectangle([bx0, by0, bx0 + 30, by0 + 20], 6,
                                  outline=INK_D, width=3)
            _cd.polygon([(bx0 + 6, by0 + 20), (bx0 + 6, by0 + 29), (bx0 + 15, by0 + 20)],
                        fill=INK_D)
            for _dx in (8, 15, 22):
                _cd.ellipse([bx0 + _dx - 2, by0 + 8, bx0 + _dx + 2, by0 + 12], fill=INK_D)
            ix = cx0 + 22 + 30 + 12
        _cd.text((ix, top + 11), label, font=font(FB, 17), fill=INK_D)
    _mchip(CX - 244, "LIKE", "like", T + 76)
    _mchip(CX, "COMMENT", "comment", T + 76)
    _mchip(CX + 244, "SHARE", "share", T + 76)

    def _cta(cx0, top, w, h, c_top, c_bot, line1, line2):
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
    _cta(292, T + 126, 368, 58, "#ff7a29", "#e04e00",
         "Read My Blog", mt.BRAND["blog_url"])
    _cta(676, T + 126, 368, 58, "#2fce6e", "#0f9d4c",
         "Message Me on WhatsApp",
         dict(mt.BRAND["handles"])["whatsapp"])

    # THE SIGNATURE — the crossover's navy plaque (compressed 4px
    # vs the AI card so the desk's hashtag line also fits inside
    # this card). Second line: the crypto desk's own line (see the
    # module docstring — flagged for Brian's ruling).
    _pq = _vgrad(W - 30 - (RAIL_W + 34) - 24, 72, "#1d2c49", "#131f36", 14)
    img.paste(_pq, (RAIL_W + 46, T + 188), _pq)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([RAIL_W + 46, T + 188, W - 42, T + 260], 14,
                        outline="#0aa5e0", width=2)
    cx_text(d, CX, T + 198, "BRIAN LATHE", font(FB, 29), "white", tracking=1)
    cx_text(d, CX, T + 234, "BUY SUPPORT \u2022 SELL RESISTANCE \u2022 HOLD LONG",
            font(FB, 12), "#f2cf7a", tracking=1)
    # the desk's hashtag line, closing the card
    cx_text(d, CX, T + 265, ct.CRYPTO_BRAND["hashtag"],
            font(FB, 13), ct.KASPA)

    img.convert("RGB").save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
