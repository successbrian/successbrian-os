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


def _pg_env(db=None):
    env = dict(os.environ)
    env.update({
        "PGHOST": os.environ.get("PGHOST", "localhost"),
        "PGPORT": os.environ.get("PGPORT", "5432"),
        "PGDATABASE": db or os.environ.get("PGDATABASE", "ecosystem_central"),
        "PGUSER": os.environ.get("PGUSER", "successbrian"),
        # people_unified.people is 215M rows — never let a query run away
        "PGOPTIONS": "-c statement_timeout=30s" if db == "people_unified" else "",
    })
    return env


def pg_query(sql, db=None):
    p = subprocess.run(["psql", "-t", "-A", "-F", "\t", "-c", sql],
                       capture_output=True, text=True,
                       env=_pg_env(db), timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"pg_query failed: {p.stderr.strip()[:300]}")
    return [l.split("\t") for l in p.stdout.strip().split("\n") if l.strip()]


def pg_exec(sql, db=None):
    p = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t"],
                       input=sql, capture_output=True, text=True,
                       env=_pg_env(db), timeout=180)
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
    "podcast": [
        # Research pulls the standing intel feeds so segments build on what
        # the ecosystem already knows.
        ("Segment topics locked (5; pull ecosystem_intel digest + "
         "memory_ai_intel discoveries + Friday coaching deep dive)", 3),
        ("Research banked per segment (save source URLs for scraper fleet)", 2),
        ("Dialogue packet written (check tools/tts/pronunciation.md FIRST; "
         "log new mispronunciations with phonetic fixes)", 1),
        ("TTS audio generated (tools/tts/make_episode.py)", 0),
        ("QA pass: glitches, speed shifts, mispronunciations fixed", 0),
        ("Episode assembled + posted", 0),
        ("Meme created", 0),
        ("Episode report filed: plan.py --report (second_brain note + "
         "enrichment for named people/companies)", 0),
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


def _pm_mirror(event_id, event_title, task, due_iso, task_id=None):
    """Mirror a life_ops task into successbrian_os.tasks (PM master).

    Returns the PM task id. Idempotent per life_ops task id."""
    if task_id:
        rows = pg_query("SELECT pm_task_id FROM life_ops.event_tasks "
                        f"WHERE id={task_id};")
        if rows and rows[0][0]:
            return int(rows[0][0])
    label = task_id if task_id else "new"
    desc = f"life_ops task {label} for event {event_id}"
    rows = pg_query(
        "INSERT INTO successbrian_os.tasks "
        "(assigned_to, assigned_by, title, description, priority, "
        " status, target_date) VALUES "
        f"('brian', 'life-ops', "
        f"{lit(f'[{event_title}] {task}')}, "
        f"{lit(desc)}, "
        f"'normal', 'pending', {lit(due_iso)}) "
        "RETURNING id;")
    pm_id = int(rows[0][0])
    if task_id:
        pg_exec("UPDATE life_ops.event_tasks "
                f"SET pm_task_id={pm_id} WHERE id={task_id};")
    return pm_id


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
            rows = pg_query(
                "INSERT INTO life_ops.event_tasks "
                "(event_id, task, due_date, lead_days, source) VALUES "
                f"({ev['id']}, {lit(task)}, {lit(due.isoformat())}, "
                f"{lead}, 'auto') ON CONFLICT (event_id, task) "
                "DO UPDATE SET task=EXCLUDED.task RETURNING id;")
            tid = int(rows[0][0])
            _pm_mirror(ev["id"], ev["title"], task, due.isoformat(), tid)
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


def ensure_weekly_podcast():
    """Create next Saturday's 7:30 PM podcast event if missing.

    The Saturday podcast is a weekly hard date. This runs Sundays and
    sets up the coming week's episode shell; --generate then plans it.
    """
    today = datetime.date.today()
    # next Saturday (weekday(): Mon=0..Sun=6; Sat=5)
    days_ahead = (5 - today.weekday()) % 7 or 7
    sat = today + datetime.timedelta(days=days_ahead)
    title = f"Saturday podcast ({sat.isoformat()})"
    rows = pg_query("SELECT id FROM successbrian_os.life_calendar "
                    f"WHERE title={lit(title)} LIMIT 1;")
    if rows:
        return f"exists: {title}"
    pg_exec(
        "INSERT INTO successbrian_os.life_calendar "
        "(title, event_date, event_type, is_hard_date, status, notes) "
        f"VALUES ({lit(title)}, "
        f"{lit(sat.isoformat() + ' 19:30:00 America/Chicago')}, "
        "'podcast', TRUE, 'scheduled', "
        "'Weekly hard date: 5 segments, then voice dialogue in TUI.');")
    return f"created: {title}"


def mark_hard(event_id, event_type=None):
    sets = ["is_hard_date=TRUE"]
    if event_type:
        sets.append(f"event_type={lit(event_type)}")
    pg_exec("UPDATE successbrian_os.life_calendar SET " +
            ", ".join(sets) + f" WHERE id={event_id};")


def episode_report(episode_date, notes, names):
    """File the post-episode loop: second_brain note, PM event, and
    vera_enrich tasks for named people already in people.people.

    This is the enrichment bridge: topics that surface real people feed
    the people/business enrichment pipeline instead of dying in chat."""
    import subprocess
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sb = subprocess.run(
        ["python3", os.path.join(repo, "second_brain.py"),
         "--topic", f"podcast episode {episode_date}",
         "--content", notes,
         "--category", "learning",
         "--source", "life-ops"],
        capture_output=True, text=True, timeout=60)
    print("second_brain:", sb.stdout.strip() or sb.stderr.strip()[:80])
    pg_exec(
        "INSERT INTO successbrian_os.ecosystem_events "
        "(event_type, source_plugin, project_ref, title, detail) VALUES "
        f"('podcast_episode_report', 'life-ops', 'podcast', "
        f"{lit(f'Episode {episode_date} reported')}, {lit(notes)});")
    print("ecosystem event filed")
    enriched = 0
    for name in [n.strip() for n in (names or "").split(",") if n.strip()]:
        # exact match on the indexed lower(full_name) expression —
        # the table is 215M rows; no fuzzy scans allowed here
        rows = pg_query(
            "SELECT id FROM people.people "
            "WHERE lower(TRIM(BOTH FROM (first_name || ' ' || last_name))) "
            f"= lower({lit(name)}) LIMIT 1;",
            db="people_unified")
        if not rows:
            print(f"  {name}: not in people.people, skipped")
            continue
        pid = int(rows[0][0])
        dup = pg_query(
            f"SELECT 1 FROM people.tasks WHERE person_id={pid} "
            f"AND task_type='vera_enrich' "
            f"AND status IN ('pending','in_progress','processing') LIMIT 1;",
            db="people_unified")
        if not dup:
            pg_exec(
                "INSERT INTO people.tasks (person_id, task_type, status, "
                f"source_group, notes) VALUES ({pid}, 'vera_enrich', "
                f"'pending', 'podcast', "
                f"{lit(f'podcast episode {episode_date}: topic surfaced this person')});",
                db="people_unified")
            enriched += 1
    print(f"enrichment tasks filed: {enriched}")
    return enriched


def mark_done(task_id):
    pg_exec("UPDATE life_ops.event_tasks SET status='done' "
            f"WHERE id={task_id};")
    rows = pg_query("SELECT pm_task_id FROM life_ops.event_tasks "
                    f"WHERE id={task_id};")
    if rows and rows[0][0]:
        pg_exec("UPDATE successbrian_os.tasks "
                "SET status='completed', completed_at=now() "
                f"WHERE id={rows[0][0]};")


def backfill_pm():
    """Mirror all existing life_ops tasks into PM (one-time)."""
    rows = pg_query(
        "SELECT t.id, t.event_id, c.title, t.task, t.due_date::text, "
        "t.status FROM life_ops.event_tasks t "
        "JOIN successbrian_os.life_calendar c ON c.id=t.event_id "
        "WHERE t.pm_task_id IS NULL;")
    n = 0
    for r in rows:
        tid, eid, title, task, due = int(r[0]), int(r[1]), r[2], r[3], r[4]
        pm_id = _pm_mirror(eid, title, task, due, tid)
        if r[5] == "done":
            pg_exec("UPDATE successbrian_os.tasks "
                    "SET status='completed', completed_at=now() "
                    f"WHERE id={pm_id};")
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--mark-hard", type=int, default=None)
    ap.add_argument("--type", default=None)
    ap.add_argument("--done", type=int, default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--weekly", action="store_true",
                    help="create next Saturday's podcast event")
    ap.add_argument("--backfill-pm", action="store_true",
                    help="mirror existing tasks into PM (one-time)")
    ap.add_argument("--report", action="store_true",
                    help="file episode report: second_brain + PM event + "
                         "enrichment for named people")
    ap.add_argument("--episode-date", default="",
                    help="episode date for --report (YYYY-MM-DD)")
    ap.add_argument("--notes", default="",
                    help="episode notes for --report")
    ap.add_argument("--names", default="",
                    help="comma-separated names for enrichment (--report)")
    args = ap.parse_args()
    if args.report:
        if not args.episode_date or not args.notes:
            print("need --episode-date and --notes")
            return
        episode_report(args.episode_date, args.notes, args.names)
    elif args.backfill_pm:
        print(f"mirrored {backfill_pm()} tasks into PM")
    elif args.weekly:
        print(ensure_weekly_podcast())
        made = generate()
        print(f"planned {len(made)} events: {made or 'none new'}")
    elif args.generate:
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
