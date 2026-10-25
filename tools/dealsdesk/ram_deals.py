#!/usr/bin/env python3
"""ram_deals.py — DealsDesk RAM $/GB market-flowing deal caps + scanner + alerts.

PURPOSE: Brian's rule (2026-10-25): RAM purchases need $/GB MAXIMUMS THAT FLOW
         WITH THE MARKET — the point is deal-hunting, not market-price buying.
         $2,272 for 128GB DDR5 on Jawa ($17.75/GB) was the trigger.
RULE:    cap_usd_per_gb(class) = market_ref_usd_per_gb(class) x factor(class).
         Factors (chosen by Muse at Brian's delegation, 2026-10-25):
           DDR5 classes 0.70 — spike-inflated market, demand a deeper cut.
           DDR4 classes 0.75 — already near honest pricing, 75% still finds deals.
MARKET:  Each class ref is ANCHORED to a seed street price from Brian's
         verified checks at the shape he buys (>=64GB kits), and FLOWS with
         the market by ratio: ref = seed_ref x (recent_median / baseline_
         median), where the medians are $/GB of >=64GB sightings (baseline =
         the sighting median when the anchor was set; recent = last 30 days,
         needs >=8 obs). Raw ask medians mix sizes/conditions and read high;
         the anchor keeps Brian's like-for-like street price as the base.
DDR3:    Server DDR3 (Gen8/Mantis fleet) added 2026-10-25 at Brian's order
         ("do a big scan and then put the best sources coded into
         dealsdesk"). Big scan of 694 unique DDR3 listings set the seeds:
         DDR3 RDIMM $1.10/GB (>=64GB kit median $1.09), DDR3 LRDIMM
         $1.30/GB (>=64GB median $1.29; LRDIMM = the 32GB-stick path to
         512GB in a Gen8), factor 0.75 like DDR4. Best sources by kept/junk
         per query: PicClick "ddr3 rdimm 256gb lot" (134/3), "ddr3 ecc reg
         rdimm" (81/4), "ddr3 server memory lot" (71/4), "pc3-12800r 16gb"
         (67/1), "ddr3 lrdimm 32gb" (69/7). DROPPED: "ddr3 rdimm 128gb kit"
         (21 junk of 72 — variant traps; covered by the others). Jawa DDR3
         is 19 small consumer listings, zero server RAM — not a DDR3
         source, and the scanner does not fetch it. CONSUMER SCRAPS RULE
         (Brian, 2026-10-25): no consumer scraps in the price database or
         coded into DealsDesk — consumer/SO-DIMM/ECC-UDIMM DDR3 is never
         classified, never logged; the big-scan recon measured those
         segments only to exclude them. DDR3
         alert gates: RDIMM total >=64GB AND >=16GB per stick (sticks
         <=8GB are rejected as parts per Brian's sourcing floor — small-
         stick lots are sightings, never alerts); LRDIMM total >=32GB.
SOURCES: Jawa public API (categoryIds=4 Memory, paginated) + PicClick (eBay)
         via picclick_rack_search. Every classified listing is stored in
         dealsdesk.ram_sightings (the market time series) and mirrored to
         public.price_history. Out-of-stock items are never sightings.
ALERTS:  A listing with total >=32GB and $/GB <= cap is a DEAL: row in
         dealsdesk.ram_deal_alerts (deduped 14d by url/title+price) + a
         message in public.successbrian_outbox — DealsDesk's own alert sink,
         the same one build_price_alerts uses (feeds Brian's digest).
         Delivery lives INSIDE DealsDesk (Brian's ruling, 2026-10-25: coded
         into the desk, never scheduled from a Muse). `pending-alerts` /
         `mark-reported` remain as manual inspection utilities only.
         NOTHING AUTO-BUYS.
CALLED BY: systemd ram-deals.timer (every 4h) running `scan`.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/ram_deals.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/ram_deals.py (k11-alpha)
MODES:   seed | caps | scan | pending-alerts | mark-reported ID [ID...] | selftest
"""

import json
import logging
import re
import subprocess
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/home/dealsdesk/scripts")
sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [ram_deals] %(message)s")
LOG = logging.getLogger("ram_deals")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126 Safari/537.36"}

# ram_class -> (factor, seed_ref_usd_per_gb, seed_basis)
CLASSES = {
    "ddr5_udimm": (0.70, 17.00,
                   "seed: median of verified desktop DDR5 kit sightings, "
                   "Newegg catalog + Jawa live, 2026-10-24/25"),
    "ddr5_sodimm": (0.70, 15.50,
                    "seed: verified DDR5 SO-DIMM kit checks, 2026-10-20 "
                    "(PNY 64GB $799.95 / Crucial 64GB $1,002.57 / 32GB $549.99)"),
    "ddr4_rdimm": (0.75, 1.90,
                   "seed: DDR4 RDIMM pull kits 8x16GB $180-300 (128GB), "
                   "SP3 build spec 2026-10-21"),
    "ddr4_consumer": (0.75, 5.70,
                      "seed: used DDR4 kit market midpoint $5.7/GB, "
                      "ram_price_reference.json 2026-10-20"),
    "ddr3_rdimm": (0.75, 1.10,
                   "seed: big DDR3 scan 2026-10-25: >=64GB RDIMM kit median "
                   "$1.09/GB across 694 unique DDR3 listings (PicClick/eBay)"),
    "ddr3_lrdimm": (0.75, 1.30,
                    "seed: big DDR3 scan 2026-10-25: >=64GB LRDIMM median "
                    "$1.29/GB (32GB-stick path to 512GB Gen8 configs)"),
}

MIN_ALERT_GB = 32        # alerts only for kit-size listings
MIN_MARKET_GB = 64       # market medians use the shape Brian buys (>=64GB)
MARKET_WINDOW_DAYS = 30
MARKET_MIN_OBS = 8
DEDUPE_DAYS = 14

JAWA_QUERIES = [("DDR5", 8), ("DDR4", 8), ("RDIMM", 4)]
PICCLICK_QUERIES = [
    "ddr5 64gb 2x32gb kit",
    "ddr5 32gb 2x16gb kit",
    "ddr5 sodimm 64gb 2x32gb",
    "ddr4 rdimm 64gb ecc reg",
    "ddr4 rdimm 128gb ecc reg",
    "ddr4 64gb 2x32gb kit",
    # DDR3 best sources (big scan 2026-10-25, kept/junk in docstring)
    "ddr3 rdimm 256gb lot",
    "ddr3 ecc reg rdimm",
    "ddr3 server memory lot",
    "pc3-12800r 16gb",
    "ddr3 lrdimm 32gb",
]

EXCLUDE = re.compile(
    r"ssd|nvme|hard drive|solid state|motherboard|graphics card|video card|"
    r"gaming pc|gaming laptop|windows 1[01]|win1[01]|poweredge|proliant|"
    r"optiplex|thinkpad|for parts|no ram|without ram|case only|empty box|"
    r"non-?working|not working|untested|defective|faulty|broken|as[ -]is|"
    r"optane|dcpm|persistent memory|nvdimm",
    re.I,
)

# Below this $/GB a "price" is a data error (multi-variation listing showing
# one stick's price, auction start, etc.) — record the sighting, never alert.
# The binding floor is relative: a real deal lives between 35% and factor% of
# market; below 35% of market the price is bad data, not a deal.
MIN_PLAUSIBLE_PER_GB = {
    "ddr5_udimm": 2.00, "ddr5_sodimm": 2.00,
    "ddr4_rdimm": 0.50, "ddr4_consumer": 1.00,
    "ddr3_rdimm": 0.20, "ddr3_lrdimm": 0.20,
}
MIN_PLAUSIBLE_FRACTION = 0.35

# ---------------------------------------------------------------- DB helpers

def psql(sql, write=False):
    args = ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:300])
        return [] if not write else False
    if write:
        return True
    rows = []
    for line in r.stdout.strip().split("\n"):
        if line.strip():
            rows.append(line.split("\x1f"))
    return rows


def esc(s):
    return (s or "").replace("'", "''")


def median(vals):
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0

# ---------------------------------------------------------------- classifier

def parse_total_gb(title):
    """Total kit GB from a listing title, or None."""
    t = title.replace(",", "")
    # '64GB (2 x 32GB)' / '64 GB (2x32)'
    m = re.search(r"(\d{2,3})\s*GB\s*\(\s*(\d+)\s*[xX]\s*(\d+)", t)
    if m:
        return int(m.group(1))
    # '2x32GB' / '4 x 16GB' kit notation; bulk lots go higher (16x16GB,
    # 37x8GB) — allowed for small server sticks, capped at 72 sticks.
    m = re.search(r"(\d+)\s*[xX]\s*(\d+)\s*GB", t)
    if m:
        n, per = int(m.group(1)), int(m.group(2))
        if 1 < n <= 8 and per in (4, 8, 16, 24, 32, 48, 64):
            return n * per
        if 8 < n <= 72 and per in (4, 8, 16, 32):
            return n * per
    # '128GB kit' / '64GB DDR5' single figure
    m = re.search(r"(\d{2,3})\s*GB", t)
    if m:
        gb = int(m.group(1))
        if gb in (16, 24, 32, 48, 64, 96, 128, 192, 256):
            return gb
    # Bulk-lot totals ('Lot of 37 ... 296GB total'): largest figure >=64GB.
    if re.search(r"\bLOT\b|\bTOTAL\b", t.upper()):
        figs = [int(x) for x in re.findall(r"(\d{2,3})\s*GB", t)]
        big = [f for f in figs if f >= 64]
        if big:
            return max(big)
    return None


def per_stick_gb(title):
    """Per-stick GB from KxS notation; single-stick listings = their total.
    Lot titles without KxS ('Lot of 37 Samsung 8GB ... 296GB') use the
    smaller GB figure as the stick size."""
    m = re.search(r"(\d+)\s*[xX]\s*(\d+)\s*GB", title.replace(",", ""))
    if m:
        return int(m.group(2))
    if "LOT" in title.upper():
        total = parse_total_gb(title)
        figs = [int(x) for x in re.findall(r"(\d+)\s*GB", title)]
        smaller = [f for f in figs if total and f < total]
        if smaller:
            return max(smaller)
    return parse_total_gb(title)


def classify(title):
    """Return (ram_class, total_gb) or None if not a RAM kit we track."""
    if not title or EXCLUDE.search(title):
        return None
    t = title.upper()
    if "GDDR" in t or "DDR2" in t:
        return None
    # Multi-variation 'lot' listings name many sizes; their price belongs to
    # one unknown variant — unusable as a sighting or an alert.
    figures = set(re.findall(r"(\d+)\s*GB", t)) | \
        set(re.findall(r"(\d+)\s*G(?![A-Za-z])", t))
    if len(figures) >= 3:
        return None
    gen = None
    if "DDR5" in t or "PC5" in t:
        gen = 5
    elif "DDR4" in t or "PC4" in t:
        gen = 4
    elif "DDR3" in t or re.search(r"PC3L?-?\d", t):
        gen = 3
    if gen is None:
        return None
    gb = parse_total_gb(title)
    if gb is None or gb < 8:
        return None
    if gen == 3:
        # Server DDR3 only (fleet Gen8/Mantis): consumer, SO-DIMM and ECC
        # UDIMM DDR3 are not tracked.
        if re.search(r"SO-?DIMM|204[ -]?PIN|LAPTOP|UNBUFFERED|UDIMM", title, re.I):
            return None
        if re.search(r"LRDIMM|LOAD\s*REDUCED|14900L|12800L", title, re.I):
            return ("ddr3_lrdimm", gb)
        if re.search(r"RDIMM|REGISTERED|\bREG\b|ECC|\d{4,5}R\b", title, re.I):
            return ("ddr3_rdimm", gb)
        return None
    if gen == 5:
        if re.search(r"SO-?DIMM|260[ -]?PIN|LAPTOP", title, re.I):
            return ("ddr5_sodimm", gb)
        return ("ddr5_udimm", gb)
    # DDR4
    if re.search(r"RDIMM|REG(ISTERED)?\b.*ECC|ECC\s*REG", title, re.I) or \
       (re.search(r"\bREG\b|REGISTERED", title, re.I) and "ECC" in t):
        return ("ddr4_rdimm", gb)
    return ("ddr4_consumer", gb)


# ---------------------------------------------------------------- sources

def fetch_jawa():
    out = []
    for q, pages in JAWA_QUERIES:
        for page in range(1, pages + 1):
            url = ("https://www.jawa.gg/api/search?q=" + urllib.parse.quote(q)
                   + f"&categoryIds=4&page={page}")
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode("utf-8", "ignore"))
            except Exception as e:
                LOG.warning("jawa fetch failed q=%s p=%s: %s", q, page, e)
                break
            prods = data.get("products") or []
            if not prods:
                break
            for p in prods:
                if p.get("is_sold_out"):
                    continue
                qty = p.get("quantity_available")
                price = (p.get("price") or 0) / 100.0
                if price <= 0:
                    continue
                out.append({
                    "title": p.get("name") or "",
                    "price": price,
                    "source": "jawa",
                    "url": "https://www.jawa.gg" + (p.get("url") or ""),
                    "seller": (p.get("user") or {}).get("displayed_name") or "",
                    "stock_note": (f"ONLY {qty} LEFT" if qty == 1
                                   else (f"{qty} available" if qty else "")),
                })
    return out


def fetch_picclick():
    try:
        import picclick_rack_search as finder
    except Exception as e:
        LOG.warning("picclick module unavailable: %s", e)
        return []
    out = []
    for q in PICCLICK_QUERIES:
        try:
            html = finder.fetch_search(q)
            for l in finder.parse_listings(html):
                if l.get("price") and l.get("name"):
                    out.append({
                        "title": l["name"], "price": float(l["price"]),
                        "source": "picclick_ebay",
                        "url": l.get("url") or "", "seller": "",
                        "stock_note": "",
                    })
        except Exception as e:
            LOG.warning("picclick fetch failed q=%s: %s", q, e)
    return out


# ---------------------------------------------------------------- core logic

def refresh_market():
    """Flow each class reference with the market by ratio against its anchor
    baseline; cap = ref x factor. Returns {class: (ref, cap)}."""
    caps = {}
    for row in psql("SELECT ram_class, factor, seed_ref_usd_per_gb, "
                    "baseline_median, ref_usd_per_gb "
                    "FROM dealsdesk.ram_market_reference"):
        ram_class, factor = row[0], float(row[1])
        seed_ref = float(row[2]) if row[2] else float(row[4])
        baseline = float(row[3]) if row[3] else None
        ref = float(row[4])
        rows = psql(
            f"""SELECT usd_per_gb FROM dealsdesk.ram_sightings
                WHERE ram_class = '{ram_class}' AND total_gb >= {MIN_MARKET_GB}
                  AND seen_at > NOW() - INTERVAL '{MARKET_WINDOW_DAYS} days'""")
        obs = [float(r[0]) for r in rows]
        if baseline and len(obs) >= MARKET_MIN_OBS:
            recent = median(obs)
            new_ref = round(seed_ref * recent / baseline, 3)
            if abs(new_ref - ref) > 0.001:
                LOG.info("%s ref %.3f -> %.3f (median %.2f vs baseline %.2f, n=%d)",
                         ram_class, ref, new_ref, recent, baseline, len(obs))
            ref = new_ref
        cap = round(ref * factor, 3)
        psql(f"""UPDATE dealsdesk.ram_market_reference
                 SET ref_usd_per_gb = {ref}, cap_usd_per_gb = {cap},
                     obs_count = {len(obs)}, updated_at = NOW()
                 WHERE ram_class = '{ram_class}'""", write=True)
        caps[ram_class] = (ref, cap)
    return caps


def record_sighting(ram_class, item):
    gb = item["gb"]
    per = round(item["price"] / gb, 3)
    psql(f"""INSERT INTO dealsdesk.ram_sightings
             (ram_class, title, total_gb, price, usd_per_gb, source, url, seller)
             VALUES ('{ram_class}', '{esc(item['title'][:250])}', {gb},
                     {item['price']}, {per}, '{esc(item['source'])}',
                     '{esc(item['url'][:500])}', '{esc(item['seller'][:120])}')""",
         write=True)
    psql(f"""INSERT INTO public.price_history (item_name, price, source)
             VALUES ('{esc(item['title'][:250])}', {item['price']},
                     'ram_deals:{esc(item['source'])}')""", write=True)
    return per


def already_alerted(item):
    rows = psql(
        f"""SELECT 1 FROM dealsdesk.ram_deal_alerts
            WHERE alerted_at > NOW() - INTERVAL '{DEDUPE_DAYS} days'
              AND ((url <> '' AND url = '{esc(item['url'][:500])}')
                   OR (title = '{esc(item['title'][:250])}' AND price = {item['price']}))
            LIMIT 1""")
    return bool(rows)


CLASS_LABEL = {
    "ddr5_udimm": "DDR5 desktop",
    "ddr5_sodimm": "DDR5 SO-DIMM",
    "ddr4_rdimm": "DDR4 RDIMM ECC",
    "ddr4_consumer": "DDR4 consumer",
    "ddr3_rdimm": "DDR3 RDIMM ECC",
    "ddr3_lrdimm": "DDR3 LRDIMM",
}

# Per-class alert gates beyond price: minimum total GB, and for DDR3 RDIMM a
# minimum per-stick size (sticks <=8GB are rejected as parts — Brian's
# sourcing floor; small-stick lots still log as sightings).
MIN_ALERT_GB_BY_CLASS = {"ddr3_rdimm": 64, "ddr3_lrdimm": 32}
MIN_STICK_GB_BY_CLASS = {"ddr3_rdimm": 16}


def alert_eligible(ram_class, title, gb):
    if gb < MIN_ALERT_GB_BY_CLASS.get(ram_class, MIN_ALERT_GB):
        return False
    min_stick = MIN_STICK_GB_BY_CLASS.get(ram_class)
    if min_stick:
        per = per_stick_gb(title)
        if per is not None and per < min_stick:
            return False
    return True


def format_alert(ram_class, item, ref, cap):
    per = item["price"] / item["gb"]
    pct = per / ref * 100.0
    under = 100.0 - pct
    lines = [
        f"RAM DEAL - {CLASS_LABEL.get(ram_class, ram_class)}",
        f"{item['title'][:110]} - ${item['price']:,.2f} = ${per:,.2f}/GB "
        f"({item['gb']}GB total)",
        f"Market is ${ref:,.2f}/GB -> this is {under:.0f}% under. "
        f"Cap: ${cap:,.2f}/GB. DEAL.",
        f"Source: {item['source']}" + (f" - seller {item['seller']}" if item["seller"] else ""),
    ]
    if item.get("stock_note"):
        lines.append(item["stock_note"])
    if item.get("url"):
        lines.append(item["url"])
    lines.append("Reply BUY and it goes to checkout for your approval. "
                 "Nothing auto-buys.")
    return "\n".join(lines)


def fire_alert(ram_class, item, ref, cap):
    per = round(item["price"] / item["gb"], 3)
    pct = round(per / ref * 100.0, 1)
    msg = format_alert(ram_class, item, ref, cap)
    ok = psql(
        f"""INSERT INTO dealsdesk.ram_deal_alerts
            (ram_class, title, total_gb, price, usd_per_gb, market_ref,
             cap_usd_per_gb, pct_of_market, source, url, seller, stock_note)
            VALUES ('{ram_class}', '{esc(item['title'][:250])}', {item['gb']},
                    {item['price']}, {per}, {ref}, {cap}, {pct},
                    '{esc(item['source'])}', '{esc(item['url'][:500])}',
                    '{esc(item['seller'][:120])}', '{esc(item.get('stock_note', '')[:80])}')
            RETURNING id""")
    if not ok:
        return False
    psql(f"""INSERT INTO public.successbrian_outbox (agent, message_text, priority)
             VALUES ('dealsdesk', '{esc(msg)}', 3)""", write=True)
    LOG.info("DEAL FIRED: %s", msg.split("\n")[1])
    return True


def scan():
    caps = refresh_market()
    raw = fetch_jawa() + fetch_picclick()
    seen_urls = set()
    sightings = deals = 0
    for item in raw:
        key = item["url"] or (item["title"], item["price"])
        if key in seen_urls:
            continue
        seen_urls.add(key)
        c = classify(item["title"])
        if not c:
            continue
        ram_class, gb = c
        item["gb"] = gb
        per = record_sighting(ram_class, item)
        sightings += 1
        ref, cap = caps.get(ram_class, (0, 0))
        floor = max(MIN_PLAUSIBLE_PER_GB.get(ram_class, 0),
                    MIN_PLAUSIBLE_FRACTION * ref)
        if per < floor:
            LOG.info("implausible price skipped: $%.2f/GB (floor $%.2f) %s",
                     per, floor, item["title"][:70])
            continue
        if (alert_eligible(ram_class, item["title"], gb) and per <= cap
                and item["price"] >= 30 and not already_alerted(item)):
            if fire_alert(ram_class, item, ref, cap):
                deals += 1
    LOG.info("scan done: %d raw, %d sightings, %d new deal(s)",
             len(raw), sightings, deals)
    psql(f"""INSERT INTO system_operations_log (subsystem, action_type, status, payload)
             VALUES ('ram_deals', 'scan', 'OK',
                     jsonb_build_object('raw', {len(raw)}, 'sightings', {sightings},
                                        'deals', {deals}))""", write=True)
    # Seller/business capture -> people_unified + AnythingLLM (Brian's
    # integration order, 2026-10-25). Guarded: capture never fails a scan.
    try:
        import seller_capture
        seller_capture.run()
    except Exception as e:
        LOG.warning("seller capture failed (scan unaffected): %s", str(e)[:200])
    return deals


def seed():
    for ram_class, (factor, ref, basis) in CLASSES.items():
        cap = round(ref * factor, 3)
        psql(f"""INSERT INTO dealsdesk.ram_market_reference
                 (ram_class, factor, ref_usd_per_gb, cap_usd_per_gb, obs_count,
                  basis, seed_ref_usd_per_gb)
                 VALUES ('{ram_class}', {factor}, {ref}, {cap}, 0,
                         '{esc(basis)}', {ref})
                 ON CONFLICT (ram_class) DO UPDATE
                   SET factor = EXCLUDED.factor, basis = EXCLUDED.basis,
                       seed_ref_usd_per_gb = EXCLUDED.seed_ref_usd_per_gb,
                       updated_at = NOW()""", write=True)
    # Anchor baselines from whatever sightings already exist (>=64GB median).
    for ram_class in CLASSES:
        rows = psql(
            f"""SELECT usd_per_gb FROM dealsdesk.ram_sightings
                WHERE ram_class = '{ram_class}' AND total_gb >= {MIN_MARKET_GB}""")
        obs = [float(r[0]) for r in rows]
        if len(obs) >= MARKET_MIN_OBS:
            base = round(median(obs), 3)
            psql(f"""UPDATE dealsdesk.ram_market_reference
                     SET baseline_median = {base}
                     WHERE ram_class = '{ram_class}' AND baseline_median IS NULL""",
                 write=True)
            LOG.info("%s baseline median anchored at %.3f (n=%d)", ram_class, base, len(obs))
    print_caps()


def print_caps():
    rows = psql("SELECT ram_class, factor, ref_usd_per_gb, cap_usd_per_gb, obs_count "
                "FROM dealsdesk.ram_market_reference ORDER BY ram_class")
    for r in rows:
        print(f"{r[0]:<14} market ${float(r[2]):>6.2f}/GB x {r[1]} "
              f"= cap ${float(r[3]):>6.2f}/GB  (obs {r[4]})  "
              f"128GB cap ${float(r[3]) * 128:,.0f}")


def pending_alerts():
    rows = psql("""SELECT id, ram_class, title, total_gb, price, usd_per_gb,
                          market_ref, cap_usd_per_gb, source, url, seller, stock_note
                   FROM dealsdesk.ram_deal_alerts
                   WHERE chat_reported_at IS NULL ORDER BY alerted_at""")
    for r in rows:
        item = {"title": r[2], "gb": int(r[3]), "price": float(r[4]),
                "source": r[8], "url": r[9] or "", "seller": r[10] or "",
                "stock_note": r[11] or ""}
        print(f"[alert {r[0]}]")
        print(format_alert(r[1], item, float(r[6]), float(r[7])))
        print()


def mark_reported(ids):
    for i in ids:
        psql(f"""UPDATE dealsdesk.ram_deal_alerts SET chat_reported_at = NOW()
                 WHERE id = {int(i)}""", write=True)
    LOG.info("marked reported: %s", ids)


SELFTEST = [
    # (title, price, source, expect_class, expect_fire) at seed caps:
    # ddr5 cap 11.90, ddr5_sodimm 10.85, rdimm 1.425, ddr4_consumer 4.275,
    # ddr3_rdimm cap 0.825, ddr3_lrdimm cap 0.975
    ("TEAMGROUP T-CREATE EXPERT DDR5 64GB kit (2x32GB) 6000 CL34", 1120.00, "jawa", "ddr5_udimm", False),
    ("G.SKILL Trident Z5 RGB 64GB (2x32GB) DDR5-5600 CL36", 745.00, "jawa", "ddr5_udimm", True),
    ("T-FORCE DELTA RGB DDR5 64GB (2 x 32GB) 6000MHz CL38", 775.00, "jawa", "ddr5_udimm", False),
    ("64GB 4x16GB Samsung PC4-2133P DDR4 ECC REG RDIMM 2Rx4", 299.99, "picclick_ebay", "ddr4_rdimm", False),
    ("128GB 8x16GB DDR4-3200 ECC REG RDIMM server memory kit", 170.00, "picclick_ebay", "ddr4_rdimm", True),
    ("PNY Performance 64GB (2x32GB) DDR4-3200 desktop kit", 219.99, "picclick_ebay", "ddr4_consumer", True),
    ("Crucial 64GB (2x32GB) DDR5-5600 SO-DIMM laptop kit", 1002.57, "picclick_ebay", "ddr5_sodimm", False),
    ("Gaming PC RTX 4070 Ryzen 7600X 32GB DDR5 1TB NVME SSD", 1529.99, "jawa", None, False),
    ("Hynix 128GB DDR4-3200MHz ECC RDIMM Memory (Non-Working)", 399.00, "picclick_ebay", None, False),
    ("Dell 128GB DDR4 PC4-3200 ECC Optane RAM SNP", 180.00, "picclick_ebay", None, False),
    ("ADATA 64GB 2x32GB DDR5-4800 CL40 Laptop SO-DIMM RAM", 105.50, "picclick_ebay", "ddr5_sodimm", False),
    ("G.SKILL Flare X5 64GB (2 x 32GB) DDR5 6000 Desktop Memory", 231.99, "picclick_ebay", "ddr5_udimm", False),
    ("Patriot Viper Elite 5 Ultra 16G 32G 48G 64G 96GB DDR5 6000 RAM Lot", 967.99, "picclick_ebay", None, False),
    # DDR3 (real listings from the big scan 2026-10-25)
    ("Axiom 128GB (8x16GB) DDR3 PC3-8500R Registered RDIMM 240-Pin", 76.99, "picclick_ebay", "ddr3_rdimm", True),
    ("SK hynix 256GB (16x16GB) DDR3 RDIMM ECC Reg PC3-12800R 240-Pin", 219.99, "picclick_ebay", "ddr3_rdimm", False),
    ("Samsung 32GB 4Rx4 PC3-14900L DDR3 ECC Server Memory RAM", 24.99, "picclick_ebay", "ddr3_lrdimm", True),
    ("Lot of 37 Samsung 8GB PC3-10600R DDR3 ECC REG RDIMM 296GB", 129.00, "picclick_ebay", "ddr3_rdimm", False),
    ("Sk Hynix 64Gb (16GB DDR3 X 4) PC3-12800R Server Memory", 7.00, "picclick_ebay", "ddr3_rdimm", False),
    ("G.Skill Sniper Series 8GB (2x4GB) DDR3 1866MHz CL9 Desktop RAM", 20.00, "jawa", None, False),
    ("Kingston 16GB (2x8GB) DDR3-1600 SO-DIMM Laptop Memory", 28.99, "jawa", None, False),
]


def selftest():
    caps = {k: (v[1], round(v[1] * v[0], 3)) for k, v in CLASSES.items()}
    fails = 0
    for title, price, source, want_class, want_fire in SELFTEST:
        c = classify(title)
        got_class = c[0] if c else None
        fire = False
        if c and alert_eligible(c[0], title, c[1]):
            per = price / c[1]
            floor = max(MIN_PLAUSIBLE_PER_GB[c[0]],
                        MIN_PLAUSIBLE_FRACTION * caps[c[0]][0])
            fire = per <= caps[c[0]][1] and per >= floor
        ok = (got_class == want_class) and (fire == want_fire)
        if not ok:
            fails += 1
        print(f"{'PASS' if ok else 'FAIL'}  class={got_class} fire={fire}  "
              f"${price:,.2f}  {title[:60]}")
    print("selftest:", "ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
    return 1 if fails else 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if mode == "seed":
        seed()
    elif mode == "caps":
        refresh_market()
        print_caps()
    elif mode == "scan":
        scan()
    elif mode == "pending-alerts":
        pending_alerts()
    elif mode == "mark-reported":
        mark_reported(sys.argv[2:])
    elif mode == "selftest":
        sys.exit(selftest())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
