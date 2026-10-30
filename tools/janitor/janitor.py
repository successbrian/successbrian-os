#!/usr/bin/env python3
"""janitor.py — the entropy-reduction loop, coded into successbrian-os.

Brian's law (2026-10-13): work is never invented. When known queues deplete,
the system turns to data chaos: re-read, dedupe, organize, clean. The cleanup
discovers new real work, which feeds the queues again. Build -> read -> cleanup.

Runs every 6h. Deterministic, zero tokens. Judgment-call findings become
tasks for Altair (he owns the goal<->AnythingLLM re-read and has the library
access); the heartbeat decomposition routes them. Nothing here writes code —
the harness stays a coding harness.

Checks:
1. stale_harness  — queued harness jobs untouched > 48h -> triage task
2. dup_tasks      — open tasks with identical normalized titles -> merge task
3. orphan_tasks   — tasks pointing at missing goals/projects -> cleanup task
4. unread_screams — important/critical bridge msgs unread > 24h -> metric only
5. goal_reread    — at most one open "re-read goals vs AnythingLLM" task

Every check writes data_chaos metrics (scoreboard trends down = winning).
Findings dedupe on (kind, ref_ids) while open — never re-file the same one.
Max 3 new tasks per run (no flooding).
"""
import re, subprocess, sys
from datetime import datetime, timezone

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-t", "-A", "-F", "\x1f"]
MAX_NEW_TASKS = 3
STALE_HOURS = 48

def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"PSQL ERROR: {r.stderr.strip()}", file=sys.stderr)
        return []
    return [ln.split("\x1f") for ln in r.stdout.strip().split("\n") if ln.strip()]

def scalar(sql, default="0"):
    rows = q(sql)
    return rows[0][0] if rows and rows[0][0] not in ("", None) else default

# SBOS common routines - Batch C migration (2026-10-27).
import os as _os_c, sys as _sys_c
_sys_c.path.insert(0, _os_c.path.join(_os_c.path.dirname(_os_c.path.abspath(__file__)), ".."))
import sbos_common  # noqa: E402


def esc(s):
    # Batch C migration (2026-10-27): delegates to sbos_common.esc -
    # the one SQL-escape definition for the ecosystem.
    return sbos_common.esc(s)

def finding_open(kind, ref_ids):
    return bool(q(f"SELECT 1 FROM successbrian_os.janitor_findings "
                  f"WHERE kind='{kind}' AND ref_ids='{esc(ref_ids)}' "
                  f"AND status='open' LIMIT 1"))

def record_finding(kind, ref_table, ref_ids, summary, task_id=None):
    q(f"INSERT INTO successbrian_os.janitor_findings "
      f"(kind, ref_table, ref_ids, summary, status, job_id) VALUES "
      f"('{kind}','{ref_table}','{esc(ref_ids)}','{esc(summary)}','open',"
      f"{task_id if task_id else 'NULL'})")

def file_task(title, notes):
    tid = scalar(f"INSERT INTO successbrian_os.tasks "
                 f"(assigned_to, assigned_by, title, task_notes, priority, status) "
                 f"VALUES ('altair','janitor','{esc(title)}','{esc(notes)}',"
                 f"'normal','pending') RETURNING id")
    return int(tid) if tid.isdigit() else None

def chaos(domain, metric, value):
    q(f"INSERT INTO successbrian_os.data_chaos (domain, metric, value) "
      f"VALUES ('{domain}','{metric}',{int(value)})")

def norm_title(t):
    return re.sub(r"\s+", " ", (t or "").lower().strip())

def main():
    now = datetime.now(timezone.utc).isoformat()
    new_tasks = 0

    # 1. stale harness jobs
    stale = q(f"SELECT id, left(title,80) FROM successbrian_os.harness_jobs "
              f"WHERE status='queued' AND created_at < now() - interval '{STALE_HOURS} hours' "
              f"ORDER BY id LIMIT 10")
    chaos("harness", "stale_queued", len(stale))
    for jid, title in stale:
        if new_tasks >= MAX_NEW_TASKS: break
        if finding_open("stale_harness", jid): continue
        tid = file_task(
            f"Janitor: triage stale harness job #{jid}",
            f"Queued > {STALE_HOURS}h untouched ('{title}'). Still needed? "
            f"If yes, bump priority; if no, cancel it. Do not let it rot.")
        if tid:
            record_finding("stale_harness", "harness_jobs", jid,
                           f"stale queued job #{jid}: {title}", tid)
            new_tasks += 1
            print(f"task {tid}: triage stale harness job #{jid}")

    # 2. duplicate open tasks
    dups = q("SELECT lower(regexp_replace(title, '\\s+', ' ', 'g')), "
             "array_agg(id::text), count(*) FROM successbrian_os.tasks "
             "WHERE status NOT IN ('completed','cancelled') "
             "GROUP BY 1 HAVING count(*) > 1 LIMIT 10")
    chaos("tasks", "dup_groups", len(dups))
    for title, ids, n in dups:
        ids = ids.strip("{}")
        if new_tasks >= MAX_NEW_TASKS: break
        if finding_open("dup_tasks", ids): continue
        tid = file_task(
            "Janitor: merge duplicate tasks",
            f"{n} open tasks share the title '{title}' (ids {ids}). "
            f"Read them, merge into one, cancel the rest. Keep the history.")
        if tid:
            record_finding("dup_tasks", "tasks", ids,
                           f"{n}x duplicate title: {title}", tid)
            new_tasks += 1
            print(f"task {tid}: merge {n} dup tasks ({ids})")

    # 3. orphan tasks (goal/project pointing nowhere)
    orphans = q("SELECT t.id, left(t.title,60) FROM successbrian_os.tasks t "
                "LEFT JOIN public.goals g ON g.id = t.goal_id "
                "LEFT JOIN public.projects p ON p.id = t.project_id "
                "WHERE t.status NOT IN ('completed','cancelled') "
                "AND ((t.goal_id IS NOT NULL AND g.id IS NULL) "
                "OR (t.project_id IS NOT NULL AND p.id IS NULL)) LIMIT 10")
    chaos("tasks", "orphans", len(orphans))
    for tid0, title in orphans:
        if new_tasks >= MAX_NEW_TASKS: break
        if finding_open("orphan_tasks", tid0): continue
        tid = file_task(
            f"Janitor: repair orphan task #{tid0}",
            f"Task '{title}' (#{tid0}) points at a goal/project that no longer "
            f"exists. Re-link it to the right one or cancel it.")
        if tid:
            record_finding("orphan_tasks", "tasks", tid0,
                           f"orphan task #{tid0}: {title}", tid)
            new_tasks += 1
            print(f"task {tid}: repair orphan #{tid0}")

    # 4. unread screams (metric only — no auto task, avoids scream loops)
    unread = int(scalar(
        "SELECT count(*) FROM altair.knowledge_bridge "
        "WHERE urgency IN ('important','critical') AND read_at IS NULL "
        "AND created_at < now() - interval '24 hours'"))
    chaos("bridge", "unread_screams", unread)
    if unread:
        print(f"unread screams > 24h: {unread} (metric only)")

    # 5. goal re-read vs AnythingLLM (at most one open)
    open_rr = int(scalar(
        "SELECT count(*) FROM successbrian_os.tasks "
        "WHERE title LIKE 'Janitor: re-read goals vs AnythingLLM%' "
        "AND status NOT IN ('completed','cancelled')"))
    if open_rr == 0 and new_tasks < MAX_NEW_TASKS:
        tid = file_task(
            "Janitor: re-read goals vs AnythingLLM",
            "Re-read the open goals and match them against the docs in "
            "AnythingLLM. File new tasks for gaps, contradictions, or goals "
            "with no supporting knowledge. This is the re-read leg of "
            "build -> read -> cleanup: discoveries here become real work.")
        if tid:
            record_finding("goal_reread", "tasks", str(tid),
                           "periodic goal vs library re-read", tid)
            new_tasks += 1
            print(f"task {tid}: goal re-read vs AnythingLLM")
    elif open_rr:
        print(f"goal re-read already open ({open_rr}) — skipping")

    print(f"[{now}] janitor done: {new_tasks} new tasks filed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
