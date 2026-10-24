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


def route_hard_tasks(tasks, dry_run=False):
    queued = 0
    for t in tasks:
        if queued >= MAX_TASK_HANDOFFS_PER_TICK:
            break
        if (t.get("priority") or "").strip().lower() in ("high", "critical", "urgent"):
            target, why = "v4pro", "high-priority open task — forced to deep tier"
        else:
            target, why = classify(t["title"] + " " + t["notes"], None)
        if target != "v4pro":
            print("task #%d -> sonic (%s) — skip" % (t["id"], why))
            continue
        if task_handed_off_recently(t["id"]):
            print("task #%d already handed off recently — skip" % t["id"])
            continue
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
        if queue_handoff(summary, ask, "hard-task", context, constraints,
                         dry_run=dry_run):
            queued += 1
    return queued


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


def create_harness_job(parent_id, parent_summary, step, dry_run=False):
    title = step["title"][:200]
    spec = ("# %s\n\nDecomposed by DeepSeek V4 Pro from hard task #%d (%s).\n"
            "Sized for Sonic (local Qwen3.6-35B-A3B) per knowledge/JOB-SIZING.md; "
            "the harness executes autonomously — this spec is self-contained.\n\n"
            "## Spec\n%s\n\n## Rules\n"
            "- knowledge/CODE-STANDARDS.md, knowledge/JOB-SIZING.md.\n"
            "- Zero Muse tokens; Sonic only."
            % (title, parent_id, parent_summary[:80], step["spec"]))
    if dry_run:
        print("DRY-RUN would order harness job: %s" % title[:90])
        return True
    sql = ("INSERT INTO successbrian_os.harness_jobs "
           "(ordered_by, title, spec, priority, source, difficulty) "
           "VALUES ('altair', %s, %s, %d, 'v4pro-decomposition', 'easy');"
           % (pq(title), pq(spec), harness_priority(parent_id)))
    ok = exec_sql(sql)
    print(("ordered harness job" if ok else "harness job FAILED") + ": %s" % title[:80])
    return ok


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


def main():
    dry_run = "--dry-run" in sys.argv
    prev_digest = consume_completed(dry_run)
    avail = get_availability()
    if not avail.get("usable"):
        print("v4pro not usable (%s) — consume-only tick" % avail.get("reason"))
        return 0
    tasks = get_unsure_tasks()
    open_tasks = get_routable_tasks({t["id"] for t in tasks})
    tasks = tasks + open_tasks
    n = route_hard_tasks(tasks, dry_run)
    print("routed %d hard task(s) to v4pro" % n)
    queue_deep_pass(tasks, prev_digest, dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
