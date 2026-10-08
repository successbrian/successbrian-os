#!/usr/bin/env python3
"""need_status_sync.py — close the loop: needs/solutions -> tasks (successbrian-os side).

PURPOSE: Read DealsDesk need/solution status and reflect it back onto
         sbos_need_requests and sbostasks. Deterministic state machine, no AI.
WHY:     The ERP loop must close by itself: when DealsDesk satisfies a need,
         the requesting task should advance without a human updating it.
CALLED BY: cron (after needs_intake/sourcing_worker runs) or operator.
NOTES:   Rules:
         - need satisfied   -> request satisfied; if ALL of the task's requests
           are satisfied -> task done.
         - need planned/open -> request promoted; task active.
         - need dropped     -> request dropped.
         Never moves a task backwards (done stays done).
         Canonical: successbrian-os/tools/erp/need_status_sync.py
"""

import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [need_status_sync] %(message)s")
LOG = logging.getLogger("need_status_sync")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def psql(sql, write=False):
    r = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:300])
        return None
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def main():
    rows = psql(
        "SELECT r.id, r.task_id, r.status AS rstatus, n.status AS nstatus "
        "FROM successbrian_os.sbos_need_requests r "
        "JOIN dealsdesk.ecosystem_needs n ON n.id = r.need_id "
        "WHERE r.status IN ('promoted') AND r.need_id IS NOT NULL")
    if rows is None:
        return 1
    for req_id, task_id, _, nstatus in rows:
        new_rstatus = {"open": "promoted", "planned": "promoted",
                       "satisfied": "satisfied", "dropped": "dropped"}.get(nstatus, "promoted")
        psql(f"UPDATE successbrian_os.sbos_need_requests SET status='{new_rstatus}', "
             f"updated_at=NOW() WHERE id={int(req_id)}", write=True)
        LOG.info("request %s -> %s (need %s)", req_id, new_rstatus, nstatus)

    # Roll up to tasks: all requests satisfied -> task done; any live request -> active
    tasks = psql("SELECT DISTINCT task_id FROM successbrian_os.sbos_need_requests")
    for (task_id,) in (tasks or []):
        counts = psql(
            f"SELECT status, COUNT(*) FROM successbrian_os.sbos_need_requests "
            f"WHERE task_id={int(task_id)} GROUP BY status")
        by_status = {s: int(c) for s, c in (counts or [])}
        total = sum(by_status.values())
        if total and by_status.get("satisfied", 0) == total:
            psql(f"UPDATE public.sbostasks SET status='done', progress_pct=100, "
                 f"completed_at=NOW(), updated_at=NOW() "
                 f"WHERE id={int(task_id)} AND status <> 'done'", write=True)
            LOG.info("task %s -> done (all %d requests satisfied)", task_id, total)
        elif by_status.get("promoted", 0):
            psql(f"UPDATE public.sbostasks SET status='active', updated_at=NOW() "
                 f"WHERE id={int(task_id)} AND status='pending'", write=True)
    LOG.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
