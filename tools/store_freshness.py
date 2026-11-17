#!/usr/bin/env python3
"""
store_freshness — the alarm that should have screamed in November.

Brian's diagnosis (2026-11-17): altair.brian_decisions froze
2026-10-31 and altair.brian_learnings froze 2026-11-02, and NOTHING
noticed for over two weeks — tools kept binding answers to a stale
record. This check makes that silence impossible: if any watched
store goes more than THRESHOLD_HOURS without a write, it files a
loud Intel Bridge capture (the channel Brian's system actually
reads) naming the store, its last write, and its age.

Watched stores:
  altair.brian_decisions   (answered_at)
  altair.brian_learnings   (created_at)
  atlas.scattered_captures (created_at) — intake itself

Run daily by cron. Exit code 0 = all fresh, 1 = at least one stale
(the capture is the alarm; the exit code is for logs).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_research import _one, _exec  # noqa: E402

THRESHOLD_HOURS = 72

STORES = [
    ("altair.brian_decisions", "answered_at"),
    ("altair.brian_learnings", "created_at"),
    ("atlas.scattered_captures", "created_at"),
]


def check():
    stale = []
    for table, col in STORES:
        row = _one("SELECT max(%s) AS last_write, count(*) AS n, "
                   "extract(epoch FROM (now() - max(%s))) / 3600 "
                   "AS age_h FROM %s" % (col, col, table))
        last = row["last_write"]
        if last is None:
            stale.append((table, "NEVER WRITTEN", None))
            continue
        age_h = row["age_h"]
        print("%s: %d rows, last write %s (%.1fh ago)"
              % (table, row["n"], last, age_h))
        if age_h > THRESHOLD_HOURS:
            stale.append((table, str(last), age_h))
    for table, last, age_h in stale:
        age = ("%.0fh" % age_h) if age_h else "n/a"
        _exec("INSERT INTO atlas.scattered_captures (title, raw_text,"
              " status, workspace_slug) VALUES (%s, %s, 'raw', "
              "'successbrian-os')",
              ("FRESHNESS ALARM: %s stale — last write %s (%s ago)"
               % (table, last, age),
               "store_freshness: %s has had no writes for %s "
               "(threshold %dh). Last write: %s. A silent store means "
               "the distillation pipe is broken again — see the "
               "2026-11-17 diagnosis (decisions froze 2026-10-31, "
               "learnings 2026-11-02, unnoticed for 17 days)."
               % (table, age, THRESHOLD_HOURS, last)))
        print("ALARM FILED for %s" % table)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(check())
