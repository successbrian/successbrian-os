#!/usr/bin/env python3
"""daily_director.py — successbrian-os tells Brian what to do.

Brian 2026-10-15: "I want successbrian-os to be able to see my wishes and
dreams and tell me --> brian, do this x, y, z today. do a, b, c tomorrow.
do d, e, f the next day."

NOT the inbox — the output lands on the calendar view as to-dos, linked to
their projects/goals.

Each run:
  1. Reads v_brian_todos (open tasks assigned to Brian).
  2. Scores each by priority + deadline urgency (transparent, documented).
  3. Buckets items into the next 3 days by Brian's weekday capacity
     (WEEKDAY_CAPACITY — Wed is the big day, Thu/Fri are rest days).
  4. Clears prior auto-generated todos and writes fresh ones into
     life_calendar as event_type='todo', 9am Chicago, linked to project/goal.
  5. Feeds one daily_plan event to the PM feed (audit trail, not the inbox).

Idempotent: auto rows are tagged 'auto:director' and regenerated daily.

Stdlib + psycopg2, zero AI tokens. Runs on k11 as successbrian via cron.
"""
import os
import sys
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor

TAG = "auto:director"

# Wednesday is Brian's people/outreach day (2026-10-15): daytime appointments,
# errands out of the house, calls to people he needs to reach. People-tasks
# get a boost when filling Wednesday's bucket.
WEDNESDAY_BOOST_WORDS = ("call", "appointment", "meet", "errand", "visit",
                         "reach out", "phone", "dm ", "message ")
# Wed is his big day (CREW2 off, daytime free). Thu/Fri are brutal
# (CREW2 day + Idemia overnight) so the director stays quiet.
# Tune freely — the director reads this every run.
WEEKDAY_CAPACITY = {
    "mon": 2,  # CREW2 7-3:30
    "tue": 2,  # CREW2 7-3:30
    "wed": 5,  # CREW2 off, daytime free — big day
    "thu": 0,  # CREW2 + Idemia overnight — rest
    "fri": 0,  # CREW2 + Idemia overnight — rest
    "sat": 2,  # CREW2 7-3:30 WFH
    "sun": 1,  # Idemia 2am-2:30pm — recovery
}


def db():
    return psycopg2.connect(dbname="ecosystem_central", user="successbrian",
                            cursor_factory=RealDictCursor)


def feed_event(cur, event_type, title, detail):
    cur.execute(
        """INSERT INTO successbrian_os.ecosystem_events
           (event_type, source_plugin, title, detail)
           VALUES (%s, 'successbrian-os', %s, %s) RETURNING id""",
        (event_type, title, detail))
    return cur.fetchone()["id"]


def priority_pts(p):
    if p is None:
        return 3
    s = str(p).strip().lower()
    if s == "critical":
        return 10
    if s == "high":
        return 7
    if s == "medium":
        return 5
    if s == "low":
        return 3
    try:
        n = int(s)
        return max(1, min(10, 11 - n))  # 1 = highest
    except ValueError:
        return 3


def urgency_pts(target_date, today):
    if not target_date:
        return 1
    d = target_date.date() if hasattr(target_date, "date") else target_date
    delta = (d - today).days
    if delta < 0:
        return 10  # overdue
    if delta == 0:
        return 8
    if delta == 1:
        return 6
    if delta <= 7:
        return 4
    return 2


def main():
    conn = db()
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT * FROM successbrian_os.v_brian_todos")
    todos = cur.fetchall()
    today = datetime.now().date()  # k11 runs America/Chicago

    scored = []
    for t in todos:
        s = priority_pts(t["priority"]) + urgency_pts(t["target_date"], today)
        scored.append((s, t))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))

    buckets = []
    for offset in range(3):
        day = today + timedelta(days=offset)
        wd = day.strftime("%a").lower()
        buckets.append((day, WEEKDAY_CAPACITY.get(wd, 1)))
    plan_lines = []

    # clear yesterday's plan
    cur.execute(
        "DELETE FROM successbrian_os.life_calendar "
        "WHERE notes LIKE %s AND event_date::date >= %s",
        (TAG + "%", today))

    for day, capacity in buckets:
        label = day.strftime("%A").upper()
        if day == today:
            label = "TODAY (%s)" % day.strftime("%A").upper()
        elif day == today + timedelta(days=1):
            label = "TOMORROW (%s)" % day.strftime("%A").upper()
        slot = datetime(day.year, day.month, day.day, 9, 0)
        plan_lines.append("%s (%s) — capacity %d:" % (label, day.isoformat(), capacity))
        if capacity == 0:
            plan_lines.append("  - (no capacity — rest day)")
            continue
        # rank remaining todos for THIS day: Wednesday boosts people-tasks
        is_wed = day.strftime("%a").lower() == "wed"

        def day_score(item):
            s, t = item
            b = 0
            if is_wed:
                text = ((t["title"] or "") + " " + (t["description"] or "")).lower()
                if any(w in text for w in WEDNESDAY_BOOST_WORDS):
                    b = 3
            return s + b

        remaining = sorted(scored, key=lambda x: (-day_score(x), x[1]["id"]))
        items = remaining[:capacity]
        picked = {t["id"] for _, t in items}
        scored = [x for x in scored if x[1]["id"] not in picked]
        for s, t in items:
            cur.execute(
                """INSERT INTO successbrian_os.life_calendar
                   (title, event_date, event_type, project_id, goal_id,
                    status, notes)
                   VALUES (%s, %s, 'todo', %s, %s, 'scheduled', %s)""",
                (t["title"], slot, t["project_id"], t["goal_id"],
                 "%s | task_id=%s score=%d" % (TAG, t["id"], s)))
            plan_lines.append("  - %s (task %s)" % (t["title"], t["id"]))
        if not items:
            plan_lines.append("  - (nothing queued)")

    if scored:
        plan_lines.append("BACKLOG (beyond 3 days):")
        for s, t in scored:
            plan_lines.append("  - %s (task %s)" % (t["title"], t["id"]))

    detail = "Brian's plan, generated from open todos by priority + deadline:\n" \
             + "\n".join(plan_lines)
    eid = feed_event(cur, "daily_plan", "Daily plan — %s" % today.isoformat(),
                     detail)

    conn.commit()
    cur.close()
    conn.close()
    print("daily_director: plan written for %d todos (event %s)" % (len(scored), eid))
    print(detail)


if __name__ == "__main__":
    main()
