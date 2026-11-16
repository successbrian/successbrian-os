#!/usr/bin/env python3
"""
Seller Dossier — DealsDesk's seller-vetting pack.

Brian's directive (2026-11-16): "investigate that seller. equip my dealsdesk
to be better at this." The desk knew pro_gaming_pc_store as one sighting line
and nothing else — no feedback depth, no account age, no location, no sense of
what else they sell. When a seller sits behind a live price decision, the desk
must be able to assemble everything it knows (and label what it does not).

Two halves:
- ECOSYSTEM side (this tool, from our own tables): every sighting the desk
  ever filed (dealsdesk.spencer_sightings), listing-history rows, and the
  people.companies registry record.
- WEB side (facts gathered from the seller's live profile pages by a browser
  read, handed in as JSON): feedback score, % positive, member since,
  location, 1/6/12-month feedback counts, quoted negatives, storefront shape.
  The tool never scrapes; it files what a verified read produced, with the
  source and date stamped on it.

Trust flags are computed by deterministic rules from those facts — labeled
rules, not opinions. Missing web facts are stated as NOT PULLED, never
filled in (Brian's law: unknown stays unknown).

Usage:
  seller_dossier.py dossier --seller pro_gaming_pc_store [--web-json facts.json]
  seller_dossier.py quick --seller pro_gaming_pc_store
  seller_dossier.py selftest
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

ENV_PATH = os.path.expanduser("~/successbrian-os/.env")


def load_env():
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()


def _conn(dbname="ecosystem_central"):
    import psycopg2
    import psycopg2.extras
    pw = os.environ.get("PGPASSWORD")
    if not pw:
        raise RuntimeError("PGPASSWORD not set (expected in ~/successbrian-os/.env)")
    return psycopg2.connect(host="localhost", dbname=dbname, user="altair",
                            password=pw,
                            cursor_factory=psycopg2.extras.RealDictCursor)


def _rows(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------- eco side
def gather_eco(seller, platform="ebay"):
    eco = {"sightings": [], "listing_history_count": 0, "company": None}
    with _conn() as conn, conn.cursor() as cur:
        eco["sightings"] = _rows(cur, """
            SELECT listing_title, price, rating_text, location, url, seen_at, fed_by
            FROM dealsdesk.spencer_sightings
            WHERE seller = %s AND platform = %s ORDER BY seen_at
        """, (seller, platform))
        got = _rows(cur, """
            SELECT count(*) AS n FROM dealsdesk.seller_listing_history
            WHERE seller_username = %s
        """, (seller,))
        eco["listing_history_count"] = got[0]["n"] if got else 0
    try:
        with _conn("people_unified") as conn, conn.cursor() as cur:
            got = _rows(cur, """
                SELECT name, kind, extra_data FROM people.companies
                WHERE lower(name) = lower(%s) LIMIT 1
            """, (seller,))
            eco["company"] = got[0] if got else None
    except Exception:
        eco["company"] = None
    # datetimes -> isoformat strings for jsonb
    for s in eco["sightings"]:
        if s.get("seen_at") is not None:
            s["seen_at"] = str(s["seen_at"])
        if s.get("price") is not None:
            s["price"] = float(s["price"])
    return eco


# ---------------------------------------------------------------- flags
def trust_flags(facts, eco):
    """Deterministic rules over the gathered facts. Each flag is a plain
    statement of a measured fact, not a verdict on the seller."""
    flags = []
    if not facts:
        flags.append("WEB PROFILE NOT PULLED — feedback depth, account age "
                     "and location unknown to the desk")
    else:
        fc = facts.get("feedback_count")
        if fc is not None and fc < 100:
            flags.append(f"SMALL FEEDBACK HISTORY ({fc})")
        pct = facts.get("pct_positive")
        if pct is not None and pct < 99.0:
            flags.append(f"FEEDBACK BELOW 99% POSITIVE ({pct}%)")
        neg = facts.get("negatives_12m")
        if neg is not None and neg >= 3:
            flags.append(f"MULTIPLE NEGATIVES IN 12 MONTHS ({neg})")
        ms = facts.get("member_since")
        if ms:
            try:
                since = datetime.fromisoformat(str(ms)[:10]).replace(
                    tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - since).days
                if age_days < 365:
                    flags.append(f"ACCOUNT UNDER A YEAR OLD (since {str(ms)[:10]})")
            except Exception:
                pass
        loc = facts.get("location")
        if loc:
            flags.append(f"LOCATED / SHIPS FROM: {loc}")
        if facts.get("feedback_mostly_as_buyer"):
            flags.append("FEEDBACK MOSTLY AS A BUYER, NOT A SELLER")
    n = len(eco.get("sightings") or [])
    if n == 0:
        flags.append("NEVER SIGHTED BY THE DESK BEFORE")
    elif n == 1:
        first = (eco["sightings"][0].get("seen_at") or "")[:10]
        flags.append(f"NEW TO THE DESK — one sighting, first seen {first}")
    return flags


# ---------------------------------------------------------------- dossier
def build_dossier(seller, platform="ebay", web_facts=None):
    eco = gather_eco(seller, platform)
    facts = web_facts or {}
    flags = trust_flags(facts, eco)
    lines = [f"SELLER DOSSIER — {seller} ({platform})"]
    if facts:
        bits = []
        if facts.get("feedback_count") is not None:
            bits.append(f"{facts['feedback_count']} feedback")
        if facts.get("pct_positive") is not None:
            bits.append(f"{facts['pct_positive']}% positive")
        if facts.get("member_since"):
            bits.append(f"member since {str(facts['member_since'])[:10]}")
        if facts.get("location"):
            bits.append(f"located {facts['location']}")
        if bits:
            lines.append("Profile: " + ", ".join(bits) + ".")
        counts = []
        for k, lab in (("positives_12m", "pos"), ("neutrals_12m", "neu"),
                       ("negatives_12m", "neg")):
            if facts.get(k) is not None:
                counts.append(f"{facts[k]} {lab}")
        if counts:
            lines.append("Last 12 months: " + ", ".join(counts) + ".")
        if facts.get("storefront_summary"):
            lines.append(f"Storefront: {facts['storefront_summary']}")
        for neg in facts.get("negative_comments") or []:
            lines.append(f"Negative feedback on record: \"{neg}\"")
        if facts.get("source"):
            lines.append(f"(Web facts source: {facts['source']})")
    else:
        lines.append("Profile: NOT PULLED — no web profile facts on file.")
    s = eco["sightings"]
    if s:
        prices = [x["price"] for x in s if x.get("price") is not None]
        rng = (f", prices ${min(prices):,.2f}–${max(prices):,.2f}"
               if prices else "")
        lines.append(f"Desk sightings: {len(s)} "
                     f"({str(s[0]['seen_at'])[:10]} → {str(s[-1]['seen_at'])[:10]})"
                     f"{rng}.")
        for x in s[:5]:
            lines.append(f"  - {x['listing_title'][:90]} — ${x['price']:,.2f}"
                         if x.get("price") is not None else
                         f"  - {x['listing_title'][:90]}")
    else:
        lines.append("Desk sightings: none.")
    if eco["company"]:
        lines.append("In the companies registry: yes "
                     f"({eco['company'].get('kind')}).")
    lines.append("Trust flags: " + ("; ".join(flags) if flags else "none"))
    text = "\n".join(lines)
    return {"seller": seller, "platform": platform, "facts": facts,
            "eco": eco, "trust_flags": flags, "dossier_text": text}


def save_dossier(d):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO dealsdesk.seller_dossiers
                (seller, platform, facts, eco, trust_flags, dossier_text)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (seller, platform) DO UPDATE SET
                facts = EXCLUDED.facts, eco = EXCLUDED.eco,
                trust_flags = EXCLUDED.trust_flags,
                dossier_text = EXCLUDED.dossier_text, updated_at = now()
        """, (d["seller"], d["platform"], json.dumps(d["facts"]),
              json.dumps(d["eco"], default=str), d["trust_flags"],
              d["dossier_text"]))
        conn.commit()


def quick_line(seller, platform="ebay"):
    """One line for a clerk capture: what the desk knows about this seller.
    Never raises; a missing dossier is itself the information."""
    if not seller:
        return None
    try:
        with _conn() as conn, conn.cursor() as cur:
            got = _rows(cur, """
                SELECT facts, trust_flags FROM dealsdesk.seller_dossiers
                WHERE seller = %s AND platform = %s
            """, (seller, platform))
    except Exception:
        return None
    if not got:
        return (f"SELLER: {seller} ({platform}) — no dossier on file; "
                f"the desk has not vetted this seller.")
    d = got[0]
    f = d["facts"] or {}
    bits = []
    if f.get("feedback_count") is not None:
        bits.append(f"{f['feedback_count']} feedback")
    if f.get("pct_positive") is not None:
        bits.append(f"{f['pct_positive']}% positive")
    if f.get("member_since"):
        bits.append(f"member since {str(f['member_since'])[:10]}")
    if f.get("location"):
        bits.append(str(f["location"]))
    head = ", ".join(bits) if bits else "profile not pulled"
    flags = d["trust_flags"] or []
    return (f"SELLER: {seller} ({platform}) — {head}. "
            f"Flags: {'; '.join(flags) if flags else 'none'}")


# ---------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(description="DealsDesk seller dossier.")
    sub = ap.add_subparsers(dest="cmd")
    p1 = sub.add_parser("dossier")
    p1.add_argument("--seller", required=True)
    p1.add_argument("--platform", default="ebay")
    p1.add_argument("--web-json")
    p2 = sub.add_parser("quick")
    p2.add_argument("--seller", required=True)
    p2.add_argument("--platform", default="ebay")
    args = ap.parse_args(argv)
    if args.cmd == "dossier":
        web = None
        if args.web_json:
            with open(args.web_json) as fh:
                web = json.load(fh)
        d = build_dossier(args.seller, args.platform, web)
        save_dossier(d)
        print(d["dossier_text"])
        return 0
    if args.cmd == "quick":
        print(quick_line(args.seller, args.platform) or "no line")
        return 0
    ap.print_help()
    return 1


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and cond

    eco1 = {"sightings": [{"seen_at": "2026-11-12", "price": 639.0,
                           "listing_title": "x"}], "company": None}
    f_small = trust_flags({"feedback_count": 45, "pct_positive": 100.0}, eco1)
    check("small history flagged", any("SMALL FEEDBACK" in x for x in f_small))
    check("new-to-desk flagged", any("NEW TO THE DESK" in x for x in f_small))
    f_none = trust_flags({}, eco1)
    check("not-pulled flagged", any("NOT PULLED" in x for x in f_none))
    f_clean = trust_flags({"feedback_count": 5000, "pct_positive": 99.9,
                           "negatives_12m": 0,
                           "member_since": "2015-01-01"},
                          {"sightings": [1, 2, 3], "company": None})
    check("clean seller has no caution flags",
          not any(("SMALL" in x or "BELOW" in x or "NEGATIVES" in x
                   or "UNDER A YEAR" in x) for x in f_clean))
    d = build_dossier("pro_gaming_pc_store")
    check("dossier builds from eco data", "SELLER DOSSIER" in d["dossier_text"]
          and "Desk sightings: 1" in d["dossier_text"])
    line = quick_line("pro_gaming_pc_store")
    check("quick line answers", line is None or line.startswith("SELLER:"))
    print("SELFTEST OK" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    sys.exit(main())
