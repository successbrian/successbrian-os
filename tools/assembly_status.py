#!/usr/bin/env python3
"""assembly_status.py - READ-ONLY status for the assembled SBOS.

Brian directive 2026-11-13: assemble the whole system (digest ->
think/sort -> decisions for Brian). This tool only MEASURES the
assembly: is gamma's heartbeat fresh, are the team queues moving,
how much is waiting on Brian, is the Atlas goal gap still open,
how full is alpha's disk, how big is the second brain. It writes
nothing. Plan: builds/sbos-assembly/PLAN.md.

B6 adds the residue inventory (residue_inventory.py): the count of
everything waiting on Brian plus the oldest item, shown at the end.

Usage: assembly_status.py [--selftest]
"""
import os, shutil, subprocess, sys

DB = ["psql", "-d", "ecosystem_central", "-At"]

QUERIES = [
    ("gamma heartbeat (latest log row)",
     "select coalesce(max(created_at)::text,'none') "
     "from successbrian_os.logs where source_agent='gamma'"),
    ("bus reap_infer totals",
     "select status||'='||count(*) from bus.events "
     "where event_type='reap_infer' group by status order by status"),
    ("reap_queue stalled side path (queued)",
     "select count(*)::text from successbrian_os.reap_queue "
     "where status='queued'"),
    ("pm_steps (team queue) totals",
     "select status||'='||count(*) from successbrian_os.pm_steps "
     "group by status order by status"),
    ("waiting on Brian: pm_steps held_brian",
     "select count(*)::text from successbrian_os.pm_steps "
     "where status='held_brian'"),
    ("waiting on Brian: captures unruled (status=raw)",
     "select count(*)::text from atlas.scattered_captures "
     "where status='raw'"),
    ("atlas goal nodes (the gap: 0 = not built)",
     "select count(*)::text from atlas.nodes "
     "where node_type='goal'"),
    ("atlas tasks queued",
     "select count(*)::text from atlas.nodes "
     "where node_type='atlas_task' and status='queued'"),
    ("second brain: knowledge_index rows",
     "select count(*)::text from successbrian_os.knowledge_index"),
]


def run(sql):
    out = subprocess.run(DB + ["-c", sql], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return [l for l in out.stdout.splitlines() if l.strip()]


def residue_lines():
    # B6: the residue inventory lives in residue_inventory.py (the single
    # source of truth for the UNION); show its summary here, count + oldest.
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "residue_inventory.py")
    out = subprocess.run([sys.executable, tool, "--summary"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("residue_inventory failed: " + out.stderr.strip())
    return [l for l in out.stdout.splitlines() if l.strip()]


def selftest():
    # every query runs and returns at least one row
    for label, sql in QUERIES:
        rows = run(sql)
        assert rows, f"no rows for: {label}"
    # a guaranteed-empty probe stays empty (queries are scoped)
    assert run("select 1 where 1=0") == []
    # B6: residue inventory runs and reports a total + oldest item
    lines = residue_lines()
    assert any(l.startswith("residue total:") for l in lines), \
        f"no residue total in: {lines}"
    assert any(l.startswith("oldest:") for l in lines), \
        f"no oldest item in: {lines}"
    # disk probe works
    total, used, free = shutil.disk_usage("/")
    assert total > 0 and 0 <= used <= total
    print("ASSEMBLY_STATUS_OK")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    total, used, free = shutil.disk_usage("/")
    print(f"alpha disk: {used * 100 // (used + free)}% used, "
          f"{free // (1024 ** 3)}G free")
    for label, sql in QUERIES:
        rows = run(sql)
        print(f"{label}: " + (", ".join(rows) if rows else "none"))
    print("residue inventory (waiting on Brian):")
    for line in residue_lines():
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
