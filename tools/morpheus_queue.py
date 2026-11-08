#!/usr/bin/env python3
"""The ONE common Morpheus work queue — operator CLI.

Brian (2026-11-08): "everything in the ecosystem that is
making all these 'morpheus' jobs... we need one common
morpheus work queue."

    morpheus_queue.py enqueue --by sonic --kind bible-compliance \
        --title "..." [--payload '{...}'] [--source-ref X] \
        [--priority 100]
    morpheus_queue.py list [--status queued] [--limit 20]
    morpheus_queue.py claim --worker morpheus-alpha \
        [--kind bible-compliance] [--limit 1]
    morpheus_queue.py finish <id> --result "..." [--failed]
    morpheus_queue.py release <id>
    morpheus_queue.py stats

All state lives in successbrian_os.morpheus_queue through the
shared sbos_common functions — this CLI is a window, not a
second implementation.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common as sc  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enqueue")
    e.add_argument("--by", required=True)
    e.add_argument("--kind", required=True)
    e.add_argument("--title", required=True)
    e.add_argument("--payload", default="{}")
    e.add_argument("--source-ref", default="")
    e.add_argument("--priority", type=int, default=100)

    li = sub.add_parser("list")
    li.add_argument("--status", default="")
    li.add_argument("--limit", type=int, default=20)

    c = sub.add_parser("claim")
    c.add_argument("--worker", required=True)
    c.add_argument("--kind", default="")
    c.add_argument("--limit", type=int, default=1)

    f = sub.add_parser("finish")
    f.add_argument("id", type=int)
    f.add_argument("--result", default="")
    f.add_argument("--failed", action="store_true")

    r = sub.add_parser("release")
    r.add_argument("id", type=int)

    sub.add_parser("stats")

    a = p.parse_args()
    if a.cmd == "enqueue":
        jid = sc.morpheus_enqueue(
            a.by, a.kind, a.title, json.loads(a.payload),
            a.source_ref, a.priority)
        print(f"queued morpheus job #{jid}")
    elif a.cmd == "list":
        sc.pg_exec(sc.MORPHEUS_QUEUE_DDL)
        sql = ("SELECT id, created_by, kind, title, status, "
               "priority, created_at FROM "
               "successbrian_os.morpheus_queue")
        params = []
        if a.status:
            sql += " WHERE status = %s"
            params.append(a.status)
        sql += " ORDER BY priority, created_at LIMIT %s"
        params.append(a.limit)
        for row in sc.pg_rows(sql, tuple(params)):
            print(row)
    elif a.cmd == "claim":
        jobs = sc.morpheus_claim(
            a.worker, [a.kind] if a.kind else None, a.limit)
        print(json.dumps(jobs, indent=1, default=str))
    elif a.cmd == "finish":
        sc.morpheus_finish(a.id, a.result, ok=not a.failed)
        print(f"job #{a.id} finished")
    elif a.cmd == "release":
        sc.morpheus_release(a.id)
        print(f"job #{a.id} released to queued")
    elif a.cmd == "stats":
        print(sc.morpheus_stats())


if __name__ == "__main__":
    main()
