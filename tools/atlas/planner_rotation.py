#!/usr/bin/env python3
"""planner_rotation.py - Planner rotation loop v1 (BUILD_QUEUE B12).

Phase 3 (Atlas goal machinery), third piece: B10 built the goal-node
contract, B11 populated goal/task nodes from the Goals tab. This module
IS the rotation from builds/atlas-planner-goal-loop/design-2026-11-12.md
(Brian, 2026-11-12 20:36 CST: the main planner loops through ALL goals,
priority-ordered, least-recently-looked breaking the tail, over several
days; each look is unique and filed against the goal; work spawned at
the right engine tier; report by exception + a coverage line).

Rotation rules, encoded here (Brian-correctable defaults):
  - Order: Atlas priority DESC, then least-recently-looked first
    (never-looked goals head the queue), slug ASC as the deterministic
    tiebreak. No goal is skipped twice: coverage is the point.
  - Done/cancelled goals have LEFT the rotation (design: a goal leaves
    only by being completed or by Brian cancelling it). They stay in
    atlas.goal_nodes and in the ledger history, but --plan never queues
    them and --look refuses them.
  - A look files ONE ledger row (successbrian_os.goal_coverage) AND
    advances the goal node's rotation keys (last_looked_at, look_count,
    blocker, planner_seat). The ledger is the audit trail; the node is
    the current state. The B11 sync preserves these keys, so a look is
    never clobbered by a re-sync.
  - Engine tier (hard-work rule, 2026-11-12): planner = shaping/ordering
    the work; morpheus = routine/medium synthesis; sonic/reap = the
    hardest judgment (final verdicts, ambiguous/thin evidence). B12 v1
    RECORDED the tier; B12b DISPATCHES it (--dispatch): planner ->
    a pm_steps task step, morpheus -> a judgment step the
    morpheus-worker claims, reap -> a B2 feeder packet on the bus
    for gamma's REAP seat. Sonic -> a judgment step the sonic-worker
    claims (B12c: tier='sonic' in the payload; morpheus-worker
    excludes sonic-tier steps, so serving one can never fall down
    to Morpheus). A look that finds work it cannot do
    files it as a named blocker on the goal - never a silent skip.
  - Coverage line (report by exception): active goals, looked, never
    looked, oldest un-looked goal. All-clear rotations stay silent.

Nothing here sends, buys, publishes, or contacts anyone. A look is
one ledger insert + one node-details update in a single transaction.

Usage:
  planner_rotation.py --selftest   pure ordering/tier checks + live
                                   SQL/Python order agreement + a
                                   transactional probe look (rolled back:
                                   successbrian has no DELETE on
                                   atlas.nodes, so the probe never commits)
  planner_rotation.py --plan [N]   next N goals in rotation order +
                                   the coverage line (default 10)
  planner_rotation.py --status     coverage line only
  planner_rotation.py --look SLUG --findings TEXT [--work TEXT]
                      [--tier planner|morpheus|sonic|reap]
                      [--blocker TEXT] [--clear-blocker] [--seat TEXT]
                                   file one real look
  planner_rotation.py --drive [N] [--dry-run]
                                   B20-1: file up to N driver looks in
                                   rotation order (default 1), each
                                   assessed from the goal's live record
                                   + tasks; --dry-run assesses but
                                   files nothing
  planner_rotation.py --dispatch [N] [--dry-run]
                                   dispatch the N oldest undispatched
                                   looks to their recorded engine tier
                                   (default 10); --dry-run builds but
                                   sends no REAP packet
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "pm"))
import sbos_common  # noqa: E402
import goal_nodes as gn  # noqa: E402
import pm_core  # noqa: E402

ROTATION_EXCLUDED_STATUSES = ("done", "cancelled")
ENGINE_TIERS = ("planner", "morpheus", "sonic", "reap")
DEFAULT_SEAT = "planner"
DEFAULT_TIER = "planner"
# B20-1: driver looks are machine-filed on a cadence, so they carry
# their own seat in the ledger - provenance that separates them from
# looks a planner seat filed by hand.
DRIVER_SEAT = "planner-driver"
# B20-1: a driver look names a condition only when the live record
# proves it (target passed, progress 100% while still active). A
# condition is never invented, and a look never flips a goal's
# status - a status change is Brian's call or a planner seat's
# confirmed judgment, never the driver's.


def rotation_key(row):
    """Sort key: priority DESC, least-recently-looked first (None =
    never looked heads the queue), slug ASC tiebreak.
    Row shape: (goal_slug, priority, days_since_look)."""
    slug, prio, days = row[0], row[1], row[2]
    return (-prio, 0 if days is None else 1, -(days or 0), slug)


def fetch_rotation():
    """Active goal nodes in rotation order (SQL mirrors rotation_key)."""
    rows = sbos_common.pg_rows(
        "SELECT goal_slug, priority, status, days_since_look, "
        "look_overdue, blocker FROM atlas.goal_nodes "
        "WHERE status NOT IN ('done', 'cancelled') "
        "ORDER BY priority DESC, days_since_look DESC NULLS FIRST, "
        "goal_slug")
    return rows


def coverage():
    """(active, looked, never_looked, oldest_unlooked_row_or_None)."""
    rows = fetch_rotation()
    active = len(rows)
    looked = sum(1 for r in rows if r[3] is not None)
    never = active - looked
    oldest = next((r for r in rows if r[3] is None), None)
    return active, looked, never, oldest


def coverage_line():
    active, looked, never, oldest = coverage()
    oldest_s = (f"oldest un-looked: {oldest[0]} (prio {oldest[1]})"
                if oldest else "oldest un-looked: none")
    return (f"coverage: {looked}/{active} looked, {never} never looked; "
            f"{oldest_s}")


def plan(n):
    rows = fetch_rotation()
    print(coverage_line())
    print(f"next {min(n, len(rows))} in rotation order:")
    for slug, prio, status, days, overdue, blocker in rows[:n]:
        age = "never" if days is None else f"{days:.1f}d ago"
        flag = "OVERDUE" if overdue else "ok"
        extra = f" blocker: {blocker}" if blocker else ""
        print(f"  {slug} prio={prio} {status} last look {age} "
              f"[{flag}]{extra}")
    return 0


def status():
    print(coverage_line())
    return 0


def _validate_look(slug, findings, tier):
    errs = []
    if not slug:
        errs.append("goal_slug must be non-empty")
    if not findings or not findings.strip():
        errs.append("findings must be non-empty text")
    if tier not in ENGINE_TIERS:
        errs.append(f"engine_tier must be one of {ENGINE_TIERS}")
    return errs


def do_look(cur, slug, findings, work="", tier=DEFAULT_TIER,
            blocker=None, clear_blocker=False, seat=DEFAULT_SEAT):
    """File one look on an open cursor/transaction. Returns ledger id.
    Raises ValueError on a refused look (unknown goal, goal left the
    rotation, invalid tier/findings); raises on CHECK failure."""
    errs = _validate_look(slug, findings, tier)
    if errs:
        raise ValueError("; ".join(errs))
    cur.execute(
        "SELECT node_key, status, details FROM atlas.nodes "
        "WHERE node_key = %s AND node_type = 'goal'",
        [gn.node_key_for_slug(slug)])
    node = cur.fetchone()
    if node is None:
        raise ValueError(f"no goal node for slug: {slug}")
    _key, status, details = node
    if status in ROTATION_EXCLUDED_STATUSES:
        raise ValueError(
            f"goal {slug} has left the rotation (status {status})")
    details = dict(details or {})
    details["last_looked_at"] = datetime.now(timezone.utc).isoformat()
    details["look_count"] = int(details.get("look_count") or 0) + 1
    details["planner_seat"] = seat
    if clear_blocker:
        details["blocker"] = None
    elif blocker is not None:
        details["blocker"] = blocker
    derrs = gn.validate_details(details)
    if derrs:
        raise ValueError(f"look would break the goal contract: {derrs}")
    cur.execute(
        "INSERT INTO successbrian_os.goal_coverage "
        "(goal_slug, planner_seat, findings, work_spawned, engine_tier, "
        "blocker) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        [slug, seat, findings.strip(), (work or "").strip(), tier,
         details.get("blocker")])
    ledger_id = cur.fetchone()[0]
    cur.execute(
        "UPDATE atlas.nodes SET details = %s::jsonb WHERE node_key = %s",
        [json.dumps(details), gn.node_key_for_slug(slug)])
    return ledger_id


def look(slug, findings, work="", tier=DEFAULT_TIER, blocker=None,
         clear_blocker=False, seat=DEFAULT_SEAT):
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        try:
            ledger_id = do_look(cur, slug, findings, work, tier,
                                blocker, clear_blocker, seat)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        print(f"look filed: goal_coverage id {ledger_id} for {slug} "
              f"(tier {tier}, seat {seat})")
        return 0
    finally:
        conn.close()


def classify_look(state):
    """Pure classification of a driver look from a goal-state dict.

    state keys: slug, status, target_date (date|None),
    progress_pct (int|None), updated_at (datetime|None),
    tasks_total, tasks_done, blocker, has_record (bool).
    Returns (findings, work, tier, blocker_or_None). Every clause
    of the findings comes from a live row; work is spawned only
    for a record-proven condition (target passed, progress 100%
    while still active), at tier planner - the driver shapes, it
    never judges at a harder tier and never flips status.
    """
    slug = state["slug"]
    status = state["status"]
    target = state.get("target_date")
    if target is not None and hasattr(target, "date"):
        target = target.date()
    pct = state.get("progress_pct")
    updated = state.get("updated_at")
    total = state.get("tasks_total", 0)
    done = state.get("tasks_done", 0)
    blocker = state.get("blocker")
    today = datetime.now(timezone.utc).date()

    parts = [f"driver look: status {status}"]
    if not state.get("has_record", True):
        parts.append("no sbos_goals row for this slug")
    if total:
        parts.append(f"{done}/{total} tasks done")
    else:
        parts.append("no task nodes")
    if pct is not None:
        parts.append(f"progress {pct}%")
    if target is None:
        parts.append("no target date")
    else:
        delta = (today - target).days
        if delta > 0:
            parts.append(f"target {target} passed {delta}d ago")
        elif delta == 0:
            parts.append(f"target {target} today")
        else:
            parts.append(f"target {target} in {-delta}d")
    if updated is not None:
        upd = updated.date() if hasattr(updated, "date") else updated
        parts.append(f"goal record updated {upd}")
    parts.append(f"blocker on record: {blocker}" if blocker
                 else "no blocker named")
    findings = ", ".join(parts) + "."

    conditions = []
    if target is not None and (today - target).days > 0:
        conditions.append(
            f"target {target} passed while status {status}")
    if pct == 100:
        conditions.append(
            f"progress 100% while status {status}")
    if conditions:
        work = ("confirm whether this goal is complete or needs "
                "re-targeting: " + "; ".join(conditions))
        return findings, work, "planner", "; ".join(conditions)
    return (findings, "none - record current, no spawnable work "
            "this look", "planner", None)


def assess_goal(cur, slug):
    """Read a goal's live record + tasks; derive a driver look.
    Returns (findings, work, tier, blocker). Raises ValueError
    when the goal has no node (same refusal shape as do_look).
    """
    cur.execute(
        "SELECT status, blocker FROM atlas.goal_nodes "
        "WHERE goal_slug = %s", [slug])
    node = cur.fetchone()
    if node is None:
        raise ValueError(f"no goal node for slug: {slug}")
    node_status, node_blocker = node
    cur.execute(
        "SELECT status, target_date, progress_pct, updated_at "
        "FROM successbrian_os.sbos_goals WHERE goal_slug = %s",
        [slug])
    grow = cur.fetchone()
    cur.execute(
        "SELECT count(*), count(*) FILTER (WHERE status IN "
        "('done', 'completed', 'closed')) FROM atlas.goal_tasks "
        "WHERE goal_slug = %s", [slug])
    total, done = cur.fetchone()
    if grow is None:
        state = {"slug": slug, "status": node_status,
                 "target_date": None, "progress_pct": None,
                 "updated_at": None, "tasks_total": total,
                 "tasks_done": done, "blocker": node_blocker,
                 "has_record": False}
    else:
        gstatus, target, pct, updated = grow
        state = {"slug": slug, "status": gstatus,
                 "target_date": target, "progress_pct": pct,
                 "updated_at": updated, "tasks_total": total,
                 "tasks_done": done, "blocker": node_blocker,
                 "has_record": True}
    return classify_look(state)


def drive(limit=1, dry_run=False):
    """File up to N driver looks in rotation order (never-looked
    first, priority DESC). Each look is assessed from the goal's
    live record + tasks via assess_goal; one transaction per look,
    a failure rolls that look back and the run moves on. With
    --dry-run, assesses but files nothing. The cadence cron runs
    this: 1 look every 2 hours moves 12/day, so a 42-goal
    rotation turns over in ~3.5 days, inside the 4-day coverage
    window (B10)."""
    rows = fetch_rotation()[:limit]
    if not rows:
        print("drive: rotation empty")
        return 0
    done, failed = 0, 0
    for slug, prio, _status, _days, _overdue, _blocker in rows:
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN")
            try:
                findings, work, tier, new_blocker = assess_goal(
                    cur, slug)
                if dry_run:
                    print(f"  {slug}: DRY-RUN would file: {findings} "
                          f"| work: {work} | tier {tier}"
                          + (f" | blocker: {new_blocker}"
                             if new_blocker else ""))
                    conn.rollback()
                else:
                    lid = do_look(cur, slug, findings, work, tier,
                                  new_blocker, seat=DRIVER_SEAT)
                    conn.commit()
                    print(f"  look filed: goal_coverage id {lid} for "
                          f"{slug} (driver, tier {tier})")
                done += 1
            except Exception as e:
                conn.rollback()
                print(f"  {slug}: FAILED {e}")
                failed += 1
        finally:
            conn.close()
    print(coverage_line())
    if dry_run:
        print(f"drive: {done} assessed, {failed} failed (dry-run)")
    else:
        print(f"drive: {done} filed, {failed} failed (live)")
    return 0 if failed == 0 else 1


# ------------------------------------------------------------- B12b dispatch

NO_WORK_PREFIXES = ("none", "no work", "no spawnable")


def has_spawnable_work(work):
    """True when a look's work_spawned names real work. The B12 look
    convention writes 'none ...' when a look spawns nothing - that
    is a statement, not work, and must never become a step."""
    w = (work or "").strip()
    if not w:
        return False
    return not w.lower().startswith(NO_WORK_PREFIXES)


def _set_node_blocker(cur, slug, text):
    """Set a blocker on a goal node only when it has none (never
    clobber an existing blocker). Returns True when it wrote."""
    cur.execute(
        "SELECT details FROM atlas.nodes WHERE node_key = %s "
        "AND node_type = 'goal'", [gn.node_key_for_slug(slug)])
    row = cur.fetchone()
    if row is None:
        return False
    details = dict(row[0] or {})
    if details.get("blocker"):
        return False
    details["blocker"] = text
    derrs = gn.validate_details(details)
    if derrs:
        raise ValueError(f"blocker would break the goal contract: {derrs}")
    cur.execute(
        "UPDATE atlas.nodes SET details = %s::jsonb WHERE node_key = %s",
        [json.dumps(details), gn.node_key_for_slug(slug)])
    return True


def _mark_dispatched(cur, look_id, ref):
    cur.execute(
        "UPDATE successbrian_os.goal_coverage SET dispatched_at = now(), "
        "dispatch_ref = %s WHERE id = %s", [ref, look_id])


def do_dispatch(cur, look, dry_run=False):
    """Dispatch ONE look row on an open cursor/transaction.
    look: (id, goal_slug, findings, work_spawned, engine_tier,
    blocker, priority). Returns (dispatch_ref, note). Raises on a
    bad tier or a failed node write; the caller rolls that look
    back and moves on. The reap bus insert commits on its own
    connection before the ledger mark, so a crash between the two
    leaves the look undispatched and a retry re-sends with the
    same deterministic probe_id (dedup aid, never a silent loss)."""
    lid, slug, findings, work, tier, blocker, prio = look
    work = (work or "").strip()
    if not has_spawnable_work(work):
        if not (blocker or "").strip():
            _set_node_blocker(
                cur, slug,
                f"dispatch: look {lid} named no spawnable work")
        _mark_dispatched(cur, lid, "no-work:blocker-held")
        return ("no-work:blocker-held",
                "no spawnable work; blocker held, nothing created")
    step_key = f"goal-look-{lid}-dispatch"
    context = f"goal {slug} look {lid}: {(findings or '').strip()}"
    if tier == "planner":
        pm_core.add_step(
            cur, step_key, f"[{slug}] {work[:100]}", kind="task",
            source=f"goal_coverage:{lid}", priority=int(prio or 50),
            payload={"instruction": work, "context": context,
                     "source": f"goal_coverage:{lid}",
                     "engine_tier": "planner"})
        ref = f"pm_steps:{step_key}"
        _mark_dispatched(cur, lid, ref)
        return (ref, "planner task step created")
    if tier == "morpheus":
        pm_core.add_step(
            cur, step_key, f"[{slug}] {work[:100]}", kind="judgment",
            source=f"goal_coverage:{lid}", priority=int(prio or 50),
            payload={"instruction": work, "context": context,
                     "output_keys": ["verdict", "evidence"],
                     "max_tokens": 800, "engine_tier": "morpheus"})
        ref = f"pm_steps:{step_key}"
        _mark_dispatched(cur, lid, ref)
        return (ref, "morpheus judgment step created")
    if tier == "sonic":
        # B12c: the sonic-worker claims judgment steps with
        # payload.engine_tier='sonic'; morpheus-worker excludes them,
        # so this can never fall down to Morpheus.
        pm_core.add_step(
            cur, step_key, f"[{slug}] {work[:100]}", kind="judgment",
            source=f"goal_coverage:{lid}", priority=int(prio or 50),
            payload={"instruction": work, "context": context,
                     "output_keys": ["verdict", "evidence"],
                     "max_tokens": 800, "engine_tier": "sonic"})
        ref = f"pm_steps:{step_key}"
        _mark_dispatched(cur, lid, ref)
        return (ref, "sonic judgment step created")
    if tier == "reap":
        prompt = (f"Goal {slug} (look {lid}): {work}\n\n"
                  f"Findings: {(findings or '').strip()}")
        if sbos_common.estimate_tokens(prompt) > 2000:
            if not (blocker or "").strip():
                _set_node_blocker(
                    cur, slug,
                    f"work too large for one feeder packet - needs "
                    f"breakdown (look {lid})")
            _mark_dispatched(cur, lid, "blocked:packet-too-large")
            return ("blocked:packet-too-large",
                    "prompt over the packet budget; blocker filed")
        packet = sbos_common.build_reap_packet(
            prompt, source=f"goal_coverage:{lid}",
            probe_id=step_key, max_tokens=500)
        if dry_run:
            _mark_dispatched(cur, lid, "dry-run:reap-packet-ready")
            return ("dry-run:reap-packet-ready",
                    "packet builds within the 500-token ceiling; "
                    "no bus insert in dry-run")
        event_id = sbos_common.dispatch_reap_packet(
            packet, source=f"goal_coverage:{lid}")
        ref = f"bus.reap_infer:{event_id}"
        _mark_dispatched(cur, lid, ref)
        return (ref, f"REAP packet on the bus (event {event_id})")
    raise ValueError(f"unknown engine_tier: {tier}")


def fetch_undispatched(limit):
    return sbos_common.pg_rows(
        "SELECT c.id, c.goal_slug, c.findings, c.work_spawned, "
        "c.engine_tier, c.blocker, COALESCE(g.priority, 50) "
        "FROM successbrian_os.goal_coverage c "
        "LEFT JOIN atlas.goal_nodes g ON g.goal_slug = c.goal_slug "
        "WHERE c.dispatched_at IS NULL ORDER BY c.id ASC LIMIT %s",
        [limit])


def dispatch(limit=10, dry_run=False):
    """Dispatch the oldest undispatched looks, one transaction
    each: a failure rolls that look back and the run moves on."""
    looks = fetch_undispatched(limit)
    if not looks:
        print("dispatch: no undispatched looks")
        return 0
    done, failed = 0, 0
    for look in looks:
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN")
            try:
                ref, note = do_dispatch(cur, look, dry_run=dry_run)
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"  look {look[0]} ({look[1]}): FAILED {e}")
                failed += 1
                continue
            print(f"  look {look[0]} ({look[1]}, tier {look[4]}): "
                  f"{ref} - {note}")
            done += 1
        finally:
            conn.close()
    print(f"dispatch: {done} dispatched, {failed} failed "
          f"({'dry-run' if dry_run else 'live'})")
    return 0 if failed == 0 else 1


def selftest():
    steps = []

    def check(name, cond):
        steps.append((name, bool(cond)))
        assert cond, f"selftest step failed: {name}"

    # Pure ordering: priority first, never-looked before looked,
    # slug tiebreak.
    rows = [("b-goal", 75, 2.0), ("a-goal", 75, None),
            ("c-goal", 90, None), ("d-goal", 90, 5.0),
            ("e-goal", 50, None)]
    ordered = sorted(rows, key=rotation_key)
    check("rotation order: prio, never-first, slug tiebreak",
          [r[0] for r in ordered] == ["c-goal", "d-goal", "a-goal",
                                      "b-goal", "e-goal"])
    check("staler looked goal before fresher at same prio",
          rotation_key(("x", 75, 5.0)) < rotation_key(("y", 75, 1.0)))
    check("bad tier rejected",
          _validate_look("g", "f", "penny"))
    check("empty findings rejected",
          _validate_look("g", "   ", "planner"))
    check("good look validates",
          not _validate_look("g", "state checked", "reap"))

    # Live: ledger table exists, SQL order agrees with Python order.
    check("goal_coverage table present",
          sbos_common.pg_one(
              "SELECT count(*) FROM information_schema.tables "
              "WHERE table_schema = 'successbrian_os' "
              "AND table_name = 'goal_coverage'") == 1)
    live = fetch_rotation()
    check("rotation is non-empty", len(live) > 0)
    check("SQL order matches Python rotation_key",
          [r[0] for r in sorted(
              [(r[0], r[1], r[3]) for r in live],
              key=rotation_key)] == [r[0] for r in live])
    check("no done/cancelled goal in the rotation",
          all(r[2] not in ROTATION_EXCLUDED_STATUSES for r in live))
    active, looked, never, oldest = coverage()
    check("coverage sums", looked + never == active)
    check("oldest un-looked is a never-looked head goal",
          oldest is None or oldest[3] is None)

    # Transactional probe look: insert a probe goal node, file a look
    # on it, verify ledger row + node advance + view exposure, then
    # roll everything back - no residue (no DELETE on atlas.nodes).
    probe_slug = "__selftest__b12__"
    probe = {"goal_slug": probe_slug, "priority": 50,
             "coverage_window_days": 4}
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details, ref_kind, "
            "ref_id) VALUES (%s, 'goal', 'SELFTEST disposable', "
            "'planned', %s::jsonb, 'sbos_goal', '0')",
            [gn.node_key_for_slug(probe_slug), json.dumps(probe)])
        lid = do_look(cur, probe_slug,
                      "SELFTEST probe look: state checked, nothing "
                      "stale beyond the probe itself.",
                      work="none - probe only", tier="planner",
                      blocker="probe blocker")
        cur.execute("SELECT goal_slug, planner_seat, engine_tier, "
                    "blocker FROM successbrian_os.goal_coverage "
                    "WHERE id = %s", [lid])
        lrow = cur.fetchone()
        check("ledger row holds the probe look",
              lrow is not None and lrow[0] == probe_slug
              and lrow[1] == "planner" and lrow[2] == "planner"
              and lrow[3] == "probe blocker")
        cur.execute("SELECT details FROM atlas.nodes WHERE node_key = %s",
                    [gn.node_key_for_slug(probe_slug)])
        drow = cur.fetchone()[0]
        check("node advanced: look_count 1, last_looked_at set, "
              "blocker mirrored",
              drow.get("look_count") == 1
              and drow.get("last_looked_at")
              and drow.get("blocker") == "probe blocker")
        cur.execute("SELECT days_since_look FROM atlas.goal_nodes "
                    "WHERE node_key = %s",
                    [gn.node_key_for_slug(probe_slug)])
        vrow = cur.fetchone()
        check("view exposes probe as just looked",
              vrow is not None and vrow[0] is not None
              and vrow[0] < 1.0)
        # A look at a closed goal is refused.
        cur.execute(
            "UPDATE atlas.nodes SET status = 'cancelled' "
            "WHERE node_key = %s", [gn.node_key_for_slug(probe_slug)])
        refused = False
        try:
            do_look(cur, probe_slug, "should refuse")
        except ValueError as e:
            refused = "left the rotation" in str(e)
        check("look at a cancelled goal is refused", refused)
        cur.execute("ROLLBACK")
        check("probe goal node rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM atlas.nodes WHERE node_key = %s",
                  [gn.node_key_for_slug(probe_slug)]) == 0)
        check("probe ledger row rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM successbrian_os.goal_coverage "
                  "WHERE goal_slug = %s", [probe_slug]) == 0)
    finally:
        conn.close()

    # B12b dispatch: pure classification, then a live transactional
    # probe (rolled back, no residue). The reap branch runs in
    # dry-run inside the probe: a real bus insert would queue live
    # gamma work and cannot be rolled back (own connection).
    check("no-work text recognized (empty / none-prefixed)",
          not has_spawnable_work("")
          and not has_spawnable_work(
              "none this look - next work named")
          and not has_spawnable_work("No work spawned")
          and has_spawnable_work("draft the offer page"))
    probe_slug = "__selftest__b12b__"
    probe = {"goal_slug": probe_slug, "priority": 50,
             "coverage_window_days": 4}
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details, ref_kind, "
            "ref_id) VALUES (%s, 'goal', 'SELFTEST disposable', "
            "'planned', %s::jsonb, 'sbos_goal', '0')",
            [gn.node_key_for_slug(probe_slug), json.dumps(probe)])
        probe_looks = []
        for tier, work, blocker in [
                ("planner", "shape the offer ladder", None),
                ("morpheus",
                 "judge whether the offer fits the audience", None),
                ("sonic", "final verdict on the offer", None),
                ("reap", "deep pass on the offer evidence", None),
                ("reap", "x" * 9000, None),
                ("planner", "none this look - nothing spawned",
                 "probe blocker held")]:
            cur.execute(
                "INSERT INTO successbrian_os.goal_coverage "
                "(goal_slug, planner_seat, findings, work_spawned, "
                "engine_tier, blocker) VALUES (%s, 'planner', "
                "'SELFTEST probe findings', %s, %s, %s) RETURNING id",
                [probe_slug, work, tier, blocker])
            lid = cur.fetchone()[0]
            probe_looks.append((lid, probe_slug,
                                "SELFTEST probe findings", work, tier,
                                blocker, 50))
        refs = [do_dispatch(cur, lk, dry_run=True)
                for lk in probe_looks]
        # NOTE: pg_one/pg_rows open their own connection, so they
        # cannot see this transaction's uncommitted rows; all probe
        # assertions below read through this transaction's cursor.
        cur.execute("SELECT step_key, kind FROM successbrian_os.pm_steps "
                    "WHERE step_key LIKE %s AND source = %s "
                    "ORDER BY step_key",
                    ["goal-look-%-dispatch",
                     f"goal_coverage:{probe_looks[0][0]}"])
        check("planner look created exactly one task step",
              cur.fetchall() == [
                  (f"goal-look-{probe_looks[0][0]}-dispatch", "task")])
        cur.execute("SELECT kind FROM successbrian_os.pm_steps "
                    "WHERE step_key = %s",
                    [f"goal-look-{probe_looks[1][0]}-dispatch"])
        check("morpheus look -> judgment step",
              refs[1][0] == f"pm_steps:goal-look-{probe_looks[1][0]}"
              "-dispatch"
              and cur.fetchone() == ("judgment",))
        cur.execute("SELECT kind, payload->>'engine_tier' "
                    "FROM successbrian_os.pm_steps WHERE step_key = %s",
                    [f"goal-look-{probe_looks[2][0]}-dispatch"])
        check("sonic look -> sonic-tier judgment step",
              refs[2][0] == f"pm_steps:goal-look-{probe_looks[2][0]}"
              "-dispatch"
              and cur.fetchone() == ("judgment", "sonic"))
        cur.execute("SELECT details->>'blocker' FROM atlas.nodes "
                    "WHERE node_key = %s",
                    [gn.node_key_for_slug(probe_slug)])
        check("sonic branch filed no blocker (oversize reap did)",
              cur.fetchone()[0] == "work too large for one feeder "
              "packet - needs breakdown "
              f"(look {probe_looks[4][0]})")
        check("reap look dry-run -> packet ready, no bus insert",
              refs[3][0] == "dry-run:reap-packet-ready")
        check("oversize reap work -> packet-too-large blocker",
              refs[4][0] == "blocked:packet-too-large")
        check("no-work look -> blocker held, no step",
              refs[5][0] == "no-work:blocker-held")
        cur.execute("SELECT count(*) FROM successbrian_os.pm_steps "
                    "WHERE step_key IN (%s, %s, %s, %s, %s, %s)",
                    [f"goal-look-{l[0]}-dispatch"
                     for l in probe_looks])
        check("planner + morpheus + sonic looks created steps",
              cur.fetchone()[0] == 3)
        cur.execute("SELECT count(*) FROM successbrian_os.goal_coverage "
                    "WHERE goal_slug = %s AND dispatched_at IS NOT NULL",
                    [probe_slug])
        check("all six probe looks marked dispatched",
              cur.fetchone()[0] == 6)
        cur.execute("ROLLBACK")
        check("probe goal node rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM atlas.nodes WHERE node_key = %s",
                  [gn.node_key_for_slug(probe_slug)]) == 0)
        check("probe ledger rows rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM successbrian_os.goal_coverage "
                  "WHERE goal_slug = %s", [probe_slug]) == 0)
        check("probe pm_steps rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM successbrian_os.pm_steps "
                  "WHERE step_key LIKE 'goal-look-%-dispatch' "
                  "AND source LIKE 'goal_coverage:%' "
                  "AND created_at > now() - interval '1 hour'") == 0)
    finally:
        conn.close()

    # B20-1 driver: pure classification, then a transactional
    # assess + file probe (rolled back, no residue).
    from datetime import date as _date
    _past = {"slug": "g", "status": "planning",
             "target_date": _date(2026, 9, 23), "progress_pct": 100,
             "updated_at": None, "tasks_total": 0, "tasks_done": 0,
             "blocker": None, "has_record": True}
    _f, _w, _t, _b = classify_look(_past)
    check("driver: target passed -> confirm work + blocker, planner",
          _w.startswith("confirm") and _t == "planner"
          and _b is not None and "2026-09-23" in _b
          and "passed" in _f and "2026-09-23" in _f)
    _cur = {"slug": "g", "status": "in_progress",
            "target_date": _date(2099, 1, 1), "progress_pct": 50,
            "updated_at": None, "tasks_total": 2, "tasks_done": 1,
            "blocker": None, "has_record": True}
    _f2, _w2, _t2, _b2 = classify_look(_cur)
    check("driver: current goal -> no work, no new blocker",
          _w2.startswith("none") and _b2 is None
          and "1/2 tasks done" in _f2 and "progress 50%" in _f2)
    _done = dict(_cur, target_date=_date(2099, 1, 1),
                 progress_pct=100)
    _f3, _w3, _t3, _b3 = classify_look(_done)
    check("driver: 100% progress + active -> confirm-completion",
          _w3.startswith("confirm") and _b3 is not None
          and "100%" in _b3)
    _norow = dict(_cur, has_record=False)
    _f4, _w4, _t4, _b4 = classify_look(_norow)
    check("driver: no sbos_goals row -> findings say so, no work",
          "no sbos_goals row" in _f4 and _w4.startswith("none")
          and _b4 is None)
    probe_slug = "__selftest__b20__"
    probe = {"goal_slug": probe_slug, "priority": 50,
             "coverage_window_days": 4}
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details, ref_kind, "
            "ref_id) VALUES (%s, 'goal', 'SELFTEST disposable', "
            "'planned', %s::jsonb, 'sbos_goal', '0')",
            [gn.node_key_for_slug(probe_slug), json.dumps(probe)])
        pf, pw, pt, pb = assess_goal(cur, probe_slug)
        check("driver probe: assess on node without sbos row",
              "no sbos_goals row" in pf and pw.startswith("none")
              and pt == "planner" and pb is None)
        lid = do_look(cur, probe_slug, pf, pw, pt, pb,
                      seat=DRIVER_SEAT)
        cur.execute("SELECT goal_slug, planner_seat, engine_tier "
                    "FROM successbrian_os.goal_coverage WHERE id = %s",
                    [lid])
        lrow = cur.fetchone()
        check("driver probe: ledger row carries driver seat",
              lrow is not None and lrow[0] == probe_slug
              and lrow[1] == DRIVER_SEAT and lrow[2] == "planner")
        cur.execute("SELECT details FROM atlas.nodes WHERE node_key = %s",
                    [gn.node_key_for_slug(probe_slug)])
        check("driver probe: node advanced look_count 1",
              cur.fetchone()[0].get("look_count") == 1)
        cur.execute("ROLLBACK")
        check("driver probe goal node rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM atlas.nodes WHERE node_key = %s",
                  [gn.node_key_for_slug(probe_slug)]) == 0)
        check("driver probe ledger row rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM successbrian_os.goal_coverage "
                  "WHERE goal_slug = %s", [probe_slug]) == 0)
    finally:
        conn.close()

    print(f"PLANNER_ROTATION_OK ({len(steps)} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--plan", nargs="?", const=10, type=int, metavar="N")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--look", metavar="SLUG")
    ap.add_argument("--findings")
    ap.add_argument("--work", default="")
    ap.add_argument("--tier", default=DEFAULT_TIER,
                    choices=ENGINE_TIERS)
    ap.add_argument("--blocker")
    ap.add_argument("--clear-blocker", action="store_true")
    ap.add_argument("--seat", default=DEFAULT_SEAT)
    ap.add_argument("--dispatch", nargs="?", const=10, type=int,
                    metavar="N")
    ap.add_argument("--drive", nargs="?", const=1, type=int,
                    metavar="N",
                    help="B20-1: file up to N driver looks in rotation "
                    "order (default 1)")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --dispatch: build but send no REAP "
                    "packet; with --drive: assess but file no look")
    a = ap.parse_args()
    if a.drive is not None:
        return drive(a.drive, dry_run=a.dry_run)
    if a.dispatch is not None:
        return dispatch(a.dispatch, dry_run=a.dry_run)
    if a.selftest:
        return selftest()
    if a.plan is not None:
        return plan(a.plan)
    if a.status:
        return status()
    if a.look:
        if not a.findings:
            ap.error("--look requires --findings")
        try:
            return look(a.look, a.findings, a.work, a.tier, a.blocker,
                        a.clear_blocker, a.seat)
        except ValueError as e:
            print(f"look refused: {e}", file=sys.stderr)
            return 3
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
