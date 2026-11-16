#!/usr/bin/env python3
"""price_guard.py — DealsDesk price proficiency gate.

Brian's directive (2026-11-16): "I need dealsdesk to be 100% proficient
at finding prices of the specific items we want and not be confused by
scam, click bait, noise, etc..."

THE PROBLEM THIS FIXES: the desk's scout picked its "best" price as the
lowest STICKER price in the search results. That is exactly backwards
against deception: the lowest sticker in any hardware search is the
most likely to be a variant-menu floor (the $639 "B70" that was really
a $639 B50 in a menu whose B70 costs $2,509), an accessory (the $51
adapter board filed as an NVMe find, 2026-11-12), a for-parts unit, or
a shipping trap (low sticker, huge shipping — the scout never even
fetched the shipping cost). The seller blacklist gate existed but the
scout never called it. Seller feedback COUNT was never read, so a
100%-positive seller with zero sales looked the same as one with ten
thousand.

WHAT THIS MODULE IS: one deterministic screening function every price
path calls BEFORE a price is believed:

    screen_listing(title, price, shipping, seller, feedback_pct,
                   feedback_count, need, typical_sold, blocked)
        -> {"verdict": CLEAN | SUSPECT | TRAP, "reasons": [...],
            "total": price + shipping, ...}

    TRAP    — not the item, or not a working item, or a banned seller.
              Excluded from best-price selection and from captures.
    SUSPECT — might be real, but a named deception pattern is present
              (far below the sold market, zero-feedback seller, heavy
              shipping, lot listing). Never silently dropped and never
              called a find: it is captured labeled, a person verifies.
    CLEAN   — no pattern detected; the price may be ranked and used.

The guard judges the LISTING, not the deal: a clean $2,200 B70 is
CLEAN (and above target — the brief's job), a $45 M40 is SUSPECT
(below the sold floor is the classic scam/wrong-item shape).

All rules are deterministic text/number checks — no model calls, no
invented data. Where evidence is missing (no sold typical, no shipping
in the listing data) the guard says so in its notes instead of
guessing.

CLI:
    price_guard.py screen --title T --price P [--shipping S]
                          [--seller X] [--pct 100] [--count 45]
                          [--typical 196] [--target 191]
    price_guard.py selftest
"""
import argparse
import re
import sys

# ---------------------------------------------------------------- lexicon
MENU_WORDS = ("choose", "select from", "options", "variation", "variations")
BROKEN_PHRASES = (
    "for parts", "parts only", "not working", "not tested", "untested",
    "does not power", "no power", "parts or repair", "for repair",
    "salvage",
)
SAMPLE_PHRASES = (
    "engineering sample", "qualification sample", "sample cpu",
    "sample gpu", "sample chip",
)
ACCESSORY_ONLY_PHRASES = (
    "box only", "empty box", "heatsink only", "cooler only", "fan only",
    "bracket only", "shield only", "manual only", "cover only",
    "case only", "cable only", "adapter only",
)
# Nouns that name a part rather than the item. Gated by price (a part is
# priced like a part) or downgraded to SUSPECT when price says nothing.
ACCESSORY_NOUNS = (
    "adapter", "bracket", "caddy", "tray", "enclosure", "shield",
    "riser", "sled", "bezel", "shroud", "backplate",
)


def caps_in(title):
    """Capacities named in a title, in GB — ranges count as both ends
    (the scout's range-aware version; '16-32GB' -> {16, 32})."""
    out = set()
    t = title.lower()
    for a, b, unit in re.findall(r"(\d+)\s*-\s*(\d+)\s*(tb|gb)", t):
        out.add(int(a) * (1000 if unit == "tb" else 1))
        out.add(int(b) * (1000 if unit == "tb" else 1))
    for a, b, unit in re.findall(r"(\d+)\s*/\s*(\d+)\s*(tb|gb)", t):
        out.add(int(a) * (1000 if unit == "tb" else 1))
        out.add(int(b) * (1000 if unit == "tb" else 1))
    for num, unit in re.findall(r"(\d+)\s*(tb|gb)", t):
        out.add(int(num) * (1000 if unit == "tb" else 1))
    return out


def model_tokens(text):
    return set(re.findall(r"\b([a-z]\d{2})\b", text.lower()))


def need_context(subject, target=None, terms=None):
    """Build the screening context for one need: the model family it
    belongs to and the capacity it wants (if the subject names one)."""
    fam = model_tokens(subject or "")
    for t in terms or []:
        fam |= model_tokens(t)
    cap = None
    m = re.search(r"(\d+)\s*(tb|gb)", (subject or "").lower())
    if m:
        cap = int(m.group(1)) * (1000 if m.group(2) == "tb" else 1)
    return {"subject": subject, "target": target, "family": fam,
            "capacity_gb": cap}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def screen_listing(title, price, shipping=None, seller=None,
                   feedback_pct=None, feedback_count=None,
                   need=None, typical_sold=None, blocked=None):
    """Screen one listing. Returns verdict + reasons + the total price.
    Pure function when `blocked` is passed explicitly; otherwise the
    seller blacklist is consulted lazily (desk DB) and any failure to
    check reads as not-blocked, never as a crash."""
    title = title or ""
    t = title.lower()
    price = _f(price)
    shipping = _f(shipping)
    pct = _f(feedback_pct)
    reasons, notes = [], []
    verdict = "CLEAN"

    def trap(reason):
        nonlocal verdict
        verdict = "TRAP"
        reasons.append(reason)

    def suspect(reason):
        nonlocal verdict
        if verdict != "TRAP":
            verdict = "SUSPECT"
        reasons.append(reason)

    if price is None or price <= 0:
        trap("no usable price on the listing")
        price = price or 0.0
    total = price + (shipping or 0.0)

    # --- banned seller: the desk's one blacklist gate ----------------
    if blocked is None and seller:
        try:
            sys.path.insert(0, __file__.rsplit("/", 1)[0])
            from seller_blocklist import is_blocked
            blocked = bool(is_blocked(seller))
        except Exception:
            blocked = False
    if blocked:
        trap("seller is on the desk blacklist — excluded outright")

    # --- variant menu: sibling models or a capacity range ------------
    toks = model_tokens(title)
    fam = (need or {}).get("family") or set()
    if fam and (toks & fam) and (toks - fam):
        trap("variant menu — the title names "
             + "/".join(sorted(toks & fam)).upper()
             + " alongside other models ("
             + ", ".join(sorted(toks - fam)).upper()
             + "); the headline price is the cheapest variant, "
             "not this item")
    caps = caps_in(title)
    if len(caps) > 1:
        trap("capacity range in the title ("
             + "–".join(str(c) for c in sorted(caps))
             + " GB) — the headline price is a menu floor")
    want_cap = (need or {}).get("capacity_gb")
    if want_cap and caps and want_cap not in caps:
        trap(f"title capacity {sorted(caps)} GB does not match the "
             f"wanted {want_cap} GB")

    # --- broken / sample silicon -------------------------------------
    for ph in BROKEN_PHRASES:
        if ph in t:
            trap(f"listed as '{ph}' — not a working item")
            break
    if any(ph in t for ph in SAMPLE_PHRASES) or (
            re.search(r"\b(es|qs)\b", t)
            and re.search(r"\d", title)):
        trap("engineering/qualification sample — not retail silicon")

    # --- accessory, not the item -------------------------------------
    for ph in ACCESSORY_ONLY_PHRASES:
        if ph in t:
            trap(f"'{ph}' — an accessory or packaging, not the item")
            break
    ref_price = _f((need or {}).get("target")) or _f(typical_sold)
    for noun in ACCESSORY_NOUNS:
        # "with bracket" = the item plus a bracket; only a bare noun
        # naming counts.
        bare = re.search(r"(?<!with )\b" + noun + r"\b", t)
        if not bare:
            continue
        if ref_price and total < 0.30 * ref_price:
            trap(f"title names a '{noun}' and the price (${total:,.2f}) "
                 f"is part money, not item money — an accessory, "
                 f"not the item")
        else:
            suspect(f"title names a possible accessory ('{noun}') — "
                    "verify the item itself is what is sold")
        break

    # --- wording that hides the real offer ---------------------------
    if any(w in t for w in MENU_WORDS):
        suspect("menu wording in the title — confirm the price is for "
                "the wanted variant")
    if "read description" in t or "read the description" in t:
        suspect("'read description' in the title — the catch is "
                "usually in the text")
    if re.search(r"\blot\b", t) or "bulk only" in t:
        suspect("lot/bulk listing — per-unit price needs a person "
                "to check it")
    if " as-is" in t or " as is" in t:
        suspect("sold as-is — no working guarantee")

    # --- shipping: the total is the price ----------------------------
    if shipping is None:
        notes.append("shipping not shown in the listing data — the "
                     "total may be higher")
    elif price and shipping >= 0.25 * price:
        suspect(f"shipping ${shipping:,.2f} is "
                f"{shipping / price * 100:.0f}% of the item price — "
                "judge the total, not the sticker")
    target = _f((need or {}).get("target"))
    if target and price <= target < total:
        suspect(f"under target on the sticker only — the total "
                f"${total:,.2f} is over the ${target:,.2f} target")

    # --- far below the sold market: scam / wrong-item shape ----------
    typical = _f(typical_sold)
    if typical and total:
        ratio = total / typical
        if ratio < 0.30:
            suspect(f"total is {ratio * 100:.0f}% of the typical sold "
                    f"price (${typical:,.2f}) — far below market is "
                    "the classic scam / wrong-item pattern; verify "
                    "by hand before trusting it")
        elif ratio < 0.50:
            suspect(f"total is {ratio * 100:.0f}% of the typical sold "
                    f"price (${typical:,.2f}) — well below market; "
                    "verify before trusting")

    # --- seller risk ---------------------------------------------------
    if feedback_count is not None:
        try:
            fc = int(feedback_count)
            if fc == 0:
                suspect("seller has zero feedback")
            elif fc < 10:
                suspect(f"seller has only {fc} feedback")
        except (TypeError, ValueError):
            pass
    if pct is not None and pct < 98.0:
        suspect(f"seller feedback is {pct:.1f}% positive")

    return {"verdict": verdict, "reasons": reasons, "notes": notes,
            "total": round(total, 2), "sticker": price,
            "shipping": shipping}


def guard_line(res):
    """The one-line PRICE GUARD statement that rides in a capture."""
    total = res["total"]
    if res["verdict"] == "CLEAN":
        ship = (f"sticker ${res['sticker']:,.2f} + shipping "
                f"${res['shipping']:,.2f}"
                if res["shipping"] is not None
                else "shipping not shown in listing data")
        return (f"PRICE GUARD: CLEAN — total ${total:,.2f} ({ship}); "
                "no scam, menu, accessory, or condition traps detected.")
    joined = "; ".join(res["reasons"])
    if res["verdict"] == "SUSPECT":
        return (f"PRICE GUARD: SUSPECT — total ${total:,.2f}. {joined}. "
                "A person verifies before this price is trusted.")
    return (f"PRICE GUARD: TRAP — {joined}. "
            "Excluded from best-price selection.")


def typical_sold_for(need):
    """The desk's typical sold price for a need, from the pricing
    brief's own evidence gather: median of recorded solds first, then
    the reference average, then the market table median. None when the
    desk holds no evidence — never invented."""
    try:
        sys.path.insert(0, __file__.rsplit("/", 1)[0])
        import pricing_brief
        terms = pricing_brief.need_terms(need)
        with pricing_brief._conn() as conn, conn.cursor() as cur:
            ev = pricing_brief.gather(cur, terms, need.get("subject"))
        solds = sorted(float(s["price"]) for s in ev["solds"])
        if solds:
            return solds[len(solds) // 2]
        if ev["reference"]:
            return float(ev["reference"]["avg_price"])
        if ev["market"] and ev["market"]["median_sold_price"]:
            return float(ev["market"]["median_sold_price"])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- selftest
def selftest():
    failures = []

    def check(name, got, want):
        ok = got == want
        print(f"  [{'ok' if ok else 'FAIL'}] {name}: {got}"
              + ("" if ok else f" (want {want})"))
        if not ok:
            failures.append(name)

    nvme = need_context("Used 4TB Gen4 NVMe SSD (M.2 2280)",
                        target=460.0,
                        terms=["Samsung 990 PRO 4TB", "WD SN850X 4TB"])
    m40 = need_context("Tesla M40 24GB GPU", target=191.0,
                       terms=["Tesla M40 24GB"])
    b70 = need_context("Intel Arc Pro B70 32GB GPU", target=1049.0,
                       terms=["Intel Arc Pro B70"])
    board = need_context("Gigabyte MZ32-AR0 rev 1.x motherboard",
                         target=355.0, terms=["MZ32-AR0"])

    # 1. The Gunnir menu that produced the "$639 B70" (2026-11-16).
    r = screen_listing(
        "Gunnir Intel Arc Pro B50/B60/B65/B70 Xe2 AI Professional "
        "GPU 16-32GB", 639.0, seller="pro_gaming_pc_store",
        feedback_pct=100.0, feedback_count=45, need=b70)
    check("gunnir variant menu is a trap", r["verdict"], "TRAP")

    # 2. The $51 adapter board filed as an NVMe find (2026-11-12).
    r = screen_listing("M.2 NVMe to PCIe adapter board x4 card", 51.0,
                       need=nvme)
    check("adapter board is a trap", r["verdict"], "TRAP")

    # 3. Capacity range listing.
    r = screen_listing("Samsung 990 PRO NVMe SSD 1TB-4TB Gen4", 250.58,
                       need=nvme)
    check("capacity range is a trap", r["verdict"], "TRAP")

    # 4. The one sure thing: techni-build FX900 Pro, documented health.
    r = screen_listing("HP FX900 Pro 4TB NVMe SSD Gen4", 449.99,
                       shipping=0.0, seller="techni-build",
                       feedback_pct=100.0, feedback_count=120,
                       need=nvme)
    check("techni-build fx900 pro is clean", r["verdict"], "CLEAN")

    # 5. The real M40 lead: $115.94 against a $196 typical sold.
    r = screen_listing("NVIDIA Tesla M40 24GB GDDR5 GPU", 115.94,
                       shipping=0.0, feedback_pct=100.0,
                       feedback_count=250, need=m40, typical_sold=196.0)
    check("m40 lead at 59% of typical is clean", r["verdict"], "CLEAN")

    # 6. Same card at $45: scam/wrong-item shape.
    r = screen_listing("NVIDIA Tesla M40 24GB GDDR5 GPU", 45.0,
                       shipping=0.0, feedback_pct=100.0,
                       feedback_count=250, need=m40, typical_sold=196.0)
    check("m40 at 23% of typical is suspect", r["verdict"], "SUSPECT")

    # 7. For-parts unit.
    r = screen_listing("NVIDIA Tesla M40 24GB for parts not working",
                       60.0, need=m40, typical_sold=196.0)
    check("for-parts m40 is a trap", r["verdict"], "TRAP")

    # 8. Bracket priced like a bracket.
    r = screen_listing("Bracket for Tesla M40 24GB GPU", 19.0,
                       need=m40, typical_sold=196.0)
    check("m40 bracket is a trap", r["verdict"], "TRAP")

    # 9. Zero-feedback seller on a 990 PRO (the suraottik-0 shape).
    r = screen_listing("Samsung 990 PRO 4TB NVMe SSD", 300.0,
                       shipping=0.0, feedback_pct=0.0, feedback_count=0,
                       need=nvme)
    check("zero-feedback seller is suspect", r["verdict"], "SUSPECT")

    # 10. Shipping trap: cheap sticker, heavy shipping.
    r = screen_listing("WD SN850X 4TB NVMe SSD Gen4", 99.0,
                       shipping=260.0, feedback_pct=100.0,
                       feedback_count=80, need=nvme)
    check("shipping trap is suspect", r["verdict"], "SUSPECT")
    check("shipping trap total is sticker+shipping", r["total"], 359.0)

    # 11. Sticker under target, total over.
    r = screen_listing("Samsung 990 PRO 4TB NVMe SSD", 400.0,
                       shipping=120.0, feedback_pct=100.0,
                       feedback_count=80, need=nvme)
    check("sticker-under-total-over is suspect", r["verdict"],
          "SUSPECT")

    # 12. I/O shield sold against a motherboard need (Brian, 2026-09-30).
    r = screen_listing("I/O shield for Gigabyte MZ32-AR0 motherboard",
                       25.0, need=board)
    check("io shield is a trap", r["verdict"], "TRAP")

    # 13. Hard-drive caddy sold against a drive need.
    r = screen_listing("2.5 inch hard drive caddy tray", 15.0,
                       need=nvme)
    check("drive caddy is a trap", r["verdict"], "TRAP")

    # 14. Blacklisted seller.
    r = screen_listing("Samsung 990 PRO 4TB NVMe SSD", 449.0,
                       shipping=0.0, need=nvme, blocked=True)
    check("blacklisted seller is a trap", r["verdict"], "TRAP")

    # 15. A real B70 at a real price is clean (guard judges the
    # listing, not the deal).
    r = screen_listing("Intel Arc Pro B70 32GB GPU", 2200.0,
                       shipping=0.0, seller="the_fourth",
                       feedback_pct=100.0, feedback_count=500,
                       need=b70)
    check("real b70 at $2,200 is clean", r["verdict"], "CLEAN")

    # 16. "With custom cooler" must NOT trip the accessory rule — the
    # M40 sold at $195 in exactly this shape (2026-10-10).
    r = screen_listing("NVIDIA Tesla M40 24GB GPU with custom cooler",
                       195.0, shipping=0.0, feedback_pct=100.0,
                       feedback_count=300, need=m40, typical_sold=196.0)
    check("m40 with custom cooler is clean", r["verdict"], "CLEAN")

    # 17. Engineering sample.
    r = screen_listing("AMD EPYC 7763 ES engineering sample CPU",
                       180.0, need=None)
    check("engineering sample is a trap", r["verdict"], "TRAP")

    # 18. Empty box.
    r = screen_listing("Samsung 990 PRO 4TB empty box only", 30.0,
                       need=nvme)
    check("empty box is a trap", r["verdict"], "TRAP")

    # 19. Slash capacities — the live catch from the first guarded
    # scout run (2026-11-16): "M40 12/24GB" named both cards and the
    # guard's first version called it CLEAN.
    r = screen_listing(
        "NVIDIA TESLA M40 12/24GB GDDR5 PCI-E 3.0X16 GPU CARD CUDA "
        "PG600", 135.93, shipping=0.0, feedback_pct=100.0,
        feedback_count=900, need=m40, typical_sold=196.0)
    check("slash-capacity title is a trap", r["verdict"], "TRAP")

    print("PRICE GUARD SELFTEST:", "OK" if not failures else
          f"FAILED ({len(failures)}): {failures}")
    return 0 if not failures else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="price_guard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("screen")
    sc.add_argument("--title", required=True)
    sc.add_argument("--price", required=True, type=float)
    sc.add_argument("--shipping", type=float)
    sc.add_argument("--seller")
    sc.add_argument("--pct", type=float)
    sc.add_argument("--count", type=int)
    sc.add_argument("--typical", type=float)
    sc.add_argument("--target", type=float)
    sc.add_argument("--subject")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    need = need_context(args.subject, target=args.target) \
        if args.subject else None
    res = screen_listing(args.title, args.price, shipping=args.shipping,
                         seller=args.seller, feedback_pct=args.pct,
                         feedback_count=args.count, need=need,
                         typical_sold=args.typical)
    print(guard_line(res))
    for n in res["notes"]:
        print("  note:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
