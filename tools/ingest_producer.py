#!/usr/bin/env python3
"""Ingest producer — the ecosystem side of the Intel Bridge mouth.

# @docmap successbrian_os.ingest_leg

DOCTRINE (Brian, 2026-11-14, verbatim): "chat agents should dump
dump dump. intel workers dump. everything dumps. the ecosystem
manages the rest from there."

Design consequences, binding on this leg:
  * Producers stay MAXIMALLY dumb and cheap. Dumping costs a
    producer one bridge_dump call in the bridge's existing shape —
    no classification, no cleaning, no dedupe, no judging at the
    mouth. Nothing in this leg may ever ask a producer for more.
  * ALL intelligence is downstream, here and in the worker:
    dedupe, near-duplicate collapse, triage, synthesis, drafting.
    Input is assumed abundant, messy, and duplicate-prone.
  * Freshness is measured as the ECOSYSTEM's lag (dump ->
    processed), never as producer behavior.

What this script does (deterministic, no model):
  notices Intel Bridge captures (atlas.scattered_captures) that
  this leg has not yet taken, in id order past the leg's epoch,
  and enqueues ONE 'ingest' job per small batch (<= BATCH) into
  the penny queue via sbos_common.engine_job_enqueue. The
  marker table successbrian_os.capture_ingest is the dedupe:
  a capture with a marker row is never enqueued twice; marker
  rows whose enqueue crashed (job_id NULL, aged) are repaired
  on the next run.

The epoch (state key 'epoch_capture_id') bounds the leg to
captures dumped after it was stood up; the pre-leg backlog was
dispositioned by the clerk / board / WF3 machinery and one-off
propagation passes, and is out of this leg's scope by design.
Set it once with --epoch N (the 2026-11-14 stand-up used 1755
so the seed batch is the day's doctrine filings #1756-1758).

Usage:
  ingest_producer.py [--epoch N] [--dry-run]
Cron: every 15 min, flock /tmp/ingest-producer.lock.
"""
import argparse
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
import sbos_common  # noqa: E402

BATCH = 8
# Sweep/extraction is Penny's class in Brian's ruled deliberation
# flow (Penny sweeps first; Morpheus deepens). The 2026-11-14
# proof run confirmed the sizing: a Morpheus sweep of a 3-capture
# batch timed out at 240s on the loaded alpha seat.
QUEUE = "penny"
KIND = "ingest"
CREATED_BY = "ingest-producer"

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.capture_ingest (
    capture_id  BIGINT PRIMARY KEY,
    job_id      BIGINT,
    queue       TEXT,
    enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    draft_path  TEXT,
    sweep_engine TEXT,
    sweep_host  TEXT
);
CREATE TABLE IF NOT EXISTS successbrian_os.capture_ingest_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
ALTER TABLE successbrian_os.capture_ingest
    ADD COLUMN IF NOT EXISTS recovery_count INT NOT NULL DEFAULT 0;
ALTER TABLE successbrian_os.capture_ingest
    ADD COLUMN IF NOT EXISTS last_recovery_at TIMESTAMPTZ;
"""


def ensure_schema():
    sbos_common.pg_exec(DDL)


def get_epoch():
    v = sbos_common.pg_one(
        "SELECT value FROM successbrian_os.capture_ingest_state "
        "WHERE key = 'epoch_capture_id'")
    return int(v) if v is not None else None


def set_epoch(n):
    sbos_common.pg_exec(
        "INSERT INTO successbrian_os.capture_ingest_state "
        "(key, value) VALUES ('epoch_capture_id', %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (str(int(n)),))


def enqueue_batch(ids):
    """Enqueue one ingest job for ids; stamp their marker rows."""
    job_id = sbos_common.engine_job_enqueue(
        QUEUE, CREATED_BY, KIND,
        f"Ingest sweep: {len(ids)} capture(s) "
        f"#{ids[0]}-#{ids[-1]}",
        payload={"capture_ids": list(ids)},
        source_ref="intel-bridge", priority=90)
    sbos_common.pg_exec(
        "UPDATE successbrian_os.capture_ingest "
        "SET job_id = %s, queue = %s, enqueued_at = now() "
        "WHERE capture_id = ANY(%s)",
        (job_id, QUEUE, list(ids)))
    return job_id


RECOVERY_CAP = 1  # a capture is recovered at most once on the fast
# path; a second failure strands it visibly for review, never
# re-loops it.
RECOVERY_HARD_CAP = 4  # lifetime ceiling, all classes combined.
RECOVERY_RETRY_AFTER_H = 72  # a TIMEOUT failure is environmental
# (seat/bus saturation), not a property of the capture: once the
# failed job has been dead this long, one more recovery is allowed,
# at most one per window, up to the hard cap. Added 2026-11-27
# (ingestion-completeness pass): the Nov 15-22 saturation window
# timeout-failed 20 jobs / 125 captures, every one burned its single
# fast-path recovery into the same saturated window and stranded
# permanently behind a cap written for poison captures.


def find_recoverable(limit=400, only=None):
    """Marker rows stranded behind FAILED penny jobs.

    Class 1 (fast path): recovery_count < RECOVERY_CAP.
    Class 2 (aged timeout): the current job failed by timeout, has
    been finished for > RECOVERY_RETRY_AFTER_H hours, the last
    recovery (if any) is older than the same window, and the
    lifetime count is under RECOVERY_HARD_CAP.

    The EXISTS guard skips phantom markers whose capture was
    deleted after enqueue (job 535: 7 enqueued, 6 deleted by a
    bridge discard path); clean_phantoms() removes those markers.
    """
    sql = (
        "SELECT m.capture_id FROM successbrian_os.capture_ingest m "
        "JOIN successbrian_os.penny_queue q ON q.id = m.job_id "
        "WHERE m.processed_at IS NULL AND q.status = 'failed' "
        "AND EXISTS (SELECT 1 FROM atlas.scattered_captures c "
        "            WHERE c.id = m.capture_id) "
        "AND (COALESCE(m.recovery_count, 0) < %s "
        "     OR (COALESCE(m.recovery_count, 0) < %s "
        "         AND q.result::text ILIKE '%%timed out%%' "
        "         AND q.finished_at < now() - interval '%s hours' "
        "         AND (m.last_recovery_at IS NULL "
        "              OR m.last_recovery_at < "
        "                  now() - interval '%s hours'))) ")
    params = [RECOVERY_CAP, RECOVERY_HARD_CAP,
              RECOVERY_RETRY_AFTER_H, RECOVERY_RETRY_AFTER_H]
    if only is not None:
        sql += "AND m.capture_id = ANY(%s) "
        params.append(list(only))
    sql += "ORDER BY m.capture_id LIMIT %s"
    params.append(int(limit))
    rows = sbos_common.pg_rows(sql, tuple(params)) or []
    return [int(r[0]) for r in rows]


def clean_phantoms():
    """Delete unprocessed markers whose capture no longer exists.

    A marker for a deleted capture can never be processed; leaving
    it inflates the unprocessed count forever (job 535's 6). Only
    unprocessed markers are removed -- processed markers are the
    leg's history. Returns the number removed.
    """
    rows = sbos_common.pg_rows(
        "SELECT capture_id FROM successbrian_os.capture_ingest m "
        "WHERE m.processed_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM atlas.scattered_captures c "
        " WHERE c.id = m.capture_id)") or []
    ids = [int(r[0]) for r in rows]
    if ids:
        sbos_common.pg_exec(
            "DELETE FROM successbrian_os.capture_ingest "
            "WHERE capture_id = ANY(%s) AND processed_at IS NULL",
            (ids,))
        print(f"ingest-producer: removed {len(ids)} phantom "
              f"marker(s) for deleted captures: {ids}")
    return len(ids)


def recover_failed(dry_run=False, limit=400, only=None):
    """Re-enqueue stranded captures as fresh jobs, batches of <=BATCH.

    Returns (recovered_captures, jobs_made). Fast-path recoveries
    are capped at RECOVERY_CAP per capture; aged TIMEOUT failures
    earn further recoveries under RECOVERY_HARD_CAP (see
    find_recoverable). A non-timeout failure past the fast-path cap
    still strands visibly and is never re-looped. Phantom markers
    (capture deleted) are cleaned first so counts stay true.
    """
    clean_phantoms()
    ids = find_recoverable(limit=limit, only=only)
    if dry_run:
        print(f"ingest-producer [recover dry-run]: {len(ids)} "
              f"recoverable capture(s) behind failed jobs")
        return len(ids), 0
    made = 0
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        job_id = enqueue_batch(chunk)
        sbos_common.pg_exec(
            "UPDATE successbrian_os.capture_ingest "
            "SET recovery_count = COALESCE(recovery_count, 0) + 1, "
            "last_recovery_at = now() "
            "WHERE capture_id = ANY(%s)", (chunk,))
        made += 1
        print(f"ingest-producer: recovered job {job_id} -> "
              f"{QUEUE} queue, captures {chunk}")
    if not made:
        print("ingest-producer: nothing recoverable behind failed jobs")
    return len(ids), made


def run(dry_run=False):
    ensure_schema()
    epoch = get_epoch()
    if epoch is None:
        cur_max = sbos_common.pg_one(
            "SELECT COALESCE(MAX(id), 0) "
            "FROM atlas.scattered_captures")
        set_epoch(cur_max)
        print(f"ingest-producer: epoch initialized to {cur_max} "
              f"(leg covers future dumps only)")
        return 0
    # Repair: marker rows whose enqueue never landed a job id.
    repair = sbos_common.pg_rows(
        "SELECT capture_id FROM successbrian_os.capture_ingest "
        "WHERE job_id IS NULL AND processed_at IS NULL "
        "AND enqueued_at < now() - interval '10 minutes' "
        "ORDER BY capture_id LIMIT 200") or []
    repair_ids = [int(r[0]) for r in repair]
    # New: captures past the epoch with no marker row at all.
    rows = sbos_common.pg_rows(
        "SELECT c.id FROM atlas.scattered_captures c "
        "WHERE c.id > %s AND NOT EXISTS ("
        "  SELECT 1 FROM successbrian_os.capture_ingest m "
        "  WHERE m.capture_id = c.id) "
        "ORDER BY c.id LIMIT 400", (epoch,)) or []
    new_ids = [int(r[0]) for r in rows]
    if dry_run:
        print(f"ingest-producer [dry-run]: epoch={epoch} "
              f"repair={len(repair_ids)} new={len(new_ids)}")
        return 0
    made = 0
    for ids in (repair_ids, new_ids):
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            if ids is new_ids:
                # Claim the rows first; only rows we actually
                # inserted are ours to enqueue (dedupe vs a
                # concurrent run — cron is flocked, belt+braces).
                ins = sbos_common.pg_rows(
                    "INSERT INTO successbrian_os.capture_ingest "
                    "(capture_id) SELECT unnest(%s::bigint[]) "
                    "ON CONFLICT (capture_id) DO NOTHING "
                    "RETURNING capture_id", (chunk,)) or []
                chunk = [int(r[0]) for r in ins]
                if not chunk:
                    continue
            job_id = enqueue_batch(chunk)
            made += 1
            print(f"ingest-producer: job {job_id} -> "
                  f"{QUEUE} queue, captures {chunk}")
    if not made:
        print(f"ingest-producer: nothing new past epoch {epoch}")
    return 0


def selftest():
    """Live disposable probe: one labeled SELFTEST capture through
    fail -> recover -> cap, then consumed. The probe capture row stays
    in the bridge labeled SELFTEST (the B8 disposable pattern); no
    queued/claimed job and no unprocessed marker is left behind.
    """
    probe_id = sbos_common.pg_one(
        "INSERT INTO atlas.scattered_captures "
        "(title, raw_text, context, cluster_key) VALUES "
        "(%s, %s, %s, %s) RETURNING id",
        ("SELFTEST disposable -- ingest recovery probe (ignore)",
         "selftest raw", "selftest ctx", "selftest-recovery"))
    assert probe_id, "probe capture insert failed"
    job_id = sbos_common.engine_job_enqueue(
        QUEUE, "ingest-producer-selftest", KIND,
        "SELFTEST probe failed job",
        payload={"capture_ids": [probe_id]},
        source_ref="selftest", priority=90)
    sbos_common.engine_job_finish(
        QUEUE, job_id, "SELFTEST probe: failed", ok=False)
    sbos_common.pg_exec(
        "INSERT INTO successbrian_os.capture_ingest "
        "(capture_id, job_id, queue) VALUES (%s, %s, %s)",
        (probe_id, job_id, QUEUE))
    assert probe_id in find_recoverable(only=[probe_id]), \
        "probe capture not found recoverable"
    rec, made = recover_failed(only=[probe_id])
    assert (rec, made) == (1, 1), (rec, made)
    row = sbos_common.pg_rows(
        "SELECT job_id, recovery_count FROM "
        "successbrian_os.capture_ingest WHERE capture_id = %s",
        (probe_id,)) or []
    assert row and row[0][0] != job_id and int(row[0][1]) == 1, row
    new_job = int(row[0][0])
    assert probe_id not in find_recoverable(only=[probe_id]), \
        "cap did not hold: probe recoverable twice"
    rec2, made2 = recover_failed(only=[probe_id])
    assert (rec2, made2) == (0, 0), (rec2, made2)
    assert recover_failed(dry_run=True, only=[probe_id]) == (0, 0)
    # Consume the probe: the recovery job is finished done by the
    # selftest (never claimed by the worker) and the marker is
    # stamped processed, so nothing is left queued or unprocessed.
    sbos_common.engine_job_finish(
        QUEUE, new_job, "SELFTEST probe: recovery consumed", ok=True)
    sbos_common.pg_exec(
        "UPDATE successbrian_os.capture_ingest "
        "SET processed_at = now() WHERE capture_id = %s", (probe_id,))
    print("INGEST_PRODUCER_OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epoch", type=int, default=None,
                    help="set the leg's epoch capture id and exit")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recover-failed", action="store_true",
                    help="re-enqueue captures stranded behind failed "
                         "jobs (fast-path cap RECOVERY_CAP; aged "
                         "timeout failures retry under the hard cap)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    ensure_schema()
    if a.selftest:
        return selftest()
    if a.recover_failed:
        recover_failed(dry_run=a.dry_run)
        return 0
    if a.epoch is not None:
        set_epoch(a.epoch)
        print(f"ingest-producer: epoch set to {a.epoch}")
        return 0
    return run(dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
