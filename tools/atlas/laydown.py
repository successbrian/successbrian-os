#!/usr/bin/env python3
"""Laydown — goals stated become structure, in code.

Brian's law (2026-10-21, AGENT_CONTRACT rule 22): when Brian states
a goal, successbrian-os/Atlas puts it together into tasks and the
staff works it agentically. Prose rules do not run; this program is
the mechanism. A goal is DATA (a spec JSON in laydown_specs/); this
engine lays it down:

  lay     spec -> initiative (metric'd, linked) + Atlas goal plan
          + workstream plans + gates + PM tasks + CampaignsDesk
          campaign rows. Deterministic keys; re-running is a no-op
          (idempotent) — the record is respected, never duplicated.
  cycle   open a cycle instance of a recurring goal (a fresh target;
          a shortfall is scored and reported, never carried).
  score   record a cycle's count, close it, print the result.
  show    print the whole tree from the record.

Usage:
  laydown.py lay laydown_specs/gotbackup-40.json [--dry-run]
  laydown.py cycle laydown_specs/gotbackup-40.json 2026-11
  laydown.py score laydown_specs/gotbackup-40.json 2026-11 --count 37
  laydown.py show laydown_specs/gotbackup-40.json
"""

import argparse
import json
import subprocess
import sys
from datetime import date

PSQL = ["psql", "-h", "localhost", "-U", "postgres", "-d",
        "ecosystem_central", "-t", "-A", "-F", "|"]


def psql(sql):
    p = subprocess.run(PSQL + ["-c", sql], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("psql: " + p.stderr.strip())
    return [ln for ln in p.stdout.split("\n") if ln]


def q(s):
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"


def one(sql):
    rows = psql(sql)
    return rows[0] if rows else None


def node_exists(key):
    return one("SELECT 1 FROM atlas.nodes WHERE node_key = %s"
               % q(key)) is not None


def route_model(about_key=None):
    """Mirror of atlas.py route_model (kept in step, like
    discovery.py): v4pro while the freeze plan is active."""
    row = one("SELECT status FROM atlas.nodes WHERE node_key = "
              "'plan:v4-freeze'")
    if row and row.strip().lower() == "active":
        return "v4pro", "plan:v4-freeze active"
    return "sonic", "default local worker"


class Reporter:
    def __init__(self, dry):
        self.dry = dry
        self.created = 0
        self.existing = 0

    def node(self, key, ntype, name, status, details):
        if node_exists(key):
            self.existing += 1
            print("  exists   %s" % key)
            return
        self.created += 1
        print("  %s %s" % ("would-add" if self.dry else "add     ", key))
        if not self.dry:
            psql("INSERT INTO atlas.nodes (node_key, node_type, name, "
                 "status, details) VALUES (%s, %s, %s, %s, %s::jsonb) "
                 "ON CONFLICT (node_key) DO NOTHING"
                 % (q(key), q(ntype), q(name), q(status),
                    q(json.dumps(details))))

    def edge(self, a, b, etype, notes=""):
        if self.dry:
            return
        psql("INSERT INTO atlas.edges (from_node, to_node, edge_type, "
             "notes) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING"
             % (q(a), q(b), q(etype), q(notes)))


def lay_initiative(spec, rep):
    ini = spec["initiative"]
    name = ini["name"]
    row = one("SELECT id FROM public.initiatives WHERE name = %s"
              % q(name))
    metrics = {"target_per_cycle": spec["metric"]["target_per_cycle"],
               "metric": spec["metric"]["unit"],
               "cycle": spec["metric"]["cycle"]}
    if spec.get("recurrence"):
        metrics["recurrence"] = spec["recurrence"]["type"]
    desc = ("Standing goal designated by %s. Laid down by "
            "tools/atlas/laydown.py as %s."
            % (spec["designated_by"], spec["goal_key"]))
    if row is None:
        rep.created += 1
        print("  %s initiative '%s'"
              % ("would-add" if rep.dry else "add     ", name))
        if not rep.dry:
            psql("INSERT INTO public.initiatives (name, description, "
                 "type, status, lead_agent, created_by, "
                 "success_metrics) VALUES (%s, %s, %s, %s, %s, "
                 "'laydown', %s::jsonb)"
                 % (q(name), q(desc), q(ini.get("type", "ongoing")),
                    q(ini.get("status", "active")),
                    q(ini.get("lead_agent", "altair")),
                    q(json.dumps(metrics))))
        return
    rep.existing += 1
    print("  exists   initiative '%s' (metric ensured)" % name)
    if rep.dry:
        return
    cur = one("SELECT success_metrics::text FROM public.initiatives "
              "WHERE id = %s" % row)
    try:
        merged = json.loads(cur) if cur else {}
    except Exception:
        merged = {}
    merged.update(metrics)
    gid = one("SELECT id FROM public.graph_nodes WHERE name = %s"
              % q(name))
    link = ("graph_node_id = %s, " % gid) if gid else ""
    psql("UPDATE public.initiatives SET %ssuccess_metrics = %s::jsonb "
         "WHERE id = %s" % (link, q(json.dumps(merged)), row))


def lay(spec, dry):
    rep = Reporter(dry)
    goal_key = spec["goal_key"]
    prefix = spec["prefix"]
    print("LAYDOWN: %s" % spec["title"])
    lay_initiative(spec, rep)

    details = {"type": "standing_goal",
               "designated_by": spec["designated_by"],
               "target": spec["metric"]["unit"],
               "initiative": "public.initiatives '%s'"
                             % spec["initiative"]["name"],
               "cadence": spec["metric"]["cycle"]}
    if spec.get("recurrence"):
        details["recurrence"] = spec["recurrence"]
    if spec.get("goal_details"):
        details.update(spec["goal_details"])
    rep.node(goal_key, "plan", spec["title"], "planned", details)

    ws_keys = {}
    for ws in spec["workstreams"]:
        key = "plan:%s-%s" % (prefix, ws["slug"])
        ws_keys[ws["slug"]] = key
        rep.node(key, "plan", "%s %s" % (prefix.upper(),
                                         ws["slug"].replace("-", " ")),
                 "planned",
                 {"workstream": ws["slug"], "phase": ws["phase"],
                  "goal": goal_key,
                  "owner_proposed": ws["owner_proposed"],
                  "description": ws["description"],
                  "systems": ws.get("systems", []),
                  "source": "laydown:%s" % spec["slug"]})
        rep.edge(goal_key, key, "contains", "laydown")
        for t in ws.get("tasks", []):
            tkey = "task:%s:%s" % (prefix, t["slug"])
            model, _ = route_model(key)
            rep.node(tkey, "atlas_task", t["title"], "queued",
                     {"about": key, "found_by": "laydown",
                      "source": "laydown:%s" % spec["slug"],
                      "model": model})
            rep.edge(tkey, key, "about", "laydown")

    for g in spec.get("gates", []):
        gkey = "gate:%s-%s" % (prefix, g["slug"])
        rep.node(gkey, "gate", g["title"], "pending",
                 {"note": g["note"],
                  "set_by": "Laydown per AGENT_CONTRACT rule 17/22, "
                            "from %s" % spec["designated_by"]})
        if g.get("blocks"):
            rep.edge(gkey, ws_keys[g["blocks"]], "blocks",
                     g.get("blocks_note", "set by laydown"))

    lay_campaigns(spec, ws_keys, rep)
    print("DONE: %d created, %d already present%s"
          % (rep.created, rep.existing,
             " (dry run - nothing written)" if dry else ""))
    return 0


def lay_campaigns(spec, ws_keys, rep):
    camps = spec.get("campaigns")
    if not camps:
        return
    path = spec.get("campaigns_file",
                    "/home/successbrian/campaignsdesk/CAMPAIGNS.md")
    try:
        text = open(path).read()
    except OSError:
        print("  campaigns file not found: %s (skipped)" % path)
        return
    rows = []
    for c in camps:
        plan_key = ws_keys[c["workstream"]]
        if plan_key in text:
            rep.existing += 1
            print("  exists   campaign row for %s" % plan_key)
            continue
        rep.created += 1
        print("  %s campaign row: %s"
              % ("would-add" if rep.dry else "add     ", c["name"]))
        rows.append(
            "| %s | %s | %s | %s | %s | designated | Standing goal "
            "(%s); Atlas %s |"
            % (c["name"], c["business"], c["offer"], c["audience"],
               c["channel"], spec["designated_by"], plan_key))
    if not rows or rep.dry:
        return
    placeholder = "| _(none designated yet)_ | | | | | | |"
    if placeholder in text:
        text = text.replace(placeholder, "\n".join(rows))
    else:
        anchor = "\nStages:"
        assert anchor in text, "campaigns table anchor missing"
        text = text.replace(anchor, "\n" + "\n".join(rows) + anchor)
    open(path, "w").write(text)


def cycle(spec, month, dry):
    key = "plan:%s-cycle-%s" % (spec["prefix"], month)
    cur = date.today().strftime("%Y-%m")
    status = "active" if month == cur else "planned"
    rep = Reporter(dry)
    rep.node(key, "plan",
             "%s cycle %s: %s" % (spec["prefix"].upper(), month,
                                   spec["metric"]["unit"]),
             status,
             {"cycle_of": spec["goal_key"], "cycle": month,
              "target": spec["metric"]["target_per_cycle"],
              "sponsored_so_far": None,
              "state": "open" if status == "active" else "scheduled"})
    rep.edge(spec["goal_key"], key, "contains", "monthly cycle instance")
    print("cycle %s: %s" % (month, "ready" if not dry else "dry run"))
    return 0


def score(spec, month, count):
    key = "plan:%s-cycle-%s" % (spec["prefix"], month)
    if not node_exists(key):
        print("no cycle node %s - open it first" % key)
        return 1
    target = spec["metric"]["target_per_cycle"]
    result = "met" if count >= target else "shortfall"
    merge = {"sponsored": count, "result": result,
             "scored_at": date.today().isoformat()}
    psql("UPDATE atlas.nodes SET details = details || %s::jsonb, "
         "status = 'done', updated_at = now() WHERE node_key = %s"
         % (q(json.dumps(merge)), q(key)))
    print("cycle %s scored: %d of %d sponsored - %s. "
          "Shortfall is reported, never carried: next cycle's target "
          "stays %d." % (month, count, target, result.upper(), target))
    return 0


def show(spec):
    gk = spec["goal_key"]
    print(one("SELECT name || ' [' || status || ']' FROM atlas.nodes "
              "WHERE node_key = %s" % q(gk)) or "(goal plan missing)")
    ini = spec["initiative"]["name"]
    print("  initiative '%s': %s"
          % (ini, one("SELECT COALESCE(success_metrics::text, '{}') "
                      "FROM public.initiatives WHERE name = %s"
                      % q(ini)) or "missing"))
    for ln in psql("SELECT '  gate [' || status || '] ' || name "
                   "FROM atlas.nodes WHERE node_key LIKE %s "
                   "AND node_type = 'gate' ORDER BY node_key"
                   % q("gate:%s-%%" % spec["prefix"])):
        print(ln)
    for key, name, status in [
            r.split("|") for r in psql(
                "SELECT node_key, name, status FROM atlas.nodes "
                "WHERE node_key LIKE %s AND node_type = 'plan' "
                "ORDER BY node_key"
                % q("plan:%s-%%" % spec["prefix"]))]:
        tasks = psql("SELECT status, count(*) FROM atlas.nodes "
                     "WHERE node_type = 'atlas_task' "
                     "AND details->>'about' = %s GROUP BY 1" % q(key))
        tstr = ", ".join("%s: %s" % (s, n) for s, n in
                         (t.split("|") for t in tasks)) or "no tasks"
        print("  %s [%s] - %s" % (name, status, tstr))
    # NB: in Postgres, || binds tighter than ->> — parenthesize
    # every extraction or the text literals get parsed as JSON.
    for ln in psql("SELECT '  cycle ' || (details->>'cycle') || ': ' || "
                   "COALESCE((details->>'sponsored'), 'unscored') || "
                   "'/' || COALESCE((details->>'target'), '?') || ' [' "
                   "|| status || ']' FROM atlas.nodes WHERE node_key "
                   "LIKE %s ORDER BY node_key"
                   % q("plan:%s-cycle-%%" % spec["prefix"])):
        print(ln)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["lay", "cycle", "score", "show"])
    ap.add_argument("spec")
    ap.add_argument("month", nargs="?")
    ap.add_argument("--count", type=int)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    if a.cmd == "lay":
        return lay(spec, a.dry_run)
    if a.cmd == "cycle":
        assert a.month, "cycle needs YYYY-MM"
        return cycle(spec, a.month, a.dry_run)
    if a.cmd == "score":
        assert a.month and a.count is not None, "score needs month + --count"
        return score(spec, a.month, a.count)
    return show(spec)


if __name__ == "__main__":
    sys.exit(main())
