#!/usr/bin/env python3
"""decision_queue.py - Decision queue v1 (BUILD_QUEUE B7).

The decision stream's durable home: a table on alpha holding every
residue item that is genuinely Brian's to rule on, with its context
attached (origin, dates, related fields), deduplicated, ordered by
goal priority then age.

Sources (same legs as B6's residue_inventory, enriched with context):
  held_brian_step - successbrian_os.pm_steps where status='held_brian'
  unruled_capture - atlas.scattered_captures where status='raw'
  compile_residue - successbrian_os.knowledge_index where kind='compile'
                    (the B15 standing-compile contract; 0 rows until
                    B15 lands, lights up automatically when it does)

Ordering: goal_priority DESC, source_created_at ASC. Goal priority
is UNKNOWN until Phase 3 (Atlas goal machinery, B10-B12) lands, so
goal_ref defaults to 'unknown' and goal_priority to 50 for every
row today - age governs the order until Phase 3 fills the goal
columns. The columns exist now so the ordering principle is code,
not prose.

Sync semantics (carry-forward, never drop):
  - a live residue item not yet queued is INSERTED (pending);
  - a queued pending item still live is refreshed (title/context/
    last_seen_at) - never duplicated (UNIQUE source_ref);
  - a queued pending item whose source left residue is marked
    resolved with reason 'source_left_residue' - history kept,
    never deleted, never silently dropped. A ruled/carried item
    is never touched by sync.
  - ruling itself is B8's write-back path, not this tool: this
    tool only stages the queue. Nothing here sends, buys,
    publishes, or contacts anyone.

Usage:
  decision_queue.py --init        create the table if missing
  decision_queue.py --sync        sync live residue into the queue
  decision_queue.py --summary     pending counts + next item
  decision_queue.py --list        pending items, queue order
  decision_queue.py --next        the single next decision, full context
  decision_queue.py --selftest    init + sync idempotency + reconcile
                                  + ordering + resolve-on-vanish probe
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
from sbos_common import pg_exec, pg_one, pg_rows  # noqa: E402

DB = "ecosystem_central"
SCHEMA = "successbrian_os"
TABLE = "decision_queue"
SOURCES = ("held_brian_step", "unruled_capture", "compile_residue")
SELFTEST_REF = "selftest:disposable"

DDL = f"""
create table if not exists {SCHEMA}.{TABLE} (
  id serial primary key,
  source text not null,
  source_ref text not null unique,
  title text not null default '',
  context jsonb not null default '{{}}'::jsonb,
  goal_ref text not null default 'unknown',
  goal_priority integer not null default 50,
  status text not null default 'pending'
    check (status in ('pending', 'ruled', 'carried', 'resolved')),
  source_created_at timestamptz,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  resolved_reason text,
  resolved_at timestamptz,
  ruled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists {TABLE}_queue_idx
  on {SCHEMA}.{TABLE} (status, goal_priority desc, source_created_at asc);
"""

# Rich residue UNION: B6's legs, with a per-source context object
# (origin / dates / related fields) attached to each row.
RESIDUE_SQL = """
select 'held_brian_step' as source,
       'pm_steps:' || id::text as ref,
       coalesce(title, '') as title,
       created_at,
       jsonb_build_object('origin', origin, 'priority', priority,
                          'kind', kind, 'actor', coalesce(actor, ''),
                          'payload', payload) as context
  from successbrian_os.pm_steps where status = 'held_brian'
union all
select 'unruled_capture',
       'capture:' || id::text,
       coalesce(title, ''),
       created_at,
       jsonb_build_object('cluster_key', cluster_key, 'score', score,
                          'score_reasons', score_reasons,
                          'recommendation', recommendation,
                          'depth', depth,
                          'workspace_slug', workspace_slug) as context
  from atlas.scattered_captures where status = 'raw'
union all
select 'compile_residue',
       'ki:' || canonical_id,
       coalesce(title, subject, canonical_id),
       created_at,
       jsonb_build_object('subject', subject, 'kind', kind,
                          'allm_workspace', allm_workspace,
                          'source_capture_id', source_capture_id) as context
  from successbrian_os.knowledge_index where kind = 'compile'
 order by created_at asc
"""

ORDER_SQL = f"""
select source, source_ref, title, context, goal_ref, goal_priority,
       status, source_created_at
  from {SCHEMA}.{TABLE}
 where status = 'pending'
 order by goal_priority desc, source_created_at asc
"""


def init():
    pg_exec(DDL, dbname=DB)
    return 0


def fetch_residue():
    rows = pg_rows(RESIDUE_SQL, dbname=DB)
    out = []
    for source, ref, title, created, context in rows:
        if isinstance(context, str):
            context = json.loads(context)
        out.append({"source": source, "ref": ref, "title": title,
                    "created": created, "context": context or {}})
    return out


def fetch_pending():
    rows = pg_rows(ORDER_SQL, dbname=DB)
    return [{"source": r[0], "ref": r[1], "title": r[2], "context": r[3],
             "goal_ref": r[4], "goal_priority": r[5], "status": r[6],
             "created": r[7]} for r in rows]


def sync():
    init()
    live = fetch_residue()
    live_refs = {r["ref"] for r in live}
    inserted = updated = 0
    for r in live:
        n = pg_one(
            f"""insert into {SCHEMA}.{TABLE}
                   (source, source_ref, title, context, source_created_at)
                values (%s, %s, %s, %s::jsonb, %s)
                on conflict (source_ref) do update
                   set title = excluded.title,
                       context = excluded.context,
                       last_seen_at = now(),
                       updated_at = now()
                returning (xmax = 0)""",
            (r["source"], r["ref"], r["title"],
             json.dumps(r["context"]), r["created"]),
            dbname=DB)
        if n:
            inserted += 1
        else:
            updated += 1
    # Pending items whose source left residue: resolve, never delete.
    if live_refs:
        resolved = pg_rows(
            f"""update {SCHEMA}.{TABLE}
                   set status = 'resolved',
                       resolved_reason = 'source_left_residue',
                       resolved_at = now(), updated_at = now()
                 where status = 'pending' and source_ref <> ALL (%s)
                 returning source_ref""",
            (list(live_refs),), dbname=DB)
    else:
        # Genuinely empty residue (not a query failure - fetch_residue
        # raises on error): every pending item's source has left.
        resolved = pg_rows(
            f"""update {SCHEMA}.{TABLE}
                   set status = 'resolved',
                       resolved_reason = 'source_left_residue',
                       resolved_at = now(), updated_at = now()
                 where status = 'pending'
                 returning source_ref""",
            dbname=DB)
    pending = pg_one(
        f"select count(*) from {SCHEMA}.{TABLE} where status = 'pending'",
        dbname=DB)
    print(f"sync: live={len(live)} inserted={inserted} "
          f"updated={updated} resolved={len(resolved)} pending={pending}")
    for (ref,) in resolved:
        print(f"  resolved (source left residue): {ref}")
    return 0


def age_days(created):
    if not created:
        return None
    now = datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0, (now - created).days)


def show_summary():
    init()
    rows = fetch_pending()
    counts = {s: sum(1 for r in rows if r["source"] == s) for s in SOURCES}
    print(f"decision queue pending: {len(rows)}")
    for s in SOURCES:
        print(f"{s}: {counts[s]}")
    if rows:
        nxt = rows[0]
        print(f"next: {nxt['source']} {nxt['ref']} "
              f"\"{nxt['title']}\" ({age_days(nxt['created'])} days old, "
              f"goal {nxt['goal_ref']} pri {nxt['goal_priority']})")
    else:
        print("next: none")
    return 0


def show_list():
    rows = fetch_pending()
    for r in rows:
        print(f"{r['source']} | {r['ref']} | {age_days(r['created'])}d | "
              f"pri {r['goal_priority']} | goal {r['goal_ref']} | "
              f"{r['created']:%Y-%m-%d %H:%M} | {r['title']}")
    print(f"decision queue pending: {len(rows)}")
    return 0


def show_next():
    rows = fetch_pending()
    if not rows:
        print("next: none")
        return 0
    r = rows[0]
    print(f"next decision: {r['source']} {r['ref']}")
    print(f"title: {r['title']}")
    print(f"created: {r['created']} ({age_days(r['created'])} days ago)")
    print(f"goal: {r['goal_ref']} (priority {r['goal_priority']})")
    print("context:")
    print(json.dumps(r["context"], indent=2, default=str))
    return 0


def selftest():
    init()
    init()  # DDL is idempotent
    # 1. sync twice: idempotent, no duplicate source_refs.
    sync()
    before = fetch_pending()
    sync()
    after = fetch_pending()
    assert [r["ref"] for r in before] == [r["ref"] for r in after], \
        "second sync changed the pending set"
    refs = [r["ref"] for r in after]
    assert len(refs) == len(set(refs)), "duplicate source_ref in queue"
    # 2. pending count reconciles with live residue.
    live = fetch_residue()
    assert len(after) == len(live), \
        f"pending {len(after)} != live residue {len(live)}"
    # 3. ordering invariant: goal_priority DESC, source_created_at ASC.
    keys = [(r["goal_priority"], r["created"]) for r in after]
    assert keys == sorted(keys, key=lambda k: (-k[0], k[1] or
                          datetime.min.replace(tzinfo=timezone.utc))), \
        "pending rows are not in queue order"
    # 4. resolve-on-vanish: a pending row NOT in live residue is
    # resolved by sync with reason recorded, never deleted.
    pg_exec(
        f"""insert into {SCHEMA}.{TABLE}
               (source, source_ref, title, context, source_created_at)
            values ('unruled_capture', %s, 'selftest disposable',
                    '{{}}'::jsonb, now())
            on conflict (source_ref) do nothing""",
        (SELFTEST_REF,), dbname=DB)
    assert pg_one(
        f"select status from {SCHEMA}.{TABLE} where source_ref = %s",
        (SELFTEST_REF,), dbname=DB) == "pending"
    sync()
    row = pg_one(
        f"""select status, resolved_reason from {SCHEMA}.{TABLE}
             where source_ref = %s""",
        (SELFTEST_REF,), dbname=DB)
    assert row[0] == "resolved" and row[1] == "source_left_residue", \
        f"vanished row not resolved: {row}"
    pg_exec(f"delete from {SCHEMA}.{TABLE} where source_ref = %s",
            (SELFTEST_REF,), dbname=DB)
    assert pg_one(
        f"select count(*) from {SCHEMA}.{TABLE} where source_ref = %s",
        (SELFTEST_REF,), dbname=DB) == 0
    # 5. queue reconciles again after the probe is cleaned up.
    assert len(fetch_pending()) == len(fetch_residue())
    print("DECISION_QUEUE_OK")
    return 0


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    if "--init" in args:
        init()
        print("decision_queue table ready")
        return 0
    if "--sync" in args:
        return sync()
    if "--summary" in args:
        return show_summary()
    if "--list" in args:
        return show_list()
    if "--next" in args:
        return show_next()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
