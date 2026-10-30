#!/usr/bin/env python3
"""seller_capture.py — DealsDesk seller/business capture + integration sinks.

PURPOSE: Brian's upgrade order (2026-10-25): "upgrade and integrate — we
         need all found data written to anythingllm, postgresql, and
         people/businesses wrote to people_unified — we are wanting to
         build relationships with businesses and sellers that are found —
         we'll likely be leaving the actual relationship crunching
         somewhere else if that is appropriate."

DESIGN:  DealsDesk CAPTURES FACTS about the businesses and sellers its
         scanners find, and writes them to the three sanctioned stores
         (R32 homes + the people store):
           1. PostgreSQL / ecosystem_central — sightings + price_history
              (written by the scanners themselves; the system of record
              for found data).
           2. PostgreSQL / people_unified.people.companies — THE one
              companies table (Brian's ruling, 2026-10-27: only ONE
              companies table; kind says what kind of business it is).
              One row per discovered business/seller: kind = the
              capture category (marketplace_seller | supplier),
              kinds[] carries it too, collections includes
              'dealsdesk-sellers', desk='dealsdesk', and an extra_data
              JSONB carrying platform(s), first/last seen, sighting +
              deal counts, best $/GB seen, sample listing URLs.
              Upsert key: name_key (lower(name)); platforms accumulate
              in extra_data. This table is the handoff surface —
              relationship CRUNCHING (scoring, outreach, who-knows-who)
              does NOT live in DealsDesk; it belongs to ContactFlowCRM,
              which reads people.companies (desk='dealsdesk').
              NOT written: people.people (the 211M-row scraped dataset —
              wrong shape, sellers would vanish into it),
              lead_scraper.businesses (the pre-2026-10-27 seller table,
              deprecated by the one-companies-table ruling) and
              affiliate_intel.vendors (affiliate-program world, not
              marketplace sellers).
           3. AnythingLLM workspace 'dealsdesk' — two living documents
              via allm_embed.embed_latest (replace-prior-edition):
              dealsdesk-seller-registry.md (who we found, what they
              sell, best prices, last seen) and dealsdesk-ram-market.md
              (current caps/refs + recent deals). Knowledge layer, so
              any agent can answer "who sells X cheap" from the record.
SOURCES: v1 = dealsdesk.ram_sightings sellers (Jawa names today; eBay
         seller names are not in the PicClick parse yet — v2) +
         dealsdesk.suppliers (the standing supplier list). New scanners
         feed the same shape: aggregate_sellers() is source-agnostic.
CALLED BY: ram_deals.scan() at the end of every scan (guarded — a capture
         failure never fails the scan), or standalone: `seller_capture.py run`.
MODES:   run | selftest
"""

import json
import logging
import subprocess
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools/atlas")
sys.path.insert(0, "/home/dealsdesk/scripts")
sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [seller_capture] %(message)s")
LOG = logging.getLogger("seller_capture")

ECODB = "ecosystem_central"
PEOPLEDB = "people_unified"
DB_USER = "successbrian"
ALLM_WORKSPACE = "dealsdesk"


def psql(db, sql, write=False):
    args = ["psql", "-U", DB_USER, "-d", db, "-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        LOG.error("psql(%s) failed: %s", db, r.stderr.strip()[:300])
        return [] if not write else False
    if write:
        return True
    return [ln.split("\x1f") for ln in r.stdout.strip().split("\n") if ln.strip()]


# SBOS common routines - Batch C migration (2026-10-27).
import os as _os_c, sys as _sys_c
_sys_c.path.insert(0, _os_c.path.join(_os_c.path.dirname(_os_c.path.abspath(__file__)), ".."))
import sbos_common  # noqa: E402


def esc(s):
    # Batch C migration (2026-10-27): delegates to sbos_common.esc -
    # the one SQL-escape definition for the ecosystem.
    return sbos_common.esc(s)


def dedupe_key(name, platform):
    return (name or "").strip().lower() + "|" + (platform or "").strip().lower()


def aggregate_sellers():
    """Aggregate ram_sightings + ram_deal_alerts by (seller, source).
    Returns a list of business dicts in the capture shape."""
    agg = {}
    rows = psql(ECODB,
                """SELECT seller, source, ram_class, total_gb, price,
                          usd_per_gb, url, seen_at
                   FROM dealsdesk.ram_sightings WHERE seller <> ''""")
    for seller, source, ram_class, gb, price, per, url, seen in rows:
        k = dedupe_key(seller, source)
        b = agg.setdefault(k, {
            "name": seller.strip(), "platform": source,
            "category": "marketplace_seller", "classes": set(),
            "sightings": 0, "deals": 0, "best_per_gb": None,
            "first_seen": seen, "last_seen": seen, "samples": []})
        b["classes"].add(ram_class)
        b["sightings"] += 1
        per_f = float(per)
        if b["best_per_gb"] is None or per_f < b["best_per_gb"]:
            b["best_per_gb"] = per_f
        if seen < b["first_seen"]:
            b["first_seen"] = seen
        if seen > b["last_seen"]:
            b["last_seen"] = seen
        if url and len(b["samples"]) < 3:
            b["samples"].append(url)
    for seller, source, cnt in psql(
            ECODB,
            """SELECT seller, source, count(*) FROM dealsdesk.ram_deal_alerts
               WHERE seller <> '' GROUP BY seller, source"""):
        k = dedupe_key(seller, source)
        if k in agg:
            agg[k]["deals"] = int(cnt)
    return list(agg.values())


def aggregate_suppliers():
    out = []
    for name, region, reliability, relationship in psql(
            ECODB,
            "SELECT name, COALESCE(region,''), COALESCE(reliability,''), "
            "COALESCE(relationship,'') FROM dealsdesk.suppliers"):
        out.append({
            "name": name.strip(), "platform": "dealsdesk_suppliers",
            "category": "supplier", "classes": set(), "sightings": 0,
            "deals": 0, "best_per_gb": None, "first_seen": None,
            "last_seen": None, "samples": [],
            "supplier_meta": {"region": region, "reliability": reliability,
                              "relationship": relationship}})
    return out


def build_business(b):
    """Capture shape -> businesses-table fields (pure; selftested)."""
    classes = sorted(b.get("classes") or [])
    extra = {
        "platform": b["platform"],
        "captured_by": "dealsdesk.seller_capture",
        "first_seen": b.get("first_seen"),
        "last_seen": b.get("last_seen"),
        "sightings": b.get("sightings", 0),
        "deals_fired": b.get("deals", 0),
        "best_usd_per_gb": b.get("best_per_gb"),
        "ram_classes": classes,
        "sample_urls": b.get("samples", []),
    }
    if b.get("supplier_meta"):
        extra["supplier"] = b["supplier_meta"]
    tags = ["dealsdesk", b["platform"]] + classes
    if b["category"] == "marketplace_seller":
        desc = (f"Marketplace seller found by DealsDesk scanners on "
                f"{b['platform']}. Sells: {', '.join(classes) or 'RAM'}. "
                f"{b.get('sightings', 0)} listing observations tracked, "
                f"{b.get('deals', 0)} under Brian's deal caps.")
    else:
        desc = (f"Standing DealsDesk supplier "
                f"({b.get('supplier_meta', {}).get('region', '')}). "
                f"Relationship crunching lives outside DealsDesk.")
    return {"name": b["name"], "category": b["category"],
            "description": desc, "tags": tags, "extra": extra}


def build_company(rec):
    """Capture shape -> people.companies fields (pure; selftested).

    The ONE companies table (Brian, 2026-10-27): kind is the capture
    category, collections marks the DealsDesk seller collection, desk
    is dealsdesk. Seller facts (platform, sightings, deals, best $/GB,
    samples) ride in extra_data, merged on update so platforms and
    history accumulate instead of overwriting each other."""
    kind = rec["category"]
    sector = ("Hardware / RAM marketplace" if kind == "marketplace_seller"
              else "Hardware supplier")
    return {"name": rec["name"], "name_key": rec["name"].strip().lower(),
            "kind": kind, "kinds": [kind], "sector": sector,
            "collections": ["dealsdesk-sellers"], "desk": "dealsdesk",
            "what_we_know": rec["description"], "status": "active",
            "extra": rec["extra"]}


def upsert_company(rec):
    comp = build_company(rec)
    rows = psql(PEOPLEDB,
                """SELECT id, COALESCE(extra_data::text, '{}')
                   FROM people.companies WHERE name_key = '%s' LIMIT 1"""
                % esc(comp["name_key"]))
    if rows:
        try:
            old_extra = json.loads(rows[0][1])
        except Exception:
            old_extra = {}
        extra = dict(old_extra)
        platforms = sorted(set((extra.get("platforms") or [])
                               + ([extra["platform"]] if extra.get("platform") else [])
                               + [comp["extra"]["platform"]]))
        extra.update(comp["extra"])
        extra["platforms"] = platforms
        extra["platform"] = comp["extra"]["platform"]
        psql(PEOPLEDB,
             """UPDATE people.companies
                SET kinds = ARRAY(SELECT DISTINCT unnest(kinds || ARRAY['%s'])),
                    collections = ARRAY(SELECT DISTINCT unnest(collections || ARRAY['dealsdesk-sellers'])),
                    desk = COALESCE(desk, 'dealsdesk'),
                    sector = COALESCE(sector, '%s'),
                    what_we_know = CASE WHEN what_we_know = '' THEN '%s' ELSE what_we_know END,
                    extra_data = '%s'::jsonb, updated_at = NOW()
                WHERE id = %d"""
             % (esc(comp["kind"]), esc(comp["sector"]),
                esc(comp["what_we_know"]),
                esc(json.dumps(extra, ensure_ascii=False)), int(rows[0][0])),
             write=True)
        return "updated"
    psql(PEOPLEDB,
         """INSERT INTO people.companies
            (name, name_key, kind, kinds, sector, collections, desk,
             what_we_know, status, source_tables, extra_data)
            VALUES ('%s', '%s', '%s', ARRAY['%s'], '%s',
                    ARRAY['dealsdesk-sellers'], 'dealsdesk', '%s', 'active',
                    ARRAY['dealsdesk.seller_capture'], '%s'::jsonb)"""
         % (esc(comp["name"]), esc(comp["name_key"]), esc(comp["kind"]),
            esc(comp["kind"]), esc(comp["sector"]),
            esc(comp["what_we_know"]),
            esc(json.dumps(comp["extra"], ensure_ascii=False))), write=True)
    return "inserted"


def seller_registry_md(businesses):
    lines = ["# DealsDesk Seller Registry",
             "",
             "Businesses and sellers found by DealsDesk scanners, captured "
             "as facts for relationship building. DealsDesk records who "
             "they are, what they sell, and the best prices seen; "
             "relationship work itself lives in ContactFlowCRM, reading "
             "people_unified.people.companies (desk='dealsdesk').",
             ""]
    for b in sorted(businesses, key=lambda x: x["name"].lower()):
        e = b["extra"]
        best = ("$%.2f/GB best" % e["best_usd_per_gb"]
                if e.get("best_usd_per_gb") else "no priced sightings")
        lines.append(f"## {b['name']} ({e['platform']})")
        lines.append(f"- Category: {b['category']}; sells: "
                     f"{', '.join(e.get('ram_classes') or []) or '—'}")
        lines.append(f"- Sightings: {e.get('sightings', 0)}; deals fired: "
                     f"{e.get('deals_fired', 0)}; {best}")
        lines.append(f"- First seen: {e.get('first_seen')}; "
                     f"last seen: {e.get('last_seen')}")
        for u in e.get("sample_urls") or []:
            lines.append(f"- Listing: {u}")
        lines.append("")
    return "\n".join(lines)


def ram_market_md():
    rows = psql(ECODB,
                """SELECT ram_class, ref_usd_per_gb, cap_usd_per_gb, obs_count
                   FROM dealsdesk.ram_market_reference ORDER BY ram_class""")
    lines = ["# DealsDesk RAM Market — current caps", "",
             "Buy cap = market ref x factor (DDR5 x0.70, DDR4/DDR3 x0.75). "
             "Refs are anchored to verified street prices and flow with "
             "the 30-day sighting median. Nothing auto-buys.", "",
             "| class | market $/GB | cap $/GB | cap for 128GB | obs |",
             "|---|---|---|---|---|"]
    for cls, ref, cap, obs in rows:
        lines.append(f"| {cls} | ${float(ref):.2f} | ${float(cap):.2f} | "
                     f"${float(cap) * 128:,.0f} | {obs} |")
    lines += ["", "## Recent deals fired", ""]
    for title, price, per, cls, src, at in psql(
            ECODB,
            """SELECT title, price, usd_per_gb, ram_class, source, alerted_at
               FROM dealsdesk.ram_deal_alerts
               ORDER BY alerted_at DESC LIMIT 15"""):
        lines.append(f"- [{cls}] {title[:90]} — ${float(price):,.2f} "
                     f"(${float(per):.2f}/GB, {src}, {at[:16]})")
    return "\n".join(lines)


def embed(text, filename):
    try:
        import allm_embed
        loc = allm_embed.embed_latest(ALLM_WORKSPACE, filename, text)
        LOG.info("embedded %s -> %s", filename, loc)
        return True
    except Exception as e:
        LOG.warning("AnythingLLM embed failed for %s (capture continues): %s",
                    filename, str(e)[:200])
        return False


def run(embed_docs=True):
    businesses = [build_business(b)
                  for b in aggregate_sellers() + aggregate_suppliers()]
    ins = upd = 0
    for rec in businesses:
        r = upsert_company(rec)
        ins += r == "inserted"
        upd += r == "updated"
    LOG.info("businesses captured: %d (%d new, %d updated)",
             len(businesses), ins, upd)
    embedded = []
    if embed_docs:
        if embed(seller_registry_md(businesses),
                 "dealsdesk-seller-registry.md"):
            embedded.append("seller-registry")
        if embed(ram_market_md(), "dealsdesk-ram-market.md"):
            embedded.append("ram-market")
    psql(ECODB,
         """INSERT INTO system_operations_log
            (subsystem, action_type, status, payload)
            VALUES ('seller_capture', 'run', 'OK',
                    jsonb_build_object('businesses', %d, 'inserted', %d,
                                       'updated', %d, 'embedded', '%s'))"""
         % (len(businesses), ins, upd, ",".join(embedded)), write=True)
    return {"businesses": len(businesses), "inserted": ins, "updated": upd,
            "embedded": embedded}


SELFTEST = [
    ({"name": "Skywalker Builds", "platform": "jawa",
      "category": "marketplace_seller", "classes": {"ddr5_udimm"},
      "sightings": 3, "deals": 1, "best_per_gb": 11.641,
      "first_seen": "2026-10-25", "last_seen": "2026-10-25",
      "samples": ["https://www.jawa.gg/product/144302/x"]},
     "Skywalker Builds", "marketplace_seller", "jawa"),
    ({"name": "CompSource", "platform": "dealsdesk_suppliers",
      "category": "supplier", "classes": set(), "sightings": 0, "deals": 0,
      "best_per_gb": None, "first_seen": None, "last_seen": None,
      "samples": [], "supplier_meta": {"region": "US", "reliability": "",
                                       "relationship": ""}},
     "CompSource", "supplier", "dealsdesk_suppliers"),
]


def selftest():
    fails = 0
    for b, want_name, want_cat, want_platform in SELFTEST:
        rec = build_business(b)
        ok = (rec["name"] == want_name and rec["category"] == want_cat
              and rec["extra"]["platform"] == want_platform
              and "dealsdesk" in rec["tags"])
        if not ok:
            fails += 1
        print(f"{'PASS' if ok else 'FAIL'}  {rec['name']} "
              f"cat={rec['category']} platform={rec['extra']['platform']}")
    k1 = dedupe_key("  Skywalker Builds ", "JAWA")
    k2 = dedupe_key("skywalker builds", "jawa")
    if k1 != k2:
        fails += 1
        print("FAIL  dedupe_key normalization")
    else:
        print("PASS  dedupe_key normalization")
    for b, want_name, want_cat, want_platform in SELFTEST:
        comp = build_company(build_business(b))
        ok = (comp["name_key"] == want_name.strip().lower()
              and comp["kind"] == want_cat
              and comp["kinds"] == [want_cat]
              and comp["desk"] == "dealsdesk"
              and comp["collections"] == ["dealsdesk-sellers"]
              and comp["extra"]["platform"] == want_platform)
        if not ok:
            fails += 1
        print(f"{'PASS' if ok else 'FAIL'}  companies map: {comp['name']} "
              f"kind={comp['kind']} desk={comp['desk']}")
    print("selftest:", "ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
    return 1 if fails else 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "run":
        print(run())
    elif mode == "selftest":
        sys.exit(selftest())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
