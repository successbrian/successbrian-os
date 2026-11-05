#!/usr/bin/env python3
"""QA helpers for the cron-time-tracking PM project.

  fresh     — a 'cron-time-tracking' report exists for today or
              yesterday (title-dated), i.e. the tracker is alive.
  coverage  — for the target day (yesterday, or 2026-11-05 while
              yesterday predates tracking), every active
              daily-cadence job due that day has a cron_runs row
              (any status): no due job is silently untracked.

Exit 0 = pass, 1 = fail. Deterministic, zero tokens.
"""
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cron_time_tracker as ctt  # noqa: E402

TZ = ZoneInfo("America/Chicago")
TRACKING_START = date(2026, 11, 5)


def fresh(cur):
    today = datetime.now(TZ).date()
    titles = [f"Cron time tracking — {d.isoformat()}"
              for d in (today, today - timedelta(days=1))]
    cur.execute("SELECT count(*) AS n FROM successbrian_os.reports "
                "WHERE report_type='cron-time-tracking' "
                "AND title = ANY(%s)", (titles,))
    n = cur.fetchone()["n"]
    print(f"fresh: {n} report(s) for today/yesterday")
    return 0 if n > 0 else 1


def coverage(cur):
    today = datetime.now(TZ).date()
    target = today - timedelta(days=1)
    if target < TRACKING_START:
        target = TRACKING_START
    cur.execute("SELECT * FROM successbrian_os.cron_jobs "
                "WHERE status='active' AND cadence='daily'")
    missing = []
    due = 0
    for job in cur.fetchall():
        if not job["primary_time"] or not ctt.is_due(
                job["primary_time"], target):
            continue
        due += 1
        cur.execute("SELECT 1 FROM successbrian_os.cron_runs "
                    "WHERE job_id=%s AND date=%s",
                    (job["id"], target))
        if cur.fetchone() is None:
            missing.append(job["job_slug"])
    print(f"coverage {target}: {due} daily jobs due, "
          f"{len(missing)} without a run row")
    for m in missing:
        print(f"  UNTRACKED: {m}")
    return 0 if not missing else 1


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("fresh", "coverage"):
        print(__doc__)
        return 2
    conn = ctt.db()
    cur = conn.cursor()
    rc = fresh(cur) if sys.argv[1] == "fresh" else coverage(cur)
    conn.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
