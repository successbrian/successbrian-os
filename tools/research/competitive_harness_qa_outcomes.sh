#!/bin/bash
# competitive_harness_qa_outcomes.sh - QA probe for the competitive
# research harness: proves OUTCOMES are moving (a question reached
# 'routed' in the last 7d, or a study was collected, or routes were
# filed) - not mere activity. The distiller lesson (2026-11-23): a
# watcher that only proves the machine is running is worthless;
# this one requires studies landing and outputs routing.
n=$(psql -d ecosystem_central -Atc "select (select count(*) from successbrian_os.research_questions where status='routed' and routed_at > now() - interval '7 days') + (select count(*) from successbrian_os.research_questions where collected_at > now() - interval '7 days') + (select count(*) from successbrian_os.research_routes where created_at > now() - interval '7 days')")
if [ "${n:-0}" -gt 0 ] 2>/dev/null; then
  echo "RESEARCH-OUTCOMES-MOVING-$n"
else
  echo "RESEARCH-OUTCOMES-STALLED"
  exit 1
fi
