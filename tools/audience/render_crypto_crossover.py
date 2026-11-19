#!/usr/bin/env python3
"""Crypto desk in the CROSSOVER format — Brian's ruling 2026-11-18
21:49 CST: "make this look more like the one we developed today."

The format is the AI crossover meme of 2026-11-18 (full-height left
rail + kicker pill + gradient-3D headline + framed central card with
the garnet punchline joined inside it + the unified connect card),
wearing the crypto desk's identity: near-black charcoal, candlestick
texture, Kaspa teal / Cardano blue / BNB gold.

Machinery: everything renders through the existing desk machinery —
meme_template.py primitives (photo_card, holo_pill,
grad_rounded, icons, _gbar) and crypto_template.py (dark backdrop,
headline_3d_dark, candle glyphs, the branded-six DEFAULT_CONTENT).
The rail geometry follows render_crossover_graph.py (the crossover
format master) — the desk pattern until the Format Library
extraction (FORMAT_LIBRARY_SPEC.md Module 2, staged in the PM
queue) lands it in the library. NO new layout was created.

Rail ruling (Brian, 2026-11-18 21:55 CST): "the home rack comes
out, it's not related to crypto." In the crypto theme the rail
carries NO rack — the rack is AI/infrastructure branding, not
crypto. The rail is photo + name + icons + the HODL panels + a
CTA foot block, reflowed to fill the full height without the
rack. Scope: crypto theme only; the AI crossover keeps its rack.

Spencer / HODL Coins ruling (Brian, 2026-11-18 21:58 CST):
"spencer comes out — and where the home rack was, that's where
the six crypto icons go labeled as 'HODL Coins'." The rail's
Spencer foot block ("ASK BRIAN FOR YOUR FREE MUSE AI AGENT" +
badge + name) is removed — crypto piece only; Spencer stays in
the AI crossover and everywhere else. The rack's slot becomes
the HODL Coins panel: the six branded coins (Kaspa, Bitcoin,
Cardano, Solana, BNB, Aster) as drawn medallion glyphs in the
desk's own idiom — letter/symbol marks in each coin's card
color, no scraped brand art — under Brian's exact label
"HODL Coins".

HODL Stocks ruling (Brian, 2026-11-18 22:01 CST: "main" — settling
the pair he opened with "we need two HODL stocks --- O (realty
income) is one ---", #2 not realty related, monthly, very solid
like O): Brian's two HODL stocks are O (Realty Income — realty,
a REIT) and MAIN (Main Street Capital — a BDC lender to small and
mid-sized businesses, NOT realty). Both are monthly dividend
payers. The pair is recorded on Driving Dollars Digest's registry
note (the everything-but-crypto finance blog — the stocks' home
surface); it mirrors the six HODL coins on the crypto side.

Both-panels ruling (Brian, 2026-11-18 22:03 CST): "hodl stocks
and hodl coins need to both fit on the left; and it needs to look
nicer." The rail now carries BOTH HODL panels, stacked in its
lower half in one shared panel grammar (same border, gold header,
gold rule, medallion treatment): "HODL Coins" (the six, reflowed
3-wide x 2-tall) above "HODL Stocks" (O and MAIN, 2 across, drawn
medallions — a letter O in silver-blue, a letter M in money
green; no scraped brand art). The rest of the rail and the whole
right side are unchanged in substance; the pass also evened the
rail's spacing so the two panels read as one designed column.

Connect-card ruling (Brian, 2026-11-18 21:57 CST): "this meme can
pitch substack AND 'drivingdollarsdigest' and 'hashrateharbor'."
The connect card pitches THREE destinations: Substack (the orange
CTA pill), Hashrate Harbor (Brian's crypto blog) and Driving
Dollars Digest (his everything-but-crypto personal finance blog).
The two blogs are pitched BY NAME on a blogs line inside the card —
neither blog has a domain on record, so no URL is shown. This is
the two blogs' mutual cross-promotion (Brian's ruling the same
evening) in action; the blogs remain independent.

Tagline ruling (Brian, 2026-11-18 22:11 CST: "get rid of the buy
support, sell resistance text" — scope corrected 22:12 CST:
"just from the rail."): the tagline is REMOVED from the rail's
brand slot; the slot is closed. The signature plaque in the
connect card KEEPS its "BUY SUPPORT • SELL RESISTANCE • HOLD
LONG" line exactly as it was — Brian scoped the removal to the
rail only. crypto_template.py's own tagline usage is untouched.

CTA ruling (Brian, 2026-11-18 22:12 CST): "crunch everything up
to leave room for a call to action like spencer is on the other."
The rail's content is compressed upward (icons tightened, the
tagline slot closed, both HODL panels riding higher) to free a
foot block in the same position and form as the AI crossover's
Spencer CTA: a gold rule, the offer lines, an image badge.
Spencer himself stays OUT (21:58 ruling) — this is the CTA slot
and form, not Spencer, and it does not pitch the Muse AI agent.

CTA offer ruling (Brian, 2026-11-18 22:16 CST): "Ask Brian For
-- 7 Day FREE Trial -- 24/7 6TB Cloud Backup -- and an image."
The block carries Brian's own offer, replacing the agent-drafted
placeholder that stood here briefly ("STACK THE HODL LIST /
WITH BRIAN" over the Kaspa K medallion — drafted from the desk's
copy the same evening, superseded by this ruling before ever
being approved): "ASK BRIAN FOR" / "7 DAY FREE TRIAL" (the
emphasis line) / "24/7 6TB CLOUD BACKUP", over a drawn
cloud-backup medallion — a cloud with an up-arrow, in the desk's
idiom (no scraped art, no brand marks). The offer is UNNAMED:
the product behind it is never named anywhere in the piece,
per Brian's generic-surface discipline — the meme carries the
offer and the name reveals in follow-up. The offer facts are
Brian's, used exactly: 7 day free trial · 24/7 · 6TB cloud
backup.

Offer-treatment ruling (Brian, 2026-11-18 22:20 CST): "my 7 day
offer needs to stand out more -- i want people buy it, ask about
it, etc." The words are unchanged; the block's TREATMENT is now
an ad card: a filled gold-forward panel (warm gold gradient,
gold border — the format's panel grammar) separates the offer
from the rail's dark ground, "7 DAY FREE TRIAL" rides a filled
gold pill with dark text (the holo_pill idiom) sized to stay
readable at feed-thumbnail scale, and the cloud medallion sits
inside the card with the offer instead of dangling below the
lines. Hierarchy stands: ASK BRIAN FOR -> 7 DAY FREE TRIAL ->
24/7 6TB CLOUD BACKUP. The room comes from the rail crunch —
the HODL panels ride higher; their substance is unchanged.

CTA-slot ruling (Brian, 2026-11-18 22:23 CST): "it needs to be
the same SIZE as the spencer call to action -- i'm going to now
multiple call to actions all the same size and we can swap them
out per post." The CTA slot is ONE standard size across the
format — CTAs are interchangeable modules swapped per post
(Spencer / the Muse AI agent on the AI piece, this unnamed
trial offer on the crypto piece, more to come). The standard
footprint is the Spencer block's, measured in
render_crossover_graph.py: the gold rule at y881, CTA lines
895/914, badge 935-1019, name 1027 — a slot 180 wide (x36-216,
the rule's extent) x 161 tall (y881-1042) at the rail foot.
This offer card is built to exactly that footprint; the
stand-out treatment (gold card, gold pill, medallion) lives
INSIDE the slot and takes no extra rail room.

Content (the crypto desk as rebranded, commit 25e4179): headline
"BUY FEAR. SELL GREED.", the six coins as comparative cards, the
skeptics strip, punchline "SUPPORT IS WHERE YOU BUY. RESISTANCE IS
WHERE YOU SELL.", the curiosity line as the connect card's ask,
FOLLOW #SuccessBrianCrypto. The AI piece's DAY/Huang counter strip
is AI-meme content and is NOT carried over.

Open items flagged for Brian (not decided here):
- D1 (rail brand line per-theme vs global) is UNRULED. The rail's
  two-line brand slot carried the crypto desk's own tagline until
  Brian removed it (22:11/22:12 CST rulings above); the slot is
  closed and the rail carries no brand line. D1 remains open for
  the Format Library.
- The signature plaque's second line: the AI version reads "AI
  INSIGHTS THAT SAVE YOU REAL MONEY". The crypto theme's materials
  supply no insights-parallel line, so the plaque carries the desk's
  own line in full — "BUY SUPPORT • SELL RESISTANCE • HOLD LONG" —
  agent-placed, awaiting Brian's ruling on the wording. Brian's
  22:12 CST scope correction left the plaque line untouched.
- The rail CTA foot block's wording is Brian's own (22:16 CST
  ruling above) — the earlier agent-drafted placeholder was
  superseded before approval and no longer appears.
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

    # ---- Brian branding, rail top (crossover placement, reflowed
    # taller for the rack-less rail; colors adapted to the dark
    # rail) ----
    glow = mt._radial_glow(300, 300, (112, 199, 186), 70)
    img.paste(glow, (RAIL_W // 2 - 150, -20), glow)
    pc = mt.photo_card(PHOTO, size=192)
    img.paste(pc, (RAIL_W // 2 - 96, 40), pc)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([RAIL_W // 2 - 102, 34, RAIL_W // 2 + 102, 238], 32,
                        outline=(217, 165, 33, 255), width=4)
    d.rounded_rectangle([RAIL_W // 2 - 109, 27, RAIL_W // 2 + 109, 245], 36,
                        outline=(217, 165, 33, 140), width=2)
    bx, by, br = RAIL_W // 2 + 74, 200, 20
    d.ellipse([bx - br, by - br, bx + br, by + br], fill=(10, 165, 224, 255),
              outline=(255, 255, 255, 255), width=3)
    d.line([(bx - 10, by), (bx - 3, by + 8), (bx + 11, by - 8)],
           fill=(255, 255, 255, 255), width=4)
    cx_text(d, RAIL_W // 2, 272, "BRIAN LATHE", font(FB, 32), INK_D, tracking=1)
    cx_text(d, RAIL_W // 2, 314, "SUCCESS BRIAN", font(FB, 17), ct.KASPA, tracking=3)

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
    _isz, _hgap, _vgap, _iy0 = 42, 16, 12, 338
    for _i, _kind in enumerate(("facebook", "instagram", "youtube", "blog")):
        _ix = RAIL_W // 2 - _isz - _hgap // 2 if _i % 2 == 0 else RAIL_W // 2 + _hgap // 2
        _iy = _iy0 if _i < 2 else _iy0 + _isz + _vgap
        _ic = _sharp_icon(_kind, _isz)
        img.paste(_ic, (_ix, _iy), _ic)
    d = ImageDraw.Draw(img)

    # Rail brand slot — CLOSED. The slot carried the crypto desk's
    # tagline until Brian removed it (2026-11-18 22:11 CST: "get rid
    # of the buy support, sell resistance text" — scope corrected
    # 22:12 CST: "just from the rail."). The signature plaque in the
    # connect card KEEPS its tagline line; only the rail's copy is
    # gone. The freed space is part of the 22:12 crunch that lifts
    # the HODL panels and frees the CTA foot block below.

    # ---- HODL panels — the rack's slot (Brian, 2026-11-18 21:58
    # CST: "where the home rack was, that's where the six crypto
    # icons go labeled as 'HODL Coins'"; extended 22:03 CST:
    # "hodl stocks and hodl coins need to both fit on the left").
    # BOTH panels live in the rail's lower half in ONE shared
    # grammar — same border, gold header, gold rule, medallion
    # treatment — so the rail reads as one designed column:
    # "HODL Coins" (the six branded coins, 3-wide x 2-tall) above
    # "HODL Stocks" (Brian's pair — O and MAIN, 2 across; ruled
    # 22:01 CST). All glyphs are drawn in the desk's idiom —
    # letter / symbol marks ringed in their own colors; no scraped
    # brand art. Spencer is OUT of the crypto piece (21:58 ruling);
    # he stays in the AI crossover and everywhere else. ----
    def _medallion(kind, color, size=58):
        S = 4
        m = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0))
        md = ImageDraw.Draw(m)
        c = size * S // 2
        r = c - 4 * S
        md.ellipse([c - r, c - r, c + r, c + r], fill=(35, 35, 46, 255),
                   outline=mt._hex(color) + (255,), width=3 * S)
        col = mt._hex(color) + (255,)

        def _letter(t):
            f = font(FB, 30 * S)
            tw = md.textlength(t, font=f)
            md.text((c - tw / 2, c - 17 * S), t, font=f, fill=col)

        if kind == "KASPA":
            _letter("K")
        elif kind == "BITCOIN":
            # the desk's B with the two strokes through it
            for dx in (-4 * S, 3 * S):
                md.line([(c + dx, c - 16 * S), (c + dx, c + 16 * S)],
                        fill=col, width=3 * S)
            _letter("B")
        elif kind == "CARDANO":
            _letter("A")
        elif kind == "O":      # Realty Income — the letter O itself
            _letter("O")
        elif kind == "MAIN":   # Main Street Capital
            _letter("M")
        elif kind == "SOLANA":
            bw, bh, gap, sk = 30 * S, 7 * S, 5 * S, 8 * S
            y = c - (3 * bh + 2 * gap) // 2
            for i in range(3):
                xo = -sk // 2 if i % 2 == 0 else sk // 2
                md.polygon([(c - bw // 2 + xo + sk // 2, y),
                            (c + bw // 2 + xo + sk // 2, y),
                            (c + bw // 2 + xo - sk // 2, y + bh),
                            (c - bw // 2 + xo - sk // 2, y + bh)],
                           fill=col)
                y += bh + gap
        elif kind == "BNB":
            R = 16 * S
            md.polygon([(c, c - R), (c + R, c), (c, c + R), (c - R, c)],
                       outline=col, width=4 * S)
            r2 = 5 * S
            md.polygon([(c, c - r2), (c + r2, c), (c, c + r2),
                        (c - r2, c)], fill=col)
        elif kind == "CLOUD":
            # cloud backup (the rail CTA badge) — a cloud with an
            # up-arrow rising through it, drawn in the desk's
            # idiom; no brand marks. Bump bottoms align on _cyb so
            # the cloud sits on a flat base; proportions come from
            # the medallion radius r so the glyph scales.
            _cyb = c + int(0.32 * r)
            for _fx, _fr in ((-0.34, 0.30), (0.0, 0.34),
                             (0.34, 0.30)):
                _br = int(_fr * r)
                _bcx = c + int(_fx * r)
                md.ellipse([_bcx - _br, _cyb - 2 * _br, _bcx + _br,
                            _cyb], fill=col)
            md.rectangle([c - int(0.58 * r), _cyb - int(0.24 * r),
                          c + int(0.60 * r), _cyb], fill=col)
            # the up-arrow, knocked out in the medallion's dark
            _dk = (35, 35, 46, 255)
            _tip = c - int(0.28 * r)
            _aw = max(3 * S, int(0.16 * r))
            md.polygon([(c - int(0.24 * r), _tip + int(0.22 * r)),
                        (c + int(0.24 * r), _tip + int(0.22 * r)),
                        (c, _tip)], fill=_dk)
            md.rectangle([c - _aw // 2, _tip + int(0.18 * r),
                          c + _aw // 2, _cyb], fill=_dk)
        else:  # ASTER — an asterisk of three strokes
            L, dx, dy = 15 * S, 13 * S, 8 * S
            md.line([(c, c - L), (c, c + L)], fill=col, width=4 * S)
            md.line([(c - dx, c - dy), (c + dx, c + dy)], fill=col,
                    width=4 * S)
            md.line([(c - dx, c + dy), (c + dx, c - dy)], fill=col,
                    width=4 * S)
            md.ellipse([c - 3 * S, c - 3 * S, c + 3 * S, c + 3 * S],
                       fill=col)
        return m.resize((size, size), Image.LANCZOS)

    def _hodl_panel(y0, title, items, col_cxs):
        """One HODL panel in the shared grammar: bordered box, gold
        header + gold rule, medallions across col_cxs with labels
        beneath. items = [(kind, label, color), ...]. Returns the
        panel's bottom y."""
        _pd = ImageDraw.Draw(img)
        _rows = (len(items) + len(col_cxs) - 1) // len(col_cxs)
        _y1 = y0 + 72 + (_rows - 1) * 84 + 92
        _pd.rounded_rectangle([14, y0, RAIL_W - 14, _y1], 18,
                              fill=(22, 23, 31, 255),
                              outline=mt._hex(ct.KASPA_DK) + (255,),
                              width=2)
        cx_text(_pd, RAIL_W // 2, y0 + 20, title, font(FB, 18), GOLD,
                tracking=1)
        _pd.line([(40, y0 + 54), (RAIL_W - 40, y0 + 54)],
                 fill=(217, 165, 33, 255), width=2)
        for _i, (_kind, _label, _color) in enumerate(items):
            _mcx = col_cxs[_i % len(col_cxs)]
            _mtop = y0 + 72 + (_i // len(col_cxs)) * 84
            _med = _medallion(_kind, _color)
            img.paste(_med, (_mcx - 29, _mtop), _med)
            cx_text(_pd, _mcx, _mtop + 64, _label, font(FB, 11), INK_D,
                    tracking=1)
        return _y1

    _coins = [(_c["title"], _c["title"], _c["bar_color"])
              for _c in content["cards"]]
    _ybot = _hodl_panel(446, "HODL Coins", _coins, (56, 126, 196))
    # Brian's two HODL stocks (ruled 2026-11-18 22:01 CST): O =
    # Realty Income (realty) in silver-blue, MAIN = Main Street
    # Capital (BDC lender, not realty) in money green — colors
    # chosen clear of the six coin colors.
    _stocks = [("O", "O", "#d7dee8"), ("MAIN", "MAIN", "#57b06a")]
    # the pair rides the coins grid's OUTER columns (56 / 196), so
    # both panels share the same vertical lines down the rail
    _sbot = _hodl_panel(_ybot + 12, "HODL Stocks", _stocks, (56, 196))

    # ---- Rail CTA foot block (Brian, 2026-11-18 22:12 CST:
    # "crunch everything up to leave room for a call to action like
    # spencer is on the other"). Same position and form as the AI
    # crossover's Spencer block — gold rule, the offer lines, an
    # image badge — but Spencer himself stays OUT (21:58 ruling)
    # and the offer is not the Muse AI agent. The offer is Brian's
    # own (2026-11-18 22:16 CST: "Ask Brian For -- 7 Day FREE Trial
    # -- 24/7 6TB Cloud Backup -- and an image"), replacing the
    # agent-drafted placeholder that stood here briefly ("STACK
    # THE HODL LIST / WITH BRIAN" — superseded before approval).
    # The product is NEVER NAMED in the piece (generic-surface
    # discipline); the badge is a drawn cloud-backup medallion in
    # the desk's idiom — no scraped art, no brand marks. ----
    # Offer treatment (Brian, 2026-11-18 22:20 CST: "my 7 day offer
    # needs to stand out more -- i want people buy it, ask about
    # it, etc."), sized by the CTA-slot ruling (22:23 CST: "it
    # needs to be the same SIZE as the spencer call to action --
    # i'm going to now multiple call to actions all the same size
    # and we can swap them out per post"). The block is a filled
    # AD CARD — warm gold gradient, gold border — built to the
    # STANDARD CTA SLOT, the Spencer block's exact footprint
    # measured in render_crossover_graph.py: x36-216 (180 wide,
    # the rule's extent) x y881-1042 (161 tall: rule 881, lines
    # 895/914, badge 935-1019, name 1027), same rail-foot position.
    # CTAs are interchangeable modules at this size, swapped per
    # post; the stand-out treatment lives INSIDE the footprint —
    # the card's gold outline takes the rule's place at the slot's
    # top edge, "7 DAY FREE TRIAL" rides a filled gold pill (dark
    # text, the holo_pill idiom), and the cloud medallion sits at
    # the badge position. Internal order mirrors Spencer's:
    # invitation line -> hook -> badge -> closing line. Words
    # unchanged (22:16 ruling). The HODL panels crunch up to clear
    # the slot (stocks bottom 870, slot top 881); their substance
    # is unchanged.
    _sx0, _sx1, _sy0, _sy1 = 36, RAIL_W - 36, 881, 1042
    _card = _vgrad(_sx1 - _sx0, _sy1 - _sy0, "#6d5718", "#382b0b", 16)
    img.paste(_card, (_sx0, _sy0), _card)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([_sx0, _sy0, _sx1, _sy1], 16,
                        outline=(217, 165, 33, 255), width=3)
    cx_text(d, RAIL_W // 2, 895, "ASK BRIAN FOR",
            font(FB, 12), (250, 240, 214), tracking=2)
    _pf, _ = _fit("7 DAY FREE TRIAL", 17, 146)
    _ptw = d.textlength("7 DAY FREE TRIAL", font=_pf)
    _pw2 = int(_ptw) + 30
    _px0 = RAIL_W // 2 - _pw2 // 2
    _pill = _vgrad(_pw2, 36, "#f7c948", "#d9a521", 18)
    img.paste(_pill, (_px0, 915), _pill)
    d = ImageDraw.Draw(img)
    cx_text(d, RAIL_W // 2, 915 + (36 - _pf.size) // 2 - 1,
            "7 DAY FREE TRIAL", _pf, (26, 21, 4))
    _cmed = _medallion("CLOUD", _coins[0][2], 46)
    img.paste(_cmed, (RAIL_W // 2 - 23, 959), _cmed)
    d = ImageDraw.Draw(img)
    _sf, _ = _fit("24/7 6TB CLOUD BACKUP", 11, 168, floor=9)
    cx_text(d, RAIL_W // 2, 1013, "24/7 6TB CLOUD BACKUP",
            _sf, ct.KASPA, tracking=1)
    d = ImageDraw.Draw(img)

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
    # edition): ask -> chips -> CTA pills -> blogs line -> signature
    # plaque -> hashtag line. NO scorecard strip — that is AI-meme
    # content. ----
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
    cx_text(d, CX, T + 50, "Drop it below.", font(FB, 17), DIM_D)

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
    _mchip(CX - 244, "LIKE", "like", T + 72)
    _mchip(CX, "COMMENT", "comment", T + 72)
    _mchip(CX + 244, "SHARE", "share", T + 72)

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
    _cta(292, T + 120, 368, 56, "#ff7a29", "#e04e00",
         "Read My Blog", mt.BRAND["blog_url"])
    _cta(676, T + 120, 368, 56, "#2fce6e", "#0f9d4c",
         "Message Me on WhatsApp",
         dict(mt.BRAND["handles"])["whatsapp"])

    # THE BLOGS LINE — Brian's ruling 2026-11-18 21:57 CST: this
    # meme pitches Substack AND Driving Dollars Digest AND Hashrate
    # Harbor. The two blogs are pitched BY NAME (neither has a
    # domain on record — no URL is shown); the crypto blog leads on
    # the crypto meme. This is the two blogs' mutual cross-promotion
    # in action; the blogs remain independent.
    cx_text(d, CX, T + 182,
            "MY BLOGS: HASHRATE HARBOR \u2022 DRIVING DOLLARS DIGEST",
            font(FB, 15), ct.KASPA, tracking=1)

    # THE SIGNATURE — the crossover's navy plaque (slimmed vs the
    # AI card so the blogs line and the desk's hashtag line also
    # fit inside this card). Second line: the crypto desk's own
    # line (see the module docstring — flagged for Brian's ruling).
    _pq = _vgrad(W - 30 - (RAIL_W + 34) - 24, 58, "#1d2c49", "#131f36", 14)
    img.paste(_pq, (RAIL_W + 46, T + 206), _pq)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([RAIL_W + 46, T + 206, W - 42, T + 264], 14,
                        outline="#0aa5e0", width=2)
    cx_text(d, CX, T + 212, "BRIAN LATHE", font(FB, 29), "white", tracking=1)
    cx_text(d, CX, T + 243, "BUY SUPPORT \u2022 SELL RESISTANCE \u2022 HOLD LONG",
            font(FB, 12), "#f2cf7a", tracking=1)
    # the desk's hashtag line, closing the card
    cx_text(d, CX, T + 268, ct.CRYPTO_BRAND["hashtag"],
            font(FB, 13), ct.KASPA)

    img.convert("RGB").save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
