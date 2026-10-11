#!/bin/bash
# P5 hourly loop (new Vera field capture). Runs ON k11-alpha via cron.
# Order: request poll (missions from P4 proposals) -> completion check ->
# ingestion (OCR screenshots -> typed edges).
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${P5_LOG:-/home/successbrian/logs/relationship_intel/p5_hourly.log}"
mkdir -p "$(dirname "$LOG")"

{
echo "=== P5 hourly run $(date -u +%FT%TZ) ==="
python3 "$DIR/p5_missions.py" --poll --check-completions
python3 "$DIR/p5_ingest.py" --cron
echo "=== P5 hourly run end $(date -u +%FT%TZ) ==="
} >> "$LOG" 2>&1
