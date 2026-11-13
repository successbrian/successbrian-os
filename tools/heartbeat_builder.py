#!/usr/bin/env python3
"""heartbeat_builder.py - the Heartbeat Builder's own tool.

Brian's directive 2026-11-13 06:57 CST: "build Success Brian OS,
build the actual code so that it helps you do this and helps you
do it right." The 20-minute cycle (spencer-20min-cycle) senses,
repairs, builds, and verifies improvements. This tool is how it
does the record-keeping RIGHT, in code instead of prose:

  log       write one improvement_log row (intent + check date
            are mandatory - an improvement without them is not
            logged, by design)
  due       list improvement checks whose date has arrived
  check     write back a verification verdict against intent
  depths    show the Atlas intel-depth registry
  classify  stamp a depth on an Intel Bridge capture
  status    one-screen state of the improvement system
  selftest  read-only invariants + a rolled-back write test

Brian's rules encoded here (2026-11-13): improvements live in
successbrian_os.improvement_log on alpha, never in chat; every
improvement carries its original intent and a future check date;
at the date, the intent is tested and the verdict written back;
intel has depths (successbrian_os.intel_depth_levels) and only
brian_decision depth may reach Brian or his calendar.
"""
import argparse, subprocess, sys

DB = ["psql", "-d", "ecosystem_central", "-At"]
OUTCOMES = ("verified", "failed", "rolled_back", "partial")
VERDICTS = ("worked", "partial", "did_not_work", "too_early")


def run(sql):
    out = subprocess.run(DB + ["-c", sql], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return [l for l in out.stdout.splitlines() if l.strip()]


def q(text):
    """Quote a SQL string literal."""
    if text is None:
        return "NULL"
    return "'" + str(text).replace("'", "''") + "'"


def cmd_log(a):
    if not a.intent or not a.intent.strip():
        print("REFUSED: --intent is required. An improvement without "
              "its original intent cannot be checked later, so it "
              "is not logged at all. State what should be different "
              "in the world when this works.", file=sys.stderr)
        return 2
    days = int(a.check_days)
    sql = (
        "insert into successbrian_os.improvement_log "
        "(agent, kind, queue_ref, project_ref, goal_ref, title, "
        "what_changed, why, intent, expected_effect, evidence, "
        "outcome, files_touched, depth, check_due_at) values ("
        f"{q(a.agent)}, {q(a.kind)}, {q(a.queue_ref)}, "
        f"{q(a.project_ref)}, {q(a.goal_ref)}, {q(a.title)}, "
        f"{q(a.what)}, {q(a.why)}, {q(a.intent)}, "
        f"{q(a.expected)}, {q(a.evidence)}, {q(a.outcome)}, "
        f"{q(a.files)}, {q(a.depth)}, now() + interval '{days} days') "
        "returning id::text"
    )
    rows = run(sql)
    print(f"improvement_log id={rows[0]} check_due=+{days}d")
    return 0


def cmd_due(a):
    rows = run(
        "select id||' | '||kind||' | '||title||' | due '||"
        "check_due_at::date||' | intent: '||coalesce(intent,'') "
        "from successbrian_os.improvement_log "
        "where check_due_at <= now() and checked_at is null "
        f"order by check_due_at limit {int(a.limit)}")
    if not rows:
        print("no verification checks due")
    for r in rows:
        print(r)
    return 0


def cmd_check(a):
    if a.verdict not in VERDICTS:
        print(f"REFUSED: verdict must be one of {VERDICTS}", file=sys.stderr)
        return 2
    if a.verdict == "too_early":
        days = int(a.reschedule_days)
        sql = (
            "update successbrian_os.improvement_log set "
            "verification_outcome='too_early', "
            f"check_result={q(a.result)}, "
            f"check_due_at=now() + interval '{days} days' "
            f"where id={int(a.id)} and checked_at is null "
            "returning id::text")
    else:
        sql = (
            "update successbrian_os.improvement_log set "
            "checked_at=now(), "
            f"verification_outcome={q(a.verdict)}, "
            f"check_result={q(a.result)} "
            f"where id={int(a.id)} and checked_at is null "
            "returning id::text")
    rows = run(sql)
    if not rows:
        print(f"no unchecked improvement with id={a.id}", file=sys.stderr)
        return 1
    print(f"improvement {a.id} verdict={a.verdict}")
    return 0


def cmd_depths(a):
    for r in run("select depth||' | calendar='||surfaces_on_calendar"
                 "||' | pushed='||pushed_to_brian||' | '||name "
                 "from successbrian_os.intel_depth_levels "
                 "order by depth"):
        print(r)
    return 0


def cmd_classify(a):
    levels = [r.split(" |")[0] for r in run(
        "select depth from successbrian_os.intel_depth_levels")]
    if a.depth not in levels:
        print(f"REFUSED: unknown depth {a.depth}; registry: {levels}",
              file=sys.stderr)
        return 2
    rows = run(
        "update atlas.scattered_captures "
        f"set depth={q(a.depth)} where id={int(a.capture_id)} "
        "returning id::text")
    if not rows:
        print(f"capture {a.capture_id} not found", file=sys.stderr)
        return 1
    print(f"capture {a.capture_id} depth={a.depth}")
    return 0


def cmd_status(a):
    lines = ["HEARTBEAT BUILDER STATUS"]
    lines.append("improvements by outcome: " + ", ".join(run(
        "select outcome||'='||count(*) from "
        "successbrian_os.improvement_log group by outcome "
        "order by outcome") or ["none"]))
    lines.append("verification verdicts: " + ", ".join(run(
        "select verification_outcome||'='||count(*) from "
        "successbrian_os.improvement_log where "
        "verification_outcome is not null group by "
        "verification_outcome order by verification_outcome")
        or ["none yet"]))
    lines.append("checks due now: " + run(
        "select count(*)::text from successbrian_os.improvement_log "
        "where check_due_at <= now() and checked_at is null")[0])
    lines.append("next check due: " + (run(
        "select min(check_due_at)::date::text from "
        "successbrian_os.improvement_log where checked_at is null "
        "and check_due_at is not null") or ["none"])[0])
    lines.append("captures by depth: " + ", ".join(run(
        "select depth||'='||count(*) from atlas.scattered_captures "
        "group by depth order by depth") or ["none"]))
    print("\n".join(lines))
    return 0


def cmd_selftest(a):
    # invariants, read-only except one rolled-back test insert
    levels = int(run("select count(*)::text from "
                     "successbrian_os.intel_depth_levels")[0])
    assert levels == 6, f"expected 6 depth levels, got {levels}"
    run("begin; insert into successbrian_os.improvement_log "
        "(kind, title, what_changed, intent, check_due_at) values "
        "('build','SELFTEST ROW - rolled back','write-path test',"
        "'selftest intent', now()); rollback;")
    due = run("select count(*)::text from "
              "successbrian_os.improvement_log where "
              "check_due_at <= now() and checked_at is null")
    assert due, "due-check query failed"
    bad = run("select count(*)::text from "
              "successbrian_os.improvement_log where "
              "check_due_at is not null and intent is null")
    assert bad[0] == "0", "improvements with a check date but no intent"
    print("HEARTBEAT_BUILDER_OK")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("log")
    s.add_argument("--kind", required=True,
                   choices=("fix", "build", "instrument", "repair", "design"))
    s.add_argument("--title", required=True)
    s.add_argument("--what", required=True)
    s.add_argument("--intent", required=True)
    s.add_argument("--why"); s.add_argument("--expected")
    s.add_argument("--evidence"); s.add_argument("--files")
    s.add_argument("--queue-ref"); s.add_argument("--project-ref")
    s.add_argument("--goal-ref")
    s.add_argument("--agent", default="spencer")
    s.add_argument("--outcome", default="verified", choices=OUTCOMES)
    s.add_argument("--depth", default="system_self")
    s.add_argument("--check-days", type=int, default=7)
    s.set_defaults(fn=cmd_log)

    s = sub.add_parser("due"); s.add_argument("--limit", type=int, default=10)
    s.set_defaults(fn=cmd_due)

    s = sub.add_parser("check")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--verdict", required=True, choices=VERDICTS)
    s.add_argument("--result", required=True)
    s.add_argument("--reschedule-days", type=int, default=14)
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("depths"); s.set_defaults(fn=cmd_depths)
    s = sub.add_parser("classify")
    s.add_argument("--capture-id", type=int, required=True)
    s.add_argument("--depth", required=True)
    s.set_defaults(fn=cmd_classify)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("selftest"); s.set_defaults(fn=cmd_selftest)

    a = p.parse_args()
    try:
        return a.fn(a)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
