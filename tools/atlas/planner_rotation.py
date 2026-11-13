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
    hardest judgment (final verdicts, ambiguous/thin evidence). v1
    RECORDS the tier the look's spawned work belongs to; actually
    dispatching look work to an engine is the B12b follow-up, not this
    item. A look that finds work it cannot do files it as a named
    blocker on the goal - never a silent skip.
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
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402
import goal_nodes as gn  # noqa: E402

ROTATION_EXCLUDED_STATUSES = ("done", "cancelled")
ENGINE_TIERS = ("planner", "morpheus", "sonic", "reap")
DEFAULT_SEAT = "planner"
DEFAULT_TIER = "planner"


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
    a = ap.parse_args()
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
