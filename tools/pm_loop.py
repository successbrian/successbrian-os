#!/usr/bin/env python3
"""pm_loop.py — the autonomous PM worker loop.

Brian 2026-10-15: successbrian-os PM is the master event/project/goals/tasks
system; build the closed loop — agents pull work from it on their own,
execute, and feed results back without being prompted.

Each run:
  1. CLAIM   — atomically claim open PM tasks / work-queue items (one winner).
  2. TRIAGE  — deterministic [auto:*] tasks run a handler; stale physical
               tasks get escalated as events (never auto-done).
  3. REPORT  — task rows updated, everything fed to ecosystem_events.

Handlers are explicit: a task runs a handler only when its title starts with
[auto:<name>]. No fuzzy guessing about what a task means.

Stdlib + psycopg2, zero AI tokens. Runs on k11 as successbrian via cron,
staggered off the other workers.
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

AUTO_RE = re.compile(r"^\[auto:(\w+)\]\s*(.*)$", re.DOTALL)
STALE_DAYS = 7
WORKER = "pm_loop"


def db():
    return psycopg2.connect(dbname="ecosystem_central", user="successbrian",
                            cursor_factory=RealDictCursor)


def feed(cur, event_type, title, detail=None, project_ref=None):
    cur.execute(
        """INSERT INTO successbrian_os.ecosystem_events
           (event_type, source_plugin, project_ref, title, detail)
           VALUES (%s, 'pm-system', %s, %s, %s)""",
        (event_type, project_ref, title, detail))


def stale_event_recent(cur, item_key):
    cur.execute(
        """SELECT 1 FROM successbrian_os.ecosystem_events
           WHERE event_type = 'task_stale' AND title LIKE %s
             AND event_at > now() - interval '7 days' LIMIT 1""",
        ("%" + item_key + "%",))
    return cur.fetchone() is not None


# ---- handlers: deterministic work the loop can do itself ----

def h_ping(task):
    return True, "pm_loop heartbeat ok"


def h_event(task):
    return True, "fed event: %s" % task["title"][:80]


def h_fleet_review(task):
    r = subprocess.run(
        ["/usr/bin/python3", "/home/dealsdesk/scripts/fleet_deploy_review.py"],
        capture_output=True, text=True, timeout=300)
    ok = r.returncode == 0
    return ok, (r.stdout.strip() or r.stderr.strip())[:500]


HANDLERS = {"ping": h_ping, "event": h_event, "fleet_review": h_fleet_review}


def claim_pm_tasks(cur):
    """Atomically claim open [auto:*] tasks. Returns claimed rows."""
    cur.execute(
        """UPDATE successbrian_os.tasks
           SET status = 'in_progress', updated_at = now()
           WHERE status IN ('pending', 'active')
             AND title LIKE '[auto:%'
           RETURNING id, title, description""")
    # filter to titles that actually parse (LIKE is coarse)
    rows = [r for r in cur.fetchall() if AUTO_RE.match(r["title"] or "")]
    return rows


def claim_work_queue(cur):
    cur.execute(
        """UPDATE successbrian_os.work_queue
           SET claimed_by = %s, claimed_at = now(), status = 'in_progress',
               updated_at = now()
           WHERE status = 'open' AND claimed_by IS NULL
             AND title LIKE '[auto:%%'
           RETURNING id, title, detail""",
        (WORKER,))
    return [r for r in cur.fetchall() if AUTO_RE.match(r["title"] or "")]


def finish_pm_task(cur, task_id, ok, summary):
    cur.execute(
        """UPDATE successbrian_os.tasks
           SET status = %s, completed_at = CASE WHEN %s THEN now() END,
               completion_summary = %s, updated_at = now()
           WHERE id = %s""",
        ("completed" if ok else "blocked", ok, summary[:500], task_id))


def finish_wq(cur, item_id, ok, summary):
    cur.execute(
        """UPDATE successbrian_os.work_queue
           SET status = %s, result = %s, updated_at = now()
           WHERE id = %s""",
        ("done" if ok else "failed", summary[:500], item_id))


def stale_watch(cur):
    """Escalate open items untouched for STALE_DAYS as events (deduped)."""
    n = 0
    cur.execute(
        """SELECT id, title FROM successbrian_os.tasks
           WHERE status IN ('pending', 'active', 'in_progress', 'blocked')
             AND updated_at < now() - (%s || ' days')::interval""",
        (STALE_DAYS,))
    for r in cur.fetchall():
        key = "task#%s" % r["id"]
        if not stale_event_recent(cur, key):
            feed(cur, "task_stale", "Stale %s: %s" % (key, (r["title"] or "")[:80]),
                 "Open and untouched for %d+ days." % STALE_DAYS)
            n += 1
    cur.execute(
        """SELECT id, title FROM successbrian_os.work_queue
           WHERE status IN ('open', 'in_progress')
             AND updated_at < now() - (%s || ' days')::interval""",
        (STALE_DAYS,))
    for r in cur.fetchall():
        key = "work#%s" % r["id"]
        if not stale_event_recent(cur, key):
            feed(cur, "task_stale", "Stale %s: %s" % (key, (r["title"] or "")[:80]),
                 "Open and untouched for %d+ days." % STALE_DAYS)
            n += 1
    cur.execute(
        """SELECT id, task_type FROM successbrian_os.high_volume_work_queue
           WHERE status = 'pending'
             AND updated_at < now() - (%s || ' days')::interval""",
        (STALE_DAYS,))
    for r in cur.fetchall():
        key = "hv#%s" % r["id"]
        if not stale_event_recent(cur, key):
            feed(cur, "task_stale",
                 "Stale %s (%s)" % (key, r["task_type"]),
                 "Pending research untouched for %d+ days." % STALE_DAYS)
            n += 1
    return n


def main():
    conn = db()
    conn.autocommit = False
    cur = conn.cursor()
    actions = []

    for task in claim_pm_tasks(cur):
        m = AUTO_RE.match(task["title"])
        name = m.group(1)
        handler = HANDLERS.get(name)
        if handler:
            try:
                ok, summary = handler(task)
            except Exception as e:
                ok, summary = False, "handler %s raised: %s" % (name, e)
            finish_pm_task(cur, task["id"], ok, summary)
            feed(cur, "task_done" if ok else "task_failed",
                 "[auto:%s] %s" % (name, m.group(2)[:80]), summary)
            actions.append("task#%s [%s] %s" % (task["id"], name, "done" if ok else "FAILED"))
        else:
            # claimed but no handler: release back to pending
            cur.execute(
                """UPDATE successbrian_os.tasks SET status = 'pending',
                   updated_at = now() WHERE id = %s""", (task["id"],))
            actions.append("task#%s [auto:%s] no handler — released" % (task["id"], name))

    for item in claim_work_queue(cur):
        m = AUTO_RE.match(item["title"])
        name = m.group(1)
        handler = HANDLERS.get(name)
        if handler:
            try:
                ok, summary = handler(item)
            except Exception as e:
                ok, summary = False, "handler %s raised: %s" % (name, e)
            finish_wq(cur, item["id"], ok, summary)
            feed(cur, "task_done" if ok else "task_failed",
                 "[auto:%s] %s" % (name, m.group(2)[:80]), summary)
            actions.append("work#%s [%s] %s" % (item["id"], name, "done" if ok else "FAILED"))
        else:
            cur.execute(
                """UPDATE successbrian_os.work_queue
                   SET claimed_by = NULL, status = 'open', updated_at = now()
                   WHERE id = %s""", (item["id"],))
            actions.append("work#%s [auto:%s] no handler — released" % (item["id"], name))

    n_stale = stale_watch(cur)
    if n_stale:
        actions.append("%d stale escalations" % n_stale)

    if actions:
        feed(cur, "loop_run", "pm_loop: %d action(s)" % len(actions),
             "; ".join(actions)[:1000])
    conn.commit()
    cur.close()
    conn.close()
    print("pm_loop: %d action(s)" % len(actions))
    for a in actions:
        print("  -", a)


if __name__ == "__main__":
    main()
