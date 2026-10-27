#!/usr/bin/env python3
"""qa_freshness.py — PM QA check body for project verified-backups.

Pass (exit 0, prints 'qa-ok') only when ALL hold, read from the
doctor's state file (written by sbos_backup.py after every run):
  * last PG backup (all databases) finished < 36h ago
  * last local file backup finished < 36h ago
  * last restore drill verdict is PASS
"""
import json
import sys
from datetime import datetime, timezone

STATE = ("/home/successbrian/successbrian-os/tools/guardrails/"
         "state/backups_status.json")
MAX_AGE_S = 36 * 3600


def main():
    with open(STATE) as f:
        s = json.load(f)
    now = datetime.now(timezone.utc)
    for key in ("last_pg_backup", "last_file_backup_local"):
        v = s.get(key)
        if not v:
            print(f"qa-fail: {key} missing")
            return 1
        age = (now - datetime.fromisoformat(v["at"])).total_seconds()
        if age >= MAX_AGE_S:
            print(f"qa-fail: {key} is {age/3600:.1f}h old")
            return 1
    drill = s.get("last_drill") or {}
    if drill.get("verdict") != "PASS":
        print("qa-fail: last drill verdict is not PASS")
        return 1
    print("qa-ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
