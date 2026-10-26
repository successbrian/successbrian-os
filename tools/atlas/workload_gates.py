#!/usr/bin/env python3
"""Workload Gates — the ecosystem can see the gates on the workload.

Brian (2026-10-26): "upgrade the ecosystem. it needs to be able to
see the gates on the workload."

Until now the ecosystem's gates lived in disconnected piles:

  * Atlas gate nodes that `blocks` a workstream;
  * Atlas `requires` edges from a workload to a prerequisite;
  * phase gates in successbrian_os.project_gates;
  * dependency steps in the PM control plane (pm_step_deps).

Each surface showed at most a count. None answered the plain
question: WHAT is holding THIS workload, and what state is that gate
in?

This tool builds one read model over those sources:

  atlas.workload_gates_v   (PostgreSQL view — the state home, R32)
  workload_gates.py        (this file — the logic home, R32)

Gate states are words, never scores:

  open    — the gate is not cleared: a pending gate, an unfinished
            prerequisite, or an incomplete dependency step.
  closed  — the gate is cleared: the gate was passed/ruled done, the
            prerequisite is complete, or the dependency step is done.
  unknown — the record does not prove either way. A prerequisite that
            is merely "active" is underway, not proven complete; not
            knowing is not the same as not.

Inheritance is part of the read model: a gate on a parent workload is
visible on everything the parent contains (Atlas `contains` edges)
and on tasks filed `about` the gated work. The gate holds the whole
subtree, so the whole subtree can see it.

Commands:

  init                  create/refresh the view and the first-citizen
                        seed (idempotent)
  summary               counts and the workload-gate picture
  list                  every workload/gate pair
  blocked               only workloads with at least one open gate
  show <text>           every gate on one workload (key or name match)
  seed-content-factory  idempotently seed the content-factory gate
  selftest              pure logic tests + live read-model smoke

Read-only except `init` / `seed-content-factory` (which only create
the view and the seeded Atlas nodes/edges). This tool rules nothing,
clears nothing, buys nothing, and never mutates an existing gate or
workload.
"""

import argparse
import json
import sys

import psycopg2
import psycopg2.extras

DBNAME = "ecosystem_central"

CLOSED_STATUSES = ("done", "passed", "cleared", "closed", "complete",
                   "completed")
OPEN_STATUSES = ("planned", "pending", "proposed", "researching",
                 "blocked", "queued", "open")

VIEW_SQL = """
CREATE OR REPLACE VIEW atlas.workload_gates_v AS
WITH RECURSIVE
atlas_direct AS (
    -- A gate node blocks a workload.
    SELECT w.node_key AS workload_key,
           w.name AS workload_name,
           w.node_type AS workload_kind,
           w.status AS workload_status,
           g.node_key AS gate_key,
           g.name AS gate_name,
           g.status AS gate_status,
           CASE
               WHEN g.status = 'pending' THEN 'open'
               WHEN g.status IN ('done', 'passed', 'cleared', 'closed',
                                 'complete', 'completed') THEN 'closed'
               ELSE 'unknown'
           END AS gate_state,
           'blocks'::text AS relation,
           'direct'::text AS path,
           'atlas'::text AS source,
           COALESCE(g.details->>'note',
                    g.details->>'criteria') AS criteria
      FROM atlas.edges e
      JOIN atlas.nodes g
        ON g.node_key = e.from_node AND g.node_type = 'gate'
      JOIN atlas.nodes w
        ON w.node_key = e.to_node
     WHERE e.edge_type = 'blocks'

    UNION ALL

    -- A workload requires a prerequisite. The prerequisite can be a
    -- formal gate or any other Atlas node whose state matters.
    SELECT w.node_key,
           w.name,
           w.node_type,
           w.status,
           p.node_key,
           p.name,
           p.status,
           CASE
               WHEN p.node_type = 'gate' AND p.status = 'pending'
                   THEN 'open'
               WHEN p.status IN ('done', 'passed', 'cleared', 'closed',
                                 'complete', 'completed') THEN 'closed'
               WHEN p.status IN ('planned', 'pending', 'proposed',
                                 'researching', 'blocked', 'queued',
                                 'open') THEN 'open'
               ELSE 'unknown'
           END,
           'requires',
           'direct',
           'atlas',
           COALESCE(p.details->>'note', p.details->>'criteria')
      FROM atlas.edges e
      JOIN atlas.nodes w ON w.node_key = e.from_node
      JOIN atlas.nodes p ON p.node_key = e.to_node
     WHERE e.edge_type = 'requires'
),
gated AS (
    SELECT * FROM atlas_direct

    UNION ALL

    -- Inherit through both Atlas shapes that make one workload part
    -- of another: parent `contains` child, and task `about` parent.
    -- One recursive reference; the growing path is also the depth
    -- guard, so a graph cycle cannot recurse forever.
    SELECT n.node_key,
           n.name,
           n.node_type,
           n.status,
           g.gate_key,
           g.gate_name,
           g.gate_status,
           g.gate_state,
           g.relation,
           g.path || ' > ' || x.how || ' ' || n.node_key,
           g.source,
           g.criteria
      FROM gated g
      JOIN LATERAL (
               SELECT e.to_node AS child, 'contains'::text AS how
                 FROM atlas.edges e
                WHERE e.from_node = g.workload_key
                  AND e.edge_type = 'contains'
               UNION ALL
               SELECT e.from_node AS child, 'about'::text AS how
                 FROM atlas.edges e
                WHERE e.to_node = g.workload_key
                  AND e.edge_type = 'about'
           ) x ON true
      JOIN atlas.nodes n ON n.node_key = x.child
     WHERE char_length(g.path) < 240
),
proj AS (
    -- Phase gates. sbos_projects.gate_key is the trustworthy link:
    -- each phase row names its own gate.
    SELECT 'sbos-project:' || sp.id::text AS workload_key,
           sp.project_name || ' — ' ||
               left(split_part(COALESCE(sp.description, ''), E'\n', 1), 90)
               AS workload_name,
           'sbos_project'::text AS workload_kind,
           sp.status AS workload_status,
           pg.gate_key,
           pg.gate_name,
           pg.status AS gate_status,
           CASE
               WHEN pg.status = 'pending' THEN 'open'
               WHEN pg.status IN ('passed', 'done', 'cleared', 'closed',
                                  'complete', 'completed') THEN 'closed'
               ELSE 'unknown'
           END AS gate_state,
           'phase-gate'::text AS relation,
           'direct'::text AS path,
           'project_gates'::text AS source,
           pg.criteria,
           pg.depends_on_gate_key AS dep_key
      FROM successbrian_os.project_gates pg
      JOIN successbrian_os.sbos_projects sp
        ON sp.gate_key = pg.gate_key
),
proj_chain AS (
    SELECT workload_key, workload_name, workload_kind, workload_status,
           gate_key, gate_name, gate_status, gate_state, relation, path,
           source, criteria, dep_key
      FROM proj

    UNION ALL

    -- A gate that depends on another gate passes that gate down to
    -- the same workload.
    SELECT p.workload_key,
           p.workload_name,
           p.workload_kind,
           p.workload_status,
           d.gate_key,
           d.gate_name,
           d.status,
           CASE
               WHEN d.status = 'pending' THEN 'open'
               WHEN d.status IN ('passed', 'done', 'cleared', 'closed',
                                 'complete', 'completed') THEN 'closed'
               ELSE 'unknown'
           END,
           'phase-gate-dependency',
           'via ' || p.gate_key,
           'project_gates',
           d.criteria,
           d.depends_on_gate_key
      FROM proj_chain p
      JOIN successbrian_os.project_gates d
        ON d.gate_key = p.dep_key
     WHERE p.dep_key IS NOT NULL
),
pm AS (
    -- PM control-plane dependencies: a step cannot be claimed until
    -- every step it depends on is done. Those dependencies are gates
    -- on that workload step.
    SELECT 'pm-step:' || s.step_key AS workload_key,
           s.title AS workload_name,
           'pm_step'::text AS workload_kind,
           s.status AS workload_status,
           'pm-step:' || d.step_key AS gate_key,
           d.title AS gate_name,
           d.status AS gate_status,
           CASE
               WHEN d.status = 'done' THEN 'closed'
               WHEN d.status = 'cancelled' THEN 'unknown'
               ELSE 'open'
           END AS gate_state,
           'depends-on'::text AS relation,
           'direct'::text AS path,
           'pm_steps'::text AS source,
           NULL::text AS criteria
      FROM successbrian_os.pm_step_deps dd
      JOIN successbrian_os.pm_steps s ON s.id = dd.step_id
      JOIN successbrian_os.pm_steps d ON d.id = dd.depends_on_id
)
SELECT workload_key,
       workload_name,
       workload_kind,
       workload_status,
       gate_key,
       gate_name,
       gate_status,
       gate_state,
       relation,
       min(path) AS path,
       source,
       criteria
  FROM (
        SELECT workload_key, workload_name, workload_kind,
               workload_status, gate_key, gate_name, gate_status,
               gate_state, relation, path, source, criteria
          FROM gated
        UNION ALL
        SELECT workload_key, workload_name, workload_kind,
               workload_status, gate_key, gate_name, gate_status,
               gate_state, relation, path, source, criteria
          FROM proj_chain
        UNION ALL
        SELECT workload_key, workload_name, workload_kind,
               workload_status, gate_key, gate_name, gate_status,
               gate_state, relation, path, source, criteria
          FROM pm
       ) all_rows
 GROUP BY workload_key, workload_name, workload_kind, workload_status,
          gate_key, gate_name, gate_status, gate_state, relation,
          source, criteria
"""


def pg():
    return psycopg2.connect(dbname=DBNAME, host="localhost",
                            user="postgres")


def ensure_view(conn):
    with conn.cursor() as cur:
        cur.execute(VIEW_SQL)
        # The ecosystem's readers (chat brief, queue watch, clerks)
        # connect under their own roles; the read model is read-only
        # by construction, so its SELECT is public inside Brian's
        # own single-owner database.
        cur.execute(
            "GRANT SELECT ON atlas.workload_gates_v TO PUBLIC")
    conn.commit()


def seed_content_factory(conn):
    """First citizen: the content-factory workload and its Node Echo
    acquisition gate.

    The gate encodes Brian's ownership rule (2026-10-26): Node Echo
    is not owned until Brian tells Muse or Altair that it is. A live
    listing, a buy decision, and a plan are not acquisition.

    Idempotent: nodes and edges are created only when absent, and no
    existing node's fields are overwritten.
    """
    from psycopg2.extras import Json

    workload_key = "plan:content-factory"
    gate_key = "gate:node-echo-acquired"
    workload_details = {
        "source": "fleet-roadmap.md Phase 1 (Brian, 2026-10-10)",
        "stages": [
            "writing: Mantis-2 + Shakespeare (Llama 3.3 70B Q4) batch",
            "rendering: Mantis-1 — GTX 980 SD1.5 volume + "
            "Quadro RTX 5000 16GB SDXL flagship",
            "transcode + timetable: Node Echo (Quick Sync iGPU, "
            "rack timekeeper)",
            "publish: publish queue",
        ],
        "note": "The render stage alone does not depend on Echo; "
                "the end-to-end pipeline's transcode and publish "
                "stages do.",
    }
    gate_details = {
        "note": "Clears ONLY when Brian declares the purchase "
                "complete (to Muse or Altair). A live listing, a "
                "buy decision, or a plan is not acquisition "
                "(Brian, 2026-10-26).",
        "candidate": "Drew Covi's Supermicro CSE-825MTQ 2U "
                     "(X11SAE-F, Xeon E3-1245 v6, 32GB DDR4, "
                     "Noctua cooling, rails, 3x PSU, no drives)",
        "listing": "Facebook Marketplace 1089533917157580, "
                   "Minneapolis, ~18 mi",
        "listing_state": "Verified AVAILABLE at $550 on 2026-10-26",
        "scope": "Blocks the content factory's transcode/publish "
                 "stages via Node Echo, not standalone rendering.",
    }
    made = []

    def node(key, ntype, name, status, details):
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM atlas.nodes WHERE node_key=%s",
                        (key,))
            if cur.fetchone():
                return
            cur.execute(
                "INSERT INTO atlas.nodes "
                "(node_key, node_type, name, status, details) "
                "VALUES (%s, %s, %s, %s, %s)",
                (key, ntype, name, status, Json(details)))
        made.append("node " + key)

    def edge(a, b, etype, notes):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO atlas.edges "
                "(from_node, to_node, edge_type, notes) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (a, b, etype, notes))
            if cur.rowcount:
                made.append("edge %s -%s-> %s" % (a, etype, b))

    node(workload_key, "plan",
         "Content factory pipeline (Mantis-2 writes, Mantis-1 "
         "renders, Echo transcodes/publishes)",
         "planned", workload_details)
    node(gate_key, "gate",
         "Node Echo acquired (Drew Covi Supermicro 2U)",
         "pending", gate_details)
    edge("proj:blog-network", workload_key, "contains",
         "the content factory serves the 100-blog network")
    edge(workload_key, "infra:node-echo", "requires",
         "transcode, timetable, and publish stages run on Node Echo")
    edge(gate_key, workload_key, "blocks",
         "end-to-end pipeline waits on Echo acquisition; standalone "
         "rendering does not")
    conn.commit()
    return made


def fetch_rows(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) \
            as cur:
        cur.execute(
            "SELECT * FROM atlas.workload_gates_v "
            "ORDER BY CASE gate_state WHEN 'open' THEN 0 "
            "WHEN 'unknown' THEN 1 ELSE 2 END, "
            "workload_name, gate_name")
        return [dict(r) for r in cur.fetchall()]


def summarize(rows):
    workloads = {r["workload_key"] for r in rows}
    held = {r["workload_key"] for r in rows
            if r["gate_state"] == "open"}
    by_state = {"open": 0, "closed": 0, "unknown": 0}
    by_source = {}
    for r in rows:
        by_state[r["gate_state"]] = by_state.get(r["gate_state"], 0) + 1
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    return {"rows": len(rows), "workloads": len(workloads),
            "held_workloads": len(held), "by_state": by_state,
            "by_source": by_source}


def group_rows(rows):
    groups = {}
    for r in rows:
        groups.setdefault(r["workload_key"], []).append(r)
    return groups


def render_summary(rows):
    s = summarize(rows)
    lines = [
        "Workload gates: %d gate rows on %d workloads — "
        "%d open (holding %d workloads), %d unknown, %d closed."
        % (s["rows"], s["workloads"], s["by_state"].get("open", 0),
           s["held_workloads"], s["by_state"].get("unknown", 0),
           s["by_state"].get("closed", 0)),
        "By source: " + ", ".join(
            "%s %d" % (k, s["by_source"][k])
            for k in sorted(s["by_source"])),
    ]
    return "\n".join(lines)


def render_groups(rows, only_blocked=False):
    groups = group_rows(rows)
    lines = []
    for key in sorted(groups, key=lambda k: groups[k][0]["workload_name"]):
        grows = groups[key]
        if only_blocked and not any(
                r["gate_state"] == "open" for r in grows):
            continue
        head = grows[0]
        lines.append("")
        lines.append("WORKLOAD: %s" % head["workload_name"])
        lines.append("  key %s | kind %s | status %s"
                     % (key, head["workload_kind"],
                        head["workload_status"]))
        for r in grows:
            lines.append("  %-7s %s [%s]" %
                         (r["gate_state"].upper(), r["gate_name"],
                          r["gate_key"]))
            lines.append("          gate status %s | via %s (%s) | "
                         "path %s" % (r["gate_status"], r["relation"],
                                      r["source"], r["path"]))
            if r.get("criteria"):
                lines.append("          criteria: %s" % r["criteria"])
    return "\n".join(lines).strip()


def match_rows(rows, text):
    t = text.lower()
    keys = {r["workload_key"] for r in rows
            if t in r["workload_key"].lower()
            or t in r["workload_name"].lower()}
    return [r for r in rows if r["workload_key"] in keys]


def selftest():
    failures = []

    def check(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    # Pure logic: summarising and grouping need no database.
    sample = [
        {"workload_key": "w:a", "workload_name": "A",
         "workload_kind": "plan", "workload_status": "planned",
         "gate_key": "g:1", "gate_name": "G1", "gate_status": "pending",
         "gate_state": "open", "relation": "blocks", "path": "direct",
         "source": "atlas", "criteria": None},
        {"workload_key": "w:a", "workload_name": "A",
         "workload_kind": "plan", "workload_status": "planned",
         "gate_key": "g:2", "gate_name": "G2", "gate_status": "done",
         "gate_state": "closed", "relation": "requires",
         "path": "direct", "source": "atlas", "criteria": None},
        {"workload_key": "w:b", "workload_name": "B",
         "workload_kind": "plan", "workload_status": "active",
         "gate_key": "g:3", "gate_name": "G3",
         "gate_status": "active", "gate_state": "unknown",
         "relation": "requires", "path": "direct", "source": "atlas",
         "criteria": None},
    ]
    s = summarize(sample)
    check(s["rows"] == 3 and s["workloads"] == 2
          and s["held_workloads"] == 1,
          "summary: rows, workloads, and held workloads count")
    check(s["by_state"] == {"open": 1, "closed": 1, "unknown": 1},
          "summary: states are words, counted separately")
    check(len(group_rows(sample)) == 2,
          "grouping: gates gather under their workload")
    blocked_text = render_groups(sample, only_blocked=True)
    check("WORKLOAD: A" in blocked_text
          and "WORKLOAD: B" not in blocked_text,
          "blocked view: only workloads with an open gate appear")

    # Live smoke: the read model must see the known gates.
    conn = pg()
    try:
        ensure_view(conn)
        seed_content_factory(conn)
        rows = fetch_rows(conn)
    finally:
        conn.close()
    pairs = {(r["gate_key"], r["workload_key"]) for r in rows}
    states = {(r["gate_key"], r["workload_key"]): r["gate_state"]
              for r in rows}
    check(len(rows) > 0, "live: the gate read model returns rows")
    check(("gate:gb40-lead-budget", "plan:gb40-lead-flow") in pairs
          and states[("gate:gb40-lead-budget",
                      "plan:gb40-lead-flow")] == "open",
          "live: GotBackup lead budget gate holds the lead-flow "
          "workstream")
    check(("gate:zilara-executive-nov1", "proj:zilara") in pairs,
          "live: Zilara project sees its executive gate")
    check(("gate:node-echo-acquired", "plan:content-factory") in pairs
          and states[("gate:node-echo-acquired",
                      "plan:content-factory")] == "open",
          "live: content factory sees the Node Echo acquisition gate")
    inherited = [r for r in rows
                 if r["workload_key"].startswith("task:gb40:")
                 and r["gate_key"] == "gate:gb40-lead-budget"]
    check(bool(inherited),
          "live: gates inherit down to the tasks filed under the "
          "gated work")

    if failures:
        print("SELFTEST FAILED: %d" % len(failures))
        return 1
    print("SELFTEST OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["init", "summary", "list",
                                    "blocked", "show",
                                    "seed-content-factory", "selftest"])
    ap.add_argument("match", nargs="?",
                    help="workload key or name text (show)")
    ap.add_argument("--open", action="store_true",
                    help="list: only open gates")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of text")
    args = ap.parse_args(argv)

    if args.cmd == "selftest":
        return selftest()

    conn = pg()
    try:
        ensure_view(conn)
        if args.cmd == "init":
            made = seed_content_factory(conn)
            print("view atlas.workload_gates_v ready")
            print("seed: " + (", ".join(made) if made else
                              "already present, nothing added"))
            return 0
        if args.cmd == "seed-content-factory":
            made = seed_content_factory(conn)
            print("seed: " + (", ".join(made) if made else
                              "already present, nothing added"))
            return 0

        rows = fetch_rows(conn)
        if args.cmd == "show":
            if not args.match:
                print("show needs a workload key or name text")
                return 2
            rows = match_rows(rows, args.match)
            if not rows:
                print("no workload matches %r" % args.match)
                return 1
        if args.cmd == "list" and args.open:
            rows = [r for r in rows if r["gate_state"] == "open"]

        if args.json:
            print(json.dumps(rows, indent=2, default=str))
            return 0
        if args.cmd == "summary":
            print(render_summary(rows))
        elif args.cmd == "blocked":
            print(render_summary(rows))
            print(render_groups(rows, only_blocked=True))
        else:
            print(render_summary(rows))
            print(render_groups(rows))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
