#!/usr/bin/env python3
"""Queue Watch — the board's convergence instrument (R34).

Brian (2026-10-23): "the board can look at the top a
little, look at the bottom a little (the oldest tasks
that aren't completed)... basically looking at all sides
of the process and keep pushing everything to the
middle."

The board's queue is Atlas: pending gates + open/queued
tasks. A queue ground from one end starves the other —
grind oldest-first and new arrivals wait unseen; chase
the newest and the old ones rot. R34 stratifies the
board's attention:

  TOP    — pending gates + the newest open tasks
  BOTTOM — the oldest uncompleted tasks (with ages)
  MIDDLE — everything between (count, median age)

and suggests the session's pull order: gates first,
then bottom and top interleaved, then the middle in age
order — every session touches all sides, and everything
moves toward the middle: ruled, resolved, done.

Read-only. It reports and flags; it routes nothing and
rules nothing. Starvation lines live in code
(STARVATION_DAYS, QUEUE_CAP) where the board can see
and tighten them.
"""

import datetime as dt
import os
import sys

import psycopg2

DBNAME = "ecosystem_central"
STARVATION_DAYS = 14   # oldest open item older than
                       # this is starving
QUEUE_CAP = 200        # open queue beyond this is
                       # outpacing the board
EDGE = 8               # strata shown per side


def pg():
    return psycopg2.connect(dbname=DBNAME, host="localhost",
                            user="postgres")


def fetch_queue(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT node_key, name, created_at::date FROM "
            "atlas.nodes WHERE node_key LIKE 'gate:%' AND "
            "status = 'pending' ORDER BY created_at")
        gates = [{"key": r[0], "name": r[1], "created": r[2],
                  "kind": "gate"} for r in cur.fetchall()]
        cur.execute(
            "SELECT node_key, name, created_at::date FROM "
            "atlas.nodes WHERE node_type = 'atlas_task' "
            "AND status IN ('open', 'queued') ORDER BY "
            "created_at, node_key")
        tasks = [{"key": r[0], "name": r[1], "created": r[2],
                  "kind": "task"} for r in cur.fetchall()]
    # Workload-gate visibility (workload_gates.py's read model):
    # which workloads each open gate is holding. A missing view must
    # never kill the queue watch — it just reports gates plainly.
    holds = {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gate_key, workload_name FROM "
                "atlas.workload_gates_v WHERE gate_state = 'open' "
                "ORDER BY workload_name")
            for gk, wn in cur.fetchall():
                holds.setdefault(gk, []).append(wn)
    except Exception:
        conn.rollback()
        holds = {}
    return gates, tasks, holds


def stratify(tasks, today):
    """tasks sorted oldest-first. Returns the strata."""
    aged = [dict(t, age=(today - t["created"]).days)
            for t in tasks]
    bottom = aged[:EDGE]
    top = list(reversed(aged))[:EDGE]
    seen = {t["key"] for t in bottom} | {t["key"] for t in top}
    middle = [t for t in aged if t["key"] not in seen]
    ages = sorted(t["age"] for t in aged)
    median = ages[len(ages) // 2] if ages else 0
    return {"bottom": bottom, "top": top, "middle": middle,
            "median_age": median,
            "oldest_age": ages[-1] if ages else 0,
            "total": len(aged)}


def pull_order(gates, tasks):
    """R34 pull: gates, then bottom/top interleaved,
    then the middle oldest-first. tasks oldest-first."""
    order = list(gates)
    bottom = list(tasks)
    top = list(reversed(tasks))
    used = set()
    while bottom or top:
        if bottom:
            t = bottom.pop(0)
            if t["key"] not in used:
                order.append(t)
                used.add(t["key"])
        if top:
            t = top.pop(0)
            if t["key"] not in used:
                order.append(t)
                used.add(t["key"])
    return order


def flags(strata):
    out = []
    if strata["oldest_age"] > STARVATION_DAYS:
        out.append(
            "STARVATION: oldest open task is %d days old "
            "(line: %d) — the bottom is rotting"
            % (strata["oldest_age"], STARVATION_DAYS))
    if strata["total"] > QUEUE_CAP:
        out.append(
            "QUEUE OUTPACING THE BOARD: %d open (cap %d)"
            % (strata["total"], QUEUE_CAP))
    return out


def report(conn, today=None):
    today = today or dt.date.today()
    gates, tasks, holds = fetch_queue(conn)
    s = stratify(tasks, today)
    lines = ["# Queue Watch — pushing to the middle (R34)",
             "",
             "Open: %d tasks + %d pending gates. Median "
             "open-task age: %d days."
             % (s["total"], len(gates), s["median_age"])]
    fl = flags(s)
    if fl:
        lines.append("")
        for f in fl:
            lines.append("!! " + f)
    lines.append("")
    lines.append("## TOP — pending gates")
    for g in gates:
        held = holds.get(g["key"], [])
        suffix = ""
        if held:
            shown = ", ".join(held[:3])
            if len(held) > 3:
                shown += " +%d more" % (len(held) - 3)
            suffix = " — holds: " + shown
        lines.append("- %s — %s%s" % (g["key"], g["name"], suffix))
    lines.append("")
    lines.append("## TOP — newest open tasks")
    for t in s["top"]:
        lines.append("- %s (%d d) — %s"
                     % (t["key"], t["age"], t["name"][:70]))
    lines.append("")
    lines.append("## BOTTOM — oldest uncompleted")
    for t in s["bottom"]:
        lines.append("- %s (%d d) — %s"
                     % (t["key"], t["age"], t["name"][:70]))
    lines.append("")
    lines.append("## MIDDLE — %d items between the edges"
                 % len(s["middle"]))
    lines.append("")
    lines.append("## Suggested pull (gates, then bottom/"
                 "top interleaved)")
    for i, t in enumerate(pull_order(gates, tasks)[:12]):
        lines.append("%2d. [%s] %s"
                     % (i + 1, t["kind"], t["key"]))
    lines.append("")
    return "\n".join(lines)


def selftest():
    failures = []

    def check(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    today = dt.date(2026, 10, 23)
    tasks = [{"key": "task:%02d" % i, "name": "t%d" % i,
              "created": dt.date(2026, 10, 1) + dt.timedelta(
                  days=i), "kind": "task"}
             for i in range(20)]
    s = stratify(tasks, today)
    check(s["total"] == 20 and s["oldest_age"] == 22,
          "strata: totals and ages compute")
    check(s["bottom"][0]["key"] == "task:00"
          and s["top"][0]["key"] == "task:19",
          "strata: bottom is oldest, top is newest")
    check(len(s["middle"]) == 20 - 2 * EDGE,
          "strata: the middle is what the edges leave")
    gates = [{"key": "gate:x", "name": "g",
              "created": dt.date(2026, 10, 20),
              "kind": "gate"}]
    order = pull_order(gates, tasks)
    keys = [t["key"] for t in order]
    check(keys[0] == "gate:x" and keys[1] == "task:00"
          and keys[2] == "task:19" and keys[3] == "task:01",
          "pull: gates first, then bottom/top interleaved")
    check(len(keys) == len(set(keys)) == 21,
          "pull: every item exactly once")
    starving = stratify(
        [{"key": "task:old", "name": "x",
          "created": dt.date(2026, 9, 1), "kind": "task"}],
        today)
    check(any("STARVATION" in f for f in flags(starving)),
          "flags: a 52-day-old task starves loudly")
    young = stratify(
        [{"key": "task:y%d" % i, "name": "y",
          "created": dt.date(2026, 10, 20) + dt.timedelta(
              days=i), "kind": "task"} for i in range(3)],
        today)
    check(flags(young) == [],
          "flags: a young queue under the cap stays calm")
    if failures:
        print("SELFTEST FAILED: %d" % len(failures))
        return 1
    print("SELFTEST OK")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd == "selftest":
        return selftest()
    if cmd == "run":
        conn = pg()
        try:
            print(report(conn))
        finally:
            conn.close()
        return 0
    print("usage: queue_watch.py [run|selftest]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
