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
  sweep    Look at the Intel Bridge (the scatter) and sort what's
           new three ways: board packets (Workflow #1), Workflow
           #3 intel filings to their knowledge homes, and kick-
           asides to Altair (Workflow #2). [hourly cron; was
           scatter_clerk.py]
  file     File specific capture ids through Workflow #3 by hand
           (backfill / retry). Usage: clerk.py file <id> [id...]
  status   Watermark, packets filed today, queue depth. Read-only.
  jobs     Print this menu.

Usage: clerk.py <job> [args]
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
    tasks_created INT NOT NULL DEFAULT 0,
    queue_depth INT NOT NULL DEFAULT 0,
    captures_in INT NOT NULL DEFAULT 0,
    board_filed INT NOT NULL DEFAULT 0,
    sent_altair INT NOT NULL DEFAULT 0,
    bounced INT NOT NULL DEFAULT 0,
    filed_kept INT NOT NULL DEFAULT 0,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb
)
"""
# Brian, 2026-10-24: 'more table, less text. query-able.' The flow
# numbers live in COLUMNS Lyra and January can aggregate with SQL —
# never baked into the prose line, never trapped in a blob.
CHECKIN_ALTERS = [
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS metrics JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS captures_in INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS board_filed INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS sent_altair INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS bounced INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS filed_kept INT NOT NULL DEFAULT 0",
]


def write_checkin(tasks_created, metrics):
    """The hourly report to Lyra: one line, with the flow's numbers.

    Brian, 2026-10-24: 'maybe it puts one line hourly in a table
    somewhere to tell Lyra it's still ok. hi lyra, clerk checking in.
    created 14 tasks this hour, see ya next hour...' — extended the
    same morning: 'hourly numbers to measure the flow — as part of
    the hourly report to lyra.' The line is both the pattern's
    liveness signal (if it stops appearing, the ladder knows the
    pattern is broken — silence = death, never health) and the
    flow's hourly instrument reading. The metrics JSONB grows as
    the pattern gains phases (Sonic/Gemma timings, bounce counts);
    the message stays one human line.
    """
    import json as _json

    con = scatter_clerk.pm_core.conn()
    cur = con.cursor()
    cur.execute(CHECKIN_DDL)
    for alter in CHECKIN_ALTERS:
        cur.execute(alter)
    cur.execute(
        "SELECT COUNT(*) FROM atlas.nodes WHERE node_type='atlas_task' "
        "AND status = 'queued' AND node_key LIKE 'task:ssb-packet-%%'"
    )
    queue_depth = cur.fetchone()[0]
    metrics = dict(metrics or {})
    metrics["queue_depth"] = queue_depth
    # More table, less text: the line is just the pulse now; every
    # number is a column.
    message = "hi lyra, clerk checking in. see ya next hour"
    cur.execute(
        "INSERT INTO successbrian_os.clerk_checkins "
        "(source, message, tasks_created, queue_depth, captures_in, "
        "board_filed, sent_altair, bounced, filed_kept, metrics) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("clerk", message, tasks_created, queue_depth,
         int(metrics.get("captures_in", 0)), int(metrics.get("board_filed", 0)),
         int(metrics.get("sent_altair", 0)), int(metrics.get("bounced", 0)),
         int(metrics.get("filed_kept", 0)),
         _json.dumps(metrics)),
    )
    con.commit()
    con.close()
    print(f"hourly report written: tasks={tasks_created} "
          f"captures_in={metrics.get('captures_in', 0)} "
          f"board_filed={metrics.get('board_filed', 0)} "
          f"sent_altair={metrics.get('sent_altair', 0)} "
          f"bounced={metrics.get('bounced', 0)} "
          f"filed_kept={metrics.get('filed_kept', 0)} queue={queue_depth}")


def job_sweep(_args=None):
    """The hourly look at the Intel Bridge: sort everything new."""
    state = scatter_clerk.load_state()
    before = state.get("last_capture_id", 0)
    keys, wf3_results = scatter_clerk.run()
    after = scatter_clerk.load_state().get("last_capture_id", before)
    captures_in = 0
    if keys or wf3_results:
        con = scatter_clerk.pm_core.conn()
        cur = con.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM atlas.scattered_captures "
            "WHERE id > %s AND id <= %s", (before, after))
        captures_in = cur.fetchone()[0]
        con.close()
    kept = [r for r in wf3_results if r["outcome"] == "kept"]
    kicked = [r for r in wf3_results if r["outcome"] == "kicked"]
    metrics = {
        "captures_in": captures_in,
        "board_filed": len(keys),
        "sent_altair": len(kicked),
        "bounced": 0,
        "filed_kept": len(kept),
    }
    write_checkin(len(keys) + len(kicked), metrics)


def job_file(args=None):
    """File capture ids through Workflow #3 (backfill / retry)."""
    ids = []
    for a in (args or []):
        try:
            ids.append(int(a))
        except ValueError:
            print(f"file: '{a}' is not a capture id")
    if not ids:
        print("usage: clerk.py file <capture-id> [capture-id...]")
        return
    done = []
    for cid in ids:
        cap = scatter_clerk.fetch_capture(cid)
        if cap is None:
            print(f"file: capture #{cid} not found")
            continue
        if cap["status"] != "raw":
            print(f"file: capture #{cid} is '{cap['status']}', "
                  f"not raw — skipping (already dispositioned)")
            continue
        res = scatter_clerk.file_wf3(cap)
        done.append(res)
        print(f"wf3 {res['outcome']} capture #{res['id']} -> "
              f"{res['workspace'] or 'wf2'} ({res['detail']})")
    if done:
        con = scatter_clerk.pm_core.conn()
        cur = con.cursor()
        scatter_clerk.pm_core.decide(
            cur, "scatter-clerk",
            "Workflow #3 manual filing: "
            + "; ".join(f"#{r['id']} {r['outcome']} -> "
                        f"{r['workspace'] or 'wf2'}" for r in done),
            origin="system")
        con.commit()
        con.close()


def job_status(_args=None):
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


def job_jobs(_args=None):
    """Print this menu."""
    print("THE CLERK — job menu (if it's not on the menu, the clerk doesn't do it):")
    for name, fn in sorted(JOBS.items()):
        lines = (fn.__doc__ or "").strip().splitlines()
        print(f"  {name:8s} {lines[0] if lines else ''}")


JOBS = {
    "sweep": job_sweep,
    "file": job_file,
    "status": job_status,
    "jobs": job_jobs,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in JOBS:
        job_jobs()
        sys.exit(0 if len(sys.argv) == 2 and sys.argv[1] == "jobs" else 2)
    JOBS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
