#!/usr/bin/env python3
"""
Sync phone notifications into the intake queue.

PURPOSE:
    Copy rows from public.phone_notifications into public.intake_items so
    every phone notification waits in the triage queue like everything else,
    instead of being treated as implicitly important on arrival.

WHY:
    Brian 2026-09-27: incoming volume never implies importance. The phone
    notification logger writes to phone_notifications every 15 minutes; without
    this sync those rows would sit in a table nobody triages. The intake
    queue is the single airlock for all incoming items, so notifications
    join it here — researched by intake_triage before anything surfaces.

CALLED BY:
    - Future intake-sync cron (not yet created — Brian hasn't set cadence).
    - Humans / shift workers: python3 tools/intake_sync.py [--dry-run]

NOTES:
    - Append-only and idempotent: UNIQUE(source, source_id) on
      ('phone_notification', dedup_key) plus ON CONFLICT DO NOTHING, so
      re-running copies nothing new. No watermark needed.
    - Deliberately does NOT touch /home/successbrian/notifications/ingest.py
      on k11: the prod ingest path stays untouched; this sync reads the table
      it already maintains. Less risk than modifying ingest.
    - title falls back to app name when the notification has no title;
      sender falls back to app. url is left NULL — phone notifications
      rarely carry URLs; triage research finds them if needed.
"""

import argparse
import subprocess
import sys
from pathlib import Path

KSSH = Path.home() / "workspace" / "bin" / "kssh"


def pg(query: str, timeout: int = 120) -> str:
    out = subprocess.run(
        [str(KSSH), f'psql -d ecosystem_central -t -A -c "{query}"'],
        capture_output=True, text=True, timeout=timeout,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:300]}")
    return out.stdout.strip()


SYNC_SQL = """
INSERT INTO public.intake_items
    (source, source_id, received_at, title, sender, url, raw, status)
SELECT
    'phone_notification',
    dedup_key,
    COALESCE(ts_utc, ingested_at, now()),
    COALESCE(NULLIF(title, ''), app, 'notification'),
    COALESCE(NULLIF(sender, ''), app),
    NULL,
    jsonb_build_object(
        'app', app, 'app_package', app_package, 'body', body,
        'category', category, 'notif_key', notif_key,
        'device_id', device_id, 'device_name', device_name,
        'dedup_key', dedup_key),
    'pending'
FROM public.phone_notifications
ON CONFLICT (source, source_id) DO NOTHING;
"""


def count_new() -> int:
    row = pg(
        "SELECT count(*) FROM public.phone_notifications p "
        "WHERE NOT EXISTS (SELECT 1 FROM public.intake_items i "
        "WHERE i.source='phone_notification' AND i.source_id=p.dedup_key);"
    )
    return int(row or 0)


def main() -> int:
    p = argparse.ArgumentParser(description="Sync phone notifications to intake")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    n = count_new()
    if a.dry_run:
        print(f"DRY RUN: {n} phone notification(s) would be queued")
        return 0
    if n == 0:
        print("0 new phone notifications — nothing to sync")
        return 0
    pg(SYNC_SQL)
    print(f"synced {n} phone notification(s) into intake_items as pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
