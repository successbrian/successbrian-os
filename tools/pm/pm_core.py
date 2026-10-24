#!/usr/bin/env python3
"""SBOS main PM — the control plane for the one coded loop.

Brian's design (2026-10-24): SuccessBrian OS core and its main PM control
everything. Every step of work is a database row (pm_steps) carrying status,
priority, dependencies, actor, and timestamps, so the system always knows
what is happening, when, and where. Every decision any layer makes is
written to ONE stream (pm_decisions) as it is made — that stream is what
Altair reports from and what the dashboard's "100 decisions without Brian"
list reads.

Scheduling rule (slice 1): a queued step is READY when all its dependencies
are done. claim() hands out ready steps highest-priority first (ties:
oldest first). Steps wait only on true dependencies, priority, or capacity
— never on Brian and never on an unrelated step ahead of them.

Origin discipline: a step/decision counts as "without Brian" only when
origin='ecosystem' — no prompt, approval, nudge, or task from Brian behind
it. Brian-assigned work is origin='brian' and never counts toward the 100.

State home: PostgreSQL (successbrian_os.pm_steps / pm_step_deps /
pm_decisions in ecosystem_central). Logic home: this file, in the repo.
Idempotent schema: run `init` any number of times.
"""
import argparse
import json
import sys
import time

import psycopg2
import psycopg2.extras

DBNAME = "ecosystem_central"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS successbrian_os.pm_steps (
    id          bigserial PRIMARY KEY,
    step_key    text UNIQUE NOT NULL,
    title       text NOT NULL,
    kind        text NOT NULL DEFAULT 'task',
    source      text,
    origin      text NOT NULL DEFAULT 'ecosystem'
                CHECK (origin IN ('ecosystem','brian','system')),
    status      text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','blocked','held_brian',
                                  'done','failed','cancelled')),
    priority    integer NOT NULL DEFAULT 50,
    certainty   numeric(4,3),
    actor       text,
    location    text,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    result      jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz,
    heartbeat_at timestamptz
);
CREATE TABLE IF NOT EXISTS successbrian_os.pm_step_deps (
    step_id       bigint NOT NULL REFERENCES successbrian_os.pm_steps(id) ON DELETE CASCADE,
    depends_on_id bigint NOT NULL REFERENCES successbrian_os.pm_steps(id) ON DELETE CASCADE,
    PRIMARY KEY (step_id, depends_on_id)
);
CREATE TABLE IF NOT EXISTS successbrian_os.pm_decisions (
    id         bigserial PRIMARY KEY,
    step_id    bigint REFERENCES successbrian_os.pm_steps(id) ON DELETE SET NULL,
    decided_by text NOT NULL,
    decision   text NOT NULL,
    rationale  text,
    certainty  numeric(4,3),
    origin     text NOT NULL DEFAULT 'ecosystem'
               CHECK (origin IN ('ecosystem','brian','system')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pm_decisions_created_idx
    ON successbrian_os.pm_decisions (created_at DESC);
CREATE INDEX IF NOT EXISTS pm_steps_ready_idx
    ON successbrian_os.pm_steps (status, priority DESC, created_at);
"""


def conn():
    return psycopg2.connect(dbname=DBNAME, host="localhost")


def first_id(row):
    return row["id"] if isinstance(row, dict) else row[0]


def init_schema(cur):
    cur.execute(SCHEMA_SQL)


def add_step(cur, key, title, kind="task", source=None, origin="ecosystem",
             priority=50, certainty=None, payload=None, depends_on=()):
    cur.execute(
        """INSERT INTO successbrian_os.pm_steps
             (step_key, title, kind, source, origin, priority, certainty, payload)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (step_key) DO NOTHING
           RETURNING id""",
        (key, title, kind, source, origin, priority, certainty,
         json.dumps(payload or {})))
    row = cur.fetchone()
    if row is None:
        cur.execute("SELECT id FROM successbrian_os.pm_steps WHERE step_key=%s", (key,))
        step_id = first_id(cur.fetchone())
        created = False
    else:
        step_id, created = first_id(row), True
    for dep_key in depends_on:
        cur.execute("SELECT id FROM successbrian_os.pm_steps WHERE step_key=%s", (dep_key,))
        dep = cur.fetchone()
        if dep is None:
            raise SystemExit(f"dependency step not found: {dep_key}")
        cur.execute(
            """INSERT INTO successbrian_os.pm_step_deps (step_id, depends_on_id)
               VALUES (%s,%s) ON CONFLICT DO NOTHING""", (step_id, first_id(dep)))
    return step_id, created


def claim(cur, actor, limit=1, location=None):
    """Hand out ready steps: queued, all deps done, priority desc, oldest first."""
    cur.execute(
        """SELECT s.id, s.step_key, s.title, s.kind, s.priority, s.origin
             FROM successbrian_os.pm_steps s
            WHERE s.status = 'queued'
              AND NOT EXISTS (
                    SELECT 1 FROM successbrian_os.pm_step_deps d
                      JOIN successbrian_os.pm_steps dep ON dep.id = d.depends_on_id
                     WHERE d.step_id = s.id AND dep.status <> 'done')
            ORDER BY s.priority DESC, s.created_at ASC
            LIMIT %s
            FOR UPDATE OF s SKIP LOCKED""", (limit,))
    raw = cur.fetchall()
    def v(r, i, k):
        return r[k] if isinstance(r, dict) else r[i]
    rows = [(v(r, 0, "id"), v(r, 1, "step_key"), v(r, 2, "title"),
             v(r, 3, "kind"), v(r, 4, "priority"), v(r, 5, "origin")) for r in raw]
    ids = [r[0] for r in rows]
    if ids:
        cur.execute(
            """UPDATE successbrian_os.pm_steps
                  SET status='running', actor=%s, location=%s,
                      started_at=now(), heartbeat_at=now(), updated_at=now()
                WHERE id = ANY(%s)""", (actor, location, ids))
    return rows


def finish(cur, key, status, result=None):
    cur.execute(
        """UPDATE successbrian_os.pm_steps
              SET status=%s, result=%s, finished_at=now(), updated_at=now()
            WHERE step_key=%s
            RETURNING id""",
        (status, json.dumps(result) if result is not None else None, key))
    row = cur.fetchone()
    if row is None:
        raise SystemExit(f"step not found: {key}")
    return first_id(row)


def decide(cur, by, decision, step_key=None, certainty=None, why=None, origin="ecosystem"):
    step_id = None
    if step_key:
        cur.execute("SELECT id FROM successbrian_os.pm_steps WHERE step_key=%s", (step_key,))
        r = cur.fetchone()
        if r is None:
            raise SystemExit(f"step not found: {step_key}")
        step_id = first_id(r)
    cur.execute(
        """INSERT INTO successbrian_os.pm_decisions
             (step_id, decided_by, decision, rationale, certainty, origin)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (step_id, by, decision, why, certainty, origin))
    return first_id(cur.fetchone())


def selftest():
    tag = f"pm-selftest-{int(time.time())}"
    c = conn()
    cur = c.cursor()
    init_schema(cur)
    # A: high priority, no deps. B: highest priority but depends on A. C: mid.
    add_step(cur, f"{tag}-a", "selftest A", priority=90)
    add_step(cur, f"{tag}-b", "selftest B", priority=99, depends_on=(f"{tag}-a",))
    add_step(cur, f"{tag}-c", "selftest C", priority=50)
    c.commit()
    got1 = claim(cur, "selftest", limit=1)
    c.commit()
    assert got1 and got1[0][1] == f"{tag}-a", f"claim1 should be A, got {got1}"
    print("PASS claim skips blocked B (dep unmet), takes highest ready A")
    finish(cur, f"{tag}-a", "done", {"ok": True})
    c.commit()
    got2 = claim(cur, "selftest", limit=1)
    c.commit()
    assert got2 and got2[0][1] == f"{tag}-b", f"claim2 should be B after A done, got {got2}"
    print("PASS dependency releases B; priority 99 beats C's 50")
    did = decide(cur, "selftest", "selftest decision", step_key=f"{tag}-b",
                 certainty=0.95, why=tag)
    c.commit()
    cur.execute("SELECT count(*) FROM successbrian_os.pm_decisions WHERE rationale=%s", (tag,))
    assert cur.fetchone()[0] == 1, "decision stream write failed"
    print(f"PASS decision stream write (id {did})")
    cur.execute("DELETE FROM successbrian_os.pm_decisions WHERE rationale=%s", (tag,))
    cur.execute("DELETE FROM successbrian_os.pm_steps WHERE step_key LIKE %s", (tag + "-%",))
    c.commit()
    cur.execute("SELECT count(*) FROM successbrian_os.pm_steps WHERE step_key LIKE %s", (tag + "-%",))
    assert cur.fetchone()[0] == 0, "selftest cleanup failed"
    c.close()
    print("PASS cleanup — selftest green")


def main(argv=None):
    ap = argparse.ArgumentParser(description="SBOS main PM — control plane for the coded loop")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    a = sub.add_parser("add")
    a.add_argument("--key", required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--kind", default="task")
    a.add_argument("--source")
    a.add_argument("--origin", default="ecosystem", choices=["ecosystem", "brian", "system"])
    a.add_argument("--priority", type=int, default=50)
    a.add_argument("--certainty", type=float)
    a.add_argument("--depends-on", action="append", default=[])
    cl = sub.add_parser("claim")
    cl.add_argument("--actor", required=True)
    cl.add_argument("--limit", type=int, default=1)
    cl.add_argument("--location")
    d = sub.add_parser("done")
    d.add_argument("--key", required=True)
    d.add_argument("--result")
    f = sub.add_parser("fail")
    f.add_argument("--key", required=True)
    f.add_argument("--why", required=True)
    h = sub.add_parser("hold")
    h.add_argument("--key", required=True)
    dc = sub.add_parser("decide")
    dc.add_argument("--by", required=True)
    dc.add_argument("--decision", required=True)
    dc.add_argument("--step")
    dc.add_argument("--certainty", type=float)
    dc.add_argument("--why")
    dc.add_argument("--origin", default="ecosystem", choices=["ecosystem", "brian", "system"])
    ls = sub.add_parser("steps")
    ls.add_argument("--status")
    ls.add_argument("--limit", type=int, default=20)
    ld = sub.add_parser("decisions")
    ld.add_argument("--limit", type=int, default=20)
    ld.add_argument("--without-brian", action="store_true")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)

    if args.cmd == "selftest":
        selftest()
        return 0
    c = conn()
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    init_schema(cur)
    if args.cmd == "init":
        c.commit()
        print("pm schema ready: pm_steps, pm_step_deps, pm_decisions")
    elif args.cmd == "add":
        sid, created = add_step(cur, args.key, args.title, args.kind, args.source,
                                args.origin, args.priority, args.certainty,
                                depends_on=tuple(args.depends_on))
        c.commit()
        print(f"step id={sid} key={args.key} {'created' if created else 'already present'}")
    elif args.cmd == "claim":
        rows = claim(cur, args.actor, args.limit, args.location)
        c.commit()
        for r in rows:
            print(f"claimed id={r[0]} key={r[1]} pri={r[4]} "
                  f"origin={r[5]} title={r[2]}")
        if not rows:
            print("nothing ready")
    elif args.cmd == "done":
        finish(cur, args.key, "done", {"note": args.result} if args.result else None)
        c.commit()
        print(f"done {args.key}")
    elif args.cmd == "fail":
        finish(cur, args.key, "failed", {"why": args.why})
        c.commit()
        print(f"failed {args.key}: {args.why}")
    elif args.cmd == "hold":
        cur.execute("UPDATE successbrian_os.pm_steps SET status='held_brian', updated_at=now() "
                    "WHERE step_key=%s", (args.key,))
        c.commit()
        print(f"held for Brian: {args.key}")
    elif args.cmd == "decide":
        did = decide(cur, args.by, args.decision, args.step, args.certainty,
                     args.why, args.origin)
        c.commit()
        print(f"decision id={did} recorded")
    elif args.cmd == "steps":
        if args.status:
            cur.execute("SELECT id, step_key, status, priority, origin, actor, title "
                        "FROM successbrian_os.pm_steps WHERE status=%s "
                        "ORDER BY priority DESC, created_at LIMIT %s", (args.status, args.limit))
        else:
            cur.execute("SELECT id, step_key, status, priority, origin, actor, title "
                        "FROM successbrian_os.pm_steps "
                        "ORDER BY priority DESC, created_at LIMIT %s", (args.limit,))
        for r in cur.fetchall():
            print(f"{r['id']:>5} [{r['status']:<10}] pri={r['priority']:>3} "
                  f"{r['origin']:<9} {r['step_key']} — {r['title']}")
    elif args.cmd == "decisions":
        if args.without_brian:
            cur.execute("SELECT id, decided_by, decision, certainty, created_at "
                        "FROM successbrian_os.pm_decisions WHERE origin='ecosystem' "
                        "ORDER BY created_at DESC LIMIT %s", (args.limit,))
        else:
            cur.execute("SELECT id, decided_by, decision, certainty, created_at "
                        "FROM successbrian_os.pm_decisions "
                        "ORDER BY created_at DESC LIMIT %s", (args.limit,))
        for r in cur.fetchall():
            print(f"{r['id']:>5} {r['created_at']} [{r['decided_by']}] {r['decision']}")
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
