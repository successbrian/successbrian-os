#!/usr/bin/env python3
"""Ingestion completeness gauge -- Brian's directive 2026-11-27:
"I want the system to fully process the ingestion."

DEFINITION: an ingestion stream is fully processed when every item
has passed every stage the system itself can perform, and the only
items still waiting are genuine Brian-residue sitting in his inbox
(successbrian_os.pending_questions). An item stalled in a MACHINE
stage past its leg's age threshold -- or Brian-residue parked
anywhere other than the inbox -- makes the whole gauge fail.

Legs (thresholds are per-stream, stated here, honest defaults):
  captures_raw     raw captures older than 4h (clerk sweep is hourly)
  ingest_leg       capture_ingest markers unprocessed > 96h (the
                   recovery design renews timeout eligibility at
                   72h; past 96h unprocessed means stranded again)
  distill_parked   distill_log error-parked rows older than 7d
                   (parked = the machine gave up after its retry cap)
  job_grading      job_tracking rows with skill_gaps NULL > 48h
                   (grading leg runs daily)
  kb_dead_targets  knowledge_bridge messages unread > 7d addressed
                   to targets with ZERO lifetime reads (no consumer
                   exists; red until Brian rules on the channels --
                   residue question is in his inbox, 2026-11-27)
  os_ingester      unprocessed os_ingester items > 48h in classes
                   that HAVE routed before (a real router stall), or
                   > 8d in never-routed classes (the dead-letter
                   sweeper dispositions those at 7d, daily)
  tray_unaccounted unsorted-tray documents the clerk-tray loop has
                   not accounted (same measure as QA 814)
  intel_freshness  newest public.intel_items fetch older than 48h
                   (the scraper is daily)
  residue_outside  triaged captures whose depth is brian_decision /
                   brian_review, unruled, with NO open question in
                   Brian's inbox referencing them

Companion (printed, not pass/fail): the triaged-unruled backlog --
the ruling stage is Brian/board work (friction #72; bulk-ruling
authority is Brian's pending call), surfaced in his inbox and the
review passes, not a machine stall this gauge may hide or fix.

Output: one LEG line per leg, then INGESTION_COMPLETE_OK or
INGESTION_INCOMPLETE. Exit 0 iff complete.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402

legs = []  # (name, breach_count, detail)


def leg(name, sql, detail_fmt="count={} oldest_h={}"):
    rows = sbos_common.pg_rows(sql) or [(0, 0)]
    count, oldest_h = int(rows[0][0] or 0), rows[0][1]
    legs.append((name, count,
                 detail_fmt.format(count, oldest_h)))


def main():
    leg("captures_raw",
        "SELECT COUNT(*), ROUND(EXTRACT(EPOCH FROM "
        "(now()-MIN(created_at)))/3600) FROM atlas.scattered_captures "
        "WHERE status='raw' AND created_at < now()-interval '4 hours'")
    leg("ingest_leg",
        "SELECT COUNT(*), ROUND(EXTRACT(EPOCH FROM "
        "(now()-MIN(enqueued_at)))/3600) FROM "
        "successbrian_os.capture_ingest WHERE processed_at IS NULL "
        "AND enqueued_at < now()-interval '96 hours'")
    leg("distill_parked",
        "SELECT COUNT(*), ROUND(EXTRACT(EPOCH FROM "
        "(now()-MIN(created_at)))/3600) FROM altair.distill_log "
        "WHERE outcome='error-parked' "
        "AND created_at < now()-interval '7 days'")
    leg("job_grading",
        "SELECT COUNT(*), ROUND(EXTRACT(EPOCH FROM "
        "(now()-MIN(discovered_at)))/3600) FROM public.job_tracking "
        "WHERE skill_gaps IS NULL "
        "AND discovered_at < now()-interval '48 hours'")
    leg("kb_dead_targets",
        "SELECT COUNT(*), ROUND(EXTRACT(EPOCH FROM "
        "(now()-MIN(k.created_at)))/3600) FROM "
        "altair.knowledge_bridge k WHERE k.read_at IS NULL "
        "AND k.created_at < now()-interval '7 days' AND NOT EXISTS "
        "(SELECT 1 FROM altair.knowledge_bridge r "
        " WHERE r.target = k.target AND r.read_at IS NOT NULL)")
    leg("os_ingester",
        "SELECT COUNT(*), ROUND(EXTRACT(EPOCH FROM "
        "(now()-MIN(ingested_at)))/3600) FROM altair.os_ingester o "
        "WHERE NOT o.processed AND ("
        " (EXISTS (SELECT 1 FROM altair.os_ingester p "
        "   WHERE p.intel_type = o.intel_type AND p.processed "
        "   AND COALESCE(p.routing_target, '') NOT LIKE "
        "   'dead-letter:%%') "
        "  AND o.ingested_at < now()-interval '48 hours') OR "
        " (NOT EXISTS (SELECT 1 FROM altair.os_ingester p "
        "   WHERE p.intel_type = o.intel_type AND p.processed "
        "   AND COALESCE(p.routing_target, '') NOT LIKE "
        "   'dead-letter:%%') "
        "  AND o.ingested_at < now()-interval '8 days'))")
    # Tray leg: same command QA 814 runs; parse its accounting.
    try:
        out = subprocess.run(
            ["python3",
             "/home/successbrian/successbrian-os/board/"
             "filing_flow_qa.py", "drainage"],
            capture_output=True, text=True, timeout=240).stdout
        unacc = None
        import re
        m = re.search(r"unaccounted=(\d+)", out)
        unacc = int(m.group(1)) if m else None
        if unacc is None:
            legs.append(("tray_unaccounted", 1,
                         "drainage measure unreadable: " +
                         out.strip()[:120]))
        else:
            legs.append(("tray_unaccounted", unacc,
                         f"unaccounted={unacc}"))
    except Exception as e:  # cannot verify = not complete
        legs.append(("tray_unaccounted", 1, f"measure failed: {e}"))
    leg("intel_freshness",
        "SELECT CASE WHEN MAX(fetched_at) < now()-interval "
        "'48 hours' THEN 1 ELSE 0 END, ROUND(EXTRACT(EPOCH FROM "
        "(now()-MAX(fetched_at)))/3600) FROM public.intel_items")
    leg("residue_outside_inbox",
        "SELECT COUNT(*), ROUND(EXTRACT(EPOCH FROM "
        "(now()-MIN(c.created_at)))/3600) FROM "
        "atlas.scattered_captures c WHERE c.status='triaged' "
        "AND c.ruled_at IS NULL AND c.depth IN "
        "('brian_decision','brian_review') AND NOT EXISTS "
        "(SELECT 1 FROM successbrian_os.pending_questions p "
        " WHERE p.status='open' AND p.question LIKE "
        " 'Capture #' || c.id || ' %')")

    bad = []
    for name, count, detail in legs:
        state = "BREACH" if count > 0 else "OK"
        if count > 0:
            bad.append(name)
        print(f"LEG {name} {state} {detail}")
    info = sbos_common.pg_rows(
        "SELECT COUNT(*) FROM atlas.scattered_captures "
        "WHERE status='triaged' AND ruled_at IS NULL") or [(0,)]
    print(f"INFO triaged_unruled={int(info[0][0])} "
          "(Brian/board ruling stage, friction #72 -- not a "
          "machine-stage stall)")
    if bad:
        print("INGESTION_INCOMPLETE legs=" + ",".join(bad))
        return 1
    print("INGESTION_COMPLETE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
