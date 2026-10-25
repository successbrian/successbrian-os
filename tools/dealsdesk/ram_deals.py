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
SOURCES: Jawa public API (categoryIds=4 Memory, paginated) + PicClick (eBay)
         via picclick_rack_search. Every classified listing is stored in
         dealsdesk.ram_sightings (the market time series) and mirrored to
         public.price_history. Out-of-stock items are never sightings.
ALERTS:  A listing with total >=32GB and $/GB <= cap is a DEAL: row in
         dealsdesk.ram_deal_alerts (deduped 14d by url/title+price) + a
         message in public.successbrian_outbox (feeds Brian's digest), and it
         is printed by `pending-alerts` for chat delivery. NOTHING AUTO-BUYS.
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
    # '2x32GB' / '4 x 16GB' leading kit notation
    m = re.search(r"(\d+)\s*[xX]\s*(\d+)\s*GB", t)
    if m:
        n, per = int(m.group(1)), int(m.group(2))
        if 1 < n <= 8 and per in (4, 8, 16, 24, 32, 48, 64):
            return n * per
    # '128GB kit' / '64GB DDR5' single figure
    m = re.search(r"(\d{2,3})\s*GB", t)
    if m:
        gb = int(m.group(1))
        if gb in (16, 24, 32, 48, 64, 96, 128, 192, 256):
            return gb
    return None


def classify(title):
    """Return (ram_class, total_gb) or None if not a RAM kit we track."""
    if not title or EXCLUDE.search(title):
        return None
    t = title.upper()
    if "GDDR" in t or "DDR3" in t or "DDR2" in t:
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
    if gen is None:
        return None
    gb = parse_total_gb(title)
    if gb is None or gb < 8:
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
}


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
        if (gb >= MIN_ALERT_GB and per <= cap and item["price"] >= 30
                and not already_alerted(item)):
            if fire_alert(ram_class, item, ref, cap):
                deals += 1
    LOG.info("scan done: %d raw, %d sightings, %d new deal(s)",
             len(raw), sightings, deals)
    psql(f"""INSERT INTO system_operations_log (subsystem, action_type, status, payload)
             VALUES ('ram_deals', 'scan', 'OK',
                     jsonb_build_object('raw', {len(raw)}, 'sightings', {sightings},
                                        'deals', {deals}))""", write=True)
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
    # ddr5 cap 11.90, ddr5_sodimm 10.85, rdimm 1.425, ddr4_consumer 4.275
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
]


def selftest():
    caps = {k: (v[1], round(v[1] * v[0], 3)) for k, v in CLASSES.items()}
    fails = 0
    for title, price, source, want_class, want_fire in SELFTEST:
        c = classify(title)
        got_class = c[0] if c else None
        fire = False
        if c and c[1] >= MIN_ALERT_GB:
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
