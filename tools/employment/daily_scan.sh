#!/bin/bash
# employment-daily-scan -- restored 2026-11-27 (ingestion-completeness
# pass). The chain scan_mailbox -> grade_skills -> extract_entities
# was called by a daily cron of this name that no longer exists in
# any crontab on alpha, and all three scripts shell out to
# ~/workspace/bin/kssh, which existed nowhere -- the chain was dead
# twice over. The on-alpha kssh shim (~/workspace/bin/kssh) runs
# their commands locally; this wrapper restores the schedule.
# Archive: the Outlook download on alpha (frozen 2026-10-03; the
# download leg itself is a separate, connector-side step).
set -u
cd /home/successbrian/successbrian-os
ARCH=/home/successbrian/mail-archive/brian.lathe@outlook.com/cur
python3 tools/employment/scan_mailbox.py --archive-dir "$ARCH"
python3 tools/employment/grade_skills.py
python3 tools/employment/extract_entities.py --archive-dir "$ARCH" --limit 100
