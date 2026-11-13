#!/usr/bin/env python3
"""goal_task_sync.py - Goal->task conversion v1 (BUILD_QUEUE B11).

Phase 3 (Atlas goal machinery), second half: B10 built the goal-node
contract and left population to this item; this module IS the sync.
It converts the Goals-tab record into Atlas nodes, idempotently:

  1. goal nodes: every successbrian_os.sbos_goals row WITH a goal_slug
     becomes/updates atlas.nodes node_key 'goal:<slug>' (B10's builder
     + status map, ref_kind 'sbos_goal'). Rotation-owned detail keys
     (last_looked_at, look_count, planner_seat, blocker) are preserved
     across syncs — the sync never clobbers the rotation's ledger.
  2. task nodes: every OPEN successbrian_os.tasks row under a slugged
     goal becomes/updates node_key 'task:<goal_slug>:<task_id>'
     (node_type 'task', ref_kind 'sbos_task'), with a
     goal:<slug> --contains--> task node edge.
  3. reconcile: a task node whose source task left open status is
     updated to its terminal status (done/cancelled/archived) instead
     of being left stale or deleted.

Scope decisions, from live data on 2026-11-13 (recorded here so the
next reader does not re-derive them):
  - 3,030 of 3,087 sbos_goals rows have NO goal_slug, so they have no
    stable node_key. They are counted as skipped, never slug-invented.
    57 rows carry slugs; one slug is duplicated
    (infra-provisioning-worker-20260913: id 96 cancelled, id 167
    planning) — the sync takes the non-cancelled row, lowest id first.
  - Only OPEN tasks sync (pending/active/open/in_progress/blocked):
    6 under slugged goals on 2026-11-13, all DealsDesk/Mantis work.
    The other 811 tasks under slugged goals are completed/cancelled/
    archived and stay in successbrian_os.tasks — importing them would
    fill Atlas with dead history. 173 open tasks belong to unslugged
    goals and stay unlinked; the sync reports that count.
  - The three pre-existing hand-made task nodes (ref_kind NULL) are
    untouched: the B11 CHECK binds only ref_kind='sbos_task' rows.

Nothing here sends, buys, publishes, or contacts anyone. One sync
runs in a single transaction; --dry-run prints the change set without
writing. Re-running the sync is a no-op when nothing changed.

Usage:
  goal_task_sync.py --selftest   contract checks + live validator/CHECK
                                 probes + a transactional round-trip
                                 (rolled back: successbrian has no DELETE
                                 on atlas.nodes/edges, so the probe never
                                 commits) + idempotency probe
  goal_task_sync.py --sync       live sync (one transaction)
  goal_task_sync.py --dry-run    print the change set, write nothing
  goal_task_sync.py --status     counts: goal nodes, task nodes, edges,
                                 unslugged goals, unlinked open tasks
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402
import goal_nodes as gn  # noqa: E402

TASK_REQUIRED_KEYS = ("task_id", "goal_slug", "priority", "status")
TASK_OPTIONAL_KEYS = ("progress_pct", "target_date", "assigned_to",
                      "stale_flag", "completed_at", "source_updated_at")
TASK_ALLOWED_KEYS = set(TASK_REQUIRED_KEYS) | set(TASK_OPTIONAL_KEYS)

# Rotation-owned goal detail keys the sync must never clobber.
ROTATION_KEYS = ("last_looked_at", "look_count", "planner_seat", "blocker")

OPEN_TASK_STATUSES = ("pending", "active", "open", "in_progress", "blocked")

TASK_STATUS_MAP = {"pending": "active", "open": "active",
                   "active": "active", "in_progress": "active",
                   "blocked": "blocked", "completed": "done",
                   "done": "done", "cancelled": "cancelled",
                   "archived": "archived"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}([T ]([01]\d|2[0-3]):[0-5]\d"
    r"(:[0-5]\d(\.\d+)?)?(Z|[+-]([01]\d|2[0-3]):?[0-5]\d)?)?$")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _valid_date(s):
    if not isinstance(s, str) or not DATE_RE.match(s):
        return False
    try:
        date.fromisoformat(s)
    except ValueError:
        return False
    return True


def _valid_ts(s):
    if not isinstance(s, str) or not TS_RE.match(s):
        return False
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def validate_task_details(d):
    """Python mirror of atlas.task_node_details_valid. Returns [errors]."""
    errs = []
    if not isinstance(d, dict):
        return ["details is not an object"]
    for k in TASK_REQUIRED_KEYS:
        if k not in d:
            errs.append(f"missing required key: {k}")
    for k in d:
        if k not in TASK_ALLOWED_KEYS:
            errs.append(f"unknown key: {k}")
    if "task_id" in d and (not _is_int(d["task_id"]) or d["task_id"] < 1):
        errs.append("task_id must be an int >= 1")
    if "goal_slug" in d and (not isinstance(d["goal_slug"], str)
                             or not d["goal_slug"]):
        errs.append("goal_slug must be a non-empty string")
    if "priority" in d and (not isinstance(d["priority"], str)
                            or not d["priority"]):
        errs.append("priority must be a non-empty string")
    if "status" in d and (not isinstance(d["status"], str)
                          or not d["status"]):
        errs.append("status must be a non-empty string")
    if "progress_pct" in d and (not _is_int(d["progress_pct"])
                                or not 0 <= d["progress_pct"] <= 100):
        errs.append("progress_pct must be an int 0-100")
    if "target_date" in d and not _valid_date(d["target_date"]):
        errs.append("target_date must be a real YYYY-MM-DD date")
    if "assigned_to" in d and d["assigned_to"] is not None \
            and not isinstance(d["assigned_to"], str):
        errs.append("assigned_to must be a string or null")
    if "stale_flag" in d and d["stale_flag"] is not None \
            and not isinstance(d["stale_flag"], str):
        errs.append("stale_flag must be a string or null")
    if "completed_at" in d and d["completed_at"] is not None \
            and not _valid_ts(d["completed_at"]):
        errs.append("completed_at must be an ISO timestamp or null")
    if "source_updated_at" in d and d["source_updated_at"] is not None \
            and not _valid_ts(d["source_updated_at"]):
        errs.append("source_updated_at must be an ISO timestamp or null")
    return errs


def node_key_for_task(goal_slug, task_id):
    return f"task:{goal_slug}:{task_id}"


def task_status_for_row(row):
    return TASK_STATUS_MAP.get((row.get("status") or "").lower(), "planned")


def details_for_task_row(row):
    """Build contract-valid details from a successbrian_os.tasks row
    joined to its goal's slug (dict with id, goal_slug, priority,
    status, progress_pct, target_date, assigned_to, stale_flag,
    completed_at, updated_at). Pure: no DB access."""
    details = {
        "task_id": int(row["id"]),
        "goal_slug": row["goal_slug"],
        "priority": (row.get("priority") or "normal").lower(),
        "status": task_status_for_row(row),
    }
    if row.get("progress_pct") is not None:
        details["progress_pct"] = int(row["progress_pct"])
    if row.get("target_date"):
        details["target_date"] = _iso(row["target_date"])
    if row.get("assigned_to"):
        details["assigned_to"] = row["assigned_to"]
    if row.get("stale_flag"):
        details["stale_flag"] = row["stale_flag"]
    if row.get("completed_at"):
        details["completed_at"] = _iso(row["completed_at"])
    if row.get("updated_at"):
        details["source_updated_at"] = _iso(row["updated_at"])
    errs = validate_task_details(details)
    assert not errs, f"builder produced invalid details: {errs}"
    return details


def sql_task_valid(details):
    """Ask the live SQL validator. Returns bool."""
    return bool(sbos_common.pg_one(
        "SELECT atlas.task_node_details_valid(%s::jsonb)",
        [json.dumps(details)]))


GOALS_SQL = """
SELECT g.id, g.goal_slug, g.goal_name, g.category, g.priority, g.status,
       g.target_date, p.goal_slug AS parent_goal_slug
FROM successbrian_os.sbos_goals g
LEFT JOIN successbrian_os.sbos_goals p ON p.id = g.parent_goal_id
WHERE g.goal_slug IS NOT NULL AND g.goal_slug <> ''
ORDER BY (g.status = 'cancelled'), g.id
"""

OPEN_TASKS_SQL = """
SELECT t.id, t.title, t.status, t.priority, t.progress_pct,
       t.target_date, t.assigned_to, t.stale_flag, t.completed_at,
       t.updated_at, g.goal_slug
FROM successbrian_os.tasks t
JOIN successbrian_os.sbos_goals g ON g.id = t.goal_id
WHERE g.goal_slug IS NOT NULL AND g.goal_slug <> ''
  AND t.status IN ('pending', 'active', 'open', 'in_progress', 'blocked')
ORDER BY g.goal_slug, t.id
"""

UPSERT_NODE_SQL = """
INSERT INTO atlas.nodes
  (node_key, node_type, name, status, details, ref_kind, ref_id)
VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
ON CONFLICT (node_key) DO UPDATE SET
  name = EXCLUDED.name, status = EXCLUDED.status,
  details = EXCLUDED.details, ref_kind = EXCLUDED.ref_kind,
  ref_id = EXCLUDED.ref_id, updated_at = now()
"""

UPSERT_EDGE_SQL = """
INSERT INTO atlas.edges (from_node, to_node, edge_type)
VALUES (%s, %s, 'contains')
ON CONFLICT (from_node, to_node, edge_type) DO NOTHING
"""


def _load_change_set():
    """Read the Goals-tab record and build the change set. No writes."""
    goal_rows = sbos_common.pg_rows(GOALS_SQL)
    goals, seen_slugs, dup_skipped = [], set(), 0
    for r in goal_rows:
        row = {"id": r[0], "goal_slug": r[1], "goal_name": r[2],
               "category": r[3], "priority": r[4], "status": r[5],
               "target_date": r[6], "parent_goal_slug": r[7]}
        if row["goal_slug"] in seen_slugs:
            dup_skipped += 1
            continue
        seen_slugs.add(row["goal_slug"])
        goals.append(row)
    task_rows = sbos_common.pg_rows(OPEN_TASKS_SQL)
    tasks = []
    for r in task_rows:
        tasks.append({"id": r[0], "title": r[1], "status": r[2],
                      "priority": r[3], "progress_pct": r[4],
                      "target_date": r[5], "assigned_to": r[6],
                      "stale_flag": r[7], "completed_at": r[8],
                      "updated_at": r[9], "goal_slug": r[10]})
    unslugged = sbos_common.pg_one(
        "SELECT count(*) FROM successbrian_os.sbos_goals "
        "WHERE goal_slug IS NULL OR goal_slug = ''")
    unlinked_open = sbos_common.pg_one(
        "SELECT count(*) FROM successbrian_os.tasks t "
        "WHERE t.status IN ('pending', 'active', 'open', 'in_progress', "
        "'blocked') AND (t.goal_id IS NULL OR t.goal_id NOT IN "
        "(SELECT id FROM successbrian_os.sbos_goals "
        "WHERE goal_slug IS NOT NULL AND goal_slug <> ''))")
    return {"goals": goals, "dup_skipped": dup_skipped, "tasks": tasks,
            "unslugged_goals": unslugged, "unlinked_open_tasks": unlinked_open}


def _reconcile_plan(conn):
    """Task nodes whose source task left open status, plus orphans
    whose source task row is gone. Returns (to_close, orphans)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT n.node_key, n.details, t.status, t.progress_pct, "
        "t.completed_at, t.updated_at "
        "FROM atlas.nodes n "
        "JOIN successbrian_os.tasks t ON t.id = (n.ref_id)::int "
        "WHERE n.node_type = 'task' AND n.ref_kind = 'sbos_task' "
        "AND t.status NOT IN ('pending', 'active', 'open', "
        "'in_progress', 'blocked')")
    to_close = [{"node_key": r[0], "details": dict(r[1]),
                 "status": r[2], "progress_pct": r[3],
                 "completed_at": r[4], "updated_at": r[5]}
                for r in cur.fetchall()]
    cur.execute(
        "SELECT n.node_key FROM atlas.nodes n "
        "WHERE n.node_type = 'task' AND n.ref_kind = 'sbos_task' "
        "AND NOT EXISTS (SELECT 1 FROM successbrian_os.tasks t "
        "WHERE t.id = (n.ref_id)::int)")
    orphans = [r[0] for r in cur.fetchall()]
    return to_close, orphans


def sync(dry_run=False):
    cs = _load_change_set()
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        existing_goal_details = {
            r[0]: r[1] for r in sbos_common.pg_rows(
                "SELECT node_key, details FROM atlas.nodes "
                "WHERE node_type = 'goal'")}
        goals_done = 0
        for g in cs["goals"]:
            details = gn.details_for_goal_row(g)
            old = existing_goal_details.get(gn.node_key_for_slug(
                g["goal_slug"]))
            if old:
                for k in ROTATION_KEYS:
                    if k in old:
                        details[k] = old[k]
            if not dry_run:
                cur.execute(UPSERT_NODE_SQL,
                            [gn.node_key_for_slug(g["goal_slug"]), "goal",
                             g["goal_name"], gn.node_status_for_goal_row(g),
                             json.dumps(details), "sbos_goal",
                             str(g["id"])])
            goals_done += 1
        tasks_done, edges_done = 0, 0
        for t in cs["tasks"]:
            details = details_for_task_row(t)
            key = node_key_for_task(t["goal_slug"], t["id"])
            if not dry_run:
                cur.execute(UPSERT_NODE_SQL,
                            [key, "task", t["title"],
                             task_status_for_row(t), json.dumps(details),
                             "sbos_task", str(t["id"])])
                cur.execute(UPSERT_EDGE_SQL,
                            [gn.node_key_for_slug(t["goal_slug"]), key])
            tasks_done += 1
            edges_done += 1
        to_close, orphans = _reconcile_plan(conn)
        closed = 0
        for item in to_close:
            details = dict(item["details"])
            details["status"] = TASK_STATUS_MAP.get(
                (item["status"] or "").lower(), "planned")
            if item["progress_pct"] is not None:
                details["progress_pct"] = int(item["progress_pct"])
            if item["completed_at"]:
                details["completed_at"] = _iso(item["completed_at"])
            if item["updated_at"]:
                details["source_updated_at"] = _iso(item["updated_at"])
            errs = validate_task_details(details)
            assert not errs, f"reconcile produced invalid details: {errs}"
            if not dry_run:
                cur.execute(
                    "UPDATE atlas.nodes SET status = %s, details = %s::jsonb,"
                    " updated_at = now() WHERE node_key = %s",
                    [details["status"], json.dumps(details),
                     item["node_key"]])
            closed += 1
        if dry_run:
            cur.execute("ROLLBACK")
        else:
            cur.execute("COMMIT")
    finally:
        conn.close()
    verb = "would sync" if dry_run else "synced"
    print(f"goals {verb}: {goals_done} "
          f"(dup slugs skipped: {cs['dup_skipped']}, "
          f"unslugged goals skipped: {cs['unslugged_goals']})")
    print(f"open task nodes {verb}: {tasks_done} "
          f"(contains edges: {edges_done})")
    print(f"task nodes reconciled to terminal status: {closed} "
          f"(orphans, source task gone: {len(orphans)})")
    print(f"open tasks under unslugged goals (unlinked): "
          f"{cs['unlinked_open_tasks']}")
    if dry_run:
        print("DRY RUN — nothing written")
    return 0


def status():
    goal_n, task_n, edge_n = sbos_common.pg_rows(
        "SELECT (SELECT count(*) FROM atlas.nodes "
        "WHERE node_type = 'goal'), "
        "(SELECT count(*) FROM atlas.nodes WHERE node_type = 'task' "
        "AND ref_kind = 'sbos_task'), "
        "(SELECT count(*) FROM atlas.edges WHERE edge_type = 'contains' "
        "AND from_node LIKE 'goal:%')")[0]
    unslugged, unlinked = sbos_common.pg_rows(
        "SELECT (SELECT count(*) FROM successbrian_os.sbos_goals "
        "WHERE goal_slug IS NULL OR goal_slug = ''), "
        "(SELECT count(*) FROM successbrian_os.tasks t WHERE t.status IN "
        "('pending', 'active', 'open', 'in_progress', 'blocked') "
        "AND (t.goal_id IS NULL OR t.goal_id NOT IN "
        "(SELECT id FROM successbrian_os.sbos_goals "
        "WHERE goal_slug IS NOT NULL AND goal_slug <> '')))")[0]
    print(f"goal nodes: {goal_n} | goal task nodes: {task_n} | "
          f"goal --contains--> task edges: {edge_n}")
    print(f"unslugged goals (no node): {unslugged} | "
          f"open tasks under unslugged goals (unlinked): {unlinked}")
    return 0


def selftest():
    steps = []

    def check(name, cond):
        steps.append((name, bool(cond)))
        assert cond, f"selftest step failed: {name}"

    good = {"task_id": 73207, "goal_slug": "dealsdesk",
            "priority": "high", "status": "active",
            "progress_pct": 40, "target_date": "2026-12-31",
            "assigned_to": "brian", "stale_flag": None,
            "source_updated_at": "2026-11-13T10:00:00+00:00"}
    check("valid details pass (python)", not validate_task_details(good))
    check("missing task_id fails",
          validate_task_details({k: v for k, v in good.items()
                                 if k != "task_id"}))
    check("task_id 0 fails",
          validate_task_details({**good, "task_id": 0}))
    check("task_id as text fails",
          validate_task_details({**good, "task_id": "73207"}))
    check("empty goal_slug fails",
          validate_task_details({**good, "goal_slug": ""}))
    check("priority as int fails",
          validate_task_details({**good, "priority": 75}))
    check("progress 101 fails",
          validate_task_details({**good, "progress_pct": 101}))
    check("unknown key fails",
          validate_task_details({**good, "surprise": 1}))
    check("2026-02-30 fails",
          validate_task_details({**good, "target_date": "2026-02-30"}))
    check("garbage timestamp fails",
          validate_task_details(
              {**good, "completed_at": "not-a-date"}))
    check("completed_at null ok",
          not validate_task_details({**good, "completed_at": None}))

    row = {"id": 73207, "goal_slug": "dealsdesk", "priority": "High",
           "status": "active", "progress_pct": 40,
           "target_date": date(2026, 12, 31), "assigned_to": "brian",
           "stale_flag": None, "completed_at": None,
           "updated_at": datetime(2026, 11, 13, 10, 0, 0)}
    built = details_for_task_row(row)
    check("builder output validates", not validate_task_details(built))
    check("builder keeps task_id int", built["task_id"] == 73207)
    check("builder lowercases priority", built["priority"] == "high")
    check("builder maps status active", built["status"] == "active")
    check("task key shape",
          node_key_for_task("dealsdesk", 73207)
          == "task:dealsdesk:73207")
    check("status blocked->blocked",
          task_status_for_row({"status": "blocked"}) == "blocked")
    check("status completed->done",
          task_status_for_row({"status": "completed"}) == "done")
    check("status unknown->planned",
          task_status_for_row({"status": "weird"}) == "planned")

    # Live side: SQL validator agrees with Python on both sides.
    check("live validator accepts good", sql_task_valid(good))
    check("live validator rejects bad task_id",
          not sql_task_valid({**good, "task_id": 0}))
    check("live validator rejects unknown key",
          not sql_task_valid({**good, "surprise": 1}))
    check("live validator rejects 2026-02-29",
          not sql_task_valid({**good, "target_date": "2026-02-29"}))
    check("live validator rejects NULL details",
          sbos_common.pg_one(
              "SELECT atlas.task_node_details_valid(NULL::jsonb)")
          is False)
    check("CHECK constraint present",
          sbos_common.pg_one(
              "SELECT count(*) FROM pg_constraint "
              "WHERE conname = 'nodes_task_details_ck' "
              "AND conrelid = 'atlas.nodes'::regclass") == 1)
    check("goal_tasks view present",
          sbos_common.pg_one(
              "SELECT count(*) FROM information_schema.views "
              "WHERE table_schema = 'atlas' "
              "AND table_name = 'goal_tasks'") == 1)

    # Transactional round-trip: goal node + task node + contains edge,
    # then roll everything back — no residue (successbrian has no
    # DELETE on atlas.nodes/edges, so the probe must never commit).
    probe_goal = "goal:__selftest__b11__"
    probe_task = "task:__selftest__b11__:1"
    probe_details = {"task_id": 1, "goal_slug": "__selftest__b11__",
                     "priority": "high", "status": "active"}
    bad_details = {"task_id": 0, "goal_slug": "__selftest__b11__",
                   "priority": "high", "status": "active"}
    legacy_details = {"purpose": "hand-made pre-contract node"}
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(UPSERT_NODE_SQL,
                    [probe_goal, "goal", "SELFTEST disposable", "planned",
                     json.dumps({"goal_slug": "__selftest__b11__",
                                 "priority": 50,
                                 "coverage_window_days": 4}),
                     "sbos_goal", "0"])
        cur.execute(UPSERT_NODE_SQL,
                    [probe_task, "task", "SELFTEST disposable task",
                     "active", json.dumps(probe_details),
                     "sbos_task", "1"])
        cur.execute(UPSERT_EDGE_SQL, [probe_goal, probe_task])
        cur.execute("SELECT goal_slug, task_id FROM atlas.goal_tasks "
                    "WHERE node_key = %s", [probe_task])
        vrow = cur.fetchone()
        check("view exposes probe task",
              vrow is not None and vrow[0] == "__selftest__b11__"
              and vrow[1] == 1)
        cur.execute("SELECT count(*) FROM atlas.edges WHERE from_node = %s "
                    "AND to_node = %s AND edge_type = 'contains'",
                    [probe_goal, probe_task])
        check("contains edge exists", cur.fetchone()[0] == 1)
        # Idempotency: the same upserts twice leave exactly one node
        # and one edge.
        cur.execute(UPSERT_NODE_SQL,
                    [probe_task, "task", "SELFTEST disposable task",
                     "active", json.dumps(probe_details),
                     "sbos_task", "1"])
        cur.execute(UPSERT_EDGE_SQL, [probe_goal, probe_task])
        cur.execute("SELECT count(*) FROM atlas.nodes WHERE node_key = %s",
                    [probe_task])
        check("re-upsert leaves one task node", cur.fetchone()[0] == 1)
        cur.execute("SELECT count(*) FROM atlas.edges WHERE from_node = %s "
                    "AND to_node = %s AND edge_type = 'contains'",
                    [probe_goal, probe_task])
        check("re-insert leaves one edge", cur.fetchone()[0] == 1)
        # CHECK bites on a bad sync row but not on a legacy-shaped row.
        cur.execute("SAVEPOINT sp_bad")
        rejected = False
        try:
            cur.execute(
                "INSERT INTO atlas.nodes "
                "(node_key, node_type, name, status, details, ref_kind, "
                "ref_id) VALUES (%s, 'task', 'SELFTEST bad', 'active', "
                "%s::jsonb, 'sbos_task', '0')",
                ["task:__selftest__b11__:bad__", json.dumps(bad_details)])
        except Exception:
            rejected = True
            cur.execute("ROLLBACK TO SAVEPOINT sp_bad")
        check("CHECK rejects invalid sbos_task details", rejected)
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details) "
            "VALUES (%s, 'task', 'SELFTEST legacy-shaped', 'active', "
            "%s::jsonb)",
            ["task:__selftest__b11__:legacy__", json.dumps(legacy_details)])
        check("CHECK allows legacy-shaped task row (ref_kind NULL)", True)
        cur.execute("ROLLBACK")
        check("probe rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM atlas.nodes WHERE node_key = %s",
                  [probe_task]) == 0)
        check("probe goal rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM atlas.nodes WHERE node_key = %s",
                  [probe_goal]) == 0)
    finally:
        conn.close()

    print(f"GOAL_TASK_SYNC_OK ({len(steps)} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.sync:
        return sync(dry_run=False)
    if a.dry_run:
        return sync(dry_run=True)
    if a.status:
        return status()
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
