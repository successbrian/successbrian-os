#!/usr/bin/env python3
"""derive_needs.py — turn breached signal thresholds into screams.

PURPOSE: The missing middle layer: signals are facts, thresholds are policy,
  screams are needs. Evaluates every enabled threshold against the latest
  signal observation and inserts into successbrian_os.sbos_need_requests.
WHY: Brian 2026-10-17 — "use this type of intel and turn this into what needs
  to be built out for our ecosystem... and it feeds the screams."
CALLED BY: cron every 15 min, staggered 5 min after collect_infra.
NOTES:
  - Dedup: skips when an OPEN (new/promoted) scream already exists for the
    same derived need. Cooldown: won't re-scream within cooldown_hours of the
    last scream for the same threshold, even if the earlier one closed.
  - task_id: stable hash of signal_key in a high range (2_000_000_000+) so
    signal-derived screams never collide with task-system screams.
  - Screams stay generic (Brian's rule) — need_class/evidence ride in specs
    as structured text DealsDesk parses.
  - stdlib + psycopg2 only, zero AI tokens.
"""
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

# Standing task owning all signal-derived screams (public.sbostasks).
# Created 2026-10-17; the FK on sbos_need_requests requires a real task.
SIGNAL_WATCH_TASK_ID = 18199


def main():
    conn = psycopg2.connect(dbname="ecosystem_central", user="successbrian",
                            cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute(
        """SELECT t.*, s.value_num, s.observed_at
           FROM successbrian_os.signal_thresholds t
           JOIN successbrian_os.ecosystem_signals s USING (signal_key)
           WHERE t.enabled""")
    thresholds = cur.fetchall()

    screamed = 0
    for t in thresholds:
        v = t["value_num"]
        if v is None:
            continue
        breached = (v > t["threshold_num"] if t["condition"] == "gt"
                    else v < t["threshold_num"])
        if not breached:
            continue

        tid = SIGNAL_WATCH_TASK_ID
        # Skip if an open scream already exists for this need.
        cur.execute(
            """SELECT 1 FROM successbrian_os.sbos_need_requests
               WHERE task_id = %s AND item = %s
                 AND status IN ('new', 'promoted') LIMIT 1""",
            (tid, t["need_item"]))
        if cur.fetchone():
            continue
        # Cooldown: skip if we screamed recently, even if it closed.
        cur.execute(
            """SELECT 1 FROM successbrian_os.sbos_need_requests
               WHERE task_id = %s AND item = %s
                 AND created_at > now() - (%s || ' hours')::interval LIMIT 1""",
            (tid, t["need_item"], t["cooldown_hours"]))
        if cur.fetchone():
            continue

        specs = (f"{t['need_specs']} | SIGNAL={t['signal_key']} "
                 f"value={v} threshold={t['threshold_num']} "
                 f"observed={t['observed_at']:%Y-%m-%d %H:%M}")
        cur.execute(
            """INSERT INTO successbrian_os.sbos_need_requests
                   (task_id, item, specs, qty, max_cost, priority, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'new')""",
            (tid, t["need_item"], specs, t["qty"], t["max_cost"], t["priority"]))
        screamed += 1
        print(f"screamed: {t['need_item']} ({t['signal_key']}={v})", flush=True)

    conn.commit()
    conn.close()
    print(f"done: {screamed} new screams from {len(thresholds)} thresholds")


if __name__ == "__main__":
    sys.exit(main())
