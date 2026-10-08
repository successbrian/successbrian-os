#!/usr/bin/env python3
"""seller_blocklist.py — the ONE common gate against blacklisted sellers.

PURPOSE: Single canonical check every writer calls before persisting
         seller-linked data: is this seller blacklisted? If yes, the write
         is refused. Covers DealsDesk listing ingest AND people/business
         intel writes (people_unified).

WHY:     Brian 2026-10-08: "we need a common way to make sure we're always
         not adding that data to our dealsdesk database and not saving the
         intel of those sellers into our people.people and business tables."
         Before this module the blacklist lived in three k11 scripts
         (auto_blacklist_dropdown_sellers.py, daily_dropdown_scammer_hunt.py,
         picclick_seller_guard.py), each with its own DB code, and NOTHING
         guarded the people/business write path at all. One module, one
         table (public.seller_blacklist), every writer calls it. Brian's
         standing policy (08-19): any seller caught on dropdown scams =
         permanent block — no listings in DB, no business, ever.

CALLED BY: Any code that writes seller-linked rows: DealsDesk ingest
         (picclick_rack_search.py --with-sellers, future timers), people /
         business intel writers, and humans via --check / --block.

NOTES:   - Detection (finding scammers) stays in the k11 scripts; this is
           the enforcement gate. Detectors call block_seller(); writers call
           is_blocked()/guard_write().
         - Table lives in ecosystem_central.public.seller_blacklist
           (28 active rows as of 2026-10-08). DB writes use the repo-standard
           psql-subprocess pattern, matching the other tools/dealsdesk code.
         - Seller matching is exact on the eBay/PicClick username (PicClick
           mirrors eBay usernames). Case-insensitive compare.
         - This module never unblocks: unblocking is a human decision done
           directly in the DB (is_active=false), never by code.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/seller_blocklist.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/seller_blocklist.py (k11-alpha; when wired in).

"""

import argparse
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [blocklist] %(message)s")
LOG = logging.getLogger("blocklist")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"
TABLE = "public.seller_blacklist"


def psql(sql, write=False):
    cmd = ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return [] if not write else False
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return (s or "").replace("'", "''")


def load_blocked():
    """All active blacklisted seller usernames (lowercased set)."""
    rows = psql("SELECT lower(seller) FROM %s WHERE is_active" % TABLE)
    return {r[0] for r in rows if r and r[0]}


def is_blocked(seller):
    """True if this seller is blacklisted. Unknown/empty seller -> False."""
    if not seller or not seller.strip():
        return False
    rows = psql(
        "SELECT 1 FROM %s WHERE is_active AND lower(seller)=lower('%s') LIMIT 1"
        % (TABLE, esc(seller.strip())))
    return bool(rows)


def block_seller(seller, reason, by="seller_blocklist"):
    """Idempotent permanent blacklist upsert. Returns True on write."""
    seller = (seller or "").strip()
    if not seller:
        return False
    ok = psql(
        "INSERT INTO %s (seller, reason, blacklisted_by, is_active) "
        "VALUES ('%s', '%s', '%s', TRUE) "
        "ON CONFLICT (seller) DO UPDATE SET reason=EXCLUDED.reason, "
        "is_active=TRUE, blacklisted_by=EXCLUDED.blacklisted_by" % (
            TABLE, esc(seller), esc(reason), esc(by)),
        write=True)
    if ok:
        LOG.warning("BLOCKED seller=%s reason=%s", seller, reason[:80])
    return bool(ok)


def guard_write(seller, table, context=""):
    """Checkpoint for people/business/DealsDesk writers.

    Returns True if the write may proceed, False if the seller is blocked
    (and logs the refusal). Call this BEFORE inserting any seller-linked
    row — people.people, business tables, listing tables, all of them.
    """
    if is_blocked(seller):
        LOG.warning("REFUSED write to %s for blacklisted seller=%s ctx=%s",
                    table, seller, context[:100])
        return False
    return True


def filter_blocked(candidates, seller_key="seller"):
    """Drop blacklisted sellers' entries from a candidate list.

    Returns (kept, dropped_count). Sellers unknown/empty are kept —
    absence of identity is not guilt; the detectors handle those.
    """
    blocked = load_blocked()
    kept, dropped = [], 0
    for c in candidates:
        s = (c.get(seller_key) or "").strip().lower()
        if s and s in blocked:
            dropped += 1
            LOG.warning("dropped blacklisted seller listing: %s",
                        c.get("name", "?")[:60])
        else:
            kept.append(c)
    return kept, dropped


def main(argv=None):
    ap = argparse.ArgumentParser(description="Seller blocklist gate.")
    ap.add_argument("--check", help="check one seller username")
    ap.add_argument("--block", nargs=2, metavar=("SELLER", "REASON"),
                    help="permanently blacklist a seller")
    ap.add_argument("--list", action="store_true", help="list active sellers")
    args = ap.parse_args(argv)

    if args.check:
        print("BLOCKED" if is_blocked(args.check) else "clean")
        return 0
    if args.block:
        print("blocked" if block_seller(args.block[0], args.block[1]) else "failed")
        return 0
    if args.list:
        for s in sorted(load_blocked()):
            print(s)
        return 0
    ap.error("one of --check, --block, --list is required")


if __name__ == "__main__":
    sys.exit(main())
