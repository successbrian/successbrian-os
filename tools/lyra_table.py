#!/usr/bin/env python3
"""Lyra's table — the operator CLI (Brian, 2026-11-08).

Lyra's table IS successbrian_os.clerk_checkins (settled by
Brian 2026-10-26): everything reports in to her there; she
sees by reading it. pulse() in sbos_common is the write
path; lyra_write / lyra_recent / lyra_stats are the named
views. This CLI is for operators and tests.

    lyra_table.py write --writer clerk --kind event \
        --title "..." [--body ...] [--source-ref ...]
    lyra_table.py recent [--limit 10] [--source clerk]
    lyra_table.py stats
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sbos_common as sc  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write")
    w.add_argument("--writer", required=True)
    w.add_argument("--kind", default="note")
    w.add_argument("--title", required=True)
    w.add_argument("--body", default="")
    w.add_argument("--source-ref", default="")
    w.add_argument("--priority", type=int, default=100)

    r = sub.add_parser("recent")
    r.add_argument("--limit", type=int, default=10)
    r.add_argument("--source", default="")

    sub.add_parser("stats")
    a = ap.parse_args()

    if a.cmd == "write":
        ok = sc.lyra_write(a.writer, a.kind, a.title, a.body,
                           None, a.source_ref, a.priority)
        print("row landed in Lyra's table (clerk_checkins)"
              if ok else "WRITE FAILED")
        return 0 if ok else 1
    elif a.cmd == "recent":
        print(json.dumps(sc.lyra_recent(a.limit, a.source),
                         indent=1, default=str))
    elif a.cmd == "stats":
        print(sc.lyra_stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
