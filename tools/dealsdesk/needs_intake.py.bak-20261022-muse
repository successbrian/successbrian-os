#!/usr/bin/env python3
"""needs_intake.py — promote staged need requests into DealsDesk needs (DealsDesk side).

PURPOSE: Poll successbrian_os.sbos_need_requests for status='new' and create
         dealsdesk.ecosystem_needs rows. This is the ownership boundary:
         successbrian-os stages, DealsDesk promotes.
WHY:     DealsDesk owns ecosystem_needs; nothing else writes it directly.
         The intake is deterministic — field mapping only, no AI judgment.
CALLED BY: cron (every 15 min) or operator. Idempotent: promoted rows are
         marked so re-runs pick up only new ones.
NOTES:   urgency: task priority 1-10 -> need urgency 1-5 (ceil(p/2)).
         need_type is always 'hardware' from this path (task-raised needs are
         hardware; other types enter via DealsDesk's own flows).
         Canonical: successbrian-os/tools/dealsdesk/needs_intake.py
         Deployed: /home/dealsdesk/scripts/needs_intake.py (k11-alpha)
"""

import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [needs_intake] %(message)s")
LOG = logging.getLogger("needs_intake")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def psql(sql, write=False):
    r = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:300])
        return None
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return str(s).replace("'", "''")


def main():
    rows = psql(
        "SELECT id, task_id, item, specs, qty, priority FROM "
        "successbrian_os.sbos_need_requests WHERE status='new' ORDER BY id")
    if rows is None:
        return 1
    for req_id, task_id, item, specs, qty, priority in rows:
        urgency = max(1, min(5, (int(priority) + 1) // 2))
        desc = f"{specs or ''} (qty {qty}; from sbos task {task_id})".strip()
        need_rows = psql(
            "INSERT INTO dealsdesk.ecosystem_needs "
            "(need_type, subject, description, magnitude, urgency, source, status) "
            f"VALUES ('hardware', '{esc(item)}', '{esc(desc)}', '{int(qty)}', "
            f"{urgency}, 'sbos_task:{task_id}', 'open') RETURNING id")
        if not need_rows:
            LOG.error("failed to create need for request %s", req_id)
            continue
        need_id = need_rows[0][0]
        psql(f"UPDATE successbrian_os.sbos_need_requests SET status='promoted', "
             f"need_id={int(need_id)}, updated_at=NOW() WHERE id={int(req_id)}",
             write=True)
        LOG.info("promoted request %s -> need %s (%s)", req_id, need_id, item)
    LOG.info("done: %d new request(s) processed", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
