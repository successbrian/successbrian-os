#!/usr/bin/env python3
"""Site Demand — every Wix site in the fleet is an ongoing need.

Brian (2026-10-26): "as we are adding more wix sites, this should be
putting more ongoing thinking, planning, content creation, video
creation, marketing promotion need for the ecosystem... campaignsdesk
or successbrian os calculating that need and dealsdesk reading it."

The calculator (SBOS side, beside demand_meter.py in the capacity
family):

  * reads the fleet registry — successbrian_os.marketing_wix_sites,
    the CampaignsDesk/SBOS chain registry every site is born into;
  * applies the per-site demand model below: a published site needs
    thinking/planning, content, video, and promotion EVERY WEEK, for
    as long as it lives. A building site needs less; a planned site
    needs planning only;
  * writes the aggregate into SBOS as a standing need (Atlas node
    need:site-fleet-demand) and files it through the same handoff
    DealsDesk reads (sbos_need_requests -> needs_intake ->
    dealsdesk.ecosystem_needs), sized against the content factory
    workload that must answer it.

The per-site rates are OPERATING DEFAULTS in one place (RATES) —
the principle is Brian's (sites generate ongoing need), the numbers
are the ecosystem's current settings, tunable in code, not a Brian
ruling. When the fleet grows, the item text changes ("... N sites"),
so DealsDesk receives a fresh need per fleet size; recalcs at the
same size refresh the SBOS need node and the decision stream.

Usage: site_demand.py [--dry-run] [--seed-known-sites] | selftest
Cron: daily 05:50, ahead of the ERP loop's 06:00 need_from_task.
"""

import argparse
import json
import sys
from datetime import date

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json

DBNAME = "ecosystem_central"
NEED_KEY = "need:site-fleet-demand"
WORKLOAD = "plan:content-factory"
SBOS_PRIORITY = 6
STANDING_TASK_TYPE = "recurring"
STANDING_TASK_TITLE = "Workload needs handoff (SBOS -> DealsDesk)"

# Per-site weekly demand by site status. Words in the output; these
# are the volumes behind the words.
RATES = {
    "published": {"planning_cycles": 1.0, "content_posts": 2.0,
                  "videos": 1.0, "promotion_touches": 3.0},
    "building": {"planning_cycles": 1.0, "content_posts": 1.0,
                 "videos": 0.0, "promotion_touches": 1.0},
    "planned": {"planning_cycles": 0.5, "content_posts": 0.0,
                "videos": 0.0, "promotion_touches": 0.0},
}

# Sites Brian has published that the registry was missing (the
# TrafficStreemz chain-registry row was never created at publish
# time — recorded in MEMORY 2026-10-26). Seeded only when absent.
KNOWN_SITES = [
    {"name": "TrafficStreemz",
     "wixsite_url": "https://aiprofits2025.wixsite.com/trafficstreemz",
     "purpose": "Front door for the $30/mo TrafficStreemz system: "
                "audience building for network marketers "
                "(published 2026-10-26; audience/waitlist until the "
                "hosting + finished-code launch gate clears)",
     "status": "published"},
]


def pg():
    return psycopg2.connect(dbname=DBNAME, host="localhost",
                            user="postgres")


def calculate(sites):
    """sites: list of dicts with at least 'status'. Returns
    (totals, counts) — pure, so the selftest can drive it."""
    totals = {"planning_cycles": 0.0, "content_posts": 0.0,
              "videos": 0.0, "promotion_touches": 0.0}
    counts = {}
    for s in sites:
        st = s["status"]
        counts[st] = counts.get(st, 0) + 1
        for k, v in RATES.get(st, {}).items():
            totals[k] += v
    return totals, counts


def fmt(x):
    return ("%g" % x)


def demand_sentence(totals, counts, n):
    return ("Site fleet demand (%d sites: %s): per week — "
            "%s thinking/planning cycle(s), %s content post(s), "
            "%s video(s), %s promotion touch(es)"
            % (n,
               ", ".join("%d %s" % (counts[k], k)
                         for k in sorted(counts)),
               fmt(totals["planning_cycles"]),
               fmt(totals["content_posts"]),
               fmt(totals["videos"]),
               fmt(totals["promotion_touches"])))


def seed_known_sites(conn):
    made = []
    with conn.cursor() as cur:
        for s in KNOWN_SITES:
            cur.execute(
                "INSERT INTO successbrian_os.marketing_wix_sites "
                "(name, wixsite_url, purpose, status) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (wixsite_url) "
                "DO NOTHING",
                (s["name"], s["wixsite_url"], s["purpose"],
                 s["status"]))
            if cur.rowcount:
                made.append(s["name"])
    conn.commit()
    return made


def standing_task(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.sbostasks WHERE task_type=%s "
            "AND title=%s ORDER BY id LIMIT 1",
            (STANDING_TASK_TYPE, STANDING_TASK_TITLE))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO public.sbostasks (task_type, title, status) "
            "VALUES (%s, %s, 'active') RETURNING id",
            (STANDING_TASK_TYPE, STANDING_TASK_TITLE))
        tid = cur.fetchone()[0]
    conn.commit()
    return tid


def run(conn, dry=False):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT name, wixsite_url, purpose, status FROM "
                "successbrian_os.marketing_wix_sites ORDER BY id")
    sites = [dict(r) for r in cur.fetchall()]
    totals, counts = calculate(sites)
    n = len(sites)
    published = counts.get("published", 0)
    sentence = demand_sentence(totals, counts, n)
    print(sentence)
    if dry:
        print("(dry run — nothing written)")
        return 0

    details = {"sites": sites, "weekly": totals, "site_counts": counts,
               "model": "site_demand RATES v1 (operating defaults)",
               "sbos_priority": SBOS_PRIORITY,
               "workload": WORKLOAD,
               "calculated_at": date.today().isoformat(),
               "calculated_by": "site_demand (SBOS, for CampaignsDesk)"}
    cur.execute("SELECT details FROM atlas.nodes WHERE node_key=%s",
                (NEED_KEY,))
    row = cur.fetchone()
    prev_weekly = (row["details"] or {}).get("weekly") if row else None
    cur.execute(
        "INSERT INTO atlas.nodes "
        "(node_key, node_type, name, status, details) "
        "VALUES (%s, 'need', %s, 'open', %s) "
        "ON CONFLICT (node_key) DO UPDATE SET "
        "details=EXCLUDED.details, status='open', updated_at=now()",
        (NEED_KEY, "Site fleet demand (%d sites)" % n, Json(details)))
    cur.execute(
        "INSERT INTO atlas.edges (from_node, to_node, edge_type, "
        "notes) VALUES (%s, %s, 'supports', %s) "
        "ON CONFLICT DO NOTHING",
        (NEED_KEY, "proj:blog-network",
         "the fleet's ongoing demand feeds the blog network"))
    if prev_weekly != totals:
        cur.execute(
            "INSERT INTO successbrian_os.pm_decisions "
            "(decided_by, decision, rationale, origin) "
            "VALUES ('site-demand', %s, %s, 'system')",
            ("Site fleet demand recalculated: " + sentence,
             "registry: marketing_wix_sites; model: site_demand "
             "RATES v1; read by DealsDesk through the need handoff"))
    conn.commit()

    tid = standing_task(conn)
    item = "Site fleet capacity — %d sites (%d published)" % (n,
                                                              published)
    specs = (sentence + " | Capacity answered by the content factory "
             "(writing/render/transcode/publish) plus promotion "
             "machinery. | workload: " + WORKLOAD)
    with conn.cursor() as cur2:
        cur2.execute(
            "INSERT INTO successbrian_os.sbos_need_requests "
            "(task_id, item, specs, qty, priority) "
            "VALUES (%s, %s, %s, 1, %s) "
            "ON CONFLICT (task_id, item) DO UPDATE SET "
            "specs=EXCLUDED.specs, updated_at=now()",
            (tid, item, specs, SBOS_PRIORITY))
    conn.commit()
    print("filed for DealsDesk: %r (task %d) — intake promotes it; "
          "SBOS need node %s updated" % (item, tid, NEED_KEY))
    return 0


def selftest():
    failures = []

    def check(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    sites = [{"status": "published"}, {"status": "published"},
             {"status": "building"}, {"status": "planned"}]
    totals, counts = calculate(sites)
    check(counts == {"published": 2, "building": 1, "planned": 1},
          "model: sites counted by status")
    check(totals["content_posts"] == 5.0
          and totals["videos"] == 2.0
          and totals["promotion_touches"] == 7.0
          and totals["planning_cycles"] == 3.5,
          "model: weekly demand sums across the fleet "
          "(2 published + 1 building + 1 planned)")
    empty, ec = calculate([])
    check(all(v == 0 for v in empty.values()) and ec == {},
          "model: an empty fleet demands nothing")
    s = demand_sentence(totals, counts, 4)
    check("content post" in s and "promotion" in s
          and "video" in s and "planning" in s,
          "model: the demand sentence names all four need kinds "
          "(thinking/planning, content, video, promotion)")
    if failures:
        print("SELFTEST FAILED: %d" % len(failures))
        return 1
    print("SELFTEST OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", nargs="?", choices=["run", "selftest"],
                    default="run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed-known-sites", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    conn = pg()
    try:
        if args.seed_known_sites:
            made = seed_known_sites(conn)
            print("seed: " + (", ".join(made) if made
                              else "known sites already registered"))
        return run(conn, dry=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
