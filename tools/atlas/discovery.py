#!/usr/bin/env python3
"""Atlas Discovery - finds keystones and mints board agenda items.

KEYSTONES (Brian's term, 2026-10-21): the top-level things of the
ecosystem - gates, projects, plans, and the systems in the readiness
register. Everything below them (tasks, docs, code, deals) is working
detail. Discovery watches the keystones; the board steers them.

Part of Atlas (tools/atlas). Brian's directive, 2026-10-21: the ecosystem
needs a system that discovers the top-level things and creates agenda
items from them (AGENT_CONTRACT rule 19: the agenda is minted, not
gathered).

Detectors run over the Atlas graph and the systems register. Each
finding becomes an atlas_task (status 'queued', found_by/source
'atlas-discovery', 'about' edge to the node it was discovered from),
with a deterministic node_key so re-runs never double-mint. Gates are
set only under rule 17 by the board / Altair / Meghan / Brian - this
system mints tasks and reports gate-shaped findings, it does not set
gates itself.

Usage:
  discovery.py            # dry run: print findings + what WOULD mint
  discovery.py --apply    # mint the tasks into Atlas
  discovery.py --detector readiness,stale   # subset

Rate limit: at most MAX_PER_DETECTOR mints per detector per run
(rule 18: establish, stabilize, add, analyze - the queue stays
digestible). Findings beyond the limit are reported, not minted.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys


# psql/q/route_model mirror tools/atlas/atlas.py exactly. They are
# copied, not imported: atlas.py parses its CLI at module level, so
# importing it would run the CLI. Keep these in step with atlas.py.
def psql(sql):
    p = subprocess.run(
        ['psql', '-h', 'localhost', '-U', 'postgres', '-d', 'ecosystem_central',
         '-t', '-A', '-F', '\t', '-v', 'ON_ERROR_STOP=1'],
        input=sql, capture_output=True, text=True,
        env={'PATH': '/usr/bin:/bin', 'HOME': os.path.expanduser('~')})
    if p.returncode != 0:
        print(p.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return [ln for ln in p.stdout.split('\n') if ln]


def q(s):
    return "'" + s.replace("'", "''") + "'"


def route_model():
    """Brian's routing (2026-10-17): V4 Pro preferred when it has API
    value; otherwise Sonic. An active plan:v4-freeze overrides."""
    fr = psql("SELECT status FROM atlas.nodes WHERE node_key='plan:v4-freeze';")
    if fr and fr[0].strip() == "active":
        return "sonic", "frozen"
    bal = psql("SELECT available, usd FROM successbrian_os.v4pro_balance_history "
               "ORDER BY checked_at DESC LIMIT 1;")
    if bal:
        parts = bal[0].split("|")
        avail = parts[0].strip().lower() == "t"
        try:
            usd = float(parts[1].strip())
        except Exception:
            usd = 0
        if avail and usd > 0:
            return "v4pro", "balance $%.2f" % usd
    return "sonic", "no V4 value"

MAX_PER_DETECTOR = 10
STALE_DAYS = 30
TOP_TYPES = ("project", "plan")

# The systems register (board/SYSTEMS_READINESS.md) is the source of
# the keystone systems list; this mirrors it. slug -> (display name,
# atlas node key or None, hold-gate key or None). A system behind a
# pending hold-gate is reported, not minted: its prerequisite comes
# first (rule 17).
SYSTEMS = [
    ("contactflowcrm", "ContactFlowCRM", "proj:contactflowcrm", None),
    ("coaching-program", "Coaching program", None, None),
    ("sbos-trafficstreemz", "SuccessBrian OS + TrafficStreemz plugin",
     "proj:trafficstreemz-plugin", None),
    ("campaignsdesk", "CampaignsDesk", None, None),
    ("tradesdesk", "TradesDesk", None, None),
    ("dealsdesk", "DealsDesk", "proj:dealsdesk", None),
    ("blog-network", "Blog network + Substack", "proj:blog-network", None),
    ("hardware-flipping", "Hardware flipping", None,
     "gate:hardware-flipping-space"),
]


def rows(sql):
    return [ln.split("\t") for ln in psql(sql)]


def node_exists(key):
    r = psql(
        "SELECT 1 FROM atlas.nodes WHERE node_key=%s;" % q(key))
    return bool(r)


def node_status(key):
    r = psql(
        "SELECT status FROM atlas.nodes WHERE node_key=%s;" % q(key))
    return r[0].strip() if r else None


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class Finding:
    def __init__(self, detector, task_key, title, about, why):
        self.detector = detector
        self.task_key = task_key
        self.title = title
        self.about = about
        self.why = why
        self.state = "would-mint"  # or already-minted / held / over-limit


def detect_readiness():
    out = []
    for slug, name, node_key, hold_gate in SYSTEMS:
        key = "task:discovery:readiness:%s" % slug
        f = Finding("readiness", key,
                    "Assess readiness: %s" % name, node_key,
                    "system in the readiness register, not yet assessed")
        if hold_gate and node_status(hold_gate) == "pending":
            f.state = "held"
            f.why = ("held behind pending gate %s - prerequisite first "
                     "(rule 17)" % hold_gate)
        elif node_exists(key):
            f.state = "already-minted"
        out.append(f)
    return out


def detect_stale():
    out = []
    found = rows(
        "SELECT node_key, node_type, name FROM atlas.nodes "
        "WHERE node_type IN ('project','plan') AND status='active' "
        "AND updated_at < now() - interval '%d days' "
        "ORDER BY updated_at ASC;" % STALE_DAYS)
    for k, t, n in found:
        key = "task:discovery:stale:%s" % slugify(k)
        f = Finding("stale", key, "Review stale active %s: %s" % (t, n),
                    k, "active %s not updated in %d+ days" % (t, STALE_DAYS))
        if node_exists(key):
            f.state = "already-minted"
        out.append(f)
    return out


def detect_orphans():
    out = []
    found = rows(
        "SELECT node_key, node_type, name FROM atlas.nodes n "
        "WHERE n.node_type IN ('project','plan') "
        "AND NOT EXISTS (SELECT 1 FROM atlas.edges e "
        "WHERE e.from_node=n.node_key OR e.to_node=n.node_key) "
        "ORDER BY n.node_type, n.node_key;")
    for k, t, n in found:
        key = "task:discovery:orphan:%s" % slugify(k)
        f = Finding("orphan", key, "Map or retire orphan %s: %s" % (t, n),
                    k, "%s has no edges - invisible to the graph" % t)
        if node_exists(key):
            f.state = "already-minted"
        out.append(f)
    return out


def detect_gate_criteria():
    out = []
    found = rows(
        "SELECT node_key, name FROM atlas.nodes WHERE node_type='gate' "
        "AND status='pending' AND (details IS NULL OR details::text='{}') "
        "ORDER BY node_key;")
    for k, n in found:
        key = "task:discovery:gate-criteria:%s" % slugify(k)
        f = Finding("gate-criteria", key, "Record gate criteria: %s" % n,
                    k, "pending gate with no recorded criteria - "
                       "it leads the agenda but cannot be ruled well")
        if node_exists(key):
            f.state = "already-minted"
        out.append(f)
    return out


def _tcp_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def _sh(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return p.stdout or ""
    except Exception:
        return ""


def detect_staff():
    """The staff are keystones (rule 21): engines, timers, and workers
    have health states too, checked like any other keystone's."""
    out = []

    def add(slug, title, about, why, bad):
        f = Finding("staff", "task:discovery:staff:%s" % slug,
                    title, about, why)
        if not bad:
            return  # healthy: no finding, no task
        if node_exists(f.task_key):
            f.state = "already-minted"
        out.append(f)

    for port, label in ((11436, "Chuck"), (11437, "Morpheus"),
                        (11438, "Penny"), (11439, "Sonic")):
        add("endpoint-%d" % port,
            "Restore model endpoint: %s (:%d)" % (label, port), None,
            "staff model endpoint :%d not listening" % port,
            bad=not _tcp_open(port))

    procs = _sh(["pgrep", "-af", "llama-server"]).lower()
    add("meghan-engine",
        "Seat Meghan: Prometheus (Gemma) is not served", 
        "plan:seat-meghan-prometheus",
        "no Gemma/Prometheus llama-server running - the CEO tier is "
        "absent from the council and from the 05:00 refinement",
        bad=not any(w in procs for w in ("gemma", "prometheus", "meghan")))

    timer = _sh(["systemctl", "--user", "is-active",
                 "ceo-heartbeat.timer"]).strip()
    add("ceo-heartbeat-timer",
        "Restore Meghan's ceo-heartbeat timer", None,
        "ceo-heartbeat.timer is '%s', not active" % (timer or "unknown"),
        bad=(timer != "active"))

    cron = _sh(["crontab", "-l"])
    live_worker = any("v4pro_handoff_worker" in ln
                      and not ln.strip().startswith("#")
                      for ln in cron.split("\n"))
    add("research-worker",
        "Research chain offline: v4pro handoff worker is disabled",
        None,
        "the Lyra/v4pro handoff worker cron is commented out (Meghan, "
        "2026-10-20) - rules 2-3 research and refinement support are off",
        bad=not live_worker)
    return out


PSQL_PU = ["psql", "-h", "localhost", "-U", "postgres", "-d",
           "people_unified", "-t", "-A", "-F", "|"]


def qpu(sql):
    p = subprocess.run(PSQL_PU + ["-c", sql], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("psql(people_unified): " + p.stderr.strip())
    return p.stdout


def rows_pu(sql):
    return [ln.split("|") for ln in qpu(sql).split("\n") if ln]


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _esc(s):
    return s.replace("'", "''")


# Companies already covered as keystones or register lines (lowercase).
COVERED_COMPANIES = {"zilara", "gotbackup", "vate life", "oliabo"}

# Initiative-name keywords that match an existing keystone system/line.
KEYSTONE_MATCH = {
    "dealsdesk": "DealsDesk (register system)",
    "gotbackup": "GotBackup (income line)",
    "zilara": "Zilara (income line)",
    "traffic": "TrafficStreemz (register system)",
    "blog": "blog network (register system)",
    "contactflow": "ContactFlowCRM (register system)",
    "campaign": "CampaignsDesk (register system)",
    "trade": "TradesDesk (register system)",
}


def detect_prospect():
    """Prospecting (Brian, 2026-10-21): find POTENTIAL keystones and
    initiatives in the record and file them as candidates. Candidates
    are proposals, never designations - the owner (or the board inside
    its gate) ratifies or dismisses; a dismissed candidate is never
    re-proposed (its node_key persists in a terminal status)."""
    out = []

    def cand(slug, title, kind, name, evidence, question):
        ckey = "cand:%s" % slug
        f = Finding("prospect", "task:discovery:prospect:%s" % slug,
                    "Rule on candidate: %s" % name, ckey,
                    "candidate %s filed by prospecting: %s"
                    % (kind, evidence))
        f.candidate = {"key": ckey, "name": "Candidate: %s" % name,
                       "kind": kind, "evidence": evidence,
                       "question": question}
        if node_exists(ckey):
            f.state = "already-proposed"
        elif node_exists(f.task_key):
            f.state = "already-minted"
        out.append(f)

    # Source A: MLM companies Brian is involved in (the ONE companies
    # table, people.companies kind='mlm' — Brian's ruling 2026-10-27;
    # formerly people.mlm_companies) that no keystone or register
    # line covers.
    comp_rows = rows_pu(
        "SELECT name, status, brians_role FROM people.companies "
        "WHERE kind = 'mlm' AND brians_role IS NOT NULL "
        "AND brians_role <> '' "
        "ORDER BY name")
    for name, status, role in comp_rows:
        if name.lower() in COVERED_COMPANIES:
            continue
        if role.strip().lower().startswith(("none", "research")):
            continue  # research/intel only, no involvement
        cand("company-%s" % _slug(name),
             None, "keystone", name,
             "people.companies (mlm): status=%s; Brian's role: %s"
             % (status, role.strip()),
             "Is %s a keystone (a business line the staff tracks and "
             "keeps healthy), a register line, or intel only?" % name)

    # Source B: initiatives with no keystone link (graph_node_id null).
    init_rows = rows(
        "SELECT name, type, status FROM public.initiatives "
        "WHERE graph_node_id IS NULL ORDER BY created_at")
    for name, itype, status in init_rows:
        low = name.lower()
        match = next((v for k, v in KEYSTONE_MATCH.items() if k in low),
                     None)
        if match:
            cand("initiative-%s" % _slug(name),
                 None, "initiative-link", name,
                 "public.initiatives: '%s' (%s, %s) has no graph link; "
                 "it appears to serve %s" % (name, itype, status, match),
                 "Link the %s initiative to %s in the graph, or rule "
                 "that it serves a different keystone." % (name, match))
        else:
            cand("initiative-%s" % _slug(name),
                 None, "keystone-or-retire", name,
                 "public.initiatives: '%s' (%s, %s) is active effort "
                 "with no keystone on record" % (name, itype, status),
                 "Name the keystone the %s initiative serves (and "
                 "create it if it should exist), link it, or retire "
                 "the initiative." % name)
    out.sort(key=lambda f: f.task_key)
    return out


def mint_candidate(c):
    details = {"kind": c["kind"], "source": "atlas-discovery",
               "detector": "prospect", "evidence": c["evidence"],
               "question": c["question"]}
    sql = (
        "INSERT INTO atlas.nodes (node_key, node_type, name, status, "
        "details) VALUES ('%s', 'candidate', '%s', 'proposed', "
        "'%s'::jsonb) ON CONFLICT (node_key) DO NOTHING"
        % (c["key"], _esc(c["name"]),
           _esc(json.dumps(details))))
    psql(sql)  # NB: psql() executes; q() only quotes a literal


DETECTORS = {
    "readiness": detect_readiness,
    "stale": detect_stale,
    "orphan": detect_orphans,
    "gate-criteria": detect_gate_criteria,
    "staff": detect_staff,
    "prospect": detect_prospect,
}


def mint(f):
    model, _reason = route_model()
    det = {"about": f.about or "", "found_by": "atlas-discovery",
           "source": "atlas-discovery", "detector": f.detector,
           "model": model, "why": f.why}
    psql(
        "INSERT INTO atlas.nodes (node_key, node_type, name, status, details) "
        "VALUES (%s, 'atlas_task', %s, 'queued', %s::jsonb) "
        "ON CONFLICT (node_key) DO NOTHING;"
        % (q(f.task_key), q(f.title),
           q(json.dumps(det))))
    if f.about:
        psql(
            "INSERT INTO atlas.edges (from_node, to_node, edge_type) "
            "VALUES (%s, %s, 'about') ON CONFLICT DO NOTHING;"
            % (q(f.task_key), q(f.about)))


def main():
    ap = argparse.ArgumentParser(description="Atlas Discovery")
    ap.add_argument("--apply", action="store_true",
                    help="mint tasks (default: dry run, writes nothing)")
    ap.add_argument("--detector",
                    help="comma list; default: all (%s)"
                         % ",".join(DETECTORS))
    a = ap.parse_args()

    names = (a.detector.split(",") if a.detector else list(DETECTORS))
    print("ATLAS DISCOVERY - %s" % ("APPLY" if a.apply else "DRY RUN"))
    total_minted = 0
    total_mintable = 0
    for name in names:
        findings = DETECTORS[name]()
        mintable = [f for f in findings if f.state == "would-mint"]
        total_mintable += len(mintable[:MAX_PER_DETECTOR])
        over = mintable[MAX_PER_DETECTOR:]
        for f in over:
            f.state = "over-limit"
        print("\n[%s] %d findings" % (name, len(findings)))
        for f in findings:
            print("  %-14s %s" % (f.state, f.title))
            print("  %-14s why: %s" % ("", f.why))
            if f.state == "would-mint" and a.apply:
                if getattr(f, "candidate", None):
                    mint_candidate(f.candidate)
                    print("  %-14s -> candidate %s"
                          % ("", f.candidate["key"]))
                mint(f)
                total_minted += 1
                print("  %-14s -> minted %s" % ("", f.task_key))
    print("\n%s: %d task(s) %s"
          % ("DONE" if a.apply else "DRY RUN",
             total_minted if a.apply else total_mintable,
             "minted" if a.apply else "would be minted (rate-limited)"))


if __name__ == "__main__":
    main()
