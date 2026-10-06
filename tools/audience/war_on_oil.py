"""Properly built example: war-on-oil on the new political chrome.

Full content cards with icons (refinery+flames, refinery+X, tanker),
framed ribbon top/bottom, blue 3D stars, wavy red stripes, tricolor
divider, enlisted-silver propeller.
"""
import sys
sys.path.insert(0, "/home/hatch/workspace/successbrian-os/tools/audience")
from political_meme import render_political_meme
from meme_template import font, INK, GRAY, W, FB, FR
from PIL import Image, ImageDraw

PHOTO = "/home/hatch/workspace/profile-images/brian-gina-together.jpg"
NAVY = "#16213a"


def refinery_icon(s=88, flames=False, xed=False):
    im = Image.new("RGBA", (132, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([8, s - 14, 124, s - 6], fill=NAVY)            # platform
    d.rectangle([18, s - 52, 46, s - 14], fill=NAVY)           # tower
    d.rectangle([54, s - 44, 80, s - 14], fill=NAVY)           # mid block
    d.rectangle([88, s - 64, 98, s - 14], fill=NAVY)          # stack 1
    d.rectangle([104, s - 58, 114, s - 14], fill=NAVY)        # stack 2
    d.rectangle([18, s - 52, 46, s - 46], fill="#b22234")     # roof trim
    if flames:
        for fx, fy, fs in [(93, s - 66, 15), (109, s - 60, 12), (64, s - 46, 13)]:
            d.polygon([(fx - fs * 0.6, fy), (fx + fs * 0.6, fy),
                       (fx, fy - fs * 1.7)], fill="#f59e0b")
            d.polygon([(fx - fs * 0.35, fy), (fx + fs * 0.35, fy),
                       (fx, fy - fs)], fill="#fde047")
    if xed:
        d.line([(8, 8), (124, s - 8)], fill="#dc2626", width=11)
        d.line([(124, 8), (8, s - 8)], fill="#dc2626", width=11)
    return im


def tanker_icon(s=88):
    im = Image.new("RGBA", (142, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(8, s - 36), (134, s - 36), (118, s - 12), (24, s - 12)],
              fill=NAVY)                                       # hull
    for i in range(3):                                       # containers
        d.rectangle([30 + i * 26, s - 54, 52 + i * 26, s - 36],
                    fill="#b22234")
    d.rectangle([110, s - 64, 130, s - 36], fill="#8a94a6")   # bridge
    d.rectangle([114, s - 72, 126, s - 64], fill="#8a94a6")
    for i in range(3):                                       # portholes
        d.ellipse([42 + i * 24, s - 30, 50 + i * 24, s - 22],
                  fill="#9fc3e8")
    for wx in (14, 56, 98):                                  # waves
        d.arc([wx, s - 12, wx + 38, s + 8], 180, 360,
              fill="#2b7fff", width=3)
    return im


CARDS = [
    ("UKRAINE", "51% of Russian refining offline",
     "Putin admits a 1% GDP hit", "51% DOWN",
     refinery_icon(flames=True)),
    ("CALIFORNIA", "two refineries gone - 20% of supply",
     "$8.44/gal forecast by year's end", "SHUT DOWN",
     refinery_icon(xed=True)),
    ("STRAIT OF HORMUZ", "crude flows - refined fuel doesn't",
     "diesel at record highs", "FUEL CRISIS",
     tanker_icon()),
]


def draw_content(img, d, box):
    x0, y0, x1, y1 = box
    n = len(CARDS)
    gap = 14
    ch = (y1 - y0 - gap * (n - 1)) / n
    # narrow-card layout: shrunken icon, text column, dedicated stat
    # column on the right so nothing ever collides
    for i, (title, l1, l2, stat, icon) in enumerate(CARDS):
        cy = y0 + i * (ch + gap)
        d.rounded_rectangle([x0, cy, x1, cy + ch], 22, fill="white",
                            outline="#1e3fae", width=3)
        iw, ih = icon.size
        nw = 110
        nh = int(ih * nw / iw)
        icon_s = icon.resize((nw, nh), Image.LANCZOS)
        img.paste(icon_s, (int(x0 + 18), int(cy + (ch - nh) / 2)), icon_s)
        stat_w = 200
        sx0 = x1 - 18 - stat_w
        tx = x0 + 18 + nw + 16
        ty = cy + 8
        d.text((tx, ty), title, font=font(FB, 24), fill=INK)
        fb = font(FR, 16)
        d.text((tx, ty + 34), "•  " + l1, font=fb, fill="#414b5e")
        d.text((tx, ty + 56), "•  " + l2, font=fb, fill="#414b5e")
        # stat: as large as its column allows, uniform, black stroke,
        # vertically centered
        fsize = 40
        while fsize > 16:
            _f = font(FB, fsize)
            if max(d.textlength(s, font=_f) for _, _, _, s, _ in CARDS) <= stat_w:
                break
            fsize -= 2
        fstat = font(FB, fsize)
        sw = d.textlength(stat, font=fstat)
        d.text((sx0 + (stat_w - sw) / 2, cy + ch / 2), stat, font=fstat,
               fill="#d2202f", anchor="lm", stroke_width=2,
               stroke_fill="black")
        d = ImageDraw.Draw(img)


render_political_meme(
    {
        "kicker": "TRUMP CALLS IT A WAR ON OIL",
        "headline": "WAR ON OIL",
        "punchline": "MAKE GAS HURT. BLAME TRUMP. STEAL THE MIDTERMS.",
        "curiosity": "Think the timing is a coincidence? Sound off below.",
    },
    draw_content,
    photo_path=PHOTO,
    out_path="/tmp/pol_proper_proof.png",
    headline_size=140,
)
print("wrote /tmp/pol_proper_proof.png")
