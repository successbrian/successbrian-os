#!/usr/bin/env python3
"""goal_nodes.py - Goal-node schema for atlas.nodes (BUILD_QUEUE B10).

Phase 3 (Atlas goal machinery) starts here: the schema half of closing
the confirmed gap that atlas.nodes holds no goal-type nodes. The
migration tools/atlas/2026-11-13_goal_nodes.sql enforces the contract
in the database (CHECK + validator function + atlas.goal_nodes view);
this module is the Python mirror: the same contract, the builder that
turns a successbrian_os.sbos_goals row into a goal node, and the
selftest that proves the two sides agree.

Contract (see the migration file for the authoritative SQL wording):
  node_key  'goal:<goal_slug>'
  node_type 'goal'
  name      sbos_goals.goal_name
  status    sbos_goals.status mapped (STATUS_MAP below)
  ref_kind  'sbos_goal', ref_id = sbos_goals.id as text
  details   required: goal_slug, priority 0-100,
                      coverage_window_days 1-30 (default 4: the design's
                      3-5 day working assumption for full coverage)
            optional: category, target_date, last_looked_at, look_count,
                      planner_seat, blocker, parent_goal_slug
            no other keys.

Mappings are B10 defaults, Brian-correctable: PRIORITY_MAP turns the
Goals tab's text priority into the 0-100 int the rotation orders on
(critical 90, high 75, medium 50, low 25, anything else 50 — the same
50 the candidate engine uses as its default priority).

The sync itself is B11; this file builds and validates, it does not
sync. Nothing here sends, buys, publishes, or contacts anyone.

Usage:
  goal_nodes.py --selftest   contract checks + live validator/CHECK/view
                             probes + a transactional round-trip (rolled
                             back: successbrian has no DELETE on
                             atlas.nodes, so the probe never commits)
  goal_nodes.py --list       goal nodes via atlas.goal_nodes, with the
                             coverage line (looked / total, oldest
                             un-looked) the rotation reports by
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402

REQUIRED_KEYS = ("goal_slug", "priority", "coverage_window_days")
OPTIONAL_KEYS = ("category", "target_date", "last_looked_at", "look_count",
                 "planner_seat", "blocker", "parent_goal_slug")
ALLOWED_KEYS = set(REQUIRED_KEYS) | set(OPTIONAL_KEYS)

DEFAULT_COVERAGE_WINDOW_DAYS = 4
DEFAULT_PRIORITY = 50

# B10 defaults, Brian-correctable (see module docstring).
PRIORITY_MAP = {"critical": 90, "high": 75, "medium": 50, "low": 25}
STATUS_MAP = {"active": "active", "in_progress": "active",
              "planning": "planned", "blocked": "blocked",
              "cancelled": "cancelled", "completed": "done"}

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


def validate_details(d):
    """Python mirror of atlas.goal_node_details_valid. Returns [errors]."""
    errs = []
    if not isinstance(d, dict):
        return ["details is not an object"]
    for k in REQUIRED_KEYS:
        if k not in d:
            errs.append(f"missing required key: {k}")
    for k in d:
        if k not in ALLOWED_KEYS:
            errs.append(f"unknown key: {k}")
    if "goal_slug" in d and (not isinstance(d["goal_slug"], str)
                             or not d["goal_slug"]):
        errs.append("goal_slug must be a non-empty string")
    if "priority" in d and (not _is_int(d["priority"])
                            or not 0 <= d["priority"] <= 100):
        errs.append("priority must be an int 0-100")
    if "coverage_window_days" in d and (
            not _is_int(d["coverage_window_days"])
            or not 1 <= d["coverage_window_days"] <= 30):
        errs.append("coverage_window_days must be an int 1-30")
    if "category" in d and not isinstance(d["category"], str):
        errs.append("category must be a string")
    if "target_date" in d and not _valid_date(d["target_date"]):
        errs.append("target_date must be a real YYYY-MM-DD date")
    if "last_looked_at" in d and not _valid_ts(d["last_looked_at"]):
        errs.append("last_looked_at must be an ISO timestamp")
    if "look_count" in d and (not _is_int(d["look_count"])
                              or d["look_count"] < 0):
        errs.append("look_count must be an int >= 0")
    if "planner_seat" in d and not isinstance(d["planner_seat"], str):
        errs.append("planner_seat must be a string")
    if "blocker" in d and d["blocker"] is not None \
            and not isinstance(d["blocker"], str):
        errs.append("blocker must be a string or null")
    if "parent_goal_slug" in d and d["parent_goal_slug"] is not None \
            and not isinstance(d["parent_goal_slug"], str):
        errs.append("parent_goal_slug must be a string or null")
    return errs


def node_key_for_slug(slug):
    return f"goal:{slug}"


def details_for_goal_row(row):
    """Build contract-valid details from a successbrian_os.sbos_goals
    row (dict with goal_slug, priority, category, target_date,
    parent_goal_id, parent_goal_slug). Pure: no DB access."""
    slug = row["goal_slug"]
    details = {
        "goal_slug": slug,
        "priority": PRIORITY_MAP.get((row.get("priority") or "").lower(),
                                     DEFAULT_PRIORITY),
        "coverage_window_days": DEFAULT_COVERAGE_WINDOW_DAYS,
    }
    if row.get("category"):
        details["category"] = row["category"]
    if row.get("target_date"):
        td = row["target_date"]
        details["target_date"] = td.isoformat() if hasattr(td, "isoformat") \
            else str(td)
    if row.get("parent_goal_slug"):
        details["parent_goal_slug"] = row["parent_goal_slug"]
    errs = validate_details(details)
    assert not errs, f"builder produced invalid details: {errs}"
    return details


def node_status_for_goal_row(row):
    return STATUS_MAP.get((row.get("status") or "").lower(), "planned")


def sql_valid(details):
    """Ask the live SQL validator. Returns bool."""
    return bool(sbos_common.pg_one(
        "SELECT atlas.goal_node_details_valid(%s::jsonb)",
        [json.dumps(details)]))


def selftest():
    steps = []

    def check(name, cond):
        steps.append((name, bool(cond)))
        assert cond, f"selftest step failed: {name}"

    good = {"goal_slug": "gotbackup-40-mo", "priority": 75,
            "coverage_window_days": 4, "category": "revenue",
            "target_date": "2026-12-31", "look_count": 0,
            "planner_seat": "planner", "blocker": None}
    check("valid details pass (python)", not validate_details(good))
    check("missing goal_slug fails",
          validate_details({k: v for k, v in good.items()
                            if k != "goal_slug"}))
    check("priority 101 fails",
          validate_details({**good, "priority": 101}))
    check("priority as text fails",
          validate_details({**good, "priority": "high"}))
    check("window 0 fails",
          validate_details({**good, "coverage_window_days": 0}))
    check("window 31 fails",
          validate_details({**good, "coverage_window_days": 31}))
    check("unknown key fails",
          validate_details({**good, "surprise": 1}))
    check("2026-02-30 fails",
          validate_details({**good, "target_date": "2026-02-30"}))
    check("2026-02-29 non-leap fails",
          validate_details({**good, "target_date": "2026-02-29"}))
    check("2024-02-29 leap passes",
          not validate_details({**good, "target_date": "2024-02-29"}))
    check("garbage timestamp fails",
          validate_details({**good, "last_looked_at": "not-a-date"}))
    check("negative look_count fails",
          validate_details({**good, "look_count": -1}))
    check("blocker null ok",
          not validate_details({**good, "blocker": None}))

    row = {"goal_slug": "trafficstreemz-30", "priority": "high",
           "category": "revenue", "target_date": date(2026, 12, 31),
           "status": "active", "parent_goal_slug": None}
    built = details_for_goal_row(row)
    check("builder output validates", not validate_details(built))
    check("builder maps high->75", built["priority"] == 75)
    check("builder default window 4",
          built["coverage_window_days"] == 4)
    check("node key shape",
          node_key_for_slug("trafficstreemz-30") == "goal:trafficstreemz-30")
    check("status active->active",
          node_status_for_goal_row(row) == "active")
    check("status unknown->planned",
          node_status_for_goal_row({"status": "weird"}) == "planned")

    # Live side: SQL validator agrees with Python on both sides.
    check("live validator accepts good", sql_valid(good))
    check("live validator rejects bad priority",
          not sql_valid({**good, "priority": 101}))
    check("live validator rejects unknown key",
          not sql_valid({**good, "surprise": 1}))
    check("live validator rejects 2026-02-29",
          not sql_valid({**good, "target_date": "2026-02-29"}))
    check("CHECK constraint present",
          sbos_common.pg_one(
              "SELECT count(*) FROM pg_constraint "
              "WHERE conname = 'nodes_goal_details_ck' "
              "AND conrelid = 'atlas.nodes'::regclass") == 1)
    check("goal_nodes view present",
          sbos_common.pg_one(
              "SELECT count(*) FROM information_schema.views "
              "WHERE table_schema = 'atlas' "
              "AND table_name = 'goal_nodes'") == 1)

    # Transactional round-trip: proves the CHECK bites and the view
    # exposes a valid goal node, then rolls everything back — no residue
    # (successbrian has no DELETE on atlas.nodes, so the probe must
    # never commit).
    probe_key = "goal:__selftest__b10__"
    probe = {"goal_slug": "__selftest__b10__", "priority": 50,
             "coverage_window_days": 4}
    bad_probe = {"goal_slug": "__selftest__b10__bad__", "priority": 101,
                 "coverage_window_days": 4}
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details, ref_kind, ref_id) "
            "VALUES (%s, 'goal', 'SELFTEST disposable', 'planned', "
            "%s::jsonb, 'sbos_goal', '0')",
            [probe_key, json.dumps(probe)])
        cur.execute("SELECT goal_slug, look_overdue FROM atlas.goal_nodes "
                    "WHERE node_key = %s", [probe_key])
        vrow = cur.fetchone()
        check("view exposes probe, never looked => overdue",
              vrow is not None and vrow[0] == "__selftest__b10__"
              and vrow[1] is True)
        cur.execute("SAVEPOINT sp_bad")
        rejected = False
        try:
            cur.execute(
                "INSERT INTO atlas.nodes "
                "(node_key, node_type, name, status, details) "
                "VALUES (%s, 'goal', 'SELFTEST bad', 'planned', %s::jsonb)",
                ["goal:__selftest__b10__bad__", json.dumps(bad_probe)])
        except Exception:
            rejected = True
            cur.execute("ROLLBACK TO SAVEPOINT sp_bad")
        check("CHECK rejects invalid goal details", rejected)
        cur.execute("ROLLBACK")
        check("probe rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM atlas.nodes WHERE node_key = %s",
                  [probe_key]) == 0)
    finally:
        conn.close()

    print(f"GOAL_NODES_OK ({len(steps)} checks)")
    return 0


def list_goals():
    rows = sbos_common.pg_rows(
        "SELECT goal_slug, priority, status, days_since_look, "
        "look_overdue, blocker FROM atlas.goal_nodes "
        "ORDER BY priority DESC, goal_slug")
    total = len(rows)
    looked = sum(1 for r in rows if r[3] is not None)
    print(f"goal nodes: {total} (looked {looked}, never looked "
          f"{total - looked})")
    for slug, prio, status, days, overdue, blocker in rows:
        age = "never" if days is None else f"{days:.1f}d ago"
        flag = "OVERDUE" if overdue else "ok"
        extra = f" blocker: {blocker}" if blocker else ""
        print(f"  {slug} prio={prio} {status} last look {age} "
              f"[{flag}]{extra}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.list:
        return list_goals()
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
