#!/usr/bin/env python3
"""SuccessBrian OS — systems integration layer (R28).

Brian's order (2026-10-23): 'atlas, altair's second brain,
postgresql, n8n, anythingllm, successbrian-os, meghan, altair,
lyra and everything else all needs to be integrated together.'

What this module is: the coded registry of the ecosystem's
SYSTEMS (not workspaces — those live in allm_workspaces.py),
the links between them with an honest status per link
(verified / partial / stale / gap), and the machinery that
keeps the Atlas graph truthful about them:

  seed      — upsert the registry + links into
              atlas.systems_registry / atlas.system_links and
              sync the sys:* Atlas nodes.
  integrate — seed + wire graph edges (verified and partial
              links only; stale/gap links stay in the
              registry, never asserted in the graph) +
              generate systems-map.md and embed it in the
              successbrian-os AnythingLLM workspace.
  audit     — live probes (ports, schemas, tables, profiles,
              workflow counts) + the link status report.
  selftest  — structural checks over the coded record.

Discovery basis (verified live on k11-alpha, 2026-10-23):
ports 3000/5432/5678/18789/11434/8891 listening; hermes
profiles altair/lyra/meghan present; altair.second_brain
405 rows (227 active); knowledge_bridge 1,611 rows but
bridge_log quiet since 2026-08-28; n8n (docker n8n-fresno)
holds 3 workflows, 2 active, with ecosystem endpoint
references in their node configs; meghan schema holds
1 table and her engine (Prometheus) is not served.
"""

import os
import socket
import sqlite3
import subprocess
import sys

import psycopg2

DBNAME = "ecosystem_central"
ALLM_DB = "/home/successbrian/anything-llm/server/storage/anythingllm.db"
MAP_PATH = os.path.expanduser(
    "~/successbrian-os/tools/atlas/systems-map.md")
ENV_PATH = os.path.expanduser("~/successbrian-os/.env")

DDL = """
CREATE TABLE IF NOT EXISTS atlas.systems_registry (
    key         text PRIMARY KEY,
    name        text NOT NULL,
    kind        text NOT NULL,
    home        text NOT NULL,
    interface   text NOT NULL,
    status      text NOT NULL,
    note        text
);
CREATE TABLE IF NOT EXISTS atlas.system_links (
    from_key    text NOT NULL,
    to_key      text NOT NULL,
    edge_type   text NOT NULL,
    status      text NOT NULL,
    evidence    text NOT NULL,
    PRIMARY KEY (from_key, to_key, edge_type)
);
"""

# key, name, kind, home, interface, status, note
SYSTEMS = [
    ("successbrian-os", "SuccessBrian OS", "os",
     "k11-alpha ~/successbrian-os",
     "repo + ~/successbrian-os/.env + tools/",
     "hub",
     "The umbrella: every system below is part of it or "
     "plugs into it. Canonical env source is its .env."),
    ("atlas", "Atlas", "graph",
     "k11-alpha, ecosystem_central.atlas",
     "atlas.py CLI + PG tables (nodes/edges)",
     "live",
     "The ecosystem knowledge graph. Hosts the workspace "
     "registry (R1-R27) and this systems registry."),
    ("postgresql", "PostgreSQL", "store",
     "k11-alpha :5432 (PgBouncer :6432)",
     "SQL — 21 databases; ecosystem_central is canonical",
     "live",
     "The shared store almost everything already meets "
     "in: schemas atlas, altair, meghan, calendar, "
     "campaignsdesk, dealsdesk, bus, and more."),
    ("altair-second-brain", "Altair's Second Brain", "knowledge",
     "ecosystem_central.altair (second_brain tables)",
     "tools/second_brain.py + altair.second_brain (405 "
     "rows, 227 active)",
     "live",
     "Altair's knowledge/memory layer (Brian named it "
     "2026-10-20). Decisions and learnings live here as "
     "curriculum."),
    ("anythingllm", "AnythingLLM", "knowledge",
     "k11-alpha :3000",
     "HTTP API (key in successbrian-os/.env) + SQLite store",
     "live",
     "89 governed workspaces (allm_workspaces.py); the "
     "workspace map and this systems map are embedded in "
     "its successbrian-os body."),
    ("n8n", "n8n", "automation",
     "docker n8n-fresno :5678, DB in n8n-db-fresno",
     "web UI + workflow webhooks; own Postgres store",
     "partial",
     "Only 3 workflows (2 active); node configs reference "
     "ecosystem endpoints (verified by content scan "
     "2026-10-23). Not yet a first-class citizen of the "
     "registry-driven bridges."),
    ("altair", "Altair", "agent",
     "hermes profile altair (k11-alpha)",
     "heartbeat + cron_ticker (running); engines "
     "Morpheus :11437, Penny :11438, Sonic :11439",
     "live",
     "The orchestrator. Runs the day; thinks through the "
     "local engines; his decisions land in the second "
     "brain."),
    ("lyra", "Lyra", "agent",
     "hermes profile lyra (k11-alpha)",
     "governor.py loop inside Altair's heartbeat; "
     "lyra_15min_health running",
     "live",
     "The worker/research layer: findings and gated "
     "questions file up to Altair; watchdog every 10 min; "
     "weekly learnings curation."),
    ("meghan", "Meghan (CEO agent)", "agent",
     "hermes profiles meghan + meghan-alpha",
     "PG meghan schema (1 table); ceo-heartbeat timer",
     "partial",
     "CEO agent — finance and future planning, above "
     "Altair. Her engine (Prometheus / Gemma 4 26B) is "
     "NOT served yet: no endpoint exists, so she cannot "
     "think on the fleet's engines today."),
    ("hermes", "Hermes", "framework",
     "k11-alpha ~/.hermes",
     "one profile per agent (SOUL/IDENTITY/config) + A2A",
     "live",
     "The agent framework substrate: altair, lyra, meghan "
     "and dozens of specialist profiles run on it. "
     "Core-patched 0.20.0 — upstream changes are vetted, "
     "never auto-applied."),
    ("openclaw", "OpenClaw", "framework",
     "k11-alpha gateway :18789 + node-gamma agents",
     "gateway + agent workspaces",
     "live",
     "The second agent runtime: gamma's 17 InstantlyClaw "
     "agents live on it; an alpha-side gateway listens "
     "on :18789."),
    ("gamma-fleet", "Gamma fleet (InstantlyClaw)", "node",
     "node-gamma (rented EPYC, shared-tenancy container)",
     "Tailscale tunnel to alpha PG as user gamma_fleet; "
     "OpenClaw agents",
     "partial",
     "17 agents doing scraping/enrichment. UNTRUSTED "
     "shared space (2,497 tenants, one UID). The "
     "gamma_fleet credential is exposed in plaintext "
     "across gamma — rotation is the standing first-"
     "order security action."),
    ("decision-sync", "decision_sync bridge", "bridge",
     "k11-alpha ~/successbrian-os/tools/decision_sync",
     "PG altair.brian_decisions -> AnythingLLM home-lab; "
     "weekly via sunday_shift",
     "partial",
     "Fixed 2026-10-22 (93 decisions embedded). Partial: "
     "everything still routes to home-lab only — per-body "
     "routing via determine() is the R27 follow-on, not "
     "yet wired."),
    ("knowledge-bridge", "Knowledge bridge", "bridge",
     "ecosystem_central.altair (knowledge_bridge, "
     "bridge_log)",
     "PG tables",
     "stale",
     "1,611 bridge rows exist, but bridge_log's last "
     "entry is 2026-08-28 — the bridge has been quiet "
     "for two months. Recorded, not asserted as live."),
    ("a2a-bus", "A2A messaging bus", "messaging",
     "ecosystem_central (bus schema + altair a2a_* tables)",
     "PG tables (bus.events, bus.research_summary; "
     "a2a_agents/messages/topics) + A2A-INBOX files",
     "live",
     "The agent-to-agent messaging substrate the hermes "
     "profiles coordinate through."),
    ("dashboard-api", "Dashboard API", "service",
     "k11-alpha ~/dashboard-api (uvicorn + cloudflared)",
     "HTTP /api/v1/* (calendar, workspaces, health)",
     "live",
     "Serves Brian's calendar and ecosystem state to his "
     "surfaces; reads ecosystem_central."),
    ("searxng", "SearXNG", "service",
     "docker searxng-alpha :8891",
     "HTTP search API",
     "live",
     "The fleet's own search: the one enrichment "
     "verification path that works (searxng_verified — "
     "99.9% contact yield in the gamma audit)."),
    ("model-engines", "Local model engines", "engines",
     "k11-alpha (ollama :11434, llama.cpp servers)",
     "HTTP :11434/:11437/:11438/:11439",
     "live",
     "Morpheus, Penny, Sonic and the ollama fleet — the "
     "engines Altair thinks with and Penny extracts with."),
    ("desks", "The three desks (Deals/Trades/Campaigns)",
     "plugins",
     "k11-alpha private repos + PG schemas",
     "SBOS plugins (R16); dealsdesk + campaignsdesk "
     "schemas in ecosystem_central",
     "live",
     "Private-repo plugins to SuccessBrian OS. Their "
     "knowledge bodies are governed in the workspace "
     "registry."),
    ("contactflowcrm", "ContactFlowCRM", "product",
     "build in progress (repo on k11-alpha)",
     "hosted SaaS (planned, $20/mo)",
     "building",
     "The relationship layer product. Launch gated by "
     "the launch-readiness law: reliable hosting + "
     "finished code, tracked separately in Atlas."),
    ("tailscale-fabric", "Tailscale fabric", "network",
     "tailnet (alpha, gamma, node-zero, laptops, pixel)",
     "tsproxy / ssh routes",
     "live",
     "The private network every node-to-node path rides "
     "on."),
    ("scattered-second-brain", "Scattered Second Brain",
     "subsystem",
     "k11-alpha ~/successbrian-os/tools/atlas/"
     "scattered_brain.py",
     "CLI capture/triage/rule/digest + "
     "atlas.scattered_captures; nightly triage cron 04:30",
     "live",
     "Brian's idea-refinery (R31): captures his stray "
     "ideas raw, triages them in his downtime against "
     "the business goals and the workspace map, and "
     "brings him recommendations. Brian rules — "
     "promote/park/discard; triage never rules. NOT "
     "Altair's second brain: that is the agent's "
     "curriculum; this is Brian's chaos, sorted."),
    ("node-zero", "node-zero (VPS)", "node",
     "successbrianvps.com / srv1485029 (100.118.196.66)",
     "nginx site host + tailnet member",
     "live",
     "The public VPS: hosts successbrianvps.com and "
     "egress duties for the fleet."),
]

# from_key, to_key, edge_type, status, evidence
# status: verified | partial | stale | gap
# Graph edges are asserted ONLY for verified/partial links.
LINKS = [
    ("postgresql", "atlas", "hosts", "verified",
     "atlas schema lives in ecosystem_central; atlas.py "
     "runs against it."),
    ("postgresql", "altair-second-brain", "hosts", "verified",
     "altair.second_brain tables live in ecosystem_central "
     "(405 rows counted 2026-10-23)."),
    ("postgresql", "meghan", "hosts", "partial",
     "meghan schema exists in ecosystem_central but holds "
     "1 table — presence without depth."),
    ("altair", "hermes", "runs-on", "verified",
     "hermes processes + profile altair observed running "
     "2026-10-23 (cron_ticker)."),
    ("lyra", "hermes", "runs-on", "verified",
     "hermes profile lyra exists; lyra_15min_health.py "
     "observed running."),
    ("meghan", "hermes", "runs-on", "verified",
     "hermes profiles meghan and meghan-alpha exist."),
    ("lyra", "altair", "feeds", "verified",
     "Lyra is the worker layer inside Altair's heartbeat "
     "(governor.py); lyra_queue_remediation_log lives in "
     "the altair schema."),
    ("altair", "altair-second-brain", "feeds", "verified",
     "brian_decisions (93) and brian_learnings land in "
     "the altair schema; second_brain holds 405 rows."),
    ("altair", "model-engines", "requires", "verified",
     "Altair thinks via Morpheus :11437 / Penny :11438 / "
     "Sonic :11439 — all listening 2026-10-23."),
    ("meghan", "model-engines", "requires", "gap",
     "Meghan's engine (Prometheus / Gemma 4 26B) is not "
     "served — no endpoint exists. The standing gap."),
    ("decision-sync", "postgresql", "requires", "verified",
     "sync.py reads altair.brian_decisions via psycopg2 "
     "(fixed 2026-10-22)."),
    ("decision-sync", "anythingllm", "feeds", "partial",
     "Verified 2026-10-22: 93 decisions embedded into "
     "home-lab. Partial: routes to home-lab only, not "
     "per-body via determine()."),
    ("atlas", "anythingllm", "supports", "verified",
     "The workspace registry (in Atlas's schema) governs "
     "all 89 workspaces; R27 wired 129 graph edges and "
     "embedded the workspace map in successbrian-os."),
    ("dashboard-api", "postgresql", "requires", "verified",
     "Serves /api/v1/calendar from ecosystem_central's "
     "calendar schema."),
    ("gamma-fleet", "postgresql", "feeds", "partial",
     "Gamma agents reach alpha PG through the tunnel as "
     "gamma_fleet — connected, but the credential sits "
     "exposed on gamma; rotation pending."),
    ("gamma-fleet", "openclaw", "runs-on", "verified",
     "Gamma's 17 agents are OpenClaw workspaces; the "
     "meghan-ceo agent is the working interface."),
    ("searxng", "gamma-fleet", "supports", "verified",
     "The enrichment audit: searxng_verified was the one "
     "working verification path (99.9% contact yield)."),
    ("a2a-bus", "altair", "supports", "verified",
     "a2a_* tables live in the altair schema; A2A-INBOX "
     "files cycle in the home directory."),
    ("a2a-bus", "lyra", "supports", "verified",
     "Lyra coordinates through the same A2A substrate "
     "inside the heartbeat system."),
    ("a2a-bus", "meghan", "supports", "partial",
     "The bus reaches Meghan's tier in the escalation "
     "design (altair -> meghan -> brian); her engine "
     "being unserved limits the leg."),
    ("n8n", "successbrian-os", "supports", "partial",
     "3 workflows (2 active); node configs reference "
     "ecosystem endpoints (content scan 2026-10-23). "
     "No registry-driven bridge yet."),
    ("knowledge-bridge", "anythingllm", "feeds", "stale",
     "knowledge_bridge holds 1,611 rows but bridge_log "
     "is quiet since 2026-08-28 — not asserted as a "
     "live link."),
    ("tailscale-fabric", "gamma-fleet", "supports",
     "verified",
     "Gamma is reached and reaches alpha only through "
     "the tailnet (100.97.109.65)."),
    ("tailscale-fabric", "node-zero", "supports", "verified",
     "node-zero is a tailnet member (100.118.196.66) and "
     "answers SSH over it."),
    ("scattered-second-brain", "postgresql", "requires",
     "verified",
     "Captures live in atlas.scattered_captures in "
     "ecosystem_central."),
    ("scattered-second-brain", "anythingllm", "feeds",
     "verified",
     "Promotion starts planning bodies through "
     "allm_workspaces plan start (R30); its method and "
     "digests live in the scattered-second-brain "
     "workspace."),
    ("scattered-second-brain", "altair", "supports",
     "partial",
     "Its digests and promoted plans feed the planning "
     "layer Altair coordinates; the digest file is the "
     "interface today — no automated handoff yet."),
    ("desks", "successbrian-os", "plugin_of", "verified",
     "R16: all three desks are private-repo plugins to "
     "SuccessBrian OS."),
    ("contactflowcrm", "postgresql", "requires", "gap",
     "The product's data layer (the who-knows-who map) "
     "is being dogfooded in ecosystem_central, but the "
     "product itself is not built/hosted yet — launch "
     "law gates it."),
]


def pg():
    return psycopg2.connect(dbname=DBNAME, host="localhost",
                            user="postgres", password="postgres")


def seed(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
        for row in SYSTEMS:
            cur.execute(
                """
                INSERT INTO atlas.systems_registry
                    (key, name, kind, home, interface, status,
                     note)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    name = EXCLUDED.name, kind = EXCLUDED.kind,
                    home = EXCLUDED.home,
                    interface = EXCLUDED.interface,
                    status = EXCLUDED.status,
                    note = EXCLUDED.note
                """, row)
        keys = [r[0] for r in SYSTEMS]
        cur.execute(
            "DELETE FROM atlas.systems_registry "
            "WHERE key <> ALL(%s)", (keys,))
        for row in LINKS:
            cur.execute(
                """
                INSERT INTO atlas.system_links
                    (from_key, to_key, edge_type, status,
                     evidence)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (from_key, to_key, edge_type)
                DO UPDATE SET status = EXCLUDED.status,
                    evidence = EXCLUDED.evidence
                """, row)
        link_keys = [(r[0], r[1], r[2]) for r in LINKS]
        cur.execute(
            "SELECT from_key, to_key, edge_type FROM "
            "atlas.system_links")
        for fk, tk, et in cur.fetchall():
            if (fk, tk, et) not in link_keys:
                cur.execute(
                    "DELETE FROM atlas.system_links WHERE "
                    "from_key = %s AND to_key = %s AND "
                    "edge_type = %s", (fk, tk, et))
        # Sync sys:* Atlas nodes.
        for row in SYSTEMS:
            node_key = "sys:" + row[0]
            summary = "%s — %s" % (row[1], row[6])
            cur.execute(
                "INSERT INTO atlas.nodes (node_key, node_type, "
                "name, status, summary, updated_at) "
                "SELECT %s, 'system', %s, %s, %s, now() "
                "WHERE NOT EXISTS (SELECT 1 FROM atlas.nodes "
                "WHERE node_key = %s)",
                (node_key, row[1],
                 "active" if row[5] in ("live", "hub")
                 else "planned",
                 summary, node_key))
            cur.execute(
                "UPDATE atlas.nodes SET summary = %s, "
                "updated_at = now() WHERE node_key = %s",
                (summary, node_key))
    conn.commit()
    return len(SYSTEMS), len(LINKS)


def plan_edges():
    """Graph assertions: SBOS contains every system, plus
    each link whose status is verified or partial. Stale
    and gap links are registry truth, never graph truth."""
    edges = []
    for row in SYSTEMS:
        if row[0] == "successbrian-os":
            continue
        edges.append(
            ("sys:successbrian-os", "sys:" + row[0], "contains",
             "R28: %s is part of the integrated ecosystem."
             % row[1]))
    for frm, to, etype, status, evidence in LINKS:
        if status in ("verified", "partial"):
            edges.append(
                ("sys:" + frm, "sys:" + to, etype,
                 "R28 [%s] %s" % (status, evidence)))
    return edges


def apply_edges(conn, edges):
    inserted = 0
    with conn.cursor() as cur:
        for frm, to, etype, note in edges:
            cur.execute(
                "INSERT INTO atlas.edges (from_node, to_node, "
                "edge_type, notes) SELECT %s, %s, %s, %s "
                "WHERE NOT EXISTS (SELECT 1 FROM atlas.edges "
                "WHERE from_node = %s AND to_node = %s AND "
                "edge_type = %s)",
                (frm, to, etype, note, frm, to, etype))
            inserted += cur.rowcount
    conn.commit()
    return inserted


def render_map(conn):
    lines = ["# Systems Map — the integrated ecosystem", "",
             "Generated by systems_integration.py (R28) from "
             "the coded registry. Every system, where it "
             "lives, and how it connects — with the honest "
             "status of each link.", ""]
    for row in SYSTEMS:
        lines.append("## %s (%s) — %s" % (row[1], row[2], row[5]))
        lines.append("Home: %s. Interface: %s."
                     % (row[3], row[4]))
        lines.append(row[6])
        lines.append("")
    lines.append("## Links")
    for frm, to, etype, status, evidence in LINKS:
        lines.append("- %s —[%s]-> %s [%s]: %s"
                     % (frm, etype, to, status, evidence))
    lines.append("")
    return "\n".join(lines)


def embed_map(conn):
    """Upload systems-map.md into successbrian-os and embed
    it, once. Returns a status line; never raises."""
    import json
    import urllib.request
    import uuid
    try:
        text = render_map(conn)
        with open(MAP_PATH, "w") as f:
            f.write(text)
        db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB,
                             uri=True)
        try:
            row = db.execute(
                "SELECT count(*) FROM workspace_documents wd "
                "JOIN workspaces w ON w.id = wd.workspaceId "
                "WHERE w.slug = 'successbrian-os' AND "
                "wd.filename LIKE '%systems-map%'").fetchone()
            if row and row[0]:
                return ("map: already embedded in "
                        "successbrian-os (%d doc)" % row[0])
        finally:
            db.close()
        key = None
        with open(ENV_PATH) as f:
            for ln in f:
                if ln.startswith("ANYTHINGLLM_API_KEY="):
                    key = ln.split("=", 1)[1].strip()
        if not key:
            return "map: written; no API key found"
        base = "http://127.0.0.1:3000"
        boundary = "----sys" + uuid.uuid4().hex
        body = (
            "--%s\r\nContent-Disposition: form-data; "
            "name=\"file\"; filename=\"systems-map.md\"\r\n"
            "Content-Type: text/markdown\r\n\r\n%s\r\n--%s--\r\n"
            % (boundary, text, boundary)).encode()
        req = urllib.request.Request(
            base + "/api/v1/document/upload", data=body,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "multipart/form-data; "
                     "boundary=" + boundary})
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
        loc = payload["documents"][0]["location"]
        data = json.dumps({"adds": [loc], "deletes": []}).encode()
        req = urllib.request.Request(
            base + "/api/v1/workspace/successbrian-os/"
            "update-embeddings", data=data,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        return "map: uploaded + embedded in successbrian-os"
    except Exception as exc:
        return "map: FAILED (%s) — graph unaffected" % exc


def _port(port):
    try:
        with socket.create_connection(("127.0.0.1", port),
                                      timeout=2):
            return True
    except OSError:
        return False


def audit(conn):
    lines = []
    probes = [(3000, "anythingllm"), (5432, "postgresql"),
              (5678, "n8n"), (18789, "openclaw"),
              (11434, "model-engines (ollama)"),
              (8891, "searxng")]
    for port, name in probes:
        lines.append("PROBE %s :%d — %s"
                     % (name, port,
                        "listening" if _port(port) else "DARK"))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM altair.second_brain")
        lines.append("PROBE second_brain rows: %d"
                     % cur.fetchone()[0])
        cur.execute("SELECT max(created_at) FROM "
                    "altair.bridge_log")
        lines.append("PROBE bridge_log last entry: %s "
                     "(knowledge-bridge staleness check)"
                     % cur.fetchone()[0])
    for prof in ("altair", "lyra", "meghan"):
        path = os.path.expanduser("~/.hermes/profiles/" + prof)
        lines.append("PROBE hermes profile %s — %s"
                     % (prof, "present" if os.path.isdir(path)
                        else "MISSING"))
    try:
        out = subprocess.run(
            ["docker", "exec", "n8n-db-fresno", "psql", "-U",
             "n8n", "-d", "n8n", "-Atc",
             "SELECT count(*) FROM workflow_entity"],
            capture_output=True, text=True, timeout=15)
        lines.append("PROBE n8n workflows: %s"
                     % out.stdout.strip())
    except Exception as exc:
        lines.append("PROBE n8n workflows: unprobeable (%s)"
                     % exc)
    for frm, to, etype, status, _ev in LINKS:
        if status in ("gap", "stale"):
            lines.append("LINK %s %s->%s — %s"
                         % (status.upper(), frm, to, etype))
    return lines


def cmd_integrate(conn):
    n_sys, n_links = seed(conn)
    edges = plan_edges()
    inserted = apply_edges(conn, edges)
    print("systems seeded: %d — links recorded: %d"
          % (n_sys, n_links))
    print("edges planned: %d — inserted %d, already present %d"
          % (len(edges), inserted, len(edges) - inserted))
    print(embed_map(conn))
    for ln in audit(conn):
        print(ln)
    return 0


def selftest(conn):
    failures = []

    def check(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    keys = [r[0] for r in SYSTEMS]
    check(len(keys) == len(set(keys)),
          "system keys are unique")
    check(all(r[3] and r[4] for r in SYSTEMS),
          "every system names its home and interface")
    check(all(frm in keys and to in keys for frm, to, _e, _s,
              _ev in LINKS),
          "every link joins two registered systems")
    check(all(s in ("verified", "partial", "stale", "gap")
              for _f, _t, _e, s, _ev in LINKS),
          "every link carries an honest status")
    plan = plan_edges()
    planned_pairs = {(f, t) for f, t, _e, _n in plan}
    check(all(("sys:successbrian-os", "sys:" + k) in planned_pairs
              for k in keys if k != "successbrian-os"),
          "R28: the plan contains every system under "
          "SuccessBrian OS")
    check(not any(frm == "meghan" and to == "model-engines"
                  for frm, to, _e, _n in plan),
          "R28: the Meghan-engine gap is NOT asserted in "
          "the graph")
    check(not any(frm == "knowledge-bridge"
                  for frm, _t, _e, _n in plan),
          "R28: the stale knowledge bridge is NOT asserted "
          "in the graph")
    n1 = seed(conn)
    n2 = seed(conn)
    check(n1 == n2 == (len(SYSTEMS), len(LINKS)),
          "seed idempotent: %d systems, %d links"
          % (len(SYSTEMS), len(LINKS)))
    if failures:
        print("SELFTEST FAILED: %d check(s)" % len(failures))
        return 1
    print("SELFTEST OK")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "list"
    conn = pg()
    try:
        if cmd == "seed":
            n = seed(conn)
            print("seeded systems: %d, links: %d" % n)
            return 0
        if cmd == "list":
            for r in SYSTEMS:
                print("%-24s %-10s %s" % (r[0], r[2], r[5]))
            return 0
        if cmd == "integrate":
            return cmd_integrate(conn)
        if cmd == "audit":
            seed(conn)
            for ln in audit(conn):
                print(ln)
            return 0
        if cmd == "selftest":
            return selftest(conn)
        print("usage: systems_integration.py "
              "[list|seed|integrate|audit|selftest]")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
