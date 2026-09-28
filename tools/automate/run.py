#!/usr/bin/env python3
"""
Automation runner for SuccessBrian OS.

PURPOSE:
    CLI entry point for the automation engine: evaluate rules, act at
    >=90% confidence, report what happened.

WHY:
    Heartbeats, night shifts, and humans all need the same invocation.
    Dry-run is the default so exploration is safe; --live is the explicit
    "I mean it" flag.

CALLED BY:
    - Sunday heartbeat (STEP 0, --live)
    - Night shift check-ins (--live)
    - Humans: --dry-run to preview, --snapshot to inspect live state

NOTES:
    Dry-run is the default and --live is the explicit opt-in — keep it
    that way. Heartbeat workers pass --live only after their own checks.

Usage:
    python3 tools/automate/run.py --dry-run   # preview (default)
    python3 tools/automate/run.py --live       # act for real
    python3 tools/automate/run.py --snapshot   # just print live state
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from automate.engine import run_rules
from automate.rules import RULES
from automate.watchers import snapshot


def main() -> int:
    ap = argparse.ArgumentParser(description="SuccessBrian OS automation.")
    ap.add_argument("--live", action="store_true",
                    help="act for real (default is dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="preview only (this is the default)")
    ap.add_argument("--snapshot", action="store_true",
                    help="print live state snapshot and exit")
    args = ap.parse_args()

    if args.snapshot:
        print(json.dumps(snapshot(), indent=2))
        return 0

    dry_run = not args.live
    print(f"Evaluating {len(RULES)} rules "
          f"({'DRY RUN' if dry_run else 'LIVE'})...")
    summary = run_rules(RULES, dry_run=dry_run)

    for bucket in ("acted", "queued", "needs_research", "skipped"):
        items = summary[bucket]
        print(f"\n[{bucket}] {len(items)}")
        for name, detail in items[:10]:
            print(f"  - {name}: {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
