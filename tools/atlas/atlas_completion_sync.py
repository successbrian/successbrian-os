#!/usr/bin/env python3
"""Atlas completion sync — PROPOSE MODE ONLY.

Diagnosis (2026-11-09, work order capture #1148): Atlas tasks are
write-once. Creation is automated (scatter clerk WF1/WF2/WF3, the blog
checklist mirror, discovery, one-off triages), but the only code path
that moves an atlas_task to 'done' is the manual CLI verb
`atlas.py task-done`, which has ZERO automated callers anywhere in the
repo. In the system's life exactly 16 of 1,437 tasks ever reached
'done': 10 were born done at a one-off triage, ~6 were closed by hand.
Work that finishes in the parallel systems of record (PM steps, QA
checks, price re-checks) never propagates back — so Atlas's completion
count measures manual closes, not work completion, and the horizon
toolkit's flow metric reads ~0 no matter how much real work lands.

This tool is the missing wire, run in propose mode: for each open
atlas_task it looks for MACHINE-CHECKABLE proof in the system of
record that the task's work is finished, and prints a close proposal
with its evidence. It writes NOTHING. A human or a pass runs
`atlas.py task-done <key>` per proposal (or a future apply mode is
built once a rule class demonstrably yields — today every provable
class yields ~0, so an apply path would be machinery without a load;
the standing measurement is the load-bearing part).

Rules:
  R1 pm-mirror-done      task carries details.pm_step_key and the
                         pm_steps row is done/cancelled.
  R2 blogqa-check-green  theme=wf2-blog-qa-watch task whose target
                         pm_project_checks row now reads last_status
                         'pass' (one green check closes every dated
                         duplicate kick for it — the clerk re-files
                         daily while a check stays red).
  R3 wf3-recheck-refiled task:wf3-recheck-* whose capture gained a
                         price_intel row AFTER the task was created,
                         or a wf3_filings row filed after it.
  R4 packet-moot         task:ssb-packet-* whose source captures are
                         ALL discarded in atlas.scattered_captures.
  R5 packet-duplicate    REVIEW-ONLY (never a close proposal): groups
                         of open packets sharing one title — the
                         clerk filed the same work twice.

Families with NO sound rule are reported as NO-RULE with counts —
most importantly task:inbox-*: their details.pending_question_id no
longer joins to any question store (the id spaces of
altair.question_engine and public.questions have both moved on; id
553 is three different questions in three stores). The inbox tasks
themselves are now the only surviving record of those questions, so
nothing about them may be auto-proven either way.

The census section classifies every open task by its closer (who or
what can ever finish it), computed live. That is the number the
Saturday Deep Look should quote instead of raw open counts.

Usage:
  atlas_completion_sync.py [--json]
  atlas_completion_sync.py selftest
"""

import argparse
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
from sbos_common import pg_rows, pg_one  # noqa: E402

OPEN = ("queued", "open")


def rule_pm_mirror():
    rows = pg_rows(
        "SELECT n.node_key, s.status, s.finished_at FROM atlas.nodes n "
        "JOIN successbrian_os.pm_steps s "
        "ON s.step_key = n.details->>'pm_step_key' "
        "WHERE n.node_type='atlas_task' AND n.status IN ('queued','open') "
        "AND s.status IN ('done','cancelled') ORDER BY n.node_key")
    return [{"key": r[0], "rule": "R1 pm-mirror-done",
             "evidence": f"pm step {r[1]}"
                         + (f" at {r[2]}" if r[2] else "")}
            for r in rows]


def rule_blogqa_green():
    rows = pg_rows(
        "SELECT n.node_key, c.id, c.check_key FROM atlas.nodes n "
        "JOIN successbrian_os.pm_project_checks c "
        "ON c.id = (n.details->>'check_id')::int "
        "WHERE n.node_type='atlas_task' AND n.status IN ('queued','open') "
        "AND n.details->>'theme'='wf2-blog-qa-watch' "
        "AND c.last_status='pass' ORDER BY n.node_key")
    return [{"key": r[0], "rule": "R2 blogqa-check-green",
             "evidence": f"check {r[1]} ({r[2]}) now passes"}
            for r in rows]


def rule_wf3_refiled():
    rows = pg_rows(
        "SELECT n.node_key, n.created_at, "
        "(SELECT max(p.created_at) FROM successbrian_os.price_intel p "
        " WHERE p.capture_id = (n.details->'source_captures'->>0)::int), "
        "(SELECT max(f.filed_at) FROM successbrian_os.wf3_filings f "
        " WHERE f.capture_id = (n.details->'source_captures'->>0)::int) "
        "FROM atlas.nodes n WHERE n.node_type='atlas_task' "
        "AND n.status IN ('queued','open') "
        "AND n.node_key LIKE 'task:wf3-recheck-%' ORDER BY n.node_key")
    out = []
    for key, created, price_at, filed_at in rows:
        hits = []
        if price_at and price_at > created:
            hits.append(f"price_intel row filed {price_at} after task")
        if filed_at and filed_at > created:
            hits.append(f"wf3 filing {filed_at} after task")
        if hits:
            out.append({"key": key, "rule": "R3 wf3-recheck-refiled",
                        "evidence": "; ".join(hits)})
    return out


def rule_packet_moot():
    rows = pg_rows(
        "SELECT n.node_key, n.details->'source_captures' FROM atlas.nodes n "
        "WHERE n.node_type='atlas_task' AND n.status IN ('queued','open') "
        "AND n.node_key LIKE 'task:ssb-packet-%'")
    out = []
    for key, caps in rows:
        caps = caps or []
        if not caps:
            continue
        states = [pg_one("SELECT status FROM atlas.scattered_captures "
                         "WHERE id=%s", (int(c),)) for c in caps]
        if states and all(s == "discarded" for s in states):
            out.append({"key": key, "rule": "R4 packet-moot",
                        "evidence": f"all {len(caps)} source captures "
                                    "discarded"})
    return out


def review_packet_duplicates():
    rows = pg_rows(
        "SELECT name, count(*), array_agg(node_key ORDER BY node_key) "
        "FROM atlas.nodes WHERE node_type='atlas_task' "
        "AND status IN ('queued','open') "
        "AND node_key LIKE 'task:ssb-packet-%' "
        "GROUP BY name HAVING count(*) > 1 ORDER BY 2 DESC")
    return [{"title": r[0][:110], "count": r[1], "keys": r[2]}
            for r in rows]


def census():
    """Every open task, bucketed by who/what can ever close it."""
    rows = pg_rows(
        "SELECT node_key, details->>'found_by', details->>'source', "
        "details->>'theme', (details ? 'pm_step_key') FROM atlas.nodes "
        "WHERE node_type='atlas_task' AND status IN ('queued','open')")
    buckets = Counter()
    for key, found_by, source, theme, has_pm in rows:
        if key.startswith("task:ssb-packet-"):
            buckets["board-ruling-queue (WF1 packets)"] += 1
        elif key.startswith("task:inbox-"):
            buckets["brian-decision-queue (inbox triage; link rotted)"] += 1
        elif key.startswith("task:discovery:"):
            buckets["board-ruling-queue (discovery findings)"] += 1
        elif has_pm:
            buckets["pm-mirrored backlog (blog planning packages)"] += 1
        elif key.startswith("task:wf3-recheck-"):
            buckets["altair-recheck-queue (WF3 shelf-life)"] += 1
        elif theme == "wf2-blog-qa-watch":
            buckets["desk-repair-queue (blog QA kicks)"] += 1
        elif (found_by or "") in ("broken-audit",) or \
                key.startswith(("task:broken-audit:", "task:r32:")):
            buckets["desk-repair-queue (broken/audit findings)"] += 1
        else:
            buckets["unbucketed singles (no live owner loop)"] += 1
    total = pg_one("SELECT count(*) FROM atlas.nodes WHERE "
                   "node_type='atlas_task' AND status IN ('queued','open')")
    return {"open_total": total, "by_closer": dict(buckets.most_common())}


def report():
    props = (rule_pm_mirror() + rule_blogqa_green() + rule_wf3_refiled()
             + rule_packet_moot())
    by_rule = Counter(p["rule"] for p in props)
    return {"mode": "propose-only — nothing written",
            "proposals": props,
            "proposals_by_rule": dict(by_rule),
            "review_only": {"packet_duplicate_titles":
                            review_packet_duplicates()},
            "census": census(),
            "no_rule_families": [
                "task:inbox-* — pending_question_id no longer joins "
                "any question store (id-space collision proven "
                "2026-11-09); the tasks are the only surviving "
                "record of the questions",
                "task:ssb-packet-* (unruled) — only the board can "
                "close these; no machine proof of a ruling exists",
                "blog planning-package mirrors — PM step state IS "
                "the proof channel (R1) once steps start closing"]}


def text(rep):
    L = ["ATLAS COMPLETION SYNC — propose mode (nothing written)", ""]
    c = rep["census"]
    L.append(f"OPEN TASKS BY CLOSER ({c['open_total']} total):")
    for k, v in c["by_closer"].items():
        L.append(f"  {v:>5}  {k}")
    L.append("")
    L.append(f"CLOSE PROPOSALS: {len(rep['proposals'])} "
             f"{rep['proposals_by_rule'] or ''}")
    for p in rep["proposals"]:
        L.append(f"  CLOSE {p['key']}  [{p['rule']}] {p['evidence']}")
    dups = rep["review_only"]["packet_duplicate_titles"]
    L.append(f"REVIEW-ONLY: {len(dups)} duplicated packet titles")
    for d in dups[:10]:
        L.append(f"  x{d['count']}  {d['title']}")
    L.append("NO-RULE FAMILIES:")
    for f in rep["no_rule_families"]:
        L.append(f"  - {f}")
    return "\n".join(L)


def selftest():
    ok = []
    rep = report()
    ok.append(("census sums to open total",
               sum(rep["census"]["by_closer"].values())
               == rep["census"]["open_total"]))
    ok.append(("proposals carry rule + evidence",
               all(p.get("rule") and p.get("evidence")
                   for p in rep["proposals"])))
    ok.append(("board-ruling-queue is the largest closer class",
               next(iter(rep["census"]["by_closer"]), "")
               .startswith("board-ruling-queue")))
    for name, passed in ok:
        print(f"selftest: {name}: {'PASS' if passed else 'FAIL'}")
    print(f"selftest atlas_completion_sync: "
          f"{sum(1 for _, p in ok if p)}/{len(ok)}")
    return 0 if all(p for _, p in ok) else 1


WIRED_EDGES = [
    ("proj:gamma-clerk", "sys:clerk", "part_of"),
    ("proj:gamma-board", "plan:atlas-board-pack", "part_of"),
    ("proj:penny-replaces-ollama-q4", "sys:model-engines", "part_of"),
]


def edges_report():
    """The three orphan edges wired by the 2026-11-09 diagnosis."""
    present = []
    for frm, to, et in WIRED_EDGES:
        n = pg_one("SELECT count(*) FROM atlas.edges WHERE "
                   "from_node=%s AND to_node=%s AND edge_type=%s",
                   (frm, to, et))
        present.append((frm, to, et, int(n or 0)))
    got = sum(1 for *_x, n in present if n > 0)
    print(f"wired edges present: {got}/{len(WIRED_EDGES)}")
    for frm, to, et, n in present:
        print(f"  {'OK ' if n else 'MISSING'} {frm} -{et}-> {to}")
    return 0 if got == len(WIRED_EDGES) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("cmd", nargs="?", default="report")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "edges":
        return edges_report()
    rep = report()
    print(json.dumps(rep, indent=1, default=str) if a.json else text(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
