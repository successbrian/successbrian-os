#!/usr/bin/env python3
"""clerk.py — THE CLERK: a smart script with a job menu and functions.

Brian, 2026-10-24: "we are building out the concept of having a full
time 'clerk' role with some defined jobs for the ecosystem. it's not
an agent, it's a worker or a worker/harness... it just needs to be a
smart script with a job menu and functions."

THE RULE THIS FILE ENCODES: if a job is not on the menu, the clerk
does not do it. Adding work to the clerk means adding a menu entry
and a function — an auditable code change, never a prompt, a persona,
or discretion. Models appear only inside individual functions, as
bounded calls with parsed outputs (the architecture law).

JOB MENU (each entry maps to one function below):
  sweep    Look at the Intel Bridge (the scatter), queue what's new
           as board packets. [hourly cron; was scatter_clerk.py]
  status   Watermark, packets filed today, queue depth. Read-only.
  jobs     Print this menu.

Usage: clerk.py <job>
"""
import sys
from datetime import date

import scatter_clerk  # the sweep's implementation lives there


CHECKIN_DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.clerk_checkins (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    tasks_created INT,
    queue_depth INT
)
"""


def write_checkin(tasks_created):
    """One line in the table, hourly, for Lyra: the clerk is still ok.

    Brian, 2026-10-24: 'maybe it puts one line hourly in a table
    somewhere to tell Lyra it's still ok. hi lyra, clerk checking in.
    created 14 tasks this hour, see ya next hour...' The line is the
    pattern's liveness signal: if it stops appearing, the ladder
    knows the pattern is broken (silence = death, never health).
    """
    con = scatter_clerk.pm_core.conn()
    cur = con.cursor()
    cur.execute(CHECKIN_DDL)
    cur.execute(
        "SELECT COUNT(*) FROM atlas.nodes WHERE node_type='atlas_task' "
        "AND status = 'queued' AND node_key LIKE 'task:ssb-packet-%%'"
    )
    queue_depth = cur.fetchone()[0]
    message = (
        f"hi lyra, clerk checking in. created {tasks_created} task(s) "
        f"this hour, see ya next hour"
    )
    cur.execute(
        "INSERT INTO successbrian_os.clerk_checkins "
        "(source, message, tasks_created, queue_depth) VALUES (%s, %s, %s, %s)",
        ("clerk", message, tasks_created, queue_depth),
    )
    con.commit()
    con.close()
    print(f"check-in written: {message} (queue depth {queue_depth})")


def job_sweep():
    """The hourly look at the Intel Bridge: packet everything new."""
    keys = scatter_clerk.run()
    write_checkin(len(keys))


def job_status():
    """Watermark, packets filed today, board queue depth. Read-only."""
    wm = scatter_clerk.load_state().get("last_capture_id", 0)
    con = scatter_clerk.pm_core.conn()
    cur = con.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM atlas.scattered_captures WHERE status='raw' AND id > %s",
        (wm,),
    )
    unswept = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM atlas.nodes WHERE node_key LIKE 'task:ssb-packet-%%' "
        "AND created_at::date = %s",
        (date.today(),),
    )
    packets_today = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM atlas.nodes WHERE node_type='atlas_task' "
        "AND status = 'queued' AND node_key LIKE 'task:ssb-packet-%%'"
    )
    packets_queued = cur.fetchone()[0]
    con.close()
    print(f"clerk status: watermark capture #{wm}; unswept raw captures: {unswept}; "
          f"packets filed today: {packets_today}; packets queued for the board: {packets_queued}")


def job_jobs():
    """Print this menu."""
    print("THE CLERK — job menu (if it's not on the menu, the clerk doesn't do it):")
    for name, fn in sorted(JOBS.items()):
        lines = (fn.__doc__ or "").strip().splitlines()
        print(f"  {name:8s} {lines[0] if lines else ''}")


JOBS = {
    "sweep": job_sweep,
    "status": job_status,
    "jobs": job_jobs,
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in JOBS:
        job_jobs()
        sys.exit(0 if len(sys.argv) == 2 and sys.argv[1] == "jobs" else 2)
    JOBS[sys.argv[1]]()


if __name__ == "__main__":
    main()
