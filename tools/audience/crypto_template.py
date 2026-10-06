#!/usr/bin/env python3
"""SuccessBrian CRYPTO meme renderer — 1080x1080 dark trading-terminal edition.

PURPOSE:
    Brian's crypto-desk brand: dark money-terminal maximalism. The only
    dark-background desk — political is patriotic light, AI is holographic
    light, health is EKG light. Crypto owns the night: bitcoin-orange and
    gold on deep charcoal, candlestick texture, the language of the charts
    (support / resistance / stack / hold).

WHY:
    Crypto content lives in dark mode — trading terminals, CoinMarketCap,
    exchange apps. A dark card stops the scroll against a feed of light
    memes and reads as "money talk" instantly. Brian's crypto rules are
    baked into the identity: buy-and-hold (Kaspa, Bitcoin, Cardano, BNB,
    Solana, HYPE), trading-only (Ethereum, Doge + high-liquidity movers),
    buy long-term support, sell resistance, hold long. No meme coins
    except DOGE. The desk tagline IS his strategy, so every meme teaches
    it: "BUY SUPPORT • SELL RESISTANCE • HOLD LONG".

CALLED BY:
    - Humans / agents: from crypto_template import render_crypto_meme
    - Future: crypto desk idea pipeline (mirrors the political desk flow).

NOTES:
    - Exactly 1080x1080, no exceptions.
    - Shared family bones: brand bar + Brian/Gina photo, kicker with
      flanking glyphs, gradient+3D headline (dark-extrusion variant),
      comparison cards, five-part series dots, counterpoint strip,
      soft-garnet punchline strip, curiosity line, shared footer rhythm.
    - Dark-theme adaptations live here (dark background, dark cards, dark
      footer, dark counterpoint) — never force light-theme helpers onto
      the dark canvas; their hardcoded light colors would not read.
    - Never invent prices or market numbers. Card "price" slots take
      words (STACK / TRADE / HOLD) unless the caller passes real data.
    - Hashtag: #SuccessBrianCrypto (CRYPTO_BRAND["hashtag"]).

USAGE:
    from crypto_template import render_crypto_meme
    render_crypto_meme(CONTENT,
                       photo_path="/home/hatch/workspace/profile-images/brian-gina-together.jpg",
                       out_path="meme.png")

    CONTENT = {
        "kicker": "THE CRYPTO DESK IS OPEN",
        "headline": "BUY FEAR. SELL GREED.",
        "grad_colors": [...],  # optional override; default gold->orange
        "cards": [
            {"tag": "BUY & HOLD", "title": "BITCOIN", "price": "STACK",
             "sub": "digital gold • hold long",
             "bar_frac": 0.9, "bar_color": "#16c784", "tint": "#1b1b23"},
            ...
        ],
        "punchline": "SUPPORT IS WHERE YOU BUY. RESISTANCE IS WHERE YOU SELL.",
        "curiosity": "Which coin are you stacking right now? Drop it below.",
        # optional: "counterpoint": {"label": "...", "quote": "..."},
        # optional: "series_day": 1..5
        # optional: CONTENT["hashtag"] overrides the brand default.
    }
"""
import random
import sys

sys.path.insert(0, "/home/hatch/workspace/successbrian-os/tools/audience")
from meme_template import (photo_card, icon, font, _centered, grad_rounded,
                           _gbar, _hex, BRAND,
                           GARNET_BG, YELLOW,
                           W, H, FB, FR)
from PIL import Image, ImageDraw, ImageFilter

# Crypto brand: same handles/blog as the family, own wordmark colors for
# the dark canvas, own tagline (Brian's strategy), own hashtag.
CRYPTO_BRAND = dict(BRAND)
CRYPTO_BRAND.update({
    "wordmark": [("SUCCESS", "#eceef4"), ("BRIAN", "#f7931a")],
    "tagline": "BUY SUPPORT • SELL RESISTANCE • HOLD LONG",
    "hashtag": "FOLLOW #SuccessBrianCrypto",
})

BTC_ORANGE = "#f7931a"
GOLD = "#ffb700"
EMBER = "#ff8c00"
CANDLE_GREEN = "#16c784"   # bullish — CoinMarketCap green
CANDLE_RED = "#ea3943"     # bearish
BG_TOP = "#101014"
BG_BOT = "#1a1a21"
CARD_BG = "#1b1b23"
INK_D = "#eceef4"          # body text on dark
DIM_D = "#9aa0b4"          # dim text on dark
HL_COLORS = ["#ffd23f", "#f7931a", "#ff8c00"]  # gold -> bitcoin orange -> ember
PHOTO = "/home/hatch/workspace/profile-images/brian-gina-together.jpg"


# ---------------- dark background ----------------
def dark_background():
    """Deep-charcoal vertical gradient — the trading-terminal canvas."""
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    c1, c2 = _hex(BG_TOP), _hex(BG_BOT)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    # faint warm glow top-center + cool ember wash bottom-right
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W // 2 - 460, -280, W // 2 + 460, 360], fill=(246, 147, 26, 34))
    gd.ellipse([W - 560, H - 460, W + 160, H + 120], fill=(255, 140, 0, 22))
    img = Image.alpha_composite(
        img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(70))).convert("RGB")
    return img


def _candle_shape(d, x, yc, w, body_h, wick, fill):
    """One candlestick: body rect + wick line, centered at (x, yc)."""
    d.line([(x, yc - body_h / 2 - wick), (x, yc + body_h / 2 + wick)],
           fill=fill, width=3)
    d.rectangle([x - w / 2, yc - body_h / 2, x + w / 2, yc + body_h / 2],
                fill=fill)


def crypto_backdrop(img):
    """Faint candlestick-chart texture along the edges + a giant ghost ₿.
    The crypto desk's signature backdrop — charts, not EKG/constellations."""
    rnd = random.Random(42)
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    # candlestick columns left + right edges
    for x in (70, 130):
        y = 200
        while y < H - 120:
            up = rnd.random() > 0.45
            bh = rnd.randint(18, 60)
            col = (22, 199, 132, 46) if up else (234, 57, 67, 46)
            _candle_shape(d, x + rnd.randint(-8, 8), y, 26, bh,
                          rnd.randint(8, 20), col)
            y += bh + rnd.randint(26, 54)
    for x in (W - 130, W - 70):
        y = 260
        while y < H - 120:
            up = rnd.random() > 0.45
            bh = rnd.randint(18, 60)
            col = (22, 199, 132, 46) if up else (234, 57, 67, 46)
            _candle_shape(d, x + rnd.randint(-8, 8), y, 26, bh,
                          rnd.randint(8, 20), col)
            y += bh + rnd.randint(26, 54)
    # giant ghost ₿ watermark, center — barely there
    f_big = font(FB, 640)
    t = "B"
    tw = d.textlength(t, font=f_big)
    gx, gy = (W - tw) / 2, 330
    d.text((gx, gy), t, font=f_big, fill=(246, 147, 26, 13))
    sw = 26
    d.line([(gx + tw * 0.32, gy + 40), (gx + tw * 0.32, gy + 560)],
           fill=(246, 147, 26, 13), width=sw)
    d.line([(gx + tw * 0.62, gy + 40), (gx + tw * 0.62, gy + 560)],
           fill=(246, 147, 26, 13), width=sw)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


# ---------------- emblem + glyphs ----------------
def coin_emblem(size=150):
    """Bitcoin-orange coin badge with a hand-built ₿ — the one emblem,
    standing watch top-right."""
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cx = cy = s / 2
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [cx - s * 0.47, cy - s * 0.47, cx + s * 0.47, cy + s * 0.47],
        fill=(246, 147, 26, 80))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s * 0.08)))
    d = ImageDraw.Draw(im)
    # coin face
    d.ellipse([s * 0.10, s * 0.10, s * 0.90, s * 0.90], fill=BTC_ORANGE)
    d.ellipse([s * 0.10, s * 0.10, s * 0.90, s * 0.90],
              outline="#c26a0a", width=max(3, s // 40))
    r2 = s * 0.335
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
              outline=(255, 255, 255, 110), width=2)
    # the ₿: bold B + two vertical strokes
    f = font(FB, int(s * 0.52))
    t = "B"
    tw = d.textlength(t, font=f)
    bx, by = cx - tw / 2, cy - s * 0.30
    d.text((bx, by), t, font=f, fill="white")
    sw = max(4, s // 26)
    for fx in (0.36, 0.60):
        sx = cx - tw / 2 + tw * fx
        d.line([(sx, cy - s * 0.30), (sx, cy + s * 0.30)],
               fill="white", width=sw)
    return im


def icon_candle(size=36, up=True):
    """Mini candlestick glyph for flanking the kicker."""
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = (22, 199, 132, 255) if up else (234, 57, 67, 255)
    _candle_shape(d, s / 2, s / 2, s * 0.42, s * 0.52, s * 0.18, col)
    return im


def kicker_crypto(img, y, text):
    """Kicker flanked by candle glyphs — the crypto template signature."""
    d = ImageDraw.Draw(img)
    kf = font(FB, 25)
    tw = d.textlength(text, font=kf) + 3 * (len(text) - 1)
    cx = img.size[0] / 2
    _centered(d, y, text, kf, BTC_ORANGE, tracking=3)
    g, r = icon_candle(36, up=True), icon_candle(36, up=False)
    img.paste(g, (int(cx - tw / 2 - 62), y - 2), g)
    img.paste(r, (int(cx + tw / 2 + 16), y - 2), r)
    return ImageDraw.Draw(img)


# ---------------- dark 3D headline ----------------
def headline_3d_dark(base, text, fnt, colors, depth=7):
    """Gradient face + 3D extrusion tuned for the dark canvas: the
    extrusion is near-black bronze so the depth reads against charcoal."""
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    bbox = tmp.textbbox((0, 0), text, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 24
    lw, lh = tw + pad * 2 + depth + 14, th + pad * 2 + depth + 18
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ox, oy = pad - bbox[0], pad - bbox[1]

    sh = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((ox + 5, oy + 9), text, font=fnt,
                            fill=(0, 0, 0, 170))
    layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(layer)

    for i in range(depth, 0, -1):
        d.text((ox + i, oy + i), text, font=fnt, fill=(30, 19, 8, 255))
    d.text((ox + depth, oy + depth), text, font=fnt, fill=(12, 7, 2, 255))

    n = len(colors)
    face = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
    fd = ImageDraw.Draw(face)
    mask = Image.new("L", (tw + 8, th + 8), 0)
    ImageDraw.Draw(mask).text((4 - bbox[0], 4 - bbox[1]), text, font=fnt,
                              fill=255)
    for yy in range(th + 8):
        t = yy / max(1, th + 7)
        seg = t * (n - 1)
        i = int(seg)
        f = seg - i
        c1 = _hex(colors[i])
        c2 = _hex(colors[min(i + 1, n - 1)])
        col = tuple(int(a + (b - a) * f) for a, b in zip(c1, c2))
        fd.line([(0, yy), (tw + 8, yy)], fill=col + (255,))
    face.putalpha(mask)
    hi = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
    ImageDraw.Draw(hi).text((4 - bbox[0], 4 - bbox[1]), text, font=fnt,
                            fill=(255, 255, 255, 70))
    hi.putalpha(mask.point(lambda v: int(v * 0.35)))
    face = Image.alpha_composite(face, hi)

    layer.alpha_composite(face, (ox - 4 + bbox[0], oy - 4 + bbox[1]))
    return layer, (lw, lh)


# ---------------- dark footer ----------------
def footer_dark(img, d, hashtag=None, dy=0, brand=None):
    """Same footer rhythm as the shared footer(), recolored for the dark
    canvas: light handles, gold hashtag line."""
    b = brand or CRYPTO_BRAND
    tag = hashtag if hashtag is not None else b.get("hashtag")
    d.line([(48, 840 + dy), (W - 48, 840 + dy)], fill=(120, 84, 30, 255),
           width=3)
    items = [(icon(kind, 48), handle) for kind, handle in b["handles"]]
    widths = [48 + 12 + d.textlength(h, font=font(FR, 20)) for _, h in items]
    total_w = sum(widths) + 36 * (len(items) - 1)
    x = (W - total_w) / 2
    y_ic = 852 + dy
    for (ic, handle), wdt in zip(items, widths):
        img.paste(ic, (int(x), y_ic), ic)
        d.text((x + 48 + 12, y_ic + 9), handle, font=font(FR, 20),
               fill="#cfd4e0")
        x += wdt + 36
    d = ImageDraw.Draw(img)
    bic = icon("blog", 48)
    url = b["blog_url"]
    f_blog = font(FB, 30)
    tw = d.textlength(url, font=f_blog)
    bx = (W - (48 + 14 + tw)) / 2
    img.paste(bic, (int(bx), 910 + dy), bic)
    d.text((bx + 48 + 14, 912 + dy), url, font=f_blog, fill="#f2f4fa")
    if tag:
        _centered(d, 962 + dy, tag, font(FB, 28), BTC_ORANGE)
    return img, ImageDraw.Draw(img)


# ---------------- main render ----------------
def render_crypto_meme(content, photo_path=None, out_path="meme.png",
                       brand=None, headline_size=None):
    b = brand or CRYPTO_BRAND
    img = crypto_backdrop(dark_background())
    d = ImageDraw.Draw(img)

    # brand bar
    pc = photo_card(photo_path)
    img.paste(pc, (48, 36), pc)
    # gold ring over the photo card (replaces the shared cyan ring)
    d.rounded_rectangle([48, 36, 48 + 148, 36 + 148], 28,
                        outline=BTC_ORANGE, width=4)
    x = 48 + 148 + 24
    wx = x
    for word, color in b["wordmark"]:
        f = font(FB, 46)
        d.text((wx, 44), word, font=f, fill=color)
        wx += d.textlength(word, font=f) + 10
    d.text((x, 104), b["tagline"], font=font(FR, 21), fill=DIM_D)

    # coin emblem standing watch, top right — the one emblem on the meme
    emb = coin_emblem(150)
    img.paste(emb, (W - 30 - 150, 22), emb)
    d = ImageDraw.Draw(img)

    # warm ember glow behind the headline
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W / 2 - 330, 180, W / 2 + 330, 430],
                                 fill=(246, 147, 26, 36))
    img = Image.alpha_composite(img.convert("RGBA"),
                                glow.filter(ImageFilter.GaussianBlur(40))).convert("RGB")
    d = ImageDraw.Draw(img)

    # kicker with candle glyphs
    d = kicker_crypto(img, 216, content["kicker"])

    # headline: gold gradient + dark 3D (auto-fit so nothing clips)
    size = headline_size or 92
    _tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > 40:
        f_big = font(FB, size)
        tw = _tmp.textlength(content["headline"], font=f_big)
        if tw + 2 * 24 + 7 + 14 + 24 <= W - 24:
            break
        size -= 2
    colors = content.get("grad_colors", HL_COLORS)
    hl, (lw, lh) = headline_3d_dark(img, content["headline"], f_big, colors)
    img.paste(hl, ((W - lw) // 2, 254), hl)
    # gold gradient divider under headline
    div = grad_rounded((440, 9), HL_COLORS, 4)
    img.paste(div, ((W - 440) // 2, 390), div)
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
                          fill=BTC_ORANGE)
            else:
                d.ellipse([_cx - _r, 416 - _r, _cx + _r, 416 + _r],
                          outline="#4a4a58", width=2)

    # cards: dark terminal cards, soft black shadow, gold edge
    cards = content["cards"]
    n = len(cards)
    gap, margin = 32, 48
    cw = (W - 2 * margin - gap * (n - 1)) / n
    cy0, ch = 424, 252
    for i, c in enumerate(cards):
        x = margin + i * (cw + gap)
        tint = c.get("tint", CARD_BG)
        d.rounded_rectangle([x + 6, cy0 + 10, x + cw + 6, cy0 + ch + 10], 26,
                            fill=(0, 0, 0, 170))
        d.rounded_rectangle([x, cy0, x + cw, cy0 + ch], 26, fill=tint,
                            outline=(120, 84, 30, 255), width=2)
        cx = x + cw / 2
        for txt, fnt, col, yy in [
            (c["tag"], font(FB, 19), DIM_D, cy0 + 24),
            (c["title"], font(FB, 30), INK_D, cy0 + 54),
            (c["price"], font(FB, 66), c["bar_color"], cy0 + 96),
        ]:
            tw = d.textlength(txt, font=fnt)
            d.text((cx - tw / 2, yy), txt, font=fnt, fill=col)
        t = c["sub"]
        tw = d.textlength(t, font=font(FR, 22))
        d.text((cx - tw / 2, cy0 + 178), t, font=font(FR, 22), fill=DIM_D)
        bx, bw, bh, by = x + 36, cw - 72, 24, cy0 + 214
        d.rounded_rectangle([bx, by, bx + bw, by + bh], 12,
                            fill=(42, 42, 54, 255))
        _gbar(img, [bx, by, bx + bw * c["bar_frac"], by + bh], c["bar_color"])
        d = ImageDraw.Draw(img)

    # optional counterpoint strip (dark variant)
    cp = content.get("counterpoint")
    dy = 0
    if cp:
        cs0, cs1 = 688, 758
        d.rounded_rectangle([48, cs0, W - 48, cs1], 16, fill="#20202a",
                            outline=BTC_ORANGE, width=2)
        _centered(d, cs0 + 8, cp["label"], font(FB, 19), DIM_D)
        _centered(d, cs0 + 34, cp["quote"], font(FB, 23), INK_D)
        dy = 68

    # punchline strip (garnet — Brian's birthstone; gold edge for crypto)
    py0, py1 = 700 + dy, 782 + dy
    d.rounded_rectangle([48, py0, W - 48, py1], 18, fill=GARNET_BG,
                        outline=BTC_ORANGE, width=2)
    _centered(d, py0 + 22, content["punchline"], font(FB, 29), YELLOW)

    # curiosity line
    if content.get("curiosity"):
        _centered(d, 804 + dy, content["curiosity"], font(FB, 26), INK_D)

    img, d = footer_dark(img, d, hashtag=content.get("hashtag"), dy=dy,
                         brand=b)

    img.save(out_path)
    return out_path


if __name__ == "__main__":
    render_crypto_meme(
        {
            "kicker": "THE CRYPTO DESK IS OPEN",
            "headline": "BUY FEAR. SELL GREED.",
            "cards": [
                {"tag": "BUY & HOLD", "title": "BITCOIN",
                 "price": "STACK", "sub": "digital gold • hold long",
                 "bar_frac": 0.9, "bar_color": CANDLE_GREEN},
                {"tag": "TRADING ONLY", "title": "ETHEREUM",
                 "price": "TRADE", "sub": "liquidity • catch movers",
                 "bar_frac": 0.55, "bar_color": BTC_ORANGE},
            ],
            "counterpoint": {
                "label": "THE SKEPTICS — EVERY SINGLE BEAR MARKET",
                "quote": "\"Crypto is dead. Again.\""},
            "punchline": "SUPPORT IS WHERE YOU BUY. RESISTANCE IS WHERE YOU SELL.",
            "curiosity": "Which coin are you stacking right now? Drop it below.",
            "series_day": 1,
        },
        photo_path=PHOTO,
        out_path="/home/hatch/workspace/your_files/memes/proofs/crypto-desk-proof-2026-10-06.png")
    print("wrote ~/workspace/your_files/memes/proofs/crypto-desk-proof-2026-10-06.png")
