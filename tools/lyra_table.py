#!/usr/bin/env python3
"""Lyra's table — the operator CLI (Brian, 2026-11-08).

Everything in the ecosystem writes to Lyra's table; Lyra
sees by reading it. The ONE write/read path lives in
sbos_common (lyra_write / lyra_read / lyra_handled /
lyra_stats). This CLI is for operators and tests.

  engine-style usage:
    lyra_table.py write --writer clerk --kind event \
        --title "..." [--body ...] [--source-ref ...]
    lyra_table.py read [--limit 10] [--kind event,alert]
    lyra_table.py handled <id> [--note "..."]
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

    r = sub.add_parser("read")
    r.add_argument("--limit", type=int, default=10)
    r.add_argument("--kind", default="")

    h = sub.add_parser("handled")
    h.add_argument("id", type=int)
    h.add_argument("--note", default="")

    sub.add_parser("stats")
    a = ap.parse_args()

    if a.cmd == "write":
        rid = sc.lyra_write(a.writer, a.kind, a.title, a.body,
                            None, a.source_ref, a.priority)
        print(f"wrote lyra_table row #{rid}")
    elif a.cmd == "read":
        kinds = [k for k in a.kind.split(",") if k] or None
        rows = sc.lyra_read(a.limit, kinds)
        for row in rows:
            row["payload"] = row.get("payload") or {}
        print(json.dumps(rows, indent=1, default=str))
    elif a.cmd == "handled":
        ok = sc.lyra_handled(a.id, a.note)
        print(f"row #{a.id} handled" if ok
              else f"row #{a.id} not in read state")
        return 0 if ok else 1
    elif a.cmd == "stats":
        print(sc.lyra_stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
