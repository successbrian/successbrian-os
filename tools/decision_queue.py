#!/usr/bin/env python3
"""decision_queue.py - Decision queue v1 (BUILD_QUEUE B7) + write-back
path (BUILD_QUEUE B8).

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
  - ruling itself is B8's write-back path (below): this tool only
    staged the queue before B8. Nothing here sends, buys,
    publishes, or contacts anyone.

B8 - write-back path (the ruling lands in the owning table, same pass):
  decision_queue.py --rule <source_ref> --ruling "<Brian's words>"
      [--by brian]
    Applies the ruling to the OWNING table and marks the queue row
    ruled, in the same pass, verified by read-back of both rows:
      pm_steps:N      -> status 'done', result gains
                         {ruling, ruled_by, ruled_at}; the step leaves
                         held_brian, so it leaves residue.
      capture:N       -> status 'triaged', ruled_at=now(),
                         ruling_why=<ruling>, triaged_at=now().
      ki:<canonical>  -> status 'ruled', pointer_note records the
                         ruling; the compile leg excludes ruled rows,
                         so it leaves residue too.
    A ruling is idempotent: re-ruling with the same words is a
    no-op success (owning row already in its ruled state carrying
    the same ruling); a different ruling on an already-ruled item
    is refused, never overwritten - history is append-only.
  decision_queue.py --carry <source_ref> [--note "..."]
    Records an explicit carry-forward on a pending item (Brian saw
    it, it stays): carried_count +1 in context, carried_at stamped,
    status stays pending. Unreached items carry forward
    automatically - sync never drops a pending item - and --carry
    makes the carry visible instead of silent.
  decision_queue.py --ruled
    Ruled/carried history, newest first.

Usage:
  decision_queue.py --init        create the table if missing
  decision_queue.py --sync        sync live residue into the queue
  decision_queue.py --summary     pending counts + next item
  decision_queue.py --list        pending items, queue order
  decision_queue.py --next        the single next decision, full context
  decision_queue.py --rule REF --ruling TEXT [--by NAME]
                                  apply Brian's ruling, write-back +
                                  queue row ruled (verified both sides)
  decision_queue.py --carry REF [--note TEXT]
                                  record a carry-forward on a pending item
  decision_queue.py --ruled      ruled history
  decision_queue.py --selftest    init + sync idempotency + reconcile
                                  + ordering + resolve-on-vanish probe
                                  + B8 rule/carry probes on disposable
                                  rows for all three source legs
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
SELFTEST_PM_KEY = "selftest-b8-pm"
SELFTEST_KI_ID = "selftest-b8-ki"

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
  ruling text,
  ruled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists {TABLE}_queue_idx
  on {SCHEMA}.{TABLE} (status, goal_priority desc, source_created_at asc);
"""

# B8: existing tables (created by B7) gain the ruling column.
MIGRATE_RULING = f"""
alter table {SCHEMA}.{TABLE} add column if not exists ruling text;
"""

# Rich residue UNION: B6's legs, with a per-source context object
# (origin / dates / related fields) attached to each row. A ruled
# compile row (B8) is no longer residue - it leaves the leg.
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
  from successbrian_os.knowledge_index
 where kind = 'compile' and status <> 'ruled'
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
    pg_exec(MIGRATE_RULING, dbname=DB)
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


# ------------------------------------------------------------------ B8
# Write-back path. Each leg: update the owning table under its
# pre-ruling precondition, then mark the queue row ruled, then verify
# both sides by read-back. A ruling is never overwritten: an
# already-ruled owning row carrying the SAME ruling is an idempotent
# no-op; a different ruling on an already-ruled item is refused.


def _queue_row(ref):
    row = pg_one(
        f"""select source, status, ruling from {SCHEMA}.{TABLE}
             where source_ref = %s""",
        (ref,), dbname=DB)
    if row is None:
        return None
    return {"source": row[0], "status": row[1], "ruling": row[2]}


def _owning_state(source, ref):
    """Current (status, ruling-carrying field) of the owning row."""
    if source == "held_brian_step":
        row = pg_one(
            "select status, result ->> 'ruling' from "
            "successbrian_os.pm_steps where id = %s",
            (int(ref.split(":", 1)[1]),), dbname=DB)
    elif source == "unruled_capture":
        row = pg_one(
            "select status, ruling_why from atlas.scattered_captures "
            "where id = %s",
            (int(ref.split(":", 1)[1]),), dbname=DB)
    elif source == "compile_residue":
        row = pg_one(
            "select status, pointer_note from "
            "successbrian_os.knowledge_index where canonical_id = %s",
            (ref.split(":", 1)[1],), dbname=DB)
    else:
        raise ValueError(f"unknown source {source!r}")
    if row is None:
        return None
    return {"status": row[0], "ruling_field": row[1]}


def _write_back(source, ref, ruling, by):
    """Update the owning table. Returns 'applied', 'already', or raises."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if source == "held_brian_step":
        step_id = int(ref.split(":", 1)[1])
        n = pg_exec(
            """update successbrian_os.pm_steps
                  set status = 'done', finished_at = now(),
                      result = coalesce(result, '{}'::jsonb)
                               || jsonb_build_object(
                                    'ruling', %s, 'ruled_by', %s,
                                    'ruled_at', %s),
                      updated_at = now()
                where id = %s and status = 'held_brian'""",
            (ruling, by, now_iso, step_id), dbname=DB)
        if n:
            return "applied"
        st = _owning_state(source, ref)
        if st and st["status"] == "done" and st["ruling_field"] == ruling:
            return "already"
        raise RuntimeError(
            f"pm_steps {step_id} not held_brian and not already ruled "
            f"with this ruling (state={st}) - refusing to overwrite")
    if source == "unruled_capture":
        cap_id = int(ref.split(":", 1)[1])
        n = pg_exec(
            """update atlas.scattered_captures
                  set status = 'triaged', triaged_at = now(),
                      ruled_at = now(), ruling_why = %s
                where id = %s and status = 'raw'""",
            (ruling, cap_id), dbname=DB)
        if n:
            return "applied"
        st = _owning_state(source, ref)
        if st and st["status"] == "triaged" and st["ruling_field"] == ruling:
            return "already"
        raise RuntimeError(
            f"capture {cap_id} not raw and not already ruled with this "
            f"ruling (state={st}) - refusing to overwrite")
    if source == "compile_residue":
        ki_id = ref.split(":", 1)[1]
        note = f"RULED {now_iso} by {by}: {ruling}"
        n = pg_exec(
            """update successbrian_os.knowledge_index
                  set status = 'ruled', pointer_note = %s,
                      updated_at = now()
                where canonical_id = %s and kind = 'compile'
                  and status <> 'ruled'""",
            (note, ki_id), dbname=DB)
        if n:
            return "applied"
        st = _owning_state(source, ref)
        if st and st["status"] == "ruled" and st["ruling_field"] == note:
            return "already"
        raise RuntimeError(
            f"knowledge_index {ki_id} not a live compile row and not "
            f"already ruled with this ruling (state={st}) - refusing")
    raise ValueError(f"unknown source {source!r}")


def rule(ref, ruling, by="brian"):
    """Apply Brian's ruling: owning table + queue row, verified."""
    if not ruling or not ruling.strip():
        print("rule: --ruling text is required (Brian's words, verbatim)")
        return 2
    init()
    q = _queue_row(ref)
    if q is None:
        print(f"rule: no decision-queue row for {ref} - run --sync first")
        return 1
    if q["status"] == "ruled":
        if q["ruling"] == ruling:
            print(f"rule: {ref} already ruled with the same ruling")
            return 0
        print(f"rule: {ref} already ruled with a DIFFERENT ruling "
              f"({q['ruling']!r}) - refusing to overwrite")
        return 1
    if q["status"] != "pending":
        print(f"rule: {ref} is {q['status']}, not pending - cannot rule")
        return 1
    applied = _write_back(q["source"], ref, ruling.strip(), by)
    n = pg_exec(
        f"""update {SCHEMA}.{TABLE}
               set status = 'ruled', ruling = %s, ruled_at = now(),
                   resolved_reason = 'ruled', resolved_at = now(),
                   updated_at = now()
             where source_ref = %s and status = 'pending'""",
        (ruling.strip(), ref), dbname=DB)
    if n != 1:
        raise RuntimeError(
            f"rule: queue row {ref} did not flip to ruled "
            f"(affected={n}) after owning write-back {applied} - "
            f"owning table already ruled, queue row needs a manual look")
    # Verify both sides by read-back.
    q2 = _queue_row(ref)
    st = _owning_state(q["source"], ref)
    assert q2["status"] == "ruled" and q2["ruling"] == ruling.strip(), \
        f"rule: queue read-back failed for {ref}: {q2}"
    assert st is not None and st["status"] in ("done", "triaged", "ruled"), \
        f"rule: owning read-back failed for {ref}: {st}"
    print(f"ruled: {ref} ({q['source']}) [{applied}]")
    print(f"  ruling: {ruling.strip()}")
    print(f"  owning: status={st['status']}; queue: status=ruled")
    return 0


def carry(ref, note="", by="spencer"):
    """Record an explicit carry-forward on a pending item."""
    init()
    q = _queue_row(ref)
    if q is None:
        print(f"carry: no decision-queue row for {ref} - run --sync first")
        return 1
    if q["status"] != "pending":
        print(f"carry: {ref} is {q['status']}, not pending - cannot carry")
        return 1
    row = pg_one(
        f"select context from {SCHEMA}.{TABLE} where source_ref = %s",
        (ref,), dbname=DB)
    ctx = row[0] if isinstance(row, tuple) else row
    if isinstance(ctx, str):
        ctx = json.loads(ctx)
    ctx = dict(ctx or {})
    carried = list(ctx.get("carried") or [])
    carried.append({"at": datetime.now(timezone.utc).isoformat(),
                    "by": by, "note": note or ""})
    ctx["carried"] = carried
    ctx["carried_count"] = len(carried)
    pg_exec(
        f"""update {SCHEMA}.{TABLE}
               set context = %s::jsonb, last_seen_at = now(),
                   updated_at = now()
             where source_ref = %s and status = 'pending'""",
        (json.dumps(ctx), ref), dbname=DB)
    row = pg_one(
        f"""select context ->> 'carried_count' from {SCHEMA}.{TABLE}
             where source_ref = %s and status = 'pending'""",
        (ref,), dbname=DB)
    assert row == str(len(carried)), \
        f"carry: read-back failed for {ref}: carried_count={row}"
    print(f"carried: {ref} (carry #{len(carried)}, still pending)")
    if note:
        print(f"  note: {note}")
    return 0


def show_ruled():
    rows = pg_rows(
        f"""select source, source_ref, title, status, ruling, ruled_at,
                   resolved_reason, source_created_at
              from {SCHEMA}.{TABLE}
             where status in ('ruled', 'carried', 'resolved')
             order by coalesce(ruled_at, resolved_at, updated_at) desc""",
        dbname=DB)
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[3]} | "
              f"{(r[5] or r[6] or '')} | {r[2]}"
              + (f" | ruling: {r[4]}" if r[4] else ""))
    print(f"ruled/carried/resolved history: {len(rows)}")
    return 0


def _cleanup_selftest_probe(refs=None):
    """Delete disposable probe rows: queue rows for the given refs
    (default: the selftest placeholder) plus probe source rows.
    The disposable capture row is NOT deleted - successbrian has no
    DELETE grant on atlas.scattered_captures, and the row is reused
    across runs (see _probe_refs): it stays, ruled, clearly titled,
    and never re-enters residue (status 'triaged')."""
    if refs:
        for ref in refs.values():
            pg_exec(
                f"delete from {SCHEMA}.{TABLE} where source_ref = %s",
                (ref,), dbname=DB)
    pg_exec(
        f"delete from {SCHEMA}.{TABLE} where source_ref = %s",
        (SELFTEST_REF,), dbname=DB)
    pg_exec(
        "delete from successbrian_os.pm_steps where step_key = %s",
        (SELFTEST_PM_KEY,), dbname=DB)
    pg_exec(
        "delete from successbrian_os.knowledge_index "
        "where canonical_id = %s",
        (SELFTEST_KI_ID,), dbname=DB)


def _probe_refs():
    """Disposable source rows + queue refs for the B8 rule probes.

    Returns {source: ref}. Caller must _cleanup_selftest_probe() after.
    """
    _cleanup_selftest_probe()
    step_id = pg_one(
        """insert into successbrian_os.pm_steps
               (step_key, kind, origin, payload, priority, status, title)
            values (%s, 'selftest', 'system', '{}'::jsonb, 50,
                    'held_brian', 'B8 selftest disposable')
            returning id""",
        (SELFTEST_PM_KEY,), dbname=DB)
    cap_id = pg_one(
        """select id from atlas.scattered_captures
            where title = 'B8 selftest disposable'
            order by id limit 1""",
        dbname=DB)
    if cap_id is None:
        cap_id = pg_one(
            """insert into atlas.scattered_captures
                   (context, depth, raw_text, status, title)
                values ('B8 selftest disposable', 'unclassified',
                        'B8 selftest disposable', 'raw',
                        'B8 selftest disposable')
                returning id""",
            dbname=DB)
    else:
        # Reuse the one disposable capture row: reset it to raw.
        # Test-artifact hygiene only - this row is labeled disposable
        # and its ruling was a test ruling, never Brian's ruling on a
        # real item. (DELETE is not granted on this table, so the row
        # is kept and reused rather than recreated per run.)
        pg_exec(
            """update atlas.scattered_captures
                  set status = 'raw', ruling_why = null,
                      ruled_at = null, triaged_at = null
                where id = %s""",
            (cap_id,), dbname=DB)
    pg_exec(
        """insert into successbrian_os.knowledge_index
               (canonical_id, subject, title, kind, status, version)
            values (%s, 'B8 selftest disposable',
                    'B8 selftest disposable', 'compile', 'current', 1)""",
        (SELFTEST_KI_ID,), dbname=DB)
    sync()
    return {"held_brian_step": f"pm_steps:{step_id}",
            "unruled_capture": f"capture:{cap_id}",
            "compile_residue": f"ki:{SELFTEST_KI_ID}"}


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
    # --- B8 probes: rule + carry on disposable rows, all three legs.
    live_before = len(fetch_pending())
    refs = _probe_refs()
    assert len(fetch_pending()) == live_before + 3, \
        "probe rows did not all sync in as pending"
    # 6. pm_steps leg: rule writes back, re-sync never resurrects,
    #    re-rule with the same words is an idempotent no-op.
    pm_ref = refs["held_brian_step"]
    assert rule(pm_ref, "selftest ruling: approve", by="selftest") == 0
    st = _owning_state("held_brian_step", pm_ref)
    assert st["status"] == "done" and \
        st["ruling_field"] == "selftest ruling: approve", \
        f"pm_steps write-back failed: {st}"
    assert _queue_row(pm_ref)["status"] == "ruled"
    sync()
    assert _queue_row(pm_ref)["status"] == "ruled", \
        "ruled pm_steps item resurrected by sync"
    assert len(fetch_pending()) == live_before + 2, \
        "pending count wrong after ruling pm_steps probe"
    assert rule(pm_ref, "selftest ruling: approve", by="selftest") == 0, \
        "idempotent re-rule failed"
    assert rule(pm_ref, "a different ruling", by="selftest") == 1, \
        "conflicting re-rule was not refused"
    # 7. capture leg: rule writes back to the capture row itself.
    cap_ref = refs["unruled_capture"]
    assert rule(cap_ref, "selftest ruling: park it", by="selftest") == 0
    st = _owning_state("unruled_capture", cap_ref)
    assert st["status"] == "triaged" and \
        st["ruling_field"] == "selftest ruling: park it", \
        f"capture write-back failed: {st}"
    assert _queue_row(cap_ref)["status"] == "ruled"
    # 8. compile leg: rule writes back to the knowledge_index row.
    ki_ref = refs["compile_residue"]
    assert rule(ki_ref, "selftest ruling: publish", by="selftest") == 0
    st = _owning_state("compile_residue", ki_ref)
    assert st["status"] == "ruled" and \
        "selftest ruling: publish" in (st["ruling_field"] or ""), \
        f"compile write-back failed: {st}"
    assert _queue_row(ki_ref)["status"] == "ruled"
    # 9. carry: a pending item stays pending with a visible carry.
    # (fresh disposable pm_steps row, carried then ruled to clean up)
    _cleanup_selftest_probe(refs)
    step_id = pg_one(
        """insert into successbrian_os.pm_steps
               (step_key, kind, origin, payload, priority, status, title)
            values (%s, 'selftest', 'system', '{}'::jsonb, 50,
                    'held_brian', 'B8 selftest disposable')
            returning id""",
        (SELFTEST_PM_KEY,), dbname=DB)
    carry_ref = f"pm_steps:{step_id}"
    sync()
    assert _queue_row(carry_ref)["status"] == "pending"
    assert carry(carry_ref, note="selftest carry", by="selftest") == 0
    q = _queue_row(carry_ref)
    assert q["status"] == "pending", "carry moved the item out of pending"
    ctx = pg_one(
        f"select context ->> 'carried_count' from {SCHEMA}.{TABLE} "
        "where source_ref = %s",
        (carry_ref,), dbname=DB)
    assert ctx == "1", f"carry count not recorded: {ctx}"
    assert carry(carry_ref, note="second selftest carry",
                 by="selftest") == 0
    ctx = pg_one(
        f"select context ->> 'carried_count' from {SCHEMA}.{TABLE} "
        "where source_ref = %s",
        (carry_ref,), dbname=DB)
    assert ctx == "2", f"second carry not counted: {ctx}"
    assert rule(carry_ref, "selftest ruling: approve",
                by="selftest") == 0
    # 10. all probes cleaned up; queue reconciles with live residue.
    _cleanup_selftest_probe({"held_brian_step": carry_ref})
    assert len(fetch_pending()) == len(fetch_residue()), \
        "queue does not reconcile after B8 probes"
    assert pg_one(
        f"select count(*) from {SCHEMA}.{TABLE} "
        "where source_ref = %s or source_ref = %s or source_ref = %s",
        (pm_ref, cap_ref, ki_ref), dbname=DB) == 0, \
        "probe queue rows left behind"
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
    if "--ruled" in args:
        return show_ruled()
    if "--rule" in args:
        i = args.index("--rule")
        if i + 1 >= len(args):
            print("rule: --rule <source_ref> --ruling <text> required")
            return 2
        ref = args[i + 1]
        ruling = ""
        by = "brian"
        j = 0
        while j < len(args):
            if args[j] == "--ruling" and j + 1 < len(args):
                ruling = args[j + 1]
                j += 2
            elif args[j] == "--by" and j + 1 < len(args):
                by = args[j + 1]
                j += 2
            else:
                j += 1
        return rule(ref, ruling, by=by)
    if "--carry" in args:
        i = args.index("--carry")
        if i + 1 >= len(args):
            print("carry: --carry <source_ref> [--note <text>] required")
            return 2
        ref = args[i + 1]
        note = ""
        by = "spencer"
        j = 0
        while j < len(args):
            if args[j] == "--note" and j + 1 < len(args):
                note = args[j + 1]
                j += 2
            elif args[j] == "--by" and j + 1 < len(args):
                by = args[j + 1]
                j += 2
            else:
                j += 1
        return carry(ref, note=note, by=by)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
