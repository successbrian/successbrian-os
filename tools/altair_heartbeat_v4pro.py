#!/usr/bin/env python3
"""
altair_heartbeat_v4pro.py — Altair's heartbeat deep tier on DeepSeek V4 Pro.

PURPOSE: Every heartbeat tick:
         1. CONSUME — read newly completed V4 Pro handoffs; file anything
            flagged as needing Brian's call as a pending question (one at a
            time), and fold the findings into the next deep pass's context
            so each pass builds on the last.
         2. ROUTE — pull open tasks from the task table (any assignee);
            critical/urgent/high route forced, the rest go through the
            v4pro router heuristic; queue the hard ones as individual
            handoffs, with V4 Pro instructed to decompose each into
            Sonic-sized steps. Stuck-flagged tasks are always included;
            stale-abandoned ones are excluded.
         3. DEEP PASS — queue the heartbeat deep-reasoning pass (as before).
         Steps 2-3 run only when V4 Pro is usable (checker table). Step 1 is
         free and always runs.
         DRY MODE (Brian 2026-10-16): when V4 Pro is NOT usable, the tick
         does not idle — it surges local queue-building. Hard tasks are
         decomposed into Sonic-sized harness jobs by Sonic himself (free,
         local), at a higher per-tick cap, so the harness queue keeps
         growing through dry days. While V4 IS usable, Sonic still
         decomposes the hard tasks V4 didn't take (buffer building), so
         the queue grows under both regimes. Brian's doctrine: he cares
         whether V4 has value or not, not the dollar amount — and dry
         days must be covered by a pre-built Sonic queue, not idle ticks.
         The consume step also turns V4 Pro's SONIC STEPS sections into
         harness jobs (successbrian_os.harness_jobs, ordered by Altair) so
         hard tasks become executable work for the dedicated coding harness —
         Brian 2026-10-12: "it should be working hard tasks into tasks that
         can be completed by sonic." (DealsDesk and Altair don't code
         directly anymore; the harness does.)
WHY: Brian 2026-10-09: "his HEARTBEAT should run Deepseek api if it's
     available." Brian 2026-10-12: "when it's up, we need it to do more" —
     wire real task routing (the router sat idle: only heartbeat passes ever
     ran) and close the loop (results stacked unread in the handoffs table).
CALLED BY: system cron 5,35 * * * * (successbrian).
NOTES:
  - Availability ONLY from v4pro_router.get_availability() (checker table).
    Never hardcoded, never assumed.
  - The worker re-checks availability before every API call; max 3/run.
  - Consume state: /home/successbrian/.hermes/shared/v4pro-consume-state.json
    (last consumed handoff id; initialized to current max on first run so
    old results are not backfilled).
  - Deep-pass guard is per-kind now: task handoffs no longer block it.
FIXES 2026-10-12: the unsure-tasks query referenced a nonexistent `notes`
  column (real column: task_notes) and silently returned nothing — the deep
  pass never saw those tasks. Fixed here.
"""

import json
import os
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v4pro_router import get_availability, classify, pq  # noqa: E402

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t"]
TOOLS = "/home/successbrian/successbrian-os/tools"
HEARTBEAT_MD = "/home/successbrian/.hermes/profiles/altair/HEARTBEAT.md"
CONSUME_STATE = "/home/successbrian/.hermes/shared/v4pro-consume-state.json"

MAX_TASK_HANDOFFS_PER_TICK = 2
TASK_DEDUPE_DAYS = 7
MAX_SONIC_STEPS = 5
JOB_SIZING_RUBRIC = "/home/successbrian/mantis-coding-harness/knowledge/JOB-SIZING.md"

# Dry-mode doctrine (Brian 2026-10-16): Sonic is free and local, so the
# per-tick caps for Sonic decomposition are deliberately higher than the
# V4 cap. DRY = V4 down: surge. BUFFER = V4 up: keep building anyway.
SONIC_URL = "http://localhost:11439/v1/chat/completions"
SONIC_HEALTH_URL = "http://localhost:11439/health"
SONIC_TIMEOUT = 300
DRY_SONIC_DECOMPOSE_PER_TICK = 5
BUFFER_SONIC_DECOMPOSE_PER_TICK = 2
SONIC_DEDUPE_DAYS = 7

PENDING_RE = re.compile(
    r"^\s*\*{0,2}\s*pending\s+brian\s+calls?\s*:\s*(.+?)\s*\*{0,2}\s*$",
    re.IGNORECASE | re.MULTILINE)
STEPS_HEADER_RE = re.compile(r"sonic\s+steps\s*:", re.IGNORECASE)
PARENT_TASK_RE = re.compile(r"Task #(\d+):")


def query(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def exec_sql(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    return r.returncode == 0


def load_consume_state():
    try:
        with open(CONSUME_STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_consume_state(state):
    try:
        with open(CONSUME_STATE, "w") as f:
            json.dump(state, f)
    except OSError:
        pass


def get_unsure_tasks():
    id_rows = query(
        "SELECT id FROM successbrian_os.tasks "
        "WHERE task_notes ILIKE '%not 90% sure%' AND status NOT IN "
        "('completed','archived','cancelled') ORDER BY id LIMIT 5")
    tasks = []
    for tid in [x for x in id_rows.split() if x.strip().isdigit()]:
        row = query("SELECT title, COALESCE(task_notes,'') "
                    "FROM successbrian_os.tasks WHERE id = %s" % tid)
        parts = row.split("\t")
        if parts and parts[0]:
            tasks.append({"id": int(tid), "title": parts[0],
                          "notes": "\t".join(parts[1:])})
    return tasks


def format_unsure_context(tasks):
    if not tasks:
        return "(none)"
    return "\n".join("%d: %s" % (t["id"], t["title"][:120]) for t in tasks)


def get_routable_tasks(exclude_ids):
    """Open tasks worth deep thought, any assignee. Critical/urgent/high
    ones route forced; the rest go through the router heuristic.
    Stuck-flagged tasks are included regardless of age — they're exactly
    what the deep tier is for. Stale-abandoned tasks (untouched 21+ days,
    no stale flag) are excluded."""
    id_rows = query(
        "SELECT id FROM successbrian_os.tasks "
        "WHERE status IN ('active','in_progress','blocked') "
        "AND (COALESCE(updated_at, created_at) > now() - interval '21 days' "
        "OR stale_flag IS NOT NULL) "
        "ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'urgent' THEN 1 "
        "WHEN 'high' THEN 2 ELSE 3 END, id DESC LIMIT 10")
    tasks = []
    for tid in [x for x in id_rows.split() if x.strip().isdigit()]:
        if int(tid) in exclude_ids:
            continue
        row = query("SELECT title, COALESCE(task_notes,''), priority, status "
                    "FROM successbrian_os.tasks WHERE id = %s" % tid)
        parts = row.split("\t")
        if parts and parts[0]:
            tasks.append({"id": int(tid), "title": parts[0],
                          "notes": parts[1] if len(parts) > 1 else "",
                          "priority": parts[2] if len(parts) > 2 else "",
                          "status": parts[3] if len(parts) > 3 else ""})
    return tasks


def task_handed_off_recently(task_id):
    n = query(
        "SELECT count(*) FROM successbrian_os.v4pro_handoffs "
        "WHERE task_summary LIKE 'Task #%d:%%' AND status IN "
        "('queued','working','done') AND created_at > now() - interval '%d days'"
        % (task_id, TASK_DEDUPE_DAYS))
    return n.strip().isdigit() and int(n) > 0


def queue_handoff(summary, ask, kind, context, constraints, dry_run=False):
    cmd = [sys.executable, os.path.join(TOOLS, "v4pro_router.py"), "queue",
           "--summary", summary, "--ask", ask, "--kind", kind,
           "--context", context, "--constraints", constraints,
           "--requested-by", "altair"]
    if dry_run:
        print("DRY-RUN would queue: [%s] %s" % (kind, summary[:80]))
        return True
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    out = ((r.stdout or "") + (r.stderr or ""))[:200].strip()
    print(("queued" if r.returncode == 0 else "queue-failed") + ": " + out)
    return r.returncode == 0


def build_decomposition_prompt(t):
    """Shared decomposition prompt — used for V4 handoffs AND Sonic dry-mode
    decomposition. Both produce SONIC STEPS for the coding harness."""
    summary = "Task #%d: %s" % (t["id"], t["title"][:100])
    ask = ("Break this hard task into steps Sonic can execute. Sonic is the "
           "fast local model (Qwen3.6-35B-A3B) — size every step for him per "
           "%s: single-file scripts, pattern-following builds, focused "
           "fixes, config/DDL, deterministic test loops; named files/tables; "
           "a mechanical done-check. Do NOT assign Sonic novel architecture, "
           "ambiguous research-coding, or wide cross-file context — say "
           "explicitly which parts don't fit and why. The steps feed the "
           "dedicated coding harness, which executes them autonomously — "
           "each spec must be self-contained. Output a section "
           "exactly like:\n"
           "SONIC STEPS:\n"
           "1. <step title>\n"
           "   SPEC: <exact files, tables, commands>\n"
           "   DONE WHEN: <mechanical check>\n"
           "(up to %d steps, sharpest order first)" % (JOB_SIZING_RUBRIC, MAX_SONIC_STEPS))
    context = ("TASK #%d: %s\nNOTES:\n%s"
               % (t["id"], t["title"], t["notes"][:3000] or "(none)"))
    constraints = ("Findings only -- no direct messages to Brian. Flag "
                   "anything needing Brian's call with a line exactly like: "
                   "PENDING BRIAN CALL: <the question>. Don't decide it.")
    return summary, ask, context, constraints


def hard_tasks(tasks):
    """Classify tasks; return [(task, why)] for the hard ones, priority first.
    Tasks arrive priority-sorted from get_routable_tasks; keep that order."""
    hard = []
    for t in tasks:
        if (t.get("priority") or "").strip().lower() in ("high", "critical", "urgent"):
            hard.append((t, "high-priority open task — forced to deep tier"))
            continue
        target, why = classify(t["title"] + " " + t["notes"], None)
        if target == "v4pro":
            hard.append((t, why))
        else:
            print("task #%d -> sonic (%s) — not hard" % (t["id"], why))
    return hard


def route_hard_tasks(tasks, dry_run=False):
    queued = 0
    queued_ids = set()
    for t, why in hard_tasks(tasks):
        if queued >= MAX_TASK_HANDOFFS_PER_TICK:
            break
        if task_handed_off_recently(t["id"]):
            print("task #%d already handed off recently — skip" % t["id"])
            continue
        summary, ask, context, constraints = build_decomposition_prompt(t)
        if queue_handoff(summary, ask, "hard-task", context, constraints,
                         dry_run=dry_run):
            queued += 1
            queued_ids.add(t["id"])
    return queued, queued_ids


def extract_pending_calls(result_text):
    calls = []
    for m in PENDING_RE.finditer(result_text or ""):
        c = m.group(1).strip()
        if c and c not in calls:
            calls.append(c)
    return calls


def extract_sonic_steps(result_text):
    m = STEPS_HEADER_RE.search(result_text or "")
    if not m:
        return []
    body = (result_text or "")[m.end():]
    parts = re.split(r"(?m)^\s*\d+\.\s*", body)
    steps = []
    for text in parts[1:]:
        text = text.strip()
        if not text:
            continue
        title = text.split("\n")[0].strip().rstrip("*").strip()[:120]
        if title:
            steps.append({"title": title, "spec": text[:3000]})
        if len(steps) >= MAX_SONIC_STEPS:
            break
    return steps


def parent_task_id(summary):
    m = PARENT_TASK_RE.match(summary or "")
    return int(m.group(1)) if m else None


def like_escape(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def harness_job_exists(step_title):
    n = query("SELECT count(*) FROM successbrian_os.harness_jobs "
              "WHERE title = %s AND source = 'v4pro-decomposition' "
              "AND status NOT IN ('done','cancelled')" % pq(step_title[:200]))
    return n.strip().isdigit() and int(n) > 0


def harness_priority(parent_id):
    p = query("SELECT priority FROM successbrian_os.tasks WHERE id = %d" % parent_id)
    p = p.strip().lower()
    return {"critical": 2, "urgent": 2, "high": 3}.get(p, 5)


def create_harness_job(parent_id, parent_summary, step, dry_run=False,
                      decomposer="DeepSeek V4 Pro",
                      source="v4pro-decomposition", dedup_key=None):
    title = step["title"][:200]
    spec = ("# %s\n\nDecomposed by %s from hard task #%d (%s).\n"
            "Sized for Sonic (local Qwen3.6-35B-A3B) per knowledge/JOB-SIZING.md; "
            "the harness executes autonomously — this spec is self-contained.\n\n"
            "## Spec\n%s\n\n## Rules\n"
            "- knowledge/CODE-STANDARDS.md, knowledge/JOB-SIZING.md.\n"
            "- Zero Muse tokens; Sonic only."
            % (title, decomposer, parent_id, parent_summary[:80], step["spec"]))
    if dry_run:
        print("DRY-RUN would order harness job: %s" % title[:90])
        return True
    sql = ("INSERT INTO successbrian_os.harness_jobs "
           "(ordered_by, title, spec, priority, source, difficulty, dedup_key) "
           "VALUES ('altair', %s, %s, %d, %s, 'easy', %s);"
           % (pq(title), pq(spec), harness_priority(parent_id), pq(source),
              pq(dedup_key) if dedup_key else "NULL"))
    ok = exec_sql(sql)
    print(("ordered harness job" if ok else "harness job FAILED") + ": %s" % title[:80])
    return ok


def sonic_available():
    """Is the local Sonic model up? Free, so no balance check needed."""
    try:
        req = urllib.request.Request(SONIC_HEALTH_URL)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def call_sonic(prompt):
    """Ask Sonic (local, free) for a decomposition. OpenAI-compatible API."""
    body = json.dumps({
        "messages": [
            {"role": "system",
             "content": "You are a task decomposer for Brian's agent fleet. "
                        "Be concrete, decisive, and brief."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        SONIC_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=SONIC_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def task_sonic_decomposed_recently(task_id):
    n = query(
        "SELECT count(*) FROM successbrian_os.harness_jobs "
        "WHERE dedup_key = 'decompose-task-%d' "
        "AND created_at > now() - interval '%d days'"
        % (task_id, SONIC_DEDUPE_DAYS))
    return n.strip().isdigit() and int(n) > 0


def sonic_decompose_tasks(tasks, max_n, dry_run=False, skip_ids=None):
    """Dry-mode doctrine (Brian 2026-10-16): decompose hard tasks into
    Sonic-sized harness jobs using Sonic himself — free and local, so the
    queue keeps growing through dry days. Returns (decomposed_count)."""
    skip_ids = skip_ids or set()
    if not sonic_available():
        print("sonic not available — cannot build local queue this tick")
        return 0
    decomposed = 0
    for t, why in hard_tasks(tasks):
        if decomposed >= max_n:
            break
        if t["id"] in skip_ids:
            continue
        if task_sonic_decomposed_recently(t["id"]):
            print("task #%d already Sonic-decomposed recently — skip" % t["id"])
            continue
        summary, ask, context, constraints = build_decomposition_prompt(t)
        prompt = ("TASK: %s\nYOUR ASSIGNMENT: %s\n\nCONTEXT:\n%s\n\n"
                  "CONSTRAINTS:\n%s" % (summary, ask, context, constraints))
        if dry_run:
            print("DRY-RUN would Sonic-decompose task #%d: %s"
                  % (t["id"], t["title"][:80]))
            decomposed += 1
            continue
        try:
            result = call_sonic(prompt)
        except Exception as e:
            print("task #%d Sonic decomposition failed: %s"
                  % (t["id"], str(e)[:150]))
            continue
        steps = extract_sonic_steps(result)
        if not steps:
            print("task #%d: Sonic returned no SONIC STEPS — skip" % t["id"])
            continue
        made = 0
        for step in steps:
            if create_harness_job(
                    t["id"], summary, step, dry_run,
                    decomposer="Sonic (local, dry-mode)",
                    source="sonic-decomposition",
                    dedup_key="decompose-task-%d" % t["id"]):
                made += 1
        print("task #%d: Sonic decomposed into %d harness job(s)" % (t["id"], made))
        if made:
            decomposed += 1
    return decomposed




# ---- Atlas research queue -> V4 Pro (Brian 2026-10-17) ----
RESEARCH_PER_TICK = 5  # Brian 2026-10-17: not worried about V4 burn - use it
RESEARCH_COOLDOWN_DAYS = 7

def get_research_items():
    """Atlas nodes with status=researching not handed off in cooldown."""
    rows = query(
        "SELECT node_key, name FROM atlas.nodes "
        "WHERE status = 'researching' ORDER BY updated_at LIMIT 25")
    items = []
    for ln in rows.split("\n"):
        parts = ln.split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        nk = parts[0].strip()
        recent = query(
            "SELECT count(*) FROM successbrian_os.v4pro_handoffs "
            "WHERE task_summary LIKE '%%' || %s || '%%' "
            "AND created_at > NOW() - INTERVAL '%d days'"
            % (pq("Atlas research: " + nk), RESEARCH_COOLDOWN_DAYS))
        if recent.strip().isdigit() and int(recent) > 0:
            continue
        det = query(
            "SELECT left(details::text, 1500), left(coalesce(summary,''), 400) "
            "FROM atlas.nodes WHERE node_key = %s" % pq(nk))
        dparts = det.split("\t")
        items.append({"key": nk, "name": parts[1].strip(),
                      "details": dparts[0] if dparts else "",
                      "summary": dparts[1] if len(dparts) > 1 else ""})
        if len(items) >= RESEARCH_PER_TICK:
            break
    return items

def research_context(item):
    edges = query(
        "SELECT e.edge_type, n.node_key, n.name, left(n.summary, 160) "
        "FROM atlas.edges e JOIN atlas.nodes n ON "
        "((e.from_node = %s AND e.to_node = n.node_key) OR "
        " (e.to_node = %s AND e.from_node = n.node_key)) "
        "LIMIT 20" % (pq(item["key"]), pq(item["key"])))
    docs = query(
        "SELECT n.node_key, left(n.summary, 200) FROM atlas.edges e "
        "JOIN atlas.nodes n ON e.from_node = n.node_key "
        "WHERE e.to_node = %s AND e.edge_type = 'documents' "
        "AND n.node_type = 'doc' LIMIT 5" % pq(item["key"]))
    return ("ATLAS ITEM: %s (%s)\nSUMMARY: %s\nDETAILS: %s\n\n"
            "CONNECTED NODES:\n%s\n\nLINKED DOCS:\n%s"
            % (item["key"], item["name"], item["summary"] or "(none)",
               (item["details"] or "(none)")[:1500],
               edges or "(none)", docs or "(none)"))

def queue_atlas_research(dry_run=False):
    items = get_research_items()
    if not items:
        print("atlas research: queue empty or all in cooldown")
        return 0
    n = 0
    for item in items:
        summary = "Atlas research: " + item["key"]
        ask = ("Research this Atlas planning item. You are the research tier; "
               "reason over the Atlas context below plus your own knowledge. "
               "Output EXACTLY these sections:\n\n"
               "FINDINGS:\n1. <finding>\n2. <finding>\n...\n\n"
               "PROPOSED PLANS:\n1. <plan title> | <one-line rationale>\n...\n\n"
               "DATA GAPS:\n- <what web/field data would sharpen this>\n...\n\n"
               "Keep findings concrete and tied to Brian's ecosystem "
               "(self-hosted, free-first, his hardware). Flag anything needing "
               "Brian's call as: PENDING BRIAN CALL: <question>.")
        context = research_context(item)
        constraints = ("Findings only -- no direct messages to Brian. "
                       "Proposed plans are PROPOSALS for his approval, not decisions.")
        if queue_handoff(summary, ask, "atlas-research", context, constraints,
                         dry_run=dry_run):
            n += 1
    print("queued %d atlas research handoff(s)" % n)
    return n

def parse_sections(text):
    out = {"findings": [], "plans": [], "gaps": []}
    cur = None
    for ln in (text or "").split("\n"):
        t = ln.strip()
        u = t.upper()
        if u.startswith("FINDINGS"):
            cur = "findings"; continue
        if u.startswith("PROPOSED PLANS"):
            cur = "plans"; continue
        if u.startswith("DATA GAPS"):
            cur = "gaps"; continue
        if not cur or not t:
            continue
        t = re.sub(r"^[\d\-\*\.]+\s*", "", t)
        if t:
            out[cur].append(t[:500])
    return out

def consume_research(rec, dry_run=False):
    """File V4 research: doc node with findings, plan proposals for Brian."""
    m = re.search(r"Atlas research:\s*(\S+)", rec["summary"])
    mc = re.search(r"AnythingLLM cleanup:\s*(.+)", rec["summary"])
    if m:
        nk = m.group(1)
        link_nk = nk
        doc_key = "doc:v4research-%s-%d" % (nk.replace(":", "-"), rec["id"])
        doc_name = "V4 research: " + nk
    elif mc:
        nk = mc.group(1).strip()
        link_nk = None
        doc_key = "doc:allm-cleanup-%d" % rec["id"]
        doc_name = "AnythingLLM cleanup assessment: " + nk
    else:
        return
    secs = parse_sections(rec["result"])
    if not secs["findings"] and not secs["plans"]:
        print("research handoff #%d: no parseable sections — skip" % rec["id"])
        return
    doc_key = doc_key
    body = "V4 Pro research on %s (handoff #%d).\n\nFINDINGS:\n%s\n\nDATA GAPS:\n%s" % (
        nk, rec["id"],
        "\n".join("%d. %s" % (i + 1, f) for i, f in enumerate(secs["findings"])) or "(none)",
        "\n".join("- " + g for g in secs["gaps"]) or "(none)")
    if not dry_run:
        exec_sql(
            "INSERT INTO atlas.nodes (node_key, node_type, name, status, summary, details) "
            "VALUES (%s, 'doc', %s, 'active', %s, %s) ON CONFLICT (node_key) DO NOTHING"
            % (pq(doc_key), pq(doc_name),
               pq("Lyra worker findings on " + nk),
               pq('{"researched_by": "v4pro", "handoff_id": %d, "kind": "%s"}'
                  % (rec["id"], rec["kind"]))))
        if link_nk:
            exec_sql(
                "INSERT INTO atlas.edges (from_node, to_node, edge_type, notes) "
                "VALUES (%s, %s, 'documents', 'Lyra worker research findings') "
                "ON CONFLICT DO NOTHING" % (pq(doc_key), pq(link_nk)))
    print("research handoff #%d: doc node %s (%d findings)"
          % (rec["id"], doc_key, len(secs["findings"])))
    for p in secs["plans"]:
        title = p.split("|")[0].strip()[:80]
        rationale = p.split("|")[1].strip()[:200] if "|" in p else ""
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
        plan_key = "plan:v4prop-%s-%d" % (slug, rec["id"])
        dup = query(
            "SELECT count(*) FROM atlas.nodes WHERE node_key = %s" % pq(plan_key))
        if dup.strip() == "0" and not dry_run:
            exec_sql(
                "INSERT INTO atlas.nodes (node_key, node_type, name, status, summary, details) "
                "VALUES (%s, 'plan', %s, 'planned', %s, %s)"
                % (pq(plan_key), pq(title),
                   pq(rationale or "Proposed by V4 Pro research"),
                   pq('{"proposed": true, "proposed_by": "v4pro", '
                      '"needs_brian_approval": true, "handoff_id": %d, '
                      '"research_item": "%s"}' % (rec["id"], nk))))
            exec_sql(
                "INSERT INTO atlas.edges (from_node, to_node, edge_type, notes) "
                "VALUES (%s, %s, 'about', 'proposed from V4 research on %s') "
                "ON CONFLICT DO NOTHING" % (pq(plan_key), pq(nk), nk))
            print("research handoff #%d: proposed plan %s" % (rec["id"], plan_key))


def open_question_count():
    n = query("SELECT count(*) FROM successbrian_os.pending_questions "
              "WHERE status = 'open'")
    return int(n) if n.strip().isdigit() else 0


def file_pending_question(question, handoff_id, summary, dry_run=False):
    if dry_run:
        print("DRY-RUN would file pending question: %s" % question[:100])
        return True
    sql = ("INSERT INTO successbrian_os.pending_questions "
           "(asked_by, question, context, priority) VALUES (%s, %s, %s, 3);"
           % (pq("altair"), pq(question),
              pq("From V4 Pro deep pass #%d (%s)" % (handoff_id, summary[:100]))))
    return exec_sql(sql)


def fetch_result(hid):
    row = query("SELECT task_kind, task_summary, v4pro_result "
                "FROM successbrian_os.v4pro_handoffs WHERE id = %d" % hid)
    parts = row.split("\t")
    if len(parts) < 2:
        return None
    return {"id": hid, "kind": parts[0], "summary": parts[1],
            "result": "\t".join(parts[2:])}




VALID_FIX_STATUSES = {"planned", "active", "inactive", "researching", "closed"}

def apply_health_fix(line):
    """Apply one HEALTH_FIX line. Returns (ok, note). Whitelist only."""
    try:
        _, rest = line.split("HEALTH_FIX:", 1)
        ftype, args = [x.strip() for x in rest.split("|", 1)]
    except ValueError:
        return False, "malformed"
    ftype = ftype.upper()
    try:
        if ftype == "DROP_DEAD_EDGE":
            frm, to, et = [x.strip() for x in args.split(",")]
            exists = query(
                "SELECT 1 FROM atlas.nodes WHERE node_key = %s LIMIT 1;"
                % pq(to)).strip()
            if exists:
                return False, "target exists — not dead, skipped"
            exec_sql(
                "DELETE FROM atlas.edges WHERE from_node = %s AND to_node = %s "
                "AND edge_type = %s;" % (pq(frm), pq(to), pq(et)))
            return True, "dropped dead edge %s->%s" % (frm, to)
        if ftype == "SUPERSEDE_LEARNING":
            drop, keep = [x.strip() for x in args.split(",")]
            if not (drop.isdigit() and keep.isdigit()) or drop == keep:
                return False, "bad ids"
            ok = query(
                "SELECT count(*) FROM successbrian_os.v4pro_worker_learnings "
                "WHERE id IN (%s, %s) AND status = 'active';" % (drop, keep)
                ).strip()
            if ok != "2":
                return False, "ids not both active"
            exec_sql(
                "UPDATE successbrian_os.v4pro_worker_learnings "
                "SET status = 'superseded', superseded_by = %s WHERE id = %s;"
                % (keep, drop))
            return True, "learning #%s superseded by #%s" % (drop, keep)
        if ftype == "SET_NODE_STATUS":
            nk, ns = [x.strip() for x in args.split(",")]
            if ns not in VALID_FIX_STATUSES:
                return False, "invalid status"
            exists = query(
                "SELECT 1 FROM atlas.nodes WHERE node_key = %s LIMIT 1;"
                % pq(nk)).strip()
            if not exists:
                return False, "node not found"
            exec_sql(
                "UPDATE atlas.nodes SET status = %s, updated_at = now() "
                "WHERE node_key = %s;" % (pq(ns), pq(nk)))
            return True, "%s -> %s" % (nk, ns)
        if ftype == "WIRE_ORPHAN":
            frm, to, et = [x.strip() for x in args.split(",")]
            both = query(
                "SELECT count(*) FROM atlas.nodes WHERE node_key IN (%s, %s);"
                % (pq(frm), pq(to))).strip()
            if both != "2":
                return False, "node(s) missing"
            dup = query(
                "SELECT 1 FROM atlas.edges WHERE from_node = %s AND to_node = %s "
                "AND edge_type = %s LIMIT 1;" % (pq(frm), pq(to), pq(et))).strip()
            if dup:
                return False, "edge already exists"
            exec_sql(
                "INSERT INTO atlas.edges (from_node, to_node, edge_type, notes) "
                "VALUES (%s, %s, %s, 'wired by lyra health worker');"
                % (pq(frm), pq(to), pq(et)))
            return True, "wired %s->%s (%s)" % (frm, to, et)
        return False, "type not whitelisted"
    except Exception as e:
        return False, "error: %s" % str(e)[:100]


def consume_health(c, dry_run=False):
    """Apply HEALTH_FIX lines from an ecosystem-health handoff result."""
    text = c.get("result") or ""
    applied, skipped = [], []
    for ln in text.split("\n"):
        if "HEALTH_FIX:" not in ln:
            continue
        if dry_run:
            skipped.append("dry-run: " + ln.strip()[:80])
            continue
        ok, note = apply_health_fix(ln.strip())
        (applied if ok else skipped).append(note)
    if applied or skipped:
        print("health #%d: %d fix(es) applied, %d skipped"
              % (c["id"], len(applied), len(skipped)))
        for n in (applied + ["SKIP: " + x for x in skipped])[:10]:
            print("  -", n[:120])
    return applied, skipped


def consume_completed(dry_run=False):
    """Read newly completed handoffs; file Brian-calls; return digest."""
    state = load_consume_state()
    last = state.get("last_consumed_id")
    max_id_raw = query("SELECT COALESCE(max(id),0) FROM successbrian_os.v4pro_handoffs")
    max_id = int(max_id_raw) if max_id_raw.strip().isdigit() else 0
    if last is None:
        state["last_consumed_id"] = max_id
        if not dry_run:
            save_consume_state(state)
        print("consume state initialized at handoff #%d" % max_id)
        return ""
    id_rows = query(
        "SELECT id FROM successbrian_os.v4pro_handoffs "
        "WHERE status = 'done' AND id > %d ORDER BY id" % int(last))
    ids = [int(x) for x in id_rows.split() if x.strip().isdigit()]
    consumed = []
    pending_calls = []
    for hid in ids:
        rec = fetch_result(hid)
        if not rec:
            continue
        consumed.append(rec)
        if rec["kind"] in ("atlas-research", "anythingllm-cleanup"):
            continue  # Lyra worker files its own Brian questions w/ priority
        for c in extract_pending_calls(rec["result"]):
            pending_calls.append((hid, rec["summary"], c))
    if consumed:
        new_last = max(c["id"] for c in consumed)
        if pending_calls:
            if open_question_count() == 0:
                hid, summary, call = pending_calls[0]
                if file_pending_question(call, hid, summary, dry_run):
                    print("filed pending question from handoff #%d" % hid)
            else:
                print("%d pending call(s) found but a question is already open "
                      "— skip filing" % len(pending_calls))
        state["last_consumed_id"] = new_last
        if not dry_run:
            save_consume_state(state)
        print("consumed %d completed handoff(s)" % len(consumed))
    for c in consumed:
        if c["kind"] == "ecosystem-health":
            consume_health(c, dry_run)
            consume_research(c, dry_run)  # files findings + plan proposals too
            continue
        if c["kind"] in ("atlas-research", "anythingllm-cleanup"):
            consume_research(c, dry_run)
            continue
        if c["kind"] != "hard-task":
            continue
        pid = parent_task_id(c["summary"])
        if not pid:
            continue
        for step in extract_sonic_steps(c["result"]):
            if harness_job_exists(step["title"]):
                print("harness job already exists — skip: %s" % step["title"][:60])
                continue
            create_harness_job(pid, c["summary"], step, dry_run)
    digest = ""
    for c in consumed:
        digest += "- #%d %s: %s\n" % (c["id"], c["summary"][:60],
                                      (c["result"] or "")[:800].replace("\n", " "))
    return digest[:2000]


def queue_deep_pass(tasks, prev_digest, dry_run=False):
    pending = query(
        "SELECT count(*) FROM successbrian_os.v4pro_handoffs "
        "WHERE task_kind = 'deep-analysis' AND status IN ('queued','working')")
    if pending.strip().isdigit() and int(pending) > 0:
        print("deep pass already queued/working — skip")
        return False
    try:
        hb = open(HEARTBEAT_MD).read()
    except OSError:
        hb = "(heartbeat checklist unavailable)"
    bridge = query(
        "SELECT id || ': ' || left(message, 200) FROM public.knowledge_bridge "
        "WHERE target_agent='altair' AND read_at IS NULL AND urgency='high' "
        "ORDER BY id DESC LIMIT 3")
    summary = "Altair heartbeat deep-reasoning pass"
    ask = ("Run Altair's heartbeat deep-reasoning pass. You are the deep tier; "
           "Altair (Sonic) handles routine checks locally. Do the hard thinking: "
           "work through the deep items in his heartbeat checklist against the "
           "current open work below. Identify root causes, tradeoffs, and the "
           "sharpest 2-3 recommendations. Be concrete and brief. "
           "Flag anything needing Brian's call with a line exactly like: "
           "PENDING BRIAN CALL: <the question>.")
    context = ("HEARTBEAT CHECKLIST:\n" + hb[:6000] +
               "\n\nPREVIOUS PASS FINDINGS (already consumed — build on these, "
               "don't repeat):\n" + (prev_digest or "(none yet)") +
               "\n\nOPEN not-90%-sure TASKS:\n" + format_unsure_context(tasks) +
               "\n\nOPEN ALTAIR TASKS (routed individually this tick where hard):\n" +
               "\n".join("%d [%s/%s]: %s" % (t["id"], t.get("priority", "?"),
                                             t.get("status", "?"),
                                             t["title"][:100])
                         for t in tasks) +
               "\n\nUNREAD HIGH-URGENCY BRIDGE FOR ALTAIR:\n" + (bridge or "(none)"))
    constraints = ("Findings only -- no direct messages to Brian. "
                   "Flag anything needing Brian's call as: "
                   "PENDING BRIAN CALL: <question>. Don't decide it.")
    return queue_handoff(summary, ask, "deep-analysis", context, constraints,
                         dry_run=dry_run)






CLEANUP_PER_TICK = 2


HEALTH_PER_TICK = 2




def load_scopes(worker_kind):
    """Active scopes for a worker kind, from Postgres. Data, not code."""
    rows = query(
        "SELECT scope_key, brief, coalesce(scope_sql,''), "
        "coalesce(context_extra,'') FROM successbrian_os.worker_scopes "
        "WHERE worker_kind = %s AND active ORDER BY scope_key;"
        % pq(worker_kind))
    out = []
    for ln in rows.split("\n"):
        parts = ln.split("\t")
        if len(parts) >= 2 and parts[0].strip():
            out.append((parts[0].strip(), parts[1].strip(),
                        parts[2].strip() if len(parts) > 2 else "",
                        parts[3].strip() if len(parts) > 3 else ""))
    return out


def scope_recently_queued(summary_frag, days=7):
    r = query(
        "SELECT 1 FROM successbrian_os.v4pro_handoffs "
        "WHERE task_summary LIKE %s AND created_at > NOW() - INTERVAL '%d days' "
        "LIMIT 1;" % (pq("%" + summary_frag + "%"), days)).strip()
    return bool(r)


def queue_health_assessment(dry_run=False):
    n = 0
    for scope_key, brief, sql, _extra in load_scopes("ecosystem-health"):
        if n >= HEALTH_PER_TICK:
            break
        if scope_recently_queued("Ecosystem health: " + scope_key):
            continue
        data = query(sql) if sql else ""
        if queue_handoff("Ecosystem health: " + scope_key,
                         "HEALTH SWEEP — fix what is safe, propose the rest. "
                         "Output HEALTH_FIX lines for whitelisted fixes, plus "
                         "FINDINGS / PROPOSED PLANS / DATA GAPS.",
                         "ecosystem-health",
                         "SCOPE: %s\n\n%s\n\nLIVE DATA:\n%s"
                         % (scope_key, brief, data[:3000]),
                         "Fix safe items via HEALTH_FIX lines; propose the rest.",
                         dry_run=dry_run):
            n += 1
    if n:
        print("queued %d ecosystem-health handoff(s)" % n)
    return n


def queue_cleanup_assessment(dry_run=False):
    """Queue AnythingLLM cleanup assessment handoffs (assess + propose only).
    Execution is separately gated on Brian's approval."""
    n = 0
    for scope_key, brief, _sql, extra in load_scopes("anythingllm-cleanup"):
        if n >= CLEANUP_PER_TICK:
            break
        if scope_recently_queued("AnythingLLM cleanup: " + scope_key):
            continue
        summary = "AnythingLLM cleanup: " + scope_key
        ask = ("Assess and propose. %s. Work the stages, run the board, "
               "escalate decisions. Output FINDINGS / PROPOSED PLANS / "
               "DATA GAPS. Propose only — never execute deletions." % brief)
        context = ("SCOPE: %s\n%s\n\n%s" % (scope_key, brief, extra))
        if queue_handoff(summary, ask, "anythingllm-cleanup", context,
                         "Assess and propose ONLY. No deletions, moves, or "
                         "re-embeds without Brian's explicit approval.",
                         dry_run=dry_run):
            n += 1
    if n:
        print("queued %d anythingllm-cleanup handoff(s)" % n)
    return n


def queue_monthly_eval(dry_run=False):
    """First tick of each month: re-queue canned eval items (drift watch)."""
    marker = query(
        "SELECT value FROM successbrian_os.chain_controls "
        "WHERE key = 'lyra_eval_month';").strip()
    import datetime
    this_month = datetime.datetime.now().strftime("%Y-%m")
    if marker == this_month:
        return 0
    n = 0
    for scope_key, brief, _sql, extra in load_scopes("atlas-research"):
        if not scope_key.startswith("eval-"):
            continue
        if scope_recently_queued(scope_key, days=28):
            continue
        node_key = extra.replace("EVAL ITEM:", "").strip() if extra else scope_key
        det = query(
            "SELECT left(details::text, 800), left(coalesce(summary,''), 300) "
            "FROM atlas.nodes WHERE node_key = %s" % pq(node_key))
        if queue_handoff("Atlas research: " + node_key + " [eval-monthly]",
                         "EVAL RUN — answer the research as normal. Output "
                         "FINDINGS / PROPOSED PLANS / DATA GAPS exactly. " + brief,
                         "atlas-research",
                         "EVAL ITEM (drift watch).\n" + det,
                         "Findings only.", dry_run=dry_run):
            n += 1
    if n and not dry_run:
        exec_sql(
            "UPDATE successbrian_os.chain_controls SET value = '%s', "
            "updated_at = now() WHERE key = 'lyra_eval_month';" % this_month)
    if n:
        print("queued %d monthly eval handoff(s)" % n)
    return n


def rethink_answered(dry_run=False):
    """Brian answered a Lyra worker's gated question — re-think the research
    with his decision folded in, then let the chain run again."""
    rows = query(
        "SELECT e.id, e.handoff_id, e.worker_kind, e.question, q.answer "
        "FROM successbrian_os.worker_escalations e "
        "JOIN successbrian_os.pending_questions q ON q.id = e.pq_id "
        "WHERE e.tier = 'brian' AND e.status = 'open' "
        "AND q.status = 'answered' AND q.answer IS NOT NULL")
    n = 0
    for ln in rows.split("\n"):
        parts = ln.split("\t")
        if len(parts) < 5:
            continue
        eid, hid, kind = parts[0].strip(), parts[1].strip(), parts[2].strip()
        question, answer = parts[3].strip(), parts[4].strip()
        if not eid.isdigit():
            continue
        # Storm guard: max 2 re-thinks per escalation per 7 days
        rc = query(
            "SELECT count(*) FROM successbrian_os.v4pro_handoffs "
            "WHERE task_summary LIKE '%re-think #' || %s || '%%' "
            "AND created_at > NOW() - INTERVAL '7 days'" % pq(eid))
        if rc.strip().isdigit() and int(rc.strip()) >= 2:
            print("re-think cap hit for escalation #%s — skip" % eid)
            continue
        # Recover the research item from the original handoff
        item = query(
            "SELECT task_summary, context, ask FROM successbrian_os.v4pro_handoffs "
            "WHERE id = %s" % hid)
        iparts = item.split("\t")
        summary = iparts[0].strip() if iparts else "Atlas research (re-think)"
        context = (iparts[1] if len(iparts) > 1 else "")
        ask = (iparts[2] if len(iparts) > 2 else "")
        new_context = ("BRIAN DECIDED (re-think with this as settled law):\n"
                       "Q: %s\nA: %s\n\nORIGINAL CONTEXT:\n%s"
                       % (question, answer, context))
        ok = queue_handoff(summary + " [re-think #%s]" % eid,
                           ask, "atlas-research", new_context,
                           "Findings only. Brian's decision above is settled — "
                           "build on it, don't relitigate it.",
                           dry_run=dry_run)
        if ok and not dry_run:
            exec_sql(
                "UPDATE successbrian_os.worker_escalations "
                "SET status = 'rethought', resolution = %s, resolved_at = now() "
                "WHERE id = %s" % (pq("Re-thought after Brian's answer"), eid))
            n += 1
    if n:
        print("re-think: re-queued %d research item(s) with Brian's decisions" % n)
    return n


def main():
    dry_run = "--dry-run" in sys.argv
    prev_digest = consume_completed(dry_run)
    avail = get_availability()
    dry = not avail.get("usable")
    tasks = get_unsure_tasks()
    open_tasks = get_routable_tasks({t["id"] for t in tasks})
    tasks = tasks + open_tasks
    if dry:
        # DRY MODE (Brian 2026-10-16): V4 has no value right now — do not
        # idle. Surge local queue-building so dry days are covered.
        print("v4pro not usable (%s) — DRY MODE: building Sonic queue"
              % avail.get("reason"))
        n = sonic_decompose_tasks(tasks, DRY_SONIC_DECOMPOSE_PER_TICK, dry_run)
        print("dry mode: Sonic decomposed %d task(s) into harness jobs" % n)
        return 0
    n, v4_ids = route_hard_tasks(tasks, dry_run)
    print("routed %d hard task(s) to v4pro" % n)
    # BUFFER (Brian 2026-10-16): even while funded, Sonic decomposes the
    # hard tasks V4 didn't take, so the queue grows under both regimes.
    b = sonic_decompose_tasks(tasks, BUFFER_SONIC_DECOMPOSE_PER_TICK,
                              dry_run, skip_ids=v4_ids)
    print("buffer: Sonic decomposed %d additional task(s)" % b)
    queue_deep_pass(tasks, prev_digest, dry_run)
    queue_atlas_research(dry_run)
    queue_cleanup_assessment(dry_run)
    queue_health_assessment(dry_run)
    queue_monthly_eval(dry_run)
    rethink_answered(dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
