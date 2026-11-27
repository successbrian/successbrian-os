#!/usr/bin/env python3
"""Ingest dead-letter sweeper -- terminal disposition for os_ingester
items that can never route.

# @docmap successbrian_os.ingest_leg

WHY (census 2026-11-27, ingestion-completeness pass): the ingest
router (sbos_ingest_router.py) marks an item processed only when an
agent's interests match it. Items in a class that NO agent has ever
taken therefore sit unprocessed forever and are re-scanned every
15 minutes: 1,524 items at census, 1,516 of them dealsdesk
model_usage telemetry (0 routed out of 13,491 lifetime items) plus
8 ancient manual test dumps, the oldest 87 days.

RULE (data-driven, self-limiting): an item is dead-lettered only if
  * it is still unprocessed and older than AGE_DAYS, AND
  * its intel_type has NEVER produced a processed item in the
    table's history (a class that has routed even once is exempt --
    if a consumer appears later, the class heals itself), AND
  * it is not flagged for the review queue (review_queue is a
    boolean on this table; true means a human/desk review was
    requested and the item is not the sweeper's to disposition).
Dead-lettering sets processed=true and routing_target to
'dead-letter:no-consumer' -- the row stays fully readable; the
disposition is recorded, reversible (flip processed back), and
honest: it says no consumer exists, not that anyone read it.

Usage:
  ingest_deadletter.py [--dry-run] [--selftest]
Cron: daily 05:50, flock /tmp/ingest-deadletter.lock.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402

AGE_DAYS = 7
TARGET = "dead-letter:no-consumer"


def never_routed_types():
    # "Routed" means genuinely taken by the router: processed with a
    # real routing_target. Dead-lettered rows (this sweeper's own
    # output) must not reclassify a class as routed -- that would
    # stop the sweeper working and misread the gauge.
    rows = sbos_common.pg_rows(
        "SELECT intel_type FROM altair.os_ingester "
        "GROUP BY intel_type "
        "HAVING COUNT(*) FILTER (WHERE processed AND "
        "COALESCE(routing_target, '') NOT LIKE "
        "'dead-letter:%%') = 0") or []
    return [r[0] for r in rows]


def find_candidates():
    types = never_routed_types()
    if not types:
        return []
    rows = sbos_common.pg_rows(
        "SELECT id FROM altair.os_ingester "
        "WHERE NOT processed AND intel_type = ANY(%s) "
        "AND ingested_at < now() - interval '%s days' "
        "AND NOT COALESCE(review_queue, false) ORDER BY id",
        (types, AGE_DAYS)) or []
    return [int(r[0]) for r in rows]


def run(dry_run=False):
    ids = find_candidates()
    if dry_run:
        print(f"ingest-deadletter [dry-run]: {len(ids)} item(s) "
              f"in never-routed classes older than {AGE_DAYS}d")
        return len(ids)
    if ids:
        sbos_common.pg_exec(
            "UPDATE altair.os_ingester SET processed = true, "
            "routing_target = %s WHERE id = ANY(%s)",
            (TARGET, ids))
    print(f"ingest-deadletter: dead-lettered {len(ids)} item(s) "
          f"-> {TARGET}")
    return len(ids)


def selftest():
    types = never_routed_types()
    assert isinstance(types, list)
    ids = find_candidates()
    assert all(isinstance(i, int) for i in ids)
    # A routed class must never appear: verify against live data
    # that every candidate's type has zero processed rows.
    if ids:
        rows = sbos_common.pg_rows(
            "SELECT COUNT(*) FROM altair.os_ingester "
            "WHERE processed AND COALESCE(routing_target, '') "
            "NOT LIKE 'dead-letter:%%' AND intel_type IN "
            "(SELECT intel_type FROM altair.os_ingester "
            " WHERE id = ANY(%s))", (ids,)) or [(0,)]
        assert int(rows[0][0]) == 0, "candidate in a routed class!"
    print(f"INGEST_DEADLETTER_OK types={types} candidates={len(ids)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    run(dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
