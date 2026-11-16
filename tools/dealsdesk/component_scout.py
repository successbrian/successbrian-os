#!/usr/bin/env python3
"""
Component Scout — 24/7 price monitor for ALL open build needs.
Replaces the old RAM-only scout. Covers RAM, GPU, storage, PSU, NIC, cooler, etc.
Runs every 6 hours via cron.

INTEGRATION v2 (2026-11-12, Brian: "build better dealsdesk integration"): the scout now
also reads dealsdesk.ecosystem_needs (open hardware needs) alongside build_bom; ecosystem
finds file seller sightings (fed_by='component_scout') and under-target finds raise one
clerk capture each. Drive health is NOT in the API data — price finds stay unverified
until health evidence exists (Brian's >90% documented-health gate).
"""
import os, json, sys, re
from datetime import datetime, timezone
from urllib.parse import quote


# ---------------------------------------------------------------- env
ENV_PATH = os.path.expanduser("~/successbrian-os/.env")


def load_env():
    """Read ~/successbrian-os/.env (KEY=value lines) without overriding
    real process environment variables -- same pattern as
    tools/marketing/blog_manager.py."""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()


def _require_env(name):
    """Credentials come from the environment only -- never from source.
    A loud failure beats a silent hard-coded fallback."""
    val = os.environ.get(name)
    if not val:
        print("ERROR: required environment variable %s is not set. "
              "component_scout reads credentials from the environment only "
              "(production values live in ~/successbrian-os/.env)." % name,
              file=sys.stderr)
        sys.exit(1)
    return val

DB_HOST = 'localhost'
DB_NAME = 'ecosystem_central'
DB_USER = 'altair'
DB_PASS = _require_env('PGPASSWORD')

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("[SCOUT] psycopg2 not available — cannot run")
    sys.exit(1)

def pg(sql, params=None):
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params or ())
    result = cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    return result

# ── eBay Browse API (HTML scraper gets 403'd by eBay) ──
import urllib.request, base64, ssl as _ssl

EBAY_CID = _require_env('EBAY_CLIENT_ID')
EBAY_SECRET = _require_env('EBAY_CLIENT_SECRET')

def get_ebay_token():
    auth_str = f"{EBAY_CID}:{EBAY_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()
    req = urllib.request.Request(
        "https://api.ebay.com/identity/v1/oauth2/token",
        data=b"grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope",
        headers={"Authorization": f"Basic {auth_b64}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    with urllib.request.urlopen(req, context=_ssl.create_default_context(), timeout=15) as resp:
        return json.loads(resp.read())["access_token"]

def search_ebay(query, limit=5, used_only=False):
    """Search eBay Browse API, return cheapest items first."""
    try:
        token = get_ebay_token()
        encoded = quote(query)
        filt = "buyingOptions:{FIXED_PRICE}"
        if used_only:
            filt += ",conditions:{USED}"
        url = f"https://api.ebay.com/buy/browse/v1/item_summary/search?q={encoded}&limit={limit}&sort=price&filter={filt}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for item in data.get("itemSummaries", []):
            price_obj = item.get("price", {})
            try:
                price = float(price_obj.get("value", 0))
            except (TypeError, ValueError):
                continue
            title = item.get("title", "").strip()[:80]
            seller = item.get("seller", {}) or {}
            results.append({"title": title, "price": price, "url": item.get("itemWebUrl", ""),
                            "seller": seller.get("username", ""),
                            "seller_feedback": seller.get("feedbackPercentage", "")})
        return results
    except Exception as e:
        print(f"[SCOUT] eBay API search failed: {e}")
        return []

def get_needs():
    return pg("""
        SELECT bb.*, b.build_name, b.build_stage
        FROM build_bom bb
        JOIN inv_builds b ON bb.build_id = b.id
        WHERE bb.status NOT IN ('received', 'installed')
          AND bb.urgency IN ('high', 'critical')
        ORDER BY bb.urgency DESC, bb.id
    """)

def get_eco_needs():
    """Open HARDWARE needs from dealsdesk.ecosystem_needs — the desk's other needs table.
    Search terms come from hard_terms.search_terms when the need carries them."""
    return pg("""
        SELECT id, subject, target_buy_price, qty_needed, qty_filled, hard_terms, urgency
        FROM dealsdesk.ecosystem_needs
        WHERE status = 'open' AND need_type = 'hardware' AND qty_filled < qty_needed
        ORDER BY urgency DESC, id
    """)

def file_sighting(r, need_id):
    """One seller sighting per (seller, url) — deduped. Health stays NULL: the eBay API
    does not carry drive-health data, so a scout find is a lead, never a gated find."""
    if not r.get("seller") or not r.get("url"):
        return
    cap = 4096 if "4tb" in r["title"].lower() else None
    pg("""
        INSERT INTO dealsdesk.spencer_sightings
            (seller, platform, listing_title, price, capacity_gb, health_pct,
             health_evidence, rating_text, url, notes, fed_by)
        SELECT %s, 'ebay', %s, %s, %s, NULL, NULL, %s, %s, %s, 'component_scout'
        WHERE NOT EXISTS (SELECT 1 FROM dealsdesk.spencer_sightings
                          WHERE platform = 'ebay' AND url = %s)
        RETURNING id
    """, (r["seller"], r["title"][:200], r["price"], cap,
          (f"{r['seller_feedback']}% positive" if r.get("seller_feedback") else None),
          r["url"],
          f"component_scout eBay API find for ecosystem need #{need_id}; health UNVERIFIED (not in API data)",
          r["url"]))

def raise_capture(need, best):
    title = f"DealsDesk scout UNDER TARGET: {need['subject']} at ${best['price']:.2f} (need #{need['id']})"
    raw = (f"Component Scout (eBay Browse API) found an under-target price for ecosystem need "
           f"#{need['id']} ({need['subject']}): ${best['price']:.2f} - {best['title']} - "
           f"seller {best.get('seller') or 'unknown'} - {best['url']}. "
           f"Target ${float(need['target_buy_price']):.2f}, qty still needed "
           f"{need['qty_needed'] - need['qty_filled']}. CAUTION: drive health is NOT verified - "
           f"the API carries no health data. Under Brian's rule this is a price lead, not a find, "
           f"until documented health >90% exists.")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from pricing_brief import build_brief, need_terms
        raw = raw + "\n\n" + build_brief(
            need_terms(need), float(best['price']),
            target=(float(need['target_buy_price'])
                    if need['target_buy_price'] else None),
            subject=need['subject'], need_id=need['id'])
    except Exception as e:
        raw = raw + (f"\n\nPRICING BRIEF: unavailable ({e}) - "
                     f"judge this price as UNEQUIPPED and route it to a person.")
    pg("""
        INSERT INTO atlas.scattered_captures (title, raw_text, context, status)
        SELECT %s, %s, 'dealsdesk-scout', 'raw'
        WHERE NOT EXISTS (SELECT 1 FROM atlas.scattered_captures
                          WHERE title = %s AND created_at > now() - interval '20 hours')
        RETURNING id
    """, (title, raw, title))

def scout_eco_needs():
    needs = get_eco_needs()
    for need in needs:
        ht = need.get("hard_terms") or {}
        if isinstance(ht, str):
            try:
                ht = json.loads(ht)
            except Exception:
                ht = {}
        terms = ht.get("search_terms") or [re.sub(r"\s*\([^)]*\)", "", need["subject"]).strip()]
        used_only = (ht.get("condition") == "used") or ("used" in need["subject"].lower())
        target = float(need["target_buy_price"]) if need["target_buy_price"] else None
        print(f"\n{'='*60}")
        print(f"ECO NEED #{need['id']}: {need['subject']}")
        print(f"  Target: {target} | qty still needed: {need['qty_needed'] - need['qty_filled']}")
        all_results = []
        for term in terms:
            rs = search_ebay(term, limit=5, used_only=used_only)
            print(f"  '{term}': {len(rs)} results")
            all_results.extend(rs)
        cap_m = re.search(r"(\d+)\s*(TB|GB)", need["subject"], re.I)
        if cap_m:
            tok = (cap_m.group(1) + cap_m.group(2)).lower()
            junk = ("heatsink only", "enclosure", "adapter", "for parts",
                    "not working", "box only", "empty box", "read description")
            def caps_in(title):
                out = set()
                for num, unit in re.findall(r"(\d+)\s*(tb|gb)", title.lower()):
                    out.add(int(num) * (1000 if unit == "tb" else 1))
                return out
            kept = [r for r in all_results
                    if tok in r["title"].lower().replace(" ", "")
                    and not any(j in r["title"].lower() for j in junk)
                    and len(caps_in(r["title"])) <= 1]
            if len(kept) < len(all_results):
                print(f"  capacity/junk filter: {len(all_results)} -> {len(kept)} results")
            all_results = kept
        if not all_results:
            print("  No results from eBay")
            continue
        all_results.sort(key=lambda x: x["price"])
        for r in all_results[:8]:
            try:
                file_sighting(r, need["id"])
            except Exception as e:
                print(f"  sighting file failed: {e}")
        best = all_results[0]
        print(f"  Best found: ${best['price']:.2f} - {best['title']}")
        if target and best["price"] <= target:
            print("  UNDER TARGET on price - capture raised (health still unverified)")
            try:
                raise_capture(need, best)
            except Exception as e:
                print(f"  capture raise failed: {e}")
        elif target:
            print(f"  Above target (${target:.2f})")

def main():
    print(f"[SCOUT] Running at {datetime.now(timezone.utc).isoformat()}")
    needs = get_needs()
    if not needs:
        print("[SCOUT] No open high/critical needs. All quiet.")
        return

    for need in needs:
        print(f"\n{'='*60}")
        print(f"#{need['id']}: {need['component_type']} — {need['component_subtype']}")
        print(f"  Build: {need['build_name']} ({need['build_stage']})")
        print(f"  Qty needed: {need['quantity_needed']}")
        print(f"  Urgency: {need['urgency']}")

        # Build eBay search query from component type and subtype
        query = f"{need['component_subtype'].replace(' ', '+')}"
        if need['component_type'] == 'gpu':
            query = f"tesla m40 24gb used"
        elif need['component_type'] == 'ram':
            query = f"{need['quantity_needed']}x16gb ddr3 pc3-12800r ecc reg"
        elif need['component_type'] == 'storage':
            query = f"{need['component_subtype']} used" if need['component_subtype'] else "512gb nvme m.2 2280 used"
        elif need['component_type'] == 'chassis':
            query = f"supermicro 4u chassis psu"
        elif need['component_type'] == 'cooler':
            query = f"lga2011 narrow ilm heatsink"
        elif need['component_type'] == 'nic':
            query = f"intel 1gbe pci-e network card"
        elif need['component_type'] == 'psu':
            query = f"750w 80plus atx psu"
        elif need['component_type'] == 'thermal':
            query = f"thermal paste arctic mx-6"
        elif need['component_type'] == 'cables':
            query = f"sata cable pci-e 8pin power adapter"

        print(f"  Searching: {query}")
        results = search_ebay(query, limit=5)

        if results:
            best = min(results, key=lambda x: x['price'])
            target = float(need['preferred_price']) if need['preferred_price'] else None
            gap = (target - best['price']) if target else None
            print(f"  Best found: ${best['price']:.2f} — {best['title']}")
            print(f"  URL: {best['url']}")
            if target:
                print(f"  Target: ${target:.2f} | GAP: ${gap:+.2f}")
            if target and best['price'] <= target:
                print(f"  ✓ UNDER TARGET — flag for purchase")
            else:
                print(f"  ✗ Above target" if target else "")
        else:
            print("  No results from eBay")

    print(f"\n[SCOUT] Done. {len(needs)} BOM needs checked.")
    scout_eco_needs()
    print(f"\n[SCOUT] Ecosystem needs pass done.")

if __name__ == '__main__':
    main()
