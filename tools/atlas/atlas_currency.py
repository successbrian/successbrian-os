#!/usr/bin/env python3
"""atlas_currency.py — Atlas keeps itself current.

Brian's ruling (2026-10-27): Atlas must be integrated — it
needs to know what is RUNNING, what is BEING DEVELOPED, and
what is PLANNED for the future — and that picture must stay
current: "atlas needs to check it, or existing workers need
to be reviewing it a few times a day." Brian's go on the
build: "do what is best and ideal."

This is the checker. It runs a few times a day and does four
things, all deterministic:

  1. ASSETS (R38): makes sure the marketing-asset nodes and
     their markets / captures_for edges from
     allm_workspaces.MARKETING_ASSETS actually exist in the
     live Atlas graph. Missing pieces are inserted (never
     duplicated) — so the graph itself, not just one code
     file, knows a blog is an asset, not the program.
  2. RUNNING vs REALITY: runs the existing
     systems_integration audit probes and compares what
     answers against atlas.systems_registry statuses. A
     system Atlas calls "live" that the probe cannot hear
     is a discrepancy.
  3. BEING DEVELOPED: every active PM project
     (successbrian_os.pm_projects) should be visible in
     Atlas. One with no node anywhere is registered as a
     project node — Atlas cannot know what is being built
     if the build is invisible to it.
  4. PLANNED: counts the planned picture (planned nodes,
     pending gates, queued tasks) and notes planned items
     untouched for 60+ days. (Minting stale-work tasks is
     discovery.py's job — this checker does not duplicate
     it.)

Every run is recorded in atlas.currency_checks (when, the
picture counts, what was fixed, what disagrees). Real
discrepancies are filed as Atlas tasks the way discovery.py
files them — deterministic keys (task:currency:<slug>), so
re-runs never double-file, capped at 10 per run. The checker
never deletes anything and never overwrites a status a human
set; it reports disagreements and lets the board/Brian rule.

CLI:
  atlas_currency.py check [--dry-run]
  atlas_currency.py selftest
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import allm_workspaces  # noqa: E402

import psycopg2  # noqa: E402

DBNAME = "ecosystem_central"
MAX_MINT = 10

LOG_DDL = """
CREATE TABLE IF NOT EXISTS atlas.currency_checks (
    id          serial PRIMARY KEY,
    ran_at      timestamptz NOT NULL DEFAULT now(),
    picture     jsonb NOT NULL,
    fixed       jsonb NOT NULL DEFAULT '[]',
    discrepancies jsonb NOT NULL DEFAULT '[]'
);
"""

# Probe label (as printed by systems_integration audit) ->
# atlas.systems_registry key.
PROBE_MAP = {
    "anythingllm": "anythingllm",
    "postgresql": "postgresql",
    "n8n": "n8n",
    "openclaw": "openclaw",
    "model-engines (ollama)": "model-engines",
    "searxng": "searxng",
}


def connect():
    # Same connection shape as systems_integration.py — the
    # atlas schema is owned by the postgres role.
    return psycopg2.connect(dbname=DBNAME, host="localhost",
                            user="postgres")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


# ---------- 1. assets (R38) ----------

def ensure_assets(conn, dry_run=False):
    """Insert any missing R38 asset nodes/edges. Returns the
    list of what was (or would be) fixed."""
    fixed = []
    with conn.cursor() as cur:
        for a in allm_workspaces.MARKETING_ASSETS:
            key = a["node"]
            program = "allm:" + a["markets"]  # canonical target;
            # resolution below also accepts the bare slug and the
            # proj: node (blog-fleet batches wired edges to proj:
            # nodes; code ASSET_EDGES carry registry slugs).
            cur.execute("SELECT 1 FROM atlas.nodes WHERE "
                        "node_key = %s", (key,))
            if not cur.fetchone():
                fixed.append("node " + key)
                if not dry_run:
                    cur.execute(
                        "INSERT INTO atlas.nodes (node_key, "
                        "node_type, name, status, summary) "
                        "VALUES (%s, 'marketing_asset', %s, "
                        "'active', %s)",
                        (key, a["name"],
                         "Marketing asset (R38): %s. It markets "
                         "%s; it is NOT %s — an asset is not "
                         "the program."
                         % (a.get("url") or a["name"],
                            a["markets"], a["markets"])))
            for edge in allm_workspaces.ASSET_EDGES:
                src, dst, etype = edge[0], edge[1], edge[2]
                if src != key:
                    continue
                target = None
                for cand in (program if dst == a["markets"]
                             else "allm:" + dst, dst,
                             "proj:" + dst):
                    cur.execute(
                        "SELECT 1 FROM atlas.nodes WHERE "
                        "node_key = %s", (cand,))
                    if cur.fetchone():
                        target = cand
                        break
                if target is None:
                    fixed.append(
                        "SKIP edge %s -%s-> %s (no Atlas node "
                        "for %s)" % (src, etype, dst, dst))
                    continue
                cur.execute(
                    "SELECT 1 FROM atlas.edges WHERE "
                    "from_node = %s AND to_node = %s AND "
                    "edge_type = %s", (src, target, etype))
                if not cur.fetchone():
                    fixed.append("edge %s -%s-> %s"
                                 % (src, etype, target))
                    if not dry_run:
                        cur.execute(
                            "INSERT INTO atlas.edges "
                            "(from_node, to_node, edge_type, "
                            "notes) VALUES (%s, %s, %s, %s)",
                            (src, target, etype,
                             "R38 asset edge (Brian "
                             "2026-10-27); wired by "
                             "atlas_currency"))
    if not dry_run:
        conn.commit()
    return fixed


# ---------- 2. running vs reality ----------

def parse_probes(audit_text):
    """{registry_key: True(listening)/False(not)} from the
    systems_integration audit output. Pure function."""
    heard = {}
    for line in audit_text.splitlines():
        m = re.match(r"PROBE (.+?) :\d+ — (listening|.*)$", line)
        if not m:
            continue
        label = m.group(1).strip().lower()
        if label in PROBE_MAP:
            heard[PROBE_MAP[label]] = (m.group(2) == "listening")
    return heard


def run_audit():
    here = os.path.dirname(os.path.abspath(__file__))
    proc = subprocess.run(
        [sys.executable,
         os.path.join(here, "systems_integration.py"), "audit"],
        capture_output=True, text=True, timeout=300)
    return proc.stdout + proc.stderr


def check_systems(conn, heard):
    out = []
    with conn.cursor() as cur:
        cur.execute("SELECT key, status FROM "
                    "atlas.systems_registry")
        registry = dict(cur.fetchall())
    for key, listening in sorted(heard.items()):
        status = registry.get(key)
        if status == "live" and not listening:
            out.append({
                "kind": "says-live-but-silent",
                "subject": key,
                "why": "Atlas systems_registry calls %s "
                       "'live', but the probe cannot hear it."
                       % key})
        elif status == "stale" and listening:
            # 'partial' / 'building' are honest in-between
            # states (a service can answer while its links
            # are partial) — not discrepancies. 'stale' while
            # answering is one.
            out.append({
                "kind": "running-but-marked-stale",
                "subject": key,
                "why": "%s answers its probe, but Atlas "
                       "systems_registry calls it 'stale'."
                       % key})
    return out


# ---------- 3. being developed ----------

def check_developing(conn, dry_run=False):
    """Atlas must KNOW what is being developed. A PM project
    with no Atlas presence is registered as a project node
    (the PM registry is a system of record; mirroring it is
    integration, the same pattern systems_integration uses
    for sys:* nodes). Returns (fixed, discrepancies)."""
    fixed, out = [], []
    with conn.cursor() as cur:
        cur.execute("SELECT project_key, title, description "
                    "FROM successbrian_os.pm_projects "
                    "WHERE status = 'active'")
        for key, title, desc in cur.fetchall():
            cur.execute(
                "SELECT 1 FROM atlas.nodes WHERE "
                "node_key ILIKE %s OR name ILIKE %s LIMIT 1",
                ("%" + key + "%", "%" + key.replace("-", " ")
                 + "%"))
            if cur.fetchone():
                continue
            fixed.append("registered proj:%s in Atlas "
                         "(PM project being developed)" % key)
            if not dry_run:
                cur.execute(
                    "INSERT INTO atlas.nodes (node_key, "
                    "node_type, name, status, summary) "
                    "VALUES (%s, 'project', %s, 'active', %s) "
                    "ON CONFLICT (node_key) DO NOTHING",
                    ("proj:" + key, title or key,
                     "Being developed — registered in Atlas "
                     "by atlas_currency from the PM registry "
                     "(successbrian_os.pm_projects). %s"
                     % ((desc or "")[:300])))
    if not dry_run:
        conn.commit()
    return fixed, out


# ---------- 4. planned picture ----------

def picture(conn):
    with conn.cursor() as cur:
        def count(sql, args=()):
            cur.execute(sql, args)
            return cur.fetchone()[0]
        return {
            "systems_live": count(
                "SELECT count(*) FROM atlas.systems_registry "
                "WHERE status = 'live'"),
            "systems_building": count(
                "SELECT count(*) FROM atlas.systems_registry "
                "WHERE status = 'building'"),
            "projects_active": count(
                "SELECT count(*) FROM atlas.nodes WHERE "
                "node_type = 'project' AND status = 'active'"),
            "pm_projects_active": count(
                "SELECT count(*) FROM "
                "successbrian_os.pm_projects "
                "WHERE status = 'active'"),
            "nodes_planned": count(
                "SELECT count(*) FROM atlas.nodes WHERE "
                "status IN ('planned', 'planning')"),
            "gates_pending": count(
                "SELECT count(*) FROM atlas.nodes WHERE "
                "node_type = 'gate' AND status = 'pending'"),
            "tasks_queued": count(
                "SELECT count(*) FROM atlas.nodes WHERE "
                "node_type = 'atlas_task' AND "
                "status = 'queued'"),
            "planned_quiet_60d": count(
                "SELECT count(*) FROM atlas.nodes WHERE "
                "status IN ('planned', 'planning') AND "
                "updated_at < now() - interval '60 days'"),
        }


# ---------- filing + logging ----------

def mint_tasks(conn, discrepancies, dry_run=False):
    minted = []
    with conn.cursor() as cur:
        for d in discrepancies[:MAX_MINT]:
            key = "task:currency:" + slug(
                d["kind"] + "-" + d["subject"])
            cur.execute("SELECT status FROM atlas.nodes "
                        "WHERE node_key = %s", (key,))
            row = cur.fetchone()
            if row and row[0] in ("queued", "open", "active"):
                continue  # already on file, still open
            minted.append(key)
            if dry_run:
                continue
            details = {"why": d["why"], "about": d["subject"],
                       "source": "atlas-currency",
                       "found_by": "atlas-currency",
                       "model": "sonic"}
            cur.execute(
                "INSERT INTO atlas.nodes (node_key, node_type,"
                " name, status, details) VALUES (%s, "
                "'atlas_task', %s, 'queued', %s) "
                "ON CONFLICT (node_key) DO UPDATE SET "
                "status = 'queued', details = "
                "EXCLUDED.details, updated_at = now()",
                (key, "Atlas currency: " + d["why"][:120],
                 json.dumps(details)))
            cur.execute(
                "SELECT 1 FROM atlas.nodes WHERE node_key = %s",
                (d["subject"],))
            if cur.fetchone():
                cur.execute(
                    "INSERT INTO atlas.edges (from_node, "
                    "to_node, edge_type, notes) SELECT %s, %s,"
                    " 'about', 'atlas-currency discrepancy' "
                    "WHERE NOT EXISTS (SELECT 1 FROM "
                    "atlas.edges WHERE from_node = %s AND "
                    "to_node = %s AND edge_type = 'about')",
                    (key, d["subject"], key, d["subject"]))
    if not dry_run:
        conn.commit()
    return minted


def check(dry_run=False):
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(LOG_DDL)
    conn.commit()
    fixed = ensure_assets(conn, dry_run)
    heard = parse_probes(run_audit())
    dev_fixed, dev_disc = check_developing(conn, dry_run)
    fixed = fixed + dev_fixed
    discrepancies = check_systems(conn, heard) + dev_disc
    pic = picture(conn)
    minted = mint_tasks(conn, discrepancies, dry_run)
    if not dry_run:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO atlas.currency_checks (picture, "
                "fixed, discrepancies) VALUES (%s, %s, %s)",
                (json.dumps(pic), json.dumps(fixed),
                 json.dumps(discrepancies)))
        conn.commit()
    return pic, fixed, discrepancies, minted


def selftest():
    fails = []

    def ck(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            fails.append(label)

    sample = ("PROBE anythingllm :3000 — listening\n"
              "PROBE n8n :5678 — listening\n"
              "PROBE searxng :8891 — connection refused\n"
              "PROBE bridge_log last entry: 2026-08-28\n")
    heard = parse_probes(sample)
    ck(heard == {"anythingllm": True, "n8n": True,
                 "searxng": False},
       "audit probe lines parse into registry-key verdicts")
    ck(slug("Says Live, But Silent!") == "says-live-but-silent",
       "discrepancy keys slug deterministically")
    ck(len(allm_workspaces.MARKETING_ASSETS) >= 2 and
       all(e[2] in ("markets", "captures_for")
           for e in allm_workspaces.ASSET_EDGES),
       "R38 asset registry is importable and typed")
    print("SELFTEST %s: %d failure(s)"
          % ("FAILED" if fails else "OK", len(fails)))
    return 1 if fails else 0


def main(argv):
    if len(argv) > 1 and argv[1] == "selftest":
        return selftest()
    if len(argv) > 1 and argv[1] == "check":
        dry = "--dry-run" in argv
        pic, fixed, disc, minted = check(dry)
        print("ATLAS PICTURE  running: %d systems live, "
              "%d building | being developed: %d projects "
              "active (%d in PM) | planned: %d nodes, "
              "%d gates pending, %d tasks queued "
              "(%d planned items quiet 60d+)"
              % (pic["systems_live"], pic["systems_building"],
                 pic["projects_active"],
                 pic["pm_projects_active"], pic["nodes_planned"],
                 pic["gates_pending"], pic["tasks_queued"],
                 pic["planned_quiet_60d"]))
        for f in fixed:
            print("%s %s" % ("WOULD FIX" if dry else "FIXED", f))
        for d in disc:
            print("DISAGREES  %s — %s" % (d["subject"], d["why"]))
        for m in minted:
            print("%s task %s" % ("WOULD FILE" if dry else
                                  "FILED", m))
        if not disc and not fixed:
            print("Atlas matches reality on everything "
                  "checked.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
