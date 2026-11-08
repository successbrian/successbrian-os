#!/usr/bin/env python3
"""One creator window for ALL engine job queues.

Brian (2026-11-08): optimize the ecosystem for Sonic creating
Morpheus, Penny, and DeepSeek REAP 150B jobs. This is the one
CLI every producer (Sonic first among them) uses:

    engine_jobs.py --engine penny enqueue --by sonic \
        --kind gate-check --title "..." [--payload '{...}']
    engine_jobs.py --engine reap claim --worker reap-gamma
    engine_jobs.py --engine morpheus finish 3 --result "..."
    engine_jobs.py --engine penny stats

State lives in successbrian_os.{engine}_queue through the
shared sbos_common functions — this CLI is a window, not a
second implementation.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common as sc  # noqa: E402

ENGINES = ("morpheus", "penny", "reap", "sonic")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--engine", required=True, choices=ENGINES)
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
    eng = a.engine
    if a.cmd == "enqueue":
        if eng == "morpheus":
            jid = sc.morpheus_enqueue(
                a.by, a.kind, a.title, json.loads(a.payload),
                a.source_ref, a.priority)
        else:
            jid = sc.engine_job_enqueue(
                eng, a.by, a.kind, a.title,
                json.loads(a.payload), a.source_ref, a.priority)
        print(f"queued {eng} job #{jid}")
    elif a.cmd == "list":
        table = sc.ENGINE_JOB_TABLES[eng]
        sc.pg_exec(sc._engine_queue_ddl(table)
                   if eng != "morpheus" else sc.MORPHEUS_QUEUE_DDL)
        sql = (f"SELECT id, created_by, kind, title, status, "
               f"priority, created_at FROM {table}")
        params = []
        if a.status:
            sql += " WHERE status = %s"
            params.append(a.status)
        sql += " ORDER BY priority, created_at LIMIT %s"
        params.append(a.limit)
        for row in sc.pg_rows(sql, tuple(params)):
            print(row)
    elif a.cmd == "claim":
        kinds = [a.kind] if a.kind else None
        if eng == "morpheus":
            jobs = sc.morpheus_claim(a.worker, kinds, a.limit)
        else:
            jobs = sc.engine_job_claim(eng, a.worker, kinds,
                                       a.limit)
        print(json.dumps(jobs, indent=1, default=str))
    elif a.cmd == "finish":
        if eng == "morpheus":
            sc.morpheus_finish(a.id, a.result,
                               ok=not a.failed)
        else:
            sc.engine_job_finish(eng, a.id, a.result,
                                 ok=not a.failed)
        print(f"{eng} job #{a.id} finished")
    elif a.cmd == "release":
        if eng == "morpheus":
            sc.morpheus_release(a.id)
        else:
            sc.engine_job_release(eng, a.id)
        print(f"{eng} job #{a.id} released to queued")
    elif a.cmd == "stats":
        if eng == "morpheus":
            print(sc.morpheus_stats())
        else:
            print(sc.engine_job_stats(eng))


if __name__ == "__main__":
    main()
