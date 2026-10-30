#!/usr/bin/env python3
"""build_zones.py — the build, its price-power zone, and its why.

Brian 2026-10-22: "add to dealsdesk (or improve current system) the
build and the build zones ... and the why".

PURPOSE: DealsDesk-side operator tool joining three things that used
         to live apart: a BUILD (dealsdesk.builds), the price-power
         ZONE it lives in (dealsdesk.build_zones — Z1-Z6 from
         docs/architecture/price-power-zones-2026-10-20.md, prose
         until now), and the build's WHY (builds.why) plus the need
         it satisfies (builds.need_id -> ecosystem_needs).
WHY:     Zones carried doctrine ("buy by the node, win by the
         count") that no scorer or tracker could read, and builds
         carried parts lists with no recorded reason. A build
         without a why is a shopping list; with one, it is a
         decision the system can check parts against.
RULES:   Deterministic field mapping only (house rule). Zone bands
         overlap because zones are physics classes, not partitions —
         assignment is Brian's call, recorded here, never inferred
         from price by this tool. Nothing buys anything.
CALLED BY: operator (Brian / Muse).
CANONICAL: successbrian-os/tools/dealsdesk/build_zones.py
DEPLOYED:  /home/dealsdesk/scripts/build_zones.py (k11-alpha)
SCHEMA:    2026-10-22_build_zones_why.sql.
"""

import argparse
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [build_zones] %(message)s")
LOG = logging.getLogger("build_zones")

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


# SBOS common routines - Batch C migration (2026-10-27).
import os as _os_c, sys as _sys_c
_sys_c.path.insert(0, _os_c.path.join(_os_c.path.dirname(_os_c.path.abspath(__file__)), ".."))
import sbos_common  # noqa: E402


def esc(s):
    # Batch C migration (2026-10-27): delegates to sbos_common.esc -
    # the one SQL-escape definition for the ecosystem.
    return sbos_common.esc(s)


def cmd_zones(a):
    rows = psql(
        "SELECT zone_code, name, COALESCE(price_min::text,''), "
        "COALESCE(price_max::text,''), COALESCE(doctrine,'') "
        "FROM dealsdesk.build_zones ORDER BY zone_code")
    if rows is None:
        return 1
    for code, name, lo, hi, doctrine in rows:
        band = f"${float(lo):,.0f}-${float(hi):,.0f}" if lo and hi \
            else "no capex"
        print(f"{code} {name} ({band})")
        print(f"   why/doctrine: {doctrine}")
    return 0


def cmd_show(a):
    rows = psql(
        "SELECT b.id, b.name, b.status, COALESCE(b.zone_code,''), "
        "COALESCE(b.why,''), COALESCE(b.need_id::text,''), "
        "COALESCE(z.name,''), COALESCE(z.doctrine,'') "
        "FROM dealsdesk.builds b LEFT JOIN dealsdesk.build_zones z "
        f"ON z.zone_code=b.zone_code WHERE b.id={int(a.build)}")
    if not rows:
        LOG.error("no build %s", a.build)
        return 1
    bid, name, status, zone, why, need, zname, doctrine = rows[0]
    print(f"BUILD {bid} [{status}] {name}")
    print(f"  zone: {zone} {zname}".rstrip())
    if doctrine:
        print(f"  zone why: {doctrine}")
    print(f"  why: {why or '(not recorded)'}")
    if need:
        n = psql("SELECT subject FROM dealsdesk.ecosystem_needs "
                 f"WHERE id={int(need)}")
        print(f"  satisfies need {need}: {n[0][0] if n else '?'}")
    items = psql(
        "SELECT count(*), COALESCE(sum(quantity*price_ea),0) "
        "FROM dealsdesk.build_items WHERE build_id=" + str(int(bid))
        + " AND price_ea IS NOT NULL")
    if items:
        print(f"  priced items: {items[0][0]} "
              f"(priced total ${float(items[0][1]):,.2f})")
    return 0


def cmd_set(a):
    sets = []
    if a.zone is not None:
        sets.append(f"zone_code='{esc(a.zone)}'")
    if a.why is not None:
        sets.append(f"why='{esc(a.why)}'")
    if a.need is not None:
        sets.append(f"need_id={int(a.need)}")
    if not sets:
        LOG.error("set: nothing to set")
        return 1
    ok = psql("UPDATE dealsdesk.builds SET " + ", ".join(sets)
              + f", updated_at=now() WHERE id={int(a.build)}", write=True)
    LOG.info("build %s updated (%s)", a.build, ", ".join(sets))
    return 0 if ok else 1


def cmd_add_build(a):
    rows = psql("SELECT id FROM dealsdesk.builds WHERE name='"
                + esc(a.name) + "'")
    if rows:
        LOG.info("build already exists (id %s): %s", rows[0][0], a.name)
        return 0
    rows = psql(
        "INSERT INTO dealsdesk.builds "
        "(name, description, status, zone_code, why, need_id) VALUES ("
        f"'{esc(a.name)}', '{esc(a.description or '')}', 'planning', "
        f"'{esc(a.zone)}', '{esc(a.why)}', "
        f"{int(a.need) if a.need else 'NULL'}) RETURNING id")
    if not rows:
        return 1
    LOG.info("created build %s: %s (zone %s)", rows[0][0], a.name, a.zone)
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("zones").set_defaults(fn=cmd_zones)
    s = sub.add_parser("show")
    s.add_argument("--build", type=int, required=True)
    s.set_defaults(fn=cmd_show)
    t = sub.add_parser("set")
    t.add_argument("--build", type=int, required=True)
    t.add_argument("--zone")
    t.add_argument("--why")
    t.add_argument("--need", type=int)
    t.set_defaults(fn=cmd_set)
    b = sub.add_parser("add-build")
    b.add_argument("--name", required=True)
    b.add_argument("--zone", required=True)
    b.add_argument("--why", required=True)
    b.add_argument("--need", type=int)
    b.add_argument("--description", default="")
    b.set_defaults(fn=cmd_add_build)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
