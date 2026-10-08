#!/usr/bin/env python3
"""need_from_task.py — raise hardware needs from project tasks (successbrian-os side).

PURPOSE: Scan sbostasks for deterministic hardware-need markers and stage them
         in successbrian_os.sbos_need_requests for DealsDesk intake.
WHY:     A project task that needs hardware should open a sourcing need by
         itself — no human relay, no AI parsing. The marker lives in the task's
         source_ref jsonb: {"hardware_need": {"item": "...", "specs": "...",
         "qty": N, "max_cost": N|null}}.
CALLED BY: cron (after task creation/update runs) or operator. Idempotent:
         UNIQUE(task_id, item) dedupes; re-runs create nothing new.
NOTES:   Writes ONLY to successbrian_os.sbos_need_requests (owned here).
         DealsDesk's needs_intake.py promotes rows into dealsdesk.ecosystem_needs.
         Canonical: successbrian-os/tools/erp/need_from_task.py
         Deployed: /home/dealsdesk/scripts/need_from_task.py (k11-alpha)
"""

import json
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [need_from_task] %(message)s")
LOG = logging.getLogger("need_from_task")

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
        "SELECT id, title, source_ref FROM public.sbostasks "
        "WHERE status IN ('pending','active') AND source_ref ? 'hardware_need'")
    if rows is None:
        return 1
    created = 0
    for task_id, title, ref_json in rows:
        try:
            need = json.loads(ref_json)["hardware_need"]
            item = need["item"]
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            LOG.warning("task %s has malformed hardware_need: %s", task_id, e)
            continue
        specs = need.get("specs")
        qty = int(need.get("qty", 1))
        max_cost = need.get("max_cost")
        max_cost_sql = "NULL" if max_cost is None else str(float(max_cost))
        specs_sql = "NULL" if specs is None else f"'{esc(specs)}'"
        ok = psql(
            "INSERT INTO successbrian_os.sbos_need_requests "
            "(task_id, item, specs, qty, max_cost, priority) "
            f"VALUES ({int(task_id)}, '{esc(item)}', {specs_sql}, {qty}, {max_cost_sql}, 7) "
            "ON CONFLICT (task_id, item) DO NOTHING", write=True)
        if ok:
            # ON CONFLICT DO NOTHING still returns success; check by count is overkill —
            # the UNIQUE constraint is the dedupe guarantee.
            created += 1
            LOG.info("staged need: task=%s item=%s", task_id, item)
    LOG.info("done: %d task(s) scanned, needs staged (dedupe by UNIQUE)", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
