#!/usr/bin/env python3
"""suppliers.py — DealsDesk's supplier registry: who they are, how
reliable they have proven, and EVERYTHING they offer.

Brian 2026-10-22: "anything we buy from China needs to be
reliable. not going to ditch. I want to build long term
relationships with reliable honest people" and "when we find a
good Chinese supplier, we want to know everything they offer".

PURPOSE: One record per SUPPLIER (dealsdesk.suppliers): region,
         reliability on the ladder unrated -> repeat-contact ->
         established, relationship notes, and catalog state. Their
         offerings (dealsdesk.supplier_offerings) hold the full
         known catalog, so a good supplier's whole range is
         matchable against future needs — not just the one item
         they were first quoted on.
WHY:     Reliability used to be re-tagged on every quote row; a
         relationship is with the supplier, not the quote. The
         need_sources verdict gate reads this registry when a
         source is linked (registry wins over per-quote tags).
RULES:   Reliability changes only on evidence or Brian's word —
         this tool records, it does not judge. Catalog_status:
         unknown (never swept), partial (some offerings known),
         captured (full storefront swept, date in
         catalog_checked_at). Nothing buys anything.
CALLED BY: operator (Brian / Muse).
CANONICAL: successbrian-os/tools/dealsdesk/suppliers.py
DEPLOYED:  /home/dealsdesk/scripts/suppliers.py (k11-alpha)
SCHEMA:    2026-10-22_suppliers_registry.sql.
"""

import argparse
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [suppliers] %(message)s")
LOG = logging.getLogger("suppliers")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def psql(sql, write=False):
    r = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:300])
        return None
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return str(s).replace("'", "''")


def supplier_id(name):
    rows = psql("SELECT id FROM dealsdesk.suppliers WHERE name='"
                + esc(name) + "'")
    return int(rows[0][0]) if rows else None


def cmd_add_supplier(a):
    sid = supplier_id(a.name)
    if sid:
        LOG.info("supplier exists (id %s): %s", sid, a.name)
        return 0
    rows = psql(
        "INSERT INTO dealsdesk.suppliers (name, region, reliability, "
        "relationship) VALUES ("
        f"'{esc(a.name)}', '{esc(a.region)}', '{esc(a.reliability)}', "
        f"'{esc(a.relationship or '')}') RETURNING id")
    if not rows:
        return 1
    LOG.info("supplier %s created: %s (%s, %s)",
             rows[0][0], a.name, a.region, a.reliability)
    return 0


def cmd_set(a):
    sid = supplier_id(a.supplier)
    if not sid:
        LOG.error("no supplier named %r", a.supplier)
        return 1
    sets = []
    if a.reliability is not None:
        sets.append(f"reliability='{esc(a.reliability)}'")
    if a.region is not None:
        sets.append(f"region='{esc(a.region)}'")
    if a.relationship is not None:
        sets.append(f"relationship='{esc(a.relationship)}'")
    if a.catalog_status is not None:
        sets.append(f"catalog_status='{esc(a.catalog_status)}'")
        if a.catalog_status == "captured":
            sets.append("catalog_checked_at=now()")
    if not sets:
        LOG.error("set: nothing to set")
        return 1
    ok = psql("UPDATE dealsdesk.suppliers SET " + ", ".join(sets)
              + f", updated_at=now() WHERE id={sid}", write=True)
    LOG.info("supplier %s updated (%s)", a.supplier, ", ".join(sets))
    return 0 if ok else 1


def cmd_list(a):
    rows = psql(
        "SELECT s.id, s.name, COALESCE(s.region,''), s.reliability, "
        "s.catalog_status, (SELECT count(*) FROM "
        "dealsdesk.supplier_offerings o WHERE o.supplier_id=s.id) "
        "FROM dealsdesk.suppliers s ORDER BY s.name")
    if rows is None:
        return 1
    for sid, name, region, rel, cat, n in rows:
        print(f"{name} [{region or '?'}] reliability={rel} "
              f"catalog={cat} offerings={n}")
    return 0


def cmd_offerings(a):
    sid = supplier_id(a.supplier)
    if not sid:
        LOG.error("no supplier named %r", a.supplier)
        return 1
    rows = psql(
        "SELECT COALESCE(category,''), item, COALESCE(detail,''), "
        "COALESCE(price::text,'') FROM dealsdesk.supplier_offerings "
        f"WHERE supplier_id={sid} ORDER BY category, item")
    print(f"{a.supplier} — {len(rows) if rows else 0} known offering(s)")
    for row in (rows or []):
        # pad: psql drops trailing empty columns (e.g. no price)
        cat, item, detail, price = (list(row) + [""] * 4)[:4]
        p = f" ${float(price):,.2f}" if price else ""
        print(f"  [{cat}] {item}{p} — {detail}")
    return 0


def cmd_add_offering(a):
    sid = supplier_id(a.supplier)
    if not sid:
        LOG.error("no supplier named %r", a.supplier)
        return 1
    price = str(float(a.price)) if a.price is not None else "NULL"
    rows = psql(
        "INSERT INTO dealsdesk.supplier_offerings (supplier_id, "
        "category, item, detail, price, note) VALUES ("
        f"{sid}, '{esc(a.category or '')}', '{esc(a.item)}', "
        f"'{esc(a.detail or '')}', {price}, '{esc(a.note or '')}') "
        "RETURNING id")
    if not rows:
        return 1
    psql("UPDATE dealsdesk.suppliers SET catalog_status="
         "CASE WHEN catalog_status='unknown' THEN 'partial' "
         "ELSE catalog_status END, updated_at=now() "
         f"WHERE id={sid}", write=True)
    LOG.info("offering %s added for %s: %s", rows[0][0], a.supplier, a.item)
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add-supplier")
    s.add_argument("--name", required=True)
    s.add_argument("--region", default="")
    s.add_argument("--reliability", default="unrated")
    s.add_argument("--relationship", default="")
    s.set_defaults(fn=cmd_add_supplier)

    t = sub.add_parser("set")
    t.add_argument("--supplier", required=True)
    t.add_argument("--reliability")
    t.add_argument("--region")
    t.add_argument("--relationship")
    t.add_argument("--catalog-status")
    t.set_defaults(fn=cmd_set)

    sub.add_parser("list").set_defaults(fn=cmd_list)

    o = sub.add_parser("offerings")
    o.add_argument("--supplier", required=True)
    o.set_defaults(fn=cmd_offerings)

    n = sub.add_parser("add-offering")
    n.add_argument("--supplier", required=True)
    n.add_argument("--item", required=True)
    n.add_argument("--category", default="")
    n.add_argument("--detail", default="")
    n.add_argument("--price", type=float)
    n.add_argument("--note", default="")
    n.set_defaults(fn=cmd_add_offering)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
