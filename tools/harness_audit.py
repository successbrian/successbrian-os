#!/usr/bin/env python3
"""harness_audit.py — the "hire workflows, not agents" audit, as a workflow.

Brian's thesis (2026-11-12): SBOS should be harnesses all the way down —
work addressed to roles/job classes/queues, state in PostgreSQL, procedure
in code, no capability that silently stops when one agent/model/machine is
absent, and no model location baked into an address.

This tool turns the 2026-11-12 factoring audit (docs/
hire-workflows-factoring-spec-2026-11-12.md, PM project sbos-hire-workflows)
from a one-off agent pass into a repeatable, read-only check: it re-measures
the live counts behind the spec's findings so progress on each finding is a
number, not a memory.

Verbs:
  report    print the current counts behind the findings
  selftest  prove the audit queries run and the spec is present in the
            repo docs; prints HARNESS_AUDIT_OK (QA check contract)

Read-only: SELECTs and file scans only. Never writes.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
SPEC = os.path.join(REPO, "docs", "hire-workflows-factoring-spec-2026-11-12.md")
sys.path.insert(0, TOOLS)
from sbos_common import pg_rows, pg_one  # noqa: E402

ENDPOINT_LITERAL = re.compile(r"(127\.0\.0\.1|localhost):1143[789]")
TAILNET_LITERAL = re.compile(r"100\.(118\.196\.66|97\.109\.65)")
# Files allowed to hold these literals: the shared config (the values'
# sanctioned home), the fleet registry (the hosts' sanctioned home), the
# repair ladder (it legitimately starts servers by port), and this audit.
EXEMPT = {"sbos_common.py", "repair_ladder.py", "fleet_registry.json",
          "harness_audit.py"}


def _py_files():
    for root, dirs, files in os.walk(TOOLS):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py") and not f.endswith((".bak", ".pyc")) \
                    and f not in EXEMPT:
                yield os.path.join(root, f)


def literal_files(pattern):
    hits = []
    for path in _py_files():
        try:
            with open(path, errors="ignore") as fh:
                if pattern.search(fh.read()):
                    hits.append(os.path.relpath(path, REPO))
        except OSError:
            pass
    return sorted(hits)


def counts():
    goal_nodes = pg_one(
        "SELECT count(*) FROM atlas.nodes WHERE node_type='goal'")
    tasks_total = pg_one(
        "SELECT count(*) FROM atlas.nodes WHERE node_type='atlas_task'")
    tasks_model_addressed = pg_one(
        "SELECT count(*) FROM atlas.nodes WHERE node_type='atlas_task' "
        "AND status IN ('queued','open','assigned') "
        "AND details->>'model' IN ('sonic','v4pro')")
    pending_by_assignee = pg_rows(
        "SELECT assigned_to, count(*) FROM successbrian_os.tasks "
        "WHERE status='pending' GROUP BY 1 ORDER BY 2 DESC LIMIT 8")
    return {
        "goal_nodes": goal_nodes,
        "atlas_tasks_total": tasks_total,
        "atlas_tasks_model_addressed_open": tasks_model_addressed,
        "pending_by_assignee": pending_by_assignee,
        "endpoint_literal_files": literal_files(ENDPOINT_LITERAL),
        "tailnet_literal_files": literal_files(TAILNET_LITERAL),
    }


def report():
    c = counts()
    print("HARNESS AUDIT — live counts behind the factoring spec findings")
    print(f"  F1 atlas goal-type nodes: {c['goal_nodes']} "
          f"(planner-rotation design exists; machinery not built)")
    print(f"  F2 atlas tasks: {c['atlas_tasks_total']} total, "
          f"{c['atlas_tasks_model_addressed_open']} open ones addressed to "
          f"a named model (sonic/v4pro) instead of a job class")
    print("  F5 successbrian_os.tasks pending, by assignee name:")
    for name, n in c["pending_by_assignee"]:
        print(f"       {name}: {n}")
    print(f"  F4 files with hardcoded model-endpoint literals "
          f"(outside sbos_common): {len(c['endpoint_literal_files'])}")
    for f in c["endpoint_literal_files"]:
        print(f"       {f}")
    print(f"  F6 files with raw tailnet-IP host literals "
          f"(outside the fleet registry): {len(c['tailnet_literal_files'])}")
    for f in c["tailnet_literal_files"]:
        print(f"       {f}")


def selftest():
    problems = []
    if not os.path.isfile(SPEC):
        problems.append(f"spec missing: {SPEC}")
    try:
        c = counts()
        # Queries must return sane shapes; values themselves are findings,
        # not failures (goal_nodes == 0 is today's honest state).
        assert isinstance(c["goal_nodes"], int)
        assert isinstance(c["atlas_tasks_total"], int)
        assert isinstance(c["endpoint_literal_files"], list)
    except Exception as e:  # noqa: BLE001 — a failed query IS the failure
        problems.append(f"audit query failed: {e}")
    if problems:
        for p in problems:
            print(f"HARNESS_AUDIT_FAIL: {p}")
        return 1
    print("HARNESS_AUDIT_OK")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "report":
        report()
    elif cmd == "selftest":
        sys.exit(selftest())
    else:
        print(__doc__)
        sys.exit(2)
