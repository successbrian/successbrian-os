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
"""

import math
import sys

sys.path.insert(0, "/home/hatch/workspace/successbrian-os/tools/audience")
from meme_template import (background, headline_3d, photo_card, icon, BRAND,
                           font, _centered, grad_rounded, ai_backdrop, footer,
                           INK, GRAY, GARNET_BG, YELLOW,
                           W, H, FB, FR)
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# Political template brand: same handles/blog as the AI brand, but its own
# hashtag slot — Brian will name the political hashtag later; until then the
# footer prints no hashtag line on political memes.
POL_BRAND = dict(BRAND)
POL_BRAND["hashtag"] = None

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
    """Navy anchor — flanks the kicker on both sides."""
    import math
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = s / 2
    w = max(3, s // 12)
    # ring
    rr = s * 0.10
    d.ellipse([cx - rr, s * 0.10 - rr, cx + rr, s * 0.10 + rr],
              outline=color, width=w)
    # shank
    d.rounded_rectangle([cx - w * 0.55, s * 0.18, cx + w * 0.55, s * 0.74],
                        w // 2 + 1, fill=color)
    # stock (crossbar)
    d.rounded_rectangle([cx - s * 0.26, s * 0.24, cx + s * 0.26,
                         s * 0.24 + w * 1.1], w // 2 + 1, fill=color)
    # arms (bottom arc)
    ax0, ay0, ax1, ay1 = cx - s * 0.30, s * 0.30, cx + s * 0.30, s * 0.94
    d.arc([ax0, ay0, ax1, ay1], 25, 155, fill=color, width=w)
    # flukes: small barbs at the arc ends, angled outward
    for deg in (25, 155):
        a = math.radians(deg)
        ex = cx + s * 0.30 * math.cos(a)
        ey = (ay0 + ay1) / 2 + s * 0.32 * math.sin(a)
        L = s * 0.11
        d.polygon([(ex, ey - L), (ex - L * 0.7, ey + L * 0.5),
                   (ex + L * 0.7, ey + L * 0.5)], fill=color)
    return im


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


def star(d, cx, cy, r, fill):
    """Five-point star."""
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=fill)


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
]
MN_SENATE_DEM = "Flanagan (D)"
MN_SENATE_GOP = "Tafoya (R)"
MN_SENATE_FOOTER = "RCP AVG: FLANAGAN +1.6 • TOSS-UP"


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


def render_political_meme(content, draw_content, photo_path=None,
                          out_path="meme.png", brand=None, headline_size=None,
                          post_date=None, election_day="2026-11-03",
                          countdown=True):
    """Render a political meme.

    Election season (standing until midterms pass): when countdown=True and
    election_day hasn't passed, a small inset rail (countdown + race tracker)
    is drawn inside the content zone and the caller's content box narrows to
    make room. post_date (default: today) drives the countdown math.
    """
    b = brand or POL_BRAND
    img = background()
    ribbon(img)
    img = ai_backdrop(img)  # faint neural texture — more AI visuals
    img = political_backdrop(img)  # 3D stars + wavy stripes, kept subtle
    d = ImageDraw.Draw(img)

    # brand bar (shifted below the ribbon)
    pc = photo_card(photo_path or PHOTO)
    img.paste(pc, (48, 40), pc)
    x = 48 + 148 + 24
    wx = x
    for word, color in b["wordmark"]:
        f = font(FB, 46)
        d.text((wx, 48), word, font=f, fill=color)
        wx += d.textlength(word, font=f) + 10
    tag = POLITICAL_TAGLINE
    tf = font(FR, 20)
    while d.textlength(tag, font=tf) > W - x - 40 and tf.size > 12:
        tf = font(FR, tf.size - 1)
    d.text((x, 108), tag, font=tf, fill=GRAY)
    # his ship, sailing at the right edge of the brand bar
    ship = carrier_silhouette(width=300)
    img.paste(ship, (W - 40 - 300, 48), ship)
    d = ImageDraw.Draw(img)

    # kicker flanked by navy anchors on both sides — Brian's call;
    # the trefoil + propeller hold the punchline instead
    kf = font(FB, 25)
    kt = content["kicker"]
    tw = d.textlength(kt, font=kf) + 3 * (len(kt) - 1)
    cx = W / 2
    _centered(d, 200, kt, kf, "#0a7fd4", tracking=3)
    for sx in (int(cx - tw / 2 - 58), int(cx + tw / 2 + 18)):
        anc = anchor(44)
        img.paste(anc, (sx, 194), anc)
    d = ImageDraw.Draw(img)

    # Cherenkov reactor-blue glow behind the headline, then the headline.
    # Stripes go on AFTER the glow so the blue wash doesn't bury them.
    img = cherenkov_glow(img)
    img = political_stripes(img)
    d = ImageDraw.Draw(img)

    # headline: patriotic gradient + 3D, auto-fit single line
    text = content["headline"]
    size = headline_size or 76
    while size > 40:
        f_big = font(FB, size)
        if d.textlength(text, font=f_big) <= W - 110:
            break
        size -= 2
    hl, (lw, lh) = headline_3d(img, text, f_big, HEADLINE_COLORS)
    hy = 234
    img.paste(hl, ((W - lw) // 2, hy), hl)
    d = ImageDraw.Draw(img)

    # tricolor divider: red | white | blue — unmistakably American
    div_y = hy + lh + 10
    div_w, div_h, seg = 440, 12, 440 // 3
    div = Image.new("RGBA", (div_w, div_h), (0, 0, 0, 0))
    dd = ImageDraw.Draw(div)
    dd.rounded_rectangle([0, 0, div_w - 1, div_h - 1], 6, fill="#ffffff",
                         outline=(160, 170, 190, 255), width=2)
    for i, col in enumerate(["#b22234", "#ffffff", "#3c3b6e"]):
        x0 = i * seg
        x1 = (i + 1) * seg if i < 2 else div_w
        dd.rectangle([x0 + 2, 2, x1 - 2, div_h - 2], fill=col)
    img.paste(div, ((W - div_w) // 2, div_y), div)
    d = ImageDraw.Draw(img)

    # content zone (caller paints it); the election inset rail narrows it
    cz0 = div_y + 30
    cz1 = 748
    content_box = (48, cz0, W - 48, cz1)
    if countdown and _days_until(post_date, election_day) >= 0:
        rx0 = W - 48 - 300
        election_inset(img, d, (rx0, cz0, W - 48, cz1), post_date)
        d = ImageDraw.Draw(img)
        content_box = (48, cz0, rx0 - 16, cz1)
    draw_content(img, d, content_box)
    d = ImageDraw.Draw(img)

    # punchline strip: maroon with gold edge, trefoil + propeller standing watch
    py0, py1 = 762, 838
    d.rounded_rectangle([48, py0, W - 48, py1], 18, fill=GARNET_BG,
                        outline=GOLD, width=3)
    _centered(d, py0 + 22, content["punchline"], font(FB, 29), YELLOW)
    img.paste(trefoil(46), (88, py0 + 15), trefoil(46))
    img.paste(propeller(46), (W - 88 - 46, py0 + 15), propeller(46))
    d = ImageDraw.Draw(img)

    # curiosity line
    if content.get("curiosity"):
        _centered(d, 852, content["curiosity"], font(FB, 26), INK)

    # footer (shared brand footer — social row, blog row, hashtag CTA;
    # the political brand carries its own hashtag, None until Brian names it;
    # dy=50 because the political punchline strip sits lower than the AI one)
    img, d = footer(img, d, brand=POL_BRAND, dy=50)

    img.save(out_path)
    return out_path
