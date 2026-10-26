#!/usr/bin/env python3
"""Build Loop — SBOS sees the need, DealsDesk plans the build, the
plan comes back into SBOS, and together they set priority and gates.

Brian (2026-10-26): "this should all be in successbrian-os...
successbrian-os sees the workflow and ecosystem need, hands it to
dealsdesk, dealsdesk plans the builds... puts the build plan into
successbrian os. together they determine priority and set gates."

This is R14 (the core determines, DealsDesk builds) carried through
the whole loop, in code:

  raise    SBOS files a need FOR A WORKLOAD: an Atlas need node the
           workload `requires`, plus the standing handoff row in
           successbrian_os.sbos_need_requests. DealsDesk's own
           needs_intake.py promotes it into dealsdesk.ecosystem_needs
           (the ERP contract: neither side writes the other's tables;
           each side's scripts are the only writers of its own).
  publish  DealsDesk's build plans come INTO SuccessBrian OS: every
           dealsdesk.builds row becomes an Atlas plan node carrying
           status, DealsDesk priority, cost, items, phases, and the
           workloads the build serves — linked to the SBOS need it
           implements and the workload that need serves.
  gates    Joint priority + gates, determined together: SBOS's need
           priority (ecosystem value) and DealsDesk's build priority
           and plan state are read together; the joint determination
           is written onto the plan and need nodes in SBOS and into
           the PM decision stream, and the plan's unsatisfied
           prerequisites become Atlas gates blocking the workload —
           visible through atlas.workload_gates_v (workload_gates.py).
           When a later run finds a prerequisite satisfied, the loop
           clears its own gate. It never touches a gate it did not
           mint (keys: gate:build-<id>-*).
  repair   One-time repair of the ERP loop's broken return leg: the
           live sbos_need_requests table was missing the need_id
           column its own schema declares, so needs_intake could not
           record promotions, duplicate needs accumulated, and
           need_status_sync failed daily (erp-loop.log, 2026-10-25).
           repair adds the column, backfills it, and drops duplicate
           needs (oldest per source+subject kept).

Commands: repair | raise | publish | gates | run | status | selftest
Deterministic code only; no model calls; never buys anything.
"""

import argparse
import json
import re
import sys
from datetime import date

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json

DBNAME = "ecosystem_central"
STANDING_TASK_TYPE = "recurring"
STANDING_TASK_TITLE = "Workload needs handoff (SBOS -> DealsDesk)"

PRICED_STATES = ("components_priced", "parts_ordered",
                 "parts_received", "building", "testing",
                 "deployed", "priced", "ordered", "running",
                 "complete", "done")
ONLINE_STATES = ("deployed", "running", "complete", "done")


def pg():
    return psycopg2.connect(dbname=DBNAME, host="localhost",
                            user="postgres")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def need_key_for(workload_key):
    return "need:workload-" + slugify(workload_key.split(":")[-1])


def parse_workload(text):
    if not text:
        return None
    m = re.search(r"workload:\s*(\S+)", text)
    return m.group(1) if m else None


def band_for(sbos_priority):
    if sbos_priority is None:
        return "unplanned"
    if sbos_priority >= 8:
        return "critical"
    if sbos_priority >= 6:
        return "high"
    if sbos_priority >= 4:
        return "standard"
    return "low"


# ---------------------------------------------------------------- repair

def repair(conn):
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE successbrian_os.sbos_need_requests "
            "ADD COLUMN IF NOT EXISTS need_id integer")
        cur.execute(
            "DO $$ BEGIN "
            "ALTER TABLE successbrian_os.sbos_need_requests "
            "ADD CONSTRAINT sbos_need_requests_need_id_fkey "
            "FOREIGN KEY (need_id) REFERENCES "
            "dealsdesk.ecosystem_needs(id) ON DELETE SET NULL; "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$")
        cur.execute(
            "UPDATE successbrian_os.sbos_need_requests r "
            "SET need_id = (SELECT min(n.id) FROM "
            "dealsdesk.ecosystem_needs n WHERE "
            "n.source = 'sbos_task:' || r.task_id "
            "AND n.subject = r.item) "
            "WHERE r.need_id IS NULL AND EXISTS "
            "(SELECT 1 FROM dealsdesk.ecosystem_needs n WHERE "
            "n.source = 'sbos_task:' || r.task_id "
            "AND n.subject = r.item)")
        backfilled = cur.rowcount
        cur.execute(
            "WITH ranked AS (SELECT id, row_number() OVER "
            "(PARTITION BY source, subject ORDER BY id) AS rn "
            "FROM dealsdesk.ecosystem_needs "
            "WHERE status IN ('open', 'planned')) "
            "UPDATE dealsdesk.ecosystem_needs n SET status='dropped', "
            "updated_at=now() FROM ranked r WHERE n.id = r.id "
            "AND r.rn > 1")
        dropped = cur.rowcount
    conn.commit()
    print("repair: need_id column present; %d request(s) backfilled; "
          "%d duplicate need(s) dropped" % (backfilled, dropped))
    return 0


# ---------------------------------------------------------------- raise

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


def raise_need(conn, workload, item, spec, priority, qty, max_cost):
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM atlas.nodes WHERE node_key=%s",
                    (workload,))
        row = cur.fetchone()
        if not row:
            print("no such workload in Atlas: %s" % workload)
            return 1
        wname = row[0]
    nkey = need_key_for(workload)
    details = {"workload": workload, "item": item, "spec": spec,
               "sbos_priority": priority, "qty": qty,
               "raised_by": "build_loop (SBOS)",
               "raised_at": date.today().isoformat()}
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details) "
            "VALUES (%s, 'need', %s, 'open', %s) "
            "ON CONFLICT (node_key) DO NOTHING",
            (nkey, "Need: " + item, Json(details)))
        need_made = cur.rowcount
        cur.execute(
            "INSERT INTO atlas.edges (from_node, to_node, edge_type, "
            "notes) VALUES (%s, %s, 'requires', %s) "
            "ON CONFLICT DO NOTHING",
            (workload, nkey,
             "SBOS sees this workload's need; DealsDesk plans the "
             "build that answers it"))
    conn.commit()
    tid = standing_task(conn)
    specs_full = (spec or "") + " | workload: " + workload
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO successbrian_os.sbos_need_requests "
            "(task_id, item, specs, qty, max_cost, priority) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (task_id, item) DO NOTHING",
            (tid, item, specs_full, qty, max_cost, priority))
        req_made = cur.rowcount
    conn.commit()
    print("raised need for %s (%s): atlas %s %s; handoff request %s "
          "(task %d) — DealsDesk intake promotes it"
          % (workload, wname, nkey,
             "created" if need_made else "already present",
             "created" if req_made else "already present", tid))
    return 0


# ---------------------------------------------------------------- publish

def publish(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM dealsdesk.builds ORDER BY id")
    builds = cur.fetchall()
    published = linked = 0
    for b in builds:
        bid = b["id"]
        cur.execute(
            "SELECT count(*) AS n, "
            "count(*) FILTER (WHERE price_ea IS NOT NULL) AS priced, "
            "COALESCE(sum(quantity * price_ea), 0) AS known "
            "FROM dealsdesk.build_items WHERE build_id=%s", (bid,))
        items = cur.fetchone()
        cur.execute(
            "SELECT workload FROM dealsdesk.build_workloads "
            "WHERE build_id=%s ORDER BY id", (bid,))
        workloads = [r["workload"] for r in cur.fetchall()]
        cur.execute(
            "SELECT name, status, gate_condition FROM "
            "dealsdesk.build_phases WHERE build_id=%s "
            "ORDER BY phase_no", (bid,))
        phases = [dict(r) for r in cur.fetchall()]
        details = {
            "build_id": bid, "need_id": b["need_id"],
            "dealsdesk_priority": b["priority"],
            "estimated_cost": (float(b["estimated_cost"])
                               if b["estimated_cost"] is not None
                               else None),
            "budget_target": (float(b["budget_target"])
                              if b["budget_target"] is not None
                              else None),
            "spent": float(b["spent"] or 0),
            "target_machine": b["target_machine"],
            "box_name": b["box_name"], "zone_code": b["zone_code"],
            "why": b["why"],
            "items": {"count": items["n"], "priced": items["priced"],
                      "known_cost": float(items["known"])},
            "workloads": workloads, "phases": phases,
            "published_by": "build_loop (DealsDesk plan -> SBOS)",
            "published_at": date.today().isoformat(),
        }
        pkey = "plan:build-%d" % bid
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details) "
            "VALUES (%s, 'plan', %s, %s, %s) "
            "ON CONFLICT (node_key) DO UPDATE SET "
            "name=EXCLUDED.name, status=EXCLUDED.status, "
            "details=atlas.nodes.details || EXCLUDED.details, "
            "updated_at=now()",
            (pkey, b["name"], b["status"], Json(details)))
        published += 1

        if b["need_id"]:
            cur.execute(
                "SELECT subject, description, status FROM "
                "dealsdesk.ecosystem_needs WHERE id=%s",
                (b["need_id"],))
            need = cur.fetchone()
            workload = parse_workload(need["description"]) if need \
                else None
            if not workload:
                cur.execute(
                    "SELECT specs FROM "
                    "successbrian_os.sbos_need_requests "
                    "WHERE need_id=%s ORDER BY id LIMIT 1",
                    (b["need_id"],))
                r = cur.fetchone()
                workload = parse_workload(r["specs"]) if r else None
            if workload:
                nkey = need_key_for(workload)
                cur.execute(
                    "INSERT INTO atlas.nodes "
                    "(node_key, node_type, name, status, details) "
                    "VALUES (%s, 'need', %s, %s, %s) "
                    "ON CONFLICT (node_key) DO UPDATE SET "
                    "status=EXCLUDED.status, "
                    "details=atlas.nodes.details || EXCLUDED.details, "
                    "updated_at=now()",
                    (nkey, "Need: " + (need["subject"] if need else
                                       "build %d" % bid),
                     need["status"] if need else "open",
                     Json({"workload": workload,
                           "dealsdesk_need_id": b["need_id"]})))
                cur.execute(
                    "INSERT INTO atlas.edges "
                    "(from_node, to_node, edge_type, notes) "
                    "VALUES (%s, %s, 'requires', %s) "
                    "ON CONFLICT DO NOTHING",
                    (workload, nkey,
                     "the workload's need, answered by DealsDesk "
                     "build %d" % bid))
                cur.execute(
                    "INSERT INTO atlas.edges "
                    "(from_node, to_node, edge_type, notes) "
                    "VALUES (%s, %s, 'implements', %s) "
                    "ON CONFLICT DO NOTHING",
                    (pkey, nkey,
                     "DealsDesk build plan published into SBOS"))
                linked += 1
    conn.commit()
    print("publish: %d build plan(s) in SBOS, %d linked to a "
          "workload need" % (published, linked))
    return 0


# ---------------------------------------------------------------- gates

def apply_gate(conn, workload, gate_key, name, ok, criteria, build_id):
    cur = conn.cursor()
    cur.execute("SELECT status FROM atlas.nodes WHERE node_key=%s",
                (gate_key,))
    row = cur.fetchone()
    if ok:
        if row and row[0] == "pending":
            cur.execute(
                "UPDATE atlas.nodes SET status='done', "
                "details = details || %s, updated_at=now() "
                "WHERE node_key=%s",
                (Json({"cleared_at": date.today().isoformat(),
                       "cleared_by": "build_loop",
                       "evidence": criteria}), gate_key))
            return "cleared"
        return "satisfied"
    details = {"note": criteria, "set_by": "build_loop (SBOS+DealsDesk)",
               "build_id": build_id, "workload": workload}
    if row is None:
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details) "
            "VALUES (%s, 'gate', %s, 'pending', %s)",
            (gate_key, name, Json(details)))
        state = "set"
    elif row[0] != "pending":
        cur.execute(
            "UPDATE atlas.nodes SET status='pending', "
            "details = details || %s, updated_at=now() "
            "WHERE node_key=%s",
            (Json(dict(details, reopened_at=date.today().isoformat())),
             gate_key))
        state = "reopened"
    else:
        cur.execute(
            "UPDATE atlas.nodes SET details = details || %s, "
            "updated_at=now() WHERE node_key=%s",
            (Json({"note": criteria}), gate_key))
        state = "open"
    cur.execute(
        "INSERT INTO atlas.edges (from_node, to_node, edge_type, "
        "notes) VALUES (%s, %s, 'blocks', %s) ON CONFLICT DO NOTHING",
        (gate_key, workload,
         "set by the build loop from DealsDesk build %d's plan state"
         % build_id))
    return state


def set_gates(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT e.from_node AS plan_key, e.to_node AS need_key, "
        "n.details->>'workload' AS workload, "
        "n.details->>'sbos_priority' AS sbos_priority, "
        "p.details->>'build_id' AS build_id, "
        "p.details->'joint' AS joint "
        "FROM atlas.edges e "
        "JOIN atlas.nodes n ON n.node_key = e.to_node "
        "JOIN atlas.nodes p ON p.node_key = e.from_node "
        "WHERE e.edge_type='implements' "
        "AND e.from_node LIKE 'plan:build-%' "
        "AND n.details->>'workload' IS NOT NULL")
    links = cur.fetchall()
    acted = []
    for link in links:
        bid = int(link["build_id"])
        cur.execute("SELECT * FROM dealsdesk.builds WHERE id=%s",
                    (bid,))
        b = cur.fetchone()
        if not b:
            continue
        sbos_pri = int(link["sbos_priority"]) \
            if link["sbos_priority"] else None
        joint = {"sbos_priority": sbos_pri,
                 "dealsdesk_priority": b["priority"],
                 "band": band_for(sbos_pri),
                 "determined_at": date.today().isoformat(),
                 "determined_by": "SBOS + DealsDesk (build_loop)"}
        prev = link["joint"] or {}
        if {k: prev.get(k) for k in
                ("sbos_priority", "dealsdesk_priority", "band")} != \
           {k: joint[k] for k in
                ("sbos_priority", "dealsdesk_priority", "band")}:
            for node_key in (link["plan_key"], link["need_key"]):
                cur.execute(
                    "UPDATE atlas.nodes SET details = details || %s, "
                    "updated_at=now() WHERE node_key=%s",
                    (Json({"joint": joint}), node_key))
            cur.execute(
                "INSERT INTO successbrian_os.pm_decisions "
                "(decided_by, decision, rationale, origin) "
                "VALUES ('build-loop', %s, %s, 'system')",
                ("Joint priority for %s: band %s (SBOS priority %s, "
                 "DealsDesk build priority %s)"
                 % (b["name"], joint["band"], sbos_pri, b["priority"]),
                 "workload %s; build %d; determined together per "
                 "Brian 2026-10-26" % (link["workload"], bid)))
            acted.append("joint priority set for build %d (%s)"
                         % (bid, joint["band"]))
        workload = link["workload"]
        specs = [
            ("priced", "%s — priced by DealsDesk" % b["name"],
             b["status"] in PRICED_STATES,
             "Clears when DealsDesk's build reaches components_priced "
             "or beyond (components priced). Build status now: %s."
             % b["status"]),
            ("online", "%s — online and verified" % b["name"],
             b["status"] in ONLINE_STATES,
             "Clears when the build reaches deployed in "
             "DealsDesk's lifecycle with its workloads live. "
             "Build status now: %s."
             % b["status"]),
        ]
        if b["budget_target"] is not None \
                and b["estimated_cost"] is not None:
            specs.append(
                ("budget", "%s — within budget target" % b["name"],
                 float(b["estimated_cost"]) <= float(b["budget_target"]),
                 "Estimated %s against a budget target of %s."
                 % (b["estimated_cost"], b["budget_target"])))
        for suffix, gname, ok, criteria in specs:
            gkey = "gate:build-%d-%s" % (bid, suffix)
            state = apply_gate(conn, workload, gkey, gname, ok,
                               criteria, bid)
            if state in ("set", "reopened", "cleared"):
                acted.append("gate %s %s (%s)" % (gkey, state,
                                                  link["workload"]))
    conn.commit()
    for a in acted:
        print("gates: " + a)
    print("gates: %d workload-linked build(s) processed" % len(links))
    return 0


# ---------------------------------------------------------------- status

def status(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT node_key, name, status, details->>'workload' AS w, "
        "details->>'sbos_priority' AS p FROM atlas.nodes "
        "WHERE node_type='need' AND details->>'workload' IS NOT NULL "
        "ORDER BY node_key")
    needs = cur.fetchall()
    print("Workload needs SBOS is tracking: %d" % len(needs))
    for n in needs:
        print("  %s [%s] for %s (SBOS priority %s)"
              % (n["node_key"], n["status"], n["w"], n["p"]))
    cur.execute(
        "SELECT count(*) AS n FROM atlas.nodes "
        "WHERE node_key LIKE 'plan:build-%'")
    print("Build plans published into SBOS: %d"
          % cur.fetchone()["n"])
    cur.execute(
        "SELECT workload_name, gate_name, gate_state FROM "
        "atlas.workload_gates_v WHERE gate_key LIKE 'gate:build-%' "
        "ORDER BY workload_name, gate_name")
    rows = cur.fetchall()
    print("Gates set by the build loop: %d" % len(rows))
    for r in rows:
        print("  %-7s %s — on %s"
              % (r["gate_state"].upper(), r["gate_name"],
                 r["workload_name"]))
    return 0


# ---------------------------------------------------------------- selftest

def selftest():
    failures = []

    def check(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    check(band_for(None) == "unplanned" and band_for(9) == "critical"
          and band_for(7) == "high" and band_for(5) == "standard"
          and band_for(2) == "low",
          "joint band: SBOS priority maps to words, none = unplanned")
    check(parse_workload("spec | workload: plan:content-factory")
          == "plan:content-factory"
          and parse_workload("nothing here") is None,
          "handoff specs carry the workload key, parseably")
    check("components_priced" in PRICED_STATES
          and "planning" not in PRICED_STATES
          and "running" in ONLINE_STATES
          and "building" not in ONLINE_STATES,
          "plan states: priced and online are separate gates")
    check(need_key_for("plan:content-factory")
          == "need:workload-content-factory",
          "need node key derives from the workload key")

    conn = pg()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.columns WHERE "
            "table_schema='successbrian_os' AND "
            "table_name='sbos_need_requests' AND "
            "column_name='need_id'")
        check(cur.fetchone() is not None,
              "live: sbos_need_requests carries need_id (return leg)")
        cur.execute(
            "SELECT count(*) FROM (SELECT 1 FROM "
            "dealsdesk.ecosystem_needs WHERE "
            "status IN ('open','planned') GROUP BY source, subject "
            "HAVING count(*) > 1) d")
        check(cur.fetchone()[0] == 0,
              "live: no duplicate open needs per source+subject")
        cur.execute(
            "SELECT count(*) FROM atlas.edges e JOIN atlas.nodes n "
            "ON n.node_key = e.to_node WHERE e.edge_type='implements' "
            "AND e.from_node LIKE 'plan:build-%' "
            "AND n.details->>'workload' = 'plan:content-factory'")
        check(cur.fetchone()[0] >= 1,
              "live: a DealsDesk build plan is published into SBOS "
              "for the content factory")
    finally:
        conn.close()
    if failures:
        print("SELFTEST FAILED: %d" % len(failures))
        return 1
    print("SELFTEST OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("repair")
    r = sub.add_parser("raise")
    r.add_argument("--workload", required=True)
    r.add_argument("--item", required=True)
    r.add_argument("--spec", default="")
    r.add_argument("--priority", type=int, default=5)
    r.add_argument("--qty", type=int, default=1)
    r.add_argument("--max-cost", type=float)
    sub.add_parser("publish")
    sub.add_parser("gates")
    sub.add_parser("run")
    sub.add_parser("status")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)

    if args.cmd == "selftest":
        return selftest()
    conn = pg()
    try:
        if args.cmd == "repair":
            return repair(conn)
        if args.cmd == "raise":
            return raise_need(conn, args.workload, args.item,
                              args.spec, args.priority, args.qty,
                              args.max_cost)
        if args.cmd == "publish":
            return publish(conn)
        if args.cmd == "gates":
            return set_gates(conn)
        if args.cmd == "run":
            publish(conn)
            return set_gates(conn)
        if args.cmd == "status":
            return status(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
