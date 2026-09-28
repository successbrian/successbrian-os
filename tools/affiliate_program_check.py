#!/usr/bin/env python3
"""
Affiliate-program checker: the recurring-forever promote filter.

PURPOSE:
    Score tracked offers against Brian's promote-vs-build rule and persist
    the verdicts, so the Affiliate Chief briefs promote-vs-build from
    researched terms instead of hype.

WHY:
    Brian 2026-09-27 promote-vs-build rule: PROMOTE an offer only if (1) it
    has a legit affiliate program, (2) the product is evergreen, and (3)
    commissions are RECURRING — ideally recurring forever. One-time payouts
    fail, no matter how big. Where no good affiliate option exists, the
    offer becomes a BUILD candidate instead.
    Brian refined "evergreen" the same day: evergreen means WE CAN BUILD
    CONTENT FOR IT LONG TERM. The test is content durability — will a
    review/tutorial/comparison written today still be accurate and earning
    in 2+ years? A product that exists but reinvents itself every 6 months
    fails: the content rots, and content that rots can't compound. Score it
    on product stability (no constant rebrands/pivots/pricing churn),
    vendor track record (established company vs serial launcher), category
    permanence (scheduling tools = permanent; fad AI wrapper = not), and
    affiliate-program terms stability.
    Without this filter, the marketer-watch offer signal ("what the top
    earners are pushing") would push Brian toward promoting launch-churn
    products with one-time payouts — exactly what the rule forbids.

CALLED BY:
    - Humans / driver agents: --offer, --record, --list, --verdicts
    - Watch loop: --check-offers scans marketer-watch offer tags and emits
      the research queue; a driver agent researches each item (vendor site
      first, then coverage) and records findings with --record.
    - Future: board brief puller for the Chief Affiliate Marketing Officer
      (reads --verdicts output; not wired yet — see NOTES).

NOTES:
    - Web research lives with the DRIVER, not this script: there is no
      server-side search API on the VM, and judging "legit program" vs
      "review-site rumor" needs a human/agent eye. This script emits the
      research brief (--offer), stores findings (--record), and computes
      the verdict deterministically. Same agent-driven pattern as
      tools/intake_triage.py.
    - Tri-state fields (yes/no/unknown), never bare booleans: "unknown"
      means unverified, which is not the same as "no". Never invent
      commission terms — unverified terms cap the verdict at MAYBE.
    - Slugs reuse marketer_watch.offer_slug (single definition).
    - --check-offers reads the offer:<slug> tags from second_brain (the
      marketer-watch enrichment records) and resolves display names from
      the watcher's seen db; the verdict store is affiliate_programs.db.
    - Verdicts go stale: --pending includes rows older than 180 days.
      Affiliate terms change; a 2024 "30% recurring" claim needs rechecks.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from second_brain import pg_exec          # noqa: E402  (import-safe, __main__-guarded)
from marketer_watch import offer_slug     # noqa: E402  (single slug definition)

DB_PATH = os.path.join(HERE, "affiliate_programs.db")
WATCH_DB = os.path.join(HERE, "marketer_watch.db")
RECHECK_DAYS = 180  # verdicts older than this are due for re-research

SCHEMA = """
CREATE TABLE IF NOT EXISTS affiliate_programs (
  slug               TEXT PRIMARY KEY,
  display            TEXT NOT NULL,
  has_program        TEXT NOT NULL DEFAULT 'unknown',  -- yes/no/unknown
  program_url        TEXT,
  recurring          TEXT NOT NULL DEFAULT 'unknown',  -- yes/no/unknown
  commission_terms   TEXT,                              -- e.g. "30% recurring, lifetime"
  commission_verified INTEGER NOT NULL DEFAULT 0,       -- 1 = seen on vendor's own page/docs
  cookie_days        INTEGER,                           -- NULL = unknown, never guessed
  evergreen          TEXT NOT NULL DEFAULT 'unknown',  -- yes/no/unknown (content-durability test)
  evergreen_rationale TEXT,
  verdict            TEXT,                              -- PROMOTE / MAYBE / SKIP
  build_candidate    INTEGER NOT NULL DEFAULT 0,
  build_note         TEXT,
  notes              TEXT,
  researched_at      TEXT,
  researched_by      TEXT DEFAULT 'affiliate_program_check'
)
"""


def db():
    con = sqlite3.connect(DB_PATH)
    con.execute(SCHEMA)
    con.commit()
    return con


def compute_verdict(has_program, recurring, evergreen, commission_verified):
    """Deterministic verdict from Brian's promote-vs-build rule.

    PROMOTE needs all three (legit program, evergreen content-durability,
    recurring commissions) with terms verified on the vendor's own page.
    One-time payouts always fail -> SKIP. Anything unverifiable -> MAYBE.
    """
    hp, rc, ev = has_program, recurring, evergreen
    if hp == "no":
        return ("SKIP", "no affiliate program found")
    if rc == "no":
        return ("SKIP", "one-time commissions fail Brian's recurring-forever rule")
    if hp == "unknown" or rc == "unknown":
        return ("MAYBE", "program or commission structure unverified — research deeper")
    # hp == yes and rc == yes from here
    if ev == "no":
        return ("MAYBE", "recurring program exists but product fails the "
                         "content-durability test — short-term promo only, "
                         "don't build a content moat on it")
    if ev == "unknown":
        return ("MAYBE", "recurring program exists; evergreen (content "
                         "durability) not yet assessed")
    if not commission_verified:
        return ("MAYBE", "meets the three criteria but commission terms not "
                         "verified on the vendor's own page")
    return ("PROMOTE", "legit recurring program + content-durable product, "
                       "terms verified")


# ------------------------------------------------------------------ queries

def watcher_offers(days=30):
    """Offer slugs from marketer-watch: union of second_brain offer:* tags
    (last N days) and the watcher's seen db (offer_slug set during
    enrichment/--set-offer). Display names resolve from the seen db.

    WHY the union: the seen db is the watcher's canonical offer store and
    always has display strings; second_brain tags are the durable,
    queryable record. Either side can lag the other, so the loop reads both.
    """
    slugs = set()
    try:
        rows = pg_exec(
            "SELECT DISTINCT t FROM second_brain, unnest(tags) t "
            f"WHERE t LIKE 'offer:%' AND created_at >= now() - interval '{int(days)} days';"
        )
        slugs.update(r[6:] for r in rows.splitlines() if r.startswith("offer:"))
    except Exception as e:
        print(f"warning: second_brain offer-tag query failed: {e}", file=sys.stderr)
    displays = {}
    if os.path.exists(WATCH_DB):
        con = sqlite3.connect(WATCH_DB)
        try:
            cutoff = (datetime.now(timezone.utc).timestamp() - int(days) * 86400)
            for offer, oslug, seen in con.execute(
                    "SELECT offer, offer_slug, first_seen_at FROM seen_videos "
                    "WHERE offer_slug IS NOT NULL"):
                try:
                    ts = datetime.fromisoformat(seen).timestamp()
                except (TypeError, ValueError):
                    ts = 0
                if ts >= cutoff:
                    slugs.add(oslug)
                    if offer and oslug not in displays:
                        displays[oslug] = offer
        finally:
            con.close()
    return [(s, displays.get(s, s)) for s in sorted(slugs)]


def verdict_row(con, slug):
    return con.execute(
        "SELECT * FROM affiliate_programs WHERE slug=?", (slug,)).fetchone()


def _rows(con):
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------------------ commands

def cmd_offer(name):
    slug = offer_slug(name)
    con = db()
    _rows(con)
    row = con.execute("SELECT * FROM affiliate_programs WHERE slug=?",
                      (slug,)).fetchone()
    con.close()
    if row and row["verdict"]:
        print_verdict_card(dict(row))
        return 0
    print(f"RESEARCH NEEDED: {name}  (slug: {slug})")
    print("-" * 70)
    print("1. Vendor site first: <product>.com/affiliates, /partners, /referral")
    print("   Program exists? In-house or network (JVZoo/WarriorPlus = one-time)?")
    print("2. Commission: recurring % or one-time? Get the exact terms.")
    print("   VERIFY on the vendor's own page — review-site numbers alone don't count.")
    print("3. Cookie length in days (unknown is fine; never guess).")
    print("4. EVERGREEN = content durability: will a review/tutorial written today")
    print("   still be accurate and earning in 2+ years?")
    print("   - product stability: rebrands? pivots? pricing churn?")
    print("   - vendor track record: established company vs serial launcher")
    print("   - category permanence: scheduling = permanent; fad AI wrapper = not")
    print("   - program terms stability: have payouts/terms changed before?")
    print()
    print("Then record findings:")
    print(f'  affiliate_program_check.py --record --display "{name}" \\')
    print("    --has-program yes|no|unknown --recurring yes|no|unknown \\")
    print('    --commission-terms "..." --commission-verified \\')
    print("    --cookie-days N --evergreen yes|no|unknown \\")
    print('    --evergreen-rationale "..." --notes "..."')
    return 0


def cmd_record(a):
    slug = a.slug or offer_slug(a.display)
    verdict, reason = compute_verdict(a.has_program, a.recurring,
                                      a.evergreen, a.commission_verified)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con = db()
    con.execute(
        """INSERT INTO affiliate_programs
           (slug, display, has_program, program_url, recurring,
            commission_terms, commission_verified, cookie_days,
            evergreen, evergreen_rationale, verdict,
            build_candidate, build_note, notes, researched_at, researched_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(slug) DO UPDATE SET
             display=excluded.display, has_program=excluded.has_program,
             program_url=excluded.program_url, recurring=excluded.recurring,
             commission_terms=excluded.commission_terms,
             commission_verified=excluded.commission_verified,
             cookie_days=excluded.cookie_days, evergreen=excluded.evergreen,
             evergreen_rationale=excluded.evergreen_rationale,
             verdict=excluded.verdict,
             build_candidate=excluded.build_candidate,
             build_note=excluded.build_note, notes=excluded.notes,
             researched_at=excluded.researched_at,
             researched_by=excluded.researched_by""",
        (slug, a.display, a.has_program, a.program_url, a.recurring,
         a.commission_terms, 1 if a.commission_verified else 0,
         a.cookie_days, a.evergreen, a.evergreen_rationale, verdict,
         1 if a.build_candidate else 0, a.build_note, a.notes, now,
         a.researched_by))
    con.commit()
    con.close()
    if a.dry_run:
        print(f"[dry-run] would record {slug} -> {verdict} ({reason})")
        return 0
    print(f"recorded: {a.display} [{slug}] -> {verdict}")
    print(f"reason: {reason}")
    return 0


def cmd_pending(as_json=False):
    """Offers needing research: watcher offers with no verdict or stale verdict."""
    con = db()
    _rows(con)
    cutoff = datetime.now(timezone.utc).timestamp() - RECHECK_DAYS * 86400
    pending = []
    for slug, display in watcher_offers():
        row = con.execute("SELECT verdict, researched_at FROM affiliate_programs "
                          "WHERE slug=?", (slug,)).fetchone()
        need = "no verdict yet"
        if row and row["verdict"]:
            try:
                ts = datetime.fromisoformat(row["researched_at"]).timestamp()
                need = None if ts >= cutoff else f"stale verdict ({row['verdict']}, >{RECHECK_DAYS}d old)"
            except (TypeError, ValueError):
                need = "verdict timestamp unreadable — re-research"
        if need:
            pending.append({"slug": slug, "display": display, "reason": need,
                            "existing_verdict": row["verdict"] if row else None})
    con.close()
    if as_json:
        print(json.dumps(pending, indent=2))
    elif not pending:
        print("No offers pending research — every watched offer has a fresh verdict.")
    else:
        print(f"{'SLUG':20} {'DISPLAY':40} STATUS")
        print("-" * 80)
        for p in pending:
            print(f"{p['slug']:20} {p['display'][:40]:40} {p['reason']}")
    return 0


def cmd_check_offers(days, as_json=False):
    """The loop-closer: watcher offers -> which lack verdicts."""
    offers = watcher_offers(days=days)
    con = db()
    _rows(con)
    out = []
    for slug, display in offers:
        row = con.execute("SELECT verdict FROM affiliate_programs WHERE slug=?",
                          (slug,)).fetchone()
        out.append({"slug": slug, "display": display,
                    "verdict": row["verdict"] if row else None})
    con.close()
    if as_json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"Watcher offers (last {days} days) vs affiliate verdicts")
    print("=" * 72)
    if not out:
        print("No offer tags found in second_brain for this window.")
        return 0
    for o in out:
        v = o["verdict"] or "NO VERDICT — research needed"
        print(f"  [{v:12}] {o['display']}  (offer:{o['slug']})")
    missing = [o for o in out if not o["verdict"]]
    if missing:
        print(f"\n{len(missing)} offer(s) need research: "
              + ", ".join(o["display"] for o in missing))
    return 0


def cmd_list():
    con = db()
    _rows(con)
    rows = con.execute("SELECT slug, display, verdict, recurring, evergreen, "
                       "researched_at FROM affiliate_programs "
                       "ORDER BY researched_at DESC").fetchall()
    con.close()
    if not rows:
        print("No affiliate program records yet.")
        return 0
    print(f"{'SLUG':18} {'VERDICT':9} {'RECUR':7} {'EVERGREEN':9} DISPLAY")
    print("-" * 78)
    for r in rows:
        print(f"{r['slug']:18} {(r['verdict'] or '-'):9} {r['recurring']:7} "
              f"{r['evergreen']:9} {r['display'][:34]}")
    return 0


def print_verdict_card(r):
    print(f"Offer:   {r['display']}  (offer:{r['slug']})")
    print(f"Verdict: {r['verdict']}")
    print(f"Program: {r['has_program']}" +
          (f"  ({r['program_url']})" if r.get("program_url") else ""))
    print(f"Terms:   {r['commission_terms'] or 'unknown'}"
          f"  [{'verified' if r['commission_verified'] else 'UNVERIFIED'}]")
    print(f"Cookie:  {r['cookie_days'] if r['cookie_days'] is not None else 'unknown'} days")
    print(f"Recurring: {r['recurring']}   Evergreen(content-durable): {r['evergreen']}")
    if r.get("evergreen_rationale"):
        print(f"  why: {r['evergreen_rationale']}")
    if r.get("build_candidate"):
        print(f"BUILD CANDIDATE: {r['build_note'] or 'no recurring affiliate option'}")
    if r.get("notes"):
        print(f"Notes: {r['notes']}")
    print(f"Researched: {r['researched_at']} by {r['researched_by']}")


def cmd_verdicts():
    """The promote-vs-build table for the Affiliate Chief."""
    con = db()
    _rows(con)
    rows = con.execute("SELECT * FROM affiliate_programs ORDER BY "
                       "CASE verdict WHEN 'PROMOTE' THEN 0 WHEN 'MAYBE' THEN 1 "
                       "ELSE 2 END, display").fetchall()
    con.close()
    print("Promote-vs-build verdicts (Brian's rule: legit program + evergreen "
          "content + recurring forever)")
    print("=" * 78)
    if not rows:
        print("No verdicts recorded yet.")
        return 0
    for r in [dict(x) for x in rows]:
        flag = " [BUILD CANDIDATE]" if r["build_candidate"] else ""
        terms = r["commission_terms"] or "terms unknown"
        print(f"[{r['verdict']:7}]{flag} {r['display']}")
        print(f"           {terms} | recurring={r['recurring']} "
              f"evergreen={r['evergreen']}")
    print("=" * 78)
    prom = sum(1 for r in rows if r["verdict"] == "PROMOTE")
    print(f"{prom} PROMOTE / {len(rows)} total. "
          "Evergreen = content written today still earns in 2+ years.")
    return 0


# ------------------------------------------------------------------ main

def main():
    p = argparse.ArgumentParser(
        description="Affiliate-program checker: Brian's recurring-forever "
                    "promote filter.")
    p.add_argument("--offer", metavar="NAME",
                   help="look up an offer; prints verdict or a research brief")
    p.add_argument("--record", action="store_true",
                   help="record research findings for --display")
    p.add_argument("--display", help="offer display name (for --record)")
    p.add_argument("--slug", help="override slug (default: derived from --display)")
    p.add_argument("--has-program", choices=["yes", "no", "unknown"],
                   default="unknown")
    p.add_argument("--program-url", default=None)
    p.add_argument("--recurring", choices=["yes", "no", "unknown"],
                   default="unknown")
    p.add_argument("--commission-terms", default=None)
    p.add_argument("--commission-verified", action="store_true",
                   help="terms verified on the vendor's own page/docs")
    p.add_argument("--cookie-days", type=int, default=None)
    p.add_argument("--evergreen", choices=["yes", "no", "unknown"],
                   default="unknown",
                   help="content-durability: accurate + earning in 2+ years?")
    p.add_argument("--evergreen-rationale", default=None)
    p.add_argument("--build-candidate", action="store_true")
    p.add_argument("--build-note", default=None)
    p.add_argument("--notes", default=None)
    p.add_argument("--researched-by", default="affiliate_program_check")
    p.add_argument("--pending", action="store_true",
                   help="offers needing (re)research")
    p.add_argument("--check-offers", action="store_true",
                   help="watcher offers vs verdicts (closes the loop)")
    p.add_argument("--days", type=int, default=30,
                   help="lookback window for --check-offers")
    p.add_argument("--list", action="store_true")
    p.add_argument("--verdicts", action="store_true",
                   help="promote-vs-build table")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.offer:
        return cmd_offer(a.offer)
    if a.record:
        if not a.display:
            print("--record needs --display", file=sys.stderr)
            return 2
        return cmd_record(a)
    if a.pending:
        return cmd_pending(as_json=a.json)
    if a.check_offers:
        return cmd_check_offers(a.days, as_json=a.json)
    if a.list:
        return cmd_list()
    if a.verdicts:
        return cmd_verdicts()
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
