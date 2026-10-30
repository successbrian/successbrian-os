#!/usr/bin/env python3
"""Deadline Radar — get Brian AHEAD of his goals.

Brian (2026-10-23): "I'm forgetful. I need the system to
help me remember — especially if goal deadlines are
coming. Get me ahead of my goals, not behind them...
successbrian-os needs to help a scatter brained, forgetful
human that likely has severe ADHD manage the chaos and
still be successful despite being half awake most of the
time."

Design law that follows: THE MACHINE CARRIES THE
REMEMBERING. A deadline that lives only in a chat, a
person's head, or an undated goal does not exist as far
as the system is concerned. This radar reads every dated
source the ecosystem has — his calendar
(life_calendar.events), the weekly Medium slot
(campaignsdesk.article_slots), and the standing goal
deadlines coded below from his own goal record — and
writes one brief: what is coming, in how many days, and
what to do NOW to be ahead of it.

Undated goals are reported as INVISIBLE: no date means
no radar, no reminder, no mercy. Dates get set, or the
goal stays invisible — the radar says so every day until
it changes.

Runs nightly (~04:35, after the Scattered Second Brain
triage) and on demand. v1: the standing list is coded
here with provenance; the build item
task:broken-audit:goal-deadlines-as-data moves it into
a table the radar reads.
"""

import datetime as dt
import os
import sys

import psycopg2

# SBOS common routines — Batch B migration (2026-10-27): the DB
# helpers below delegate to sbos_common (tools/), the one shared
# module. sys.path gets the tools/ dir (this file lives in tools/atlas/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402

DBNAME = "ecosystem_central"
BRIEF_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "deadline-radar-latest.md")
HORIZON_DAYS = 45

# Standing goal deadlines, from Brian's own goal record
# (business-goals charter + tracked goals, 2026-10-23).
# kind: "once" (date), "monthly" (day of month),
# "weekly-slot" (the Medium SBOS slot).
STANDING = [
    {"name": "GotBackup sponsorship month closes",
     "kind": "monthly", "day": 28,
     "goal": "40 sponsorships/month",
     "prep": "Count this month's sponsorships against "
             "40. The laydown tree is still a draft — "
             "nothing live until Brian approves it.",
     "keywords": ["gotbackup"]},
    {"name": "Locus AI last-call webinar",
     "kind": "once", "date": "2026-10-31",
     "goal": "Locus AI page-one-traffic offer",
     "prep": "8:00 PM PDT / 10:00 PM CDT, GoTo ID "
             "336-102-555. Registered 2026-10-20. "
             "Checkout code LOCVIP ($5 off) if buying.",
     "keywords": ["locus", "webinar"]},
    {"name": "Chicago TARDIS train trip (annual)",
     "kind": "once", "date": "2026-11-27",
     "goal": "Chicago trip + SBOS travel kit acceptance",
     "prep": "Travel-kit acceptance test runs on the "
             "two Dell road laptops — neither is powered "
             "on or tailnet-enrolled yet. That test must "
             "pass BEFORE the trip, not at the station.",
     "keywords": ["chicago", "tardis"]},
]

# Goals with NO date — invisible to every reminder
# system until Brian dates them (business-goals
# charter, 2026-10-23).
UNDATED = [
    "ContactFlowCRM $20/mo launch — gated on hosting + "
    "finished code (launch law); no date set.",
    "TrafficStreemz $30/mo launch — the ASAP track; no "
    "date set. ASAP is not a date.",
    "Gamma rescue completion — archives and databases "
    "still on gamma; no date set.",
]


def pg():
    # Batch B migration (2026-10-27): the connection comes from the one
    # shared factory — same database, host, and 'postgres' role as before.
    return sbos_common.connect(user="postgres")


def next_monthly(day, today):
    try:
        cand = today.replace(day=day)
    except ValueError:
        cand = None
    if cand and cand >= today:
        return cand
    nxt = (today.replace(day=1) + dt.timedelta(days=32))
    try:
        return nxt.replace(day=day)
    except ValueError:
        return nxt.replace(day=28)


def days_to_sunday(today):
    return (6 - today.weekday()) % 7


def tier(days):
    if days < 0:
        return "OVERDUE"
    if days <= 2:
        return "NOW"
    if days <= 7:
        return "THIS WEEK"
    if days <= 21:
        return "COMING"
    return "ON RADAR"


def standing_deadlines(today):
    out = []
    for s in STANDING:
        if s["kind"] == "monthly":
            d = next_monthly(s["day"], today)
        else:
            d = dt.date.fromisoformat(s["date"])
            if d < today and s["kind"] == "once":
                continue
        out.append({"name": s["name"], "date": d,
                    "days": (d - today).days,
                    "goal": s["goal"], "prep": s["prep"],
                    "keywords": s["keywords"],
                    "source": "standing goal record"})
    return out


def calendar_events(conn, today, days=21):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT start_at, title FROM "
            "life_calendar.events WHERE start_at >= %s "
            "AND start_at < %s ORDER BY start_at",
            (today, today + dt.timedelta(days=days)))
        return [(r[0], r[1]) for r in cur.fetchall()]


def dedupe(standing, events):
    """Drop a standing deadline if the calendar already
    carries it (same keywords, within 2 days)."""
    kept = []
    for s in standing:
        dup = False
        for when, title in events:
            t = title.lower()
            if any(k in t for k in s.get("keywords", [])) and \
                    abs((when.date() - s["date"]).days) <= 2:
                dup = True
                break
        if not dup:
            kept.append(s)
    return kept


def medium_slot(conn, today):
    week = "%d-W%02d" % today.isocalendar()[:2]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT idea_id FROM "
            "campaignsdesk.article_slots WHERE week = %s",
            (week,))
        row = cur.fetchone()
    if row:
        return None
    return {"name": "Medium SBOS slot — week %s UNFILLED"
            % week,
            "date": today + dt.timedelta(
                days=days_to_sunday(today)),
            "days": days_to_sunday(today),
            "goal": "One successbrian-os article per week "
                    "on Medium",
            "prep": "Idea #9 (MZ32-AR0 / EPYC 7002 hunt) "
                    "is the system's recommendation and "
                    "has been waiting since Oct 22. Assign "
                    "it, or pick another SBOS idea.",
            "keywords": ["medium"],
            "source": "campaignsdesk.article_slots"}


def build_brief(conn, today=None):
    today = today or dt.date.today()
    events = calendar_events(conn, today)
    items = standing_deadlines(today)
    slot = medium_slot(conn, today)
    if slot:
        items.append(slot)
    items = dedupe(items, events)
    items.sort(key=lambda i: i["days"])
    lines = ["# Deadline Radar — ahead of your goals",
             "",
             "Generated %s. The machine carries the "
             "remembering." % today.isoformat(),
             ""]
    lines.append("## Coming deadlines")
    if items:
        for i in items:
            lines.append(
                "- **%s — %s (%s, %d day%s)** [%s]"
                % (tier(i["days"]), i["name"],
                   i["date"].isoformat(), i["days"],
                   "" if i["days"] == 1 else "s",
                   i["source"]))
            lines.append("  Goal: %s" % i["goal"])
            lines.append("  Get ahead: %s" % i["prep"])
    else:
        lines.append("(nothing dated inside %d days)"
                     % HORIZON_DAYS)
    lines.append("")
    lines.append("## On your calendar (next 7 days)")
    week = [(w, t) for w, t in events
            if (w.date() - today).days <= 7]
    if week:
        for w, t in week:
            lines.append("- %s — %s" % (w.date().isoformat(), t))
    else:
        lines.append("(calendar empty this week)")
    lines.append("")
    lines.append("## INVISIBLE — goals with no date")
    lines.append("No date = no radar, no reminder. Set a "
                 "date or these stay invisible:")
    for u in UNDATED:
        lines.append("- %s" % u)
    lines.append("")
    return "\n".join(lines)


def selftest(conn):
    failures = []

    def check(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    check(next_monthly(28, dt.date(2026, 10, 23))
          == dt.date(2026, 10, 28),
          "monthly-28 from Oct 23 lands Oct 28")
    check(next_monthly(28, dt.date(2026, 10, 29))
          == dt.date(2026, 11, 28),
          "monthly-28 rolls to next month after the 28th")
    check(days_to_sunday(dt.date(2026, 10, 23)) == 2,
          "Friday Oct 23 is 2 days from Sunday")
    items = standing_deadlines(dt.date(2026, 10, 23))
    names = " ".join(i["name"] for i in items)
    check("GotBackup" in names and "Locus" in names
          and "Chicago" in names,
          "all three standing deadlines resolve")
    check(all(isinstance(i["days"], int) for i in items),
          "day counts are computed, not guessed")
    ev = [(dt.datetime(2026, 10, 31, 22, 0),
           "Locus AI webinar")]
    kept = dedupe(items, ev)
    check(not any("Locus" in i["name"] for i in kept)
          and any("GotBackup" in i["name"] for i in kept),
          "calendar-carried deadlines dedupe, others stay")
    check(tier(0) == "NOW" and tier(5) == "THIS WEEK"
          and tier(30) == "ON RADAR",
          "escalation tiers behave")
    if failures:
        print("SELFTEST FAILED: %d" % len(failures))
        return 1
    print("SELFTEST OK")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "run"
    conn = pg()
    try:
        if cmd == "selftest":
            return selftest(conn)
        if cmd == "run":
            text = build_brief(conn)
            with open(BRIEF_PATH, "w") as f:
                f.write(text)
            try:
                import allm_embed
                allm_embed.embed_latest(
                    "business-goals",
                    "deadline-radar-latest.md", text)
            except Exception as e:
                print("warning: brief embed failed (R32): "
                      "%s" % e, file=sys.stderr)
            print(text)
            return 0
        print("usage: deadline_radar.py [run|selftest]")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
