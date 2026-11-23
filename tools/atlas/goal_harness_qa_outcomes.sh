#!/bin/bash
# goal_harness_qa_outcomes.sh - QA probe for the goal harness:
# proves OUTCOMES are moving (a harness look collected in the
# last 26h, a movement record in the last 8d, or a harness claim
# finished in the last 7d) - not mere activity. The distiller
# lesson (2026-11-23): a watcher that only proves the machine is
# running is worthless; this one requires filings/completions.
n=$(psql -d ecosystem_central -Atc "select (select count(*) from successbrian_os.einstein_passes where probe_id like 'harness-look-%' and status='collected' and collected_at > now() - interval '26 hours') + (select count(*) from successbrian_os.harness_movements where measured_at > now() - interval '8 days') + (select count(*) from successbrian_os.harness_claims where outcome='done' and finished_at > now() - interval '7 days')")
if [ "${n:-0}" -gt 0 ] 2>/dev/null; then
  echo "HARNESS-OUTCOMES-MOVING-$n"
else
  echo "HARNESS-OUTCOMES-STALLED"
  exit 1
fi
