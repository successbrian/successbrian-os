#!/usr/bin/env python3
"""
sonic_capacity_sample.py — one capacity sample of chat-Alpha Sonic.

Brian 2026-10-29: as he adds more and more Sonic, the system must tell
him THROUGH ALTAIR when another Sonic is needed to keep the flow going.
That decision needs evidence, not impressions, so this sampler records
every 5 minutes (cron):

  - Sonic (127.0.0.1:11439, the instance Altair chat + the task worker
    share with heartbeat/council/extraction) slot state: total / busy
  - qwen_task_queue: pending count, in-progress count, oldest pending age

chat_brief.py's CAPACITY section reads the rolling 24h of samples and
puts a verdict line in CHAT_BRIEF.md, which Altair reads at chat start
and raises with Brian in conversation. Queue depth alone is NOT the
signal in this ecosystem (2026-10-24: slots sat 4/4 under batch load
while the queue looked fine) — slot saturation is the primary metric.
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402

SONIC_SLOTS_URL = "http://127.0.0.1:11439/slots"

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.sonic_capacity_samples (
    id serial PRIMARY KEY,
    sampled_at timestamptz NOT NULL DEFAULT now(),
    slots_total int,
    slots_busy int,
    queue_pending int,
    queue_in_progress int,
    oldest_pending_age_min numeric
);
"""


def sonic_slots():
    try:
        with urllib.request.urlopen(SONIC_SLOTS_URL, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        total = len(data)
        busy = sum(1 for s in data if s.get("is_processing"))
        return total, busy
    except Exception:
        return None, None


def main():
    sbos_common.pg_exec(DDL)
    total, busy = sonic_slots()
    rows = sbos_common.pg_rows(
        """SELECT
             (SELECT count(*) FROM successbrian_os.qwen_task_queue
               WHERE status = 'pending'),
             (SELECT count(*) FROM successbrian_os.qwen_task_queue
               WHERE status = 'in_progress'),
             (SELECT EXTRACT(EPOCH FROM now() - min(created_at)) / 60
                FROM successbrian_os.qwen_task_queue
               WHERE status = 'pending')""")
    pending, in_prog, oldest_min = rows[0][0], rows[0][1], rows[0][2]
    sbos_common.pg_exec(
        """INSERT INTO successbrian_os.sonic_capacity_samples
             (slots_total, slots_busy, queue_pending, queue_in_progress,
              oldest_pending_age_min)
           VALUES (%s, %s, %s, %s, %s)""",
        (total, busy, pending, in_prog, oldest_min))
    print("sample: slots %s/%s busy, queue pending=%s in_progress=%s "
          "oldest_pending_min=%s" % (busy, total, pending, in_prog,
                                     oldest_min))
    return 0


if __name__ == "__main__":
    sys.exit(main())
