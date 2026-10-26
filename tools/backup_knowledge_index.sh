#!/bin/bash
# backup_knowledge_index.sh — dump the Knowledge Index tables.
#
# Brian's master-index ruling (2026-10-25, capture #171) makes
# successbrian_os.knowledge_index + knowledge_tickets load-bearing:
# they hold what exists / what is current / what is superseded for
# the whole ecosystem. The 2026-10-23 audit's standing P0 was "no
# verified backups"; this script is the index's backup hook. Run it
# from cron or by hand; keeps the newest 14 dumps.
set -euo pipefail
DIR="$HOME/backups/knowledge-index"
mkdir -p "$DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DIR/knowledge-index-$STAMP.sql"
pg_dump -d ecosystem_central \
  -t successbrian_os.knowledge_index \
  -t successbrian_os.knowledge_tickets > "$OUT"
ls -1t "$DIR"/knowledge-index-*.sql | tail -n +15 | xargs -r rm -f
echo "BACKUP_OK $OUT"
