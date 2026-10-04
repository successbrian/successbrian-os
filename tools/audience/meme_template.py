#!/usr/bin/env python3
"""SuccessBrian reusable meme template — 1080x1080 social cards.

PURPOSE:
    One branded layout for every @successbrian insight meme. Drop in new
    content (headline + chart cards + punchline) and render a fresh card.
    Brand = SuccessBrian. Photo slot takes a real photo of Brian & Gina
    together (rounded card); until one is provided a placeholder renders.

USAGE:
    from meme_template import render_meme
    render_meme(CONTENT, photo_path="/path/they.jpg", out_path="meme.png")

    CONTENT = {
        "kicker": "SMALL CAPS HOOK",
        "headline": [("THE $620 ", "#ffffff"), ("RAM SCAM", "#ffd23f")],
        "cards": [
            {"tag": "WHAT THEY SELL YOU", "title": "1x 32GB MACO",
             "price": "$1,099", "sub": "32GB total • 1 computer",
             "bar_frac": 0.58, "bar_color": "#ff5a5a",
             "bar_label": "RAM per $100: 2.9 GB"},
            ...
        ],
        "punchline": "+16GB MORE RAM • A SECOND COMPUTER • $141 LESS",
        "callouts": ["line one", "line two"],
    }

BRAND defaults below are Brian's; override per user.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

W = H = 1080
FB = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"

BRAND = {
    "wordmark": [("SUCCESS", "#ffffff"), ("BRIAN", "#35d0ff")],
    "tagline": "AI INSIGHTS THAT SAVE YOU REAL MONEY",
    "accent": "#35d0ff",
    "handles": [
        ("facebook", "@successbrian"),
        ("instagram", "@successbrian"),
        ("x", "@MAGAUSNavyVet"),
        ("whatsapp", "+1 952 657 9982"),
    ],
    "blog_url": "successbrianhub.substack.com",
}

YELLOW = "#ffd23f"; CYAN = "#35d0ff"; WHITE = "#ffffff"
GRAY = "#9aa4b5"; DIM = "#5b6474"


def font(path, size):
    return ImageFont.truetype(path, size)


# ---------------- social icons (simple, recognizable) ----------------
def _rr(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def icon(kind, size=56):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = 2
    if kind == "facebook":
        _rr(d, [pad, pad, size-pad, size-pad], size//4, "#1877f2")
        f = font(FB, int(size*0.62))
        t = "f"; tw = d.textlength(t, font=f)
        d.text(((size-tw)/2, size*0.16), t, font=f, fill="white")
    elif kind == "instagram":
        _rr(d, [pad, pad, size-pad, size-pad], size//4, None, "white", 4)
        r = size*0.20
        d.ellipse([size/2-r, size/2-r, size/2+r, size/2+r], outline="white", width=4)
        dr = size*0.07; cx, cy = size*0.70, size*0.30
        d.ellipse([cx-dr, cy-dr, cx+dr, cy+dr], fill="white")
    elif kind == "x":
        _rr(d, [pad, pad, size-pad, size-pad], size//4, "#000000", "#8a93a3", 3)
        f = font(FB, int(size*0.55))
        t = "X"; tw = d.textlength(t, font=f)
        d.text(((size-tw)/2, size*0.20), t, font=f, fill="white")
    elif kind == "blog":
        _rr(d, [pad, pad, size-pad, size-pad], size//4, "#ff6719")
        for i, yy in enumerate([0.30, 0.47, 0.64]):
            ww = size*(0.52 if i < 2 else 0.34)
            d.rounded_rectangle([size/2-ww/2, size*yy-3, size/2+ww/2, size*yy+3],
                                3, fill="white")
    elif kind == "whatsapp":
        d.ellipse([pad, pad, size-pad, size-pad], fill="#25d366")
        # chat bubble
        bw, bh = size*0.52, size*0.42
        bx, by = (size-bw)/2, (size-bh)/2 - 2
        _rr(d, [bx, by, bx+bw, by+bh], 10, "white")
        d.polygon([(bx+bw*0.30, by+bh-2), (bx+bw*0.22, by+bh+10), (bx+bw*0.48, by+bh-2)],
                  fill="white")
    return im


# ---------------- photo slot ----------------
def photo_card(photo_path, size=148):
    """Rounded photo of Brian & Gina together; placeholder if none provided."""
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    im = None
    if photo_path and os.path.exists(photo_path):
        try:
            im = Image.open(photo_path).convert("RGB")
        except Exception:
            im = None
    if im is not None:
        # center-crop square then resize
        s = min(im.size)
        im = im.crop(((im.width-s)//2, (im.height-s)//2,
                      (im.width+s)//2, (im.height+s)//2)).resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], 28, fill=255)
        card.paste(im, (0, 0), mask)
        d.rounded_rectangle([0, 0, size, size], 28, outline=(CYAN, 255), width=4)
    else:
        d.rounded_rectangle([0, 0, size, size], 28, fill=(20, 28, 42, 255),
                            outline=(90, 100, 120, 255), width=3)
        # dashed ring
        for a in range(0, 360, 18):
            d.arc([8, 8, size-8, size-8], a, a+10, fill=(53, 208, 255, 160), width=3)
        f = font(FB, 20)
        for i, t in enumerate(["YOUR", "PHOTO", "HERE"]):
            tw = d.textlength(t, font=f)
            d.text(((size-tw)/2, size/2-34+i*26), t, font=f, fill=(120, 132, 150, 255))
    return card


# ---------------- background ----------------
def background():
    img = Image.new("RGB", (W, H), "#05070d")
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=(int(5+8*t), int(7+10*t), int(13+18*t)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W//2-420, -260, W//2+420, 380], fill=(0, 180, 255, 46))
    img = Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(60))).convert("RGB")
    d = ImageDraw.Draw(img)
    for x in range(0, W, 90):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 3))
    for y in range(0, H, 90):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 3))
    return img


def _centered(d, y, text, fnt, fill, tracking=0):
    if tracking:
        tw = d.textlength(text, font=fnt) + tracking*(len(text)-1)
        x = (W-tw)/2
        for ch in text:
            d.text((x, y), ch, font=fnt, fill=fill)
            x += d.textlength(ch, font=fnt) + tracking
        return
    d.text(((W-d.textlength(text, font=fnt))/2, y), text, font=fnt, fill=fill)


# ---------------- main render ----------------
def render_meme(content, photo_path=None, out_path="meme.png", brand=None):
    b = brand or BRAND
    img = background()
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

    # content zone
    _centered(d, 208, content["kicker"], font(FR, 24), CYAN, tracking=3)
    f_big = font(FB, 84)
    parts = content["headline"]
    total = sum(d.textlength(t, font=f_big) for t, _ in parts)
    x0 = (W-total)/2
    for t, color in parts:
        d.text((x0, 248), t, font=f_big, fill=color)
        x0 += d.textlength(t, font=f_big)

    # cards
    cards = content["cards"]
    n = len(cards)
    gap, margin = 32, 48
    cw = (W - 2*margin - gap*(n-1)) / n
    cy0, ch = 400, 296
    for i, c in enumerate(cards):
        x = margin + i*(cw+gap)
        d.rounded_rectangle([x, cy0, x+cw, cy0+ch], 26,
                            fill=(13, 18, 30, 255), outline=(70, 80, 100, 255), width=3)
        cx = x + cw/2
        for txt, fnt, col, yy in [
            (c["tag"], font(FB, 19), DIM, cy0+22),
            (c["title"], font(FB, 29), WHITE, cy0+52),
            (c["price"], font(FB, 68), c["bar_color"], cy0+94),
            (c["sub"], font(FR, 21), GRAY, cy0+178),
        ]:
            tw = d.textlength(txt, font=fnt)
            d.text((cx-tw/2, yy), txt, font=fnt, fill=col)
        bx, bw, bh, by = x+36, cw-72, 24, cy0+222
        d.rounded_rectangle([bx, by, bx+bw, by+bh], 12, fill=(30, 38, 54, 255))
        d.rounded_rectangle([bx, by, bx+bw*c["bar_frac"], by+bh], 12, fill=c["bar_color"])
        t = c["bar_label"]; tw = d.textlength(t, font=font(FR, 18))
        d.text((cx-tw/2, by+bh+8), t, font=font(FR, 18), fill=GRAY)

    # punchline
    py0, py1 = 724, 806
    d.rounded_rectangle([48, py0, W-48, py1], 18, fill=(64, 14, 18, 255),
                        outline=(255, 90, 90, 255), width=2)
    _centered(d, py0+22, content["punchline"], font(FB, 29), YELLOW)

    # callouts
    y = 828
    for line in content.get("callouts", []):
        _centered(d, y, line, font(FR, 23), WHITE if y == 828 else GRAY)
        y += 34

    # footer
    d.line([(48, 904), (W-48, 904)], fill=(40, 48, 64, 255), width=2)
    # social row
    items = []
    for kind, handle in b["handles"]:
        items.append((icon(kind, 42), handle))
    widths = [42 + 12 + d.textlength(h, font=font(FR, 20)) for _, h in items]
    total_w = sum(widths) + 40*(len(items)-1)
    x = (W-total_w)/2; y_ic = 918
    for (ic, handle), wdt in zip(items, widths):
        img.paste(ic, (int(x), y_ic), ic)
        d.text((x+42+12, y_ic+7), handle, font=font(FR, 20), fill=WHITE)
        x += wdt + 40
    # blog row — larger, with blog icon
    bic = icon("blog", 46)
    url = b["blog_url"]
    f_blog = font(FB, 30)
    tw = d.textlength(url, font=f_blog)
    bx = (W - (46 + 14 + tw))/2
    img.paste(bic, (int(bx), 972), bic)
    d.text((bx+46+14, 974), url, font=f_blog, fill=WHITE)

    img.save(out_path)
    return out_path


# ---------------- demo: the RAM SCAM card ----------------
RAM_SCAM = {
    "kicker": "MINI PC MAKERS DON'T WANT YOU DOING THIS MATH",
    "headline": [("THE $620 ", "#ffffff"), ("RAM SCAM", "#ffd23f")],
    "cards": [
        {"tag": "WHAT THEY SELL YOU", "title": "1x 32GB MACO", "price": "$1,099",
         "sub": "32GB total • 1 computer", "bar_frac": 2.91/5.01,
         "bar_color": "#ff5a5a", "bar_label": "RAM per $100: 2.9 GB"},
        {"tag": "WHAT I BOUGHT", "title": "2x 24GB MACO", "price": "$958",
         "sub": "48GB total • 2 computers", "bar_frac": 1.0,
         "bar_color": "#3ddc84", "bar_label": "RAM per $100: 5.0 GB"},
    ],
    "punchline": "+16GB MORE RAM • A SECOND COMPUTER • $141 LESS",
    "callouts": ["They charge $77.50/GB for soldered RAM. Real cost ~ $5/GB.",
                 "That's a 15x markup on a part you can never upgrade."],
}

if __name__ == "__main__":
    import sys
    photo = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else "meme.png"
    print(render_meme(RAM_SCAM, photo_path=photo, out_path=out))
