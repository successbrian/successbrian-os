#!/bin/bash
# Finisher for the ruling-audit deep pass (installed 2026-11-15).
#
# The 2026-11-15 baseline deep pass was dispatched to gamma's REAP
# over the bus with no landing step wired — verdicts were piling up
# in the outbox unread. This wrapper runs ruling_audit.py's collect
# step every 15 minutes via cron: verdicts land in deep_results.jsonl
# as gamma finishes them, and when the dispatched set completes,
# collect runs the report step (flags.jsonl + one Intel Bridge
# capture per interpretation-risk flag) and drops a marker. On the
# marker, this wrapper removes its own cron entry — the job retires
# itself, nothing keeps firing after the work is done.
set -u
WD=/tmp/ruling-audit
LOG=/home/successbrian/logs/ruling-audit-collect.log
cd /home/successbrian/successbrian-os || exit 1
python3 tools/ruling_audit.py collect --workdir "$WD" >> "$LOG" 2>&1
if [ -f "$WD/collect_report_done.json" ]; then
  echo "$(date -Is) pipeline complete; retiring cron entry" >> "$LOG"
  crontab -l 2>/dev/null | grep -v 'ruling_audit_finish.sh' | crontab -
fi
