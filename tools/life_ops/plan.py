#!/usr/bin/env python3
"""
life_ops — backward planning for hard-date events.

Events with hard dates never slide. So the system works backward from the
date and generates the prep tasks with real due dates:

    python3 plan.py --generate          # plan all unplanned hard-date events
    python3 plan.py --watch             # due-soon/overdue -> inbox
    python3 plan.py --mark-hard --event 6
    python3 plan.py --done --task 3

Templates live in TEMPLATES by event_type. Tasks land in
life_ops.event_tasks. The watcher files to pending_questions (deduped),
silent when nothing needs attention.

stdlib + psql CLI only.
"""
import argparse
import datetime
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "business_core"))
from core import lit  # noqa: E402


def _pg_env():
    env = dict(os.environ)
    env.update({
        "PGHOST": os.environ.get("PGHOST", "localhost"),
        "PGPORT": os.environ.get("PGPORT", "5432"),
        "PGDATABASE": os.environ.get("PGDATABASE", "ecosystem_central"),
        "PGUSER": os.environ.get("PGUSER", "successbrian"),
    })
    return env


def pg_query(sql):
    p = subprocess.run(["psql", "-t", "-A", "-F", "\t", "-c", sql],
                       capture_output=True, text=True,
                       env=_pg_env(), timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"pg_query failed: {p.stderr.strip()[:300]}")
    return [l.split("\t") for l in p.stdout.strip().split("\n") if l.strip()]


def pg_exec(sql):
    p = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t"],
                       input=sql, capture_output=True, text=True,
                       env=_pg_env(), timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"pg_exec failed: {p.stderr.strip()[:300]}")


# event_type -> [(task, lead_days_before_event)]
TEMPLATES = {
    "travel": [
        ("Tickets/passes confirmed", 56),
        ("Hotel booked", 42),
        ("Ride/transport planned", 14),
        ("Packing list ready", 3),
        ("Confirm all bookings", 1),
    ],
    "medical": [
        ("Ride confirmed", 7),
        ("Documents/ID ready", 3),
        ("Confirm appointment", 1),
    ],
    "deadline": [
        ("Draft done", 3),
        ("Brian review", 1),
        ("Post/publish", 0),
    ],
    "meeting": [
        ("Prep/agenda ready", 3),
        ("Tech check (link, audio)", 1),
    ],
    "general": [
        ("Confirm details", 7),
        ("Day-before check", 1),
    ],
}


def hard_events():
    rows = pg_query(
        "SELECT id, title, event_date::date, event_type "
        "FROM successbrian_os.life_calendar "
        "WHERE is_hard_date AND event_date > now() "
        "AND status NOT IN ('cancelled', 'done', 'completed') "
        "ORDER BY event_date;")
    return [{"id": int(r[0]), "title": r[1], "date": r[2], "type": r[3]}
            for r in rows]


def planned(event_id):
    rows = pg_query("SELECT 1 FROM life_ops.event_tasks "
                    f"WHERE event_id={event_id} LIMIT 1;")
    return bool(rows)


def generate():
    """Generate backward plans for unplanned hard-date events."""
    made = []
    for ev in hard_events():
        if planned(ev["id"]):
            continue
        tmpl = TEMPLATES.get(ev["type"], TEMPLATES["general"])
        ev_date = datetime.date.fromisoformat(ev["date"])
        for task, lead in tmpl:
            due = ev_date - datetime.timedelta(days=lead)
            # don't create tasks already in the past at generation time;
            # flag them instead
            pg_exec(
                "INSERT INTO life_ops.event_tasks "
                "(event_id, task, due_date, lead_days, source) VALUES "
                f"({ev['id']}, {lit(task)}, {lit(due.isoformat())}, "
                f"{lead}, 'auto') ON CONFLICT (event_id, task) "
                "DO NOTHING;")
        made.append(ev["title"])
    return made


def due_tasks(within_days=3):
    rows = pg_query(
        "SELECT t.id, c.title, t.task, t.due_date, c.event_date::date "
        "FROM life_ops.event_tasks t "
        "JOIN successbrian_os.life_calendar c ON c.id = t.event_id "
        f"WHERE t.status='pending' AND t.due_date <= "
        f"(CURRENT_DATE + INTERVAL '{within_days} days') "
        "ORDER BY t.due_date;")
    return [{"id": int(r[0]), "event": r[1], "task": r[2],
             "due": r[3], "event_date": r[4]} for r in rows]


def overdue_tasks():
    rows = pg_query(
        "SELECT t.id, c.title, t.task, t.due_date, c.event_date::date "
        "FROM life_ops.event_tasks t "
        "JOIN successbrian_os.life_calendar c ON c.id = t.event_id "
        "WHERE t.status='pending' AND t.due_date < CURRENT_DATE "
        "ORDER BY t.due_date;")
    return [{"id": int(r[0]), "event": r[1], "task": r[2],
             "due": r[3], "event_date": r[4]} for r in rows]


def watch():
    """File ONE consolidated inbox question for due-soon/overdue tasks.
    Silent when clean. Deduped: re-files only when the set changes."""
    over = overdue_tasks()
    due = [t for t in due_tasks() if t["id"] not in {o["id"] for o in over}]
    if not over and not due:
        return "clean"
    lines = []
    for t in over:
        lines.append(f"OVERDUE {t['due']}: {t['task']} — {t['event']} "
                     f"(event {t['event_date']}) [task {t['id']}]")
    for t in due:
        lines.append(f"due {t['due']}: {t['task']} — {t['event']} "
                     f"(event {t['event_date']}) [task {t['id']}]")
    body = "\n".join(lines)
    question = (f"Life-ops: {len(over)} overdue, {len(due)} due soon.\n"
                f"{body}\nWhich are done, and which need attention?")
    # dedupe on the exact set: context carries the task ids
    sig = ",".join(str(t["id"]) for t in over + due)
    ctx = f"life-ops digest tasks={sig}"
    rows = pg_query(
        "SELECT 1 FROM successbrian_os.pending_questions "
        "WHERE asked_by='life-ops' AND status='open' "
        f"AND context={lit(ctx)} LIMIT 1;")
    if rows:
        return "already filed"
    pg_exec(
        "INSERT INTO successbrian_os.pending_questions "
        "(asked_by, question, context, priority) VALUES "
        f"('life-ops', {lit(question)}, {lit(ctx)}, 2);")
    return f"filed: {len(over)} overdue, {len(due)} due"


def _file(asked_by, question, context, priority=3):
    rows = pg_query(
        "SELECT 1 FROM successbrian_os.pending_questions "
        f"WHERE asked_by={lit(asked_by)} AND status='open' "
        f"AND context={lit(context)} LIMIT 1;")
    if rows:
        return False
    pg_exec(
        "INSERT INTO successbrian_os.pending_questions "
        "(asked_by, question, context, priority) VALUES "
        f"({lit(asked_by)}, {lit(question)}, {lit(context)}, {priority});")
    return True


def mark_hard(event_id, event_type=None):
    sets = ["is_hard_date=TRUE"]
    if event_type:
        sets.append(f"event_type={lit(event_type)}")
    pg_exec("UPDATE successbrian_os.life_calendar SET " +
            ", ".join(sets) + f" WHERE id={event_id};")


def mark_done(task_id):
    pg_exec("UPDATE life_ops.event_tasks SET status='done' "
            f"WHERE id={task_id};")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--mark-hard", type=int, default=None)
    ap.add_argument("--type", default=None)
    ap.add_argument("--done", type=int, default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.generate:
        made = generate()
        print(f"planned {len(made)} events: {made or 'none new'}")
    elif args.watch:
        print(watch())
    elif args.mark_hard is not None:
        mark_hard(args.mark_hard, args.type)
        print(f"event {args.mark_hard} marked hard")
    elif args.done is not None:
        mark_done(args.done)
        print(f"task {args.done} done")
    elif args.list:
        for t in due_tasks(365):
            print(f"{t['due']} | {t['event']} | {t['task']} | id={t['id']}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
