#!/usr/bin/env python3
"""brian_inbox_route.py - route everything that needs Brian into his
ONE inbox (Brian correction 2026-11-23 19:06 CST: "needs brian - we
do already have an inbox for brian").

Brian's inbox is successbrian_os.pending_questions (status 'open') -
the store behind the unified Inbox page (tools/dashboard/
build_unified_inbox.py renders it as "Inbox / Needs your call") and
the dash-actions answer API. It is the ecosystem-wide ask-Brian
channel: lyra, qwen-worker, life-ops, altair, spencer and meghan all
ask there (993 questions on record at build time, newest same-day).

This router sweeps the places Brian-bound items were scattering and
files them into that inbox, once each:

  1. Einstein deep looks - the FOR BRIAN section of every collected
     einstein_passes plan (it used to live only in plan text).
  2. pm_steps held for Brian (status 'held_brian').
  3. The review passes' waiting decisions (successbrian_os.
     review_decisions, state 'waiting') - the passes keep their
     working queue untouched; the inbox becomes the one
     Brian-facing list and the one count.

Dedupe: every routed question carries a marker in its context,
"[inbox-route: source=<store> id=<n>]", and a source is skipped if
any pending_questions row already carries its marker. Re-runs are
idempotent. Nothing is deleted, moved, or re-stated anywhere: the
sources keep their records and states; this only ADDS questions.

Modes:
  run         route anything unrouted (the cron mode)
  --dry-run   print what would be filed, file nothing
  selftest    extractor checks on synthetic plan text

Registry: program_registry 'brian-inbox-route-py', probe = log
mtime of ~/logs/brian-inbox-route.log, cadence 120 min.
Cron: every 2h at :55 (after the Einstein cycle at :35 and the
goal harness at :50).

Selftest: python3 tools/dashboard/brian_inbox_route.py selftest
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sbos_common import pg_exec, pg_one, pg_rows  # noqa: E402

MARKER = "[inbox-route: source=%s id=%s]"
EMPTY_FOR_BRIAN = {"", "none", "none.", "n/a", "no", "nothing"}


def extract_for_brian(plan_text):
    """The FOR BRIAN tail of an Einstein plan, or None.

    Plans are one unbroken block with inline section headers; the
    FOR BRIAN section runs to the end. A section that is absent
    (older plans were clipped by the return leg) or explicitly
    empty ('none.') yields None.
    """
    if not plan_text:
        return None
    idx = plan_text.find("FOR BRIAN:")
    if idx < 0:
        return None
    tail = plan_text[idx + len("FOR BRIAN:"):].strip()
    if tail.lower() in EMPTY_FOR_BRIAN:
        return None
    return tail


def already_routed(source, source_id):
    marker = MARKER % (source, source_id)
    return bool(pg_one(
        "SELECT count(*) FROM successbrian_os.pending_questions "
        "WHERE context LIKE %s", ("%" + marker + "%",)))


def file_question(asked_by, question, context, priority, dry_run):
    if dry_run:
        print("  WOULD FILE [%s] %s" % (asked_by, question[:90]))
        return None
    row = pg_rows(
        "INSERT INTO successbrian_os.pending_questions "
        "(asked_by, question, context, priority, status) "
        "VALUES (%s,%s,%s,%s,'open') RETURNING id",
        (asked_by, question, context, priority))
    qid = row[0][0]
    print("  filed inbox question #%d [%s] %s" % (qid, asked_by,
                                                  question[:90]))
    return qid


def route_einstein(dry_run):
    print("Einstein FOR BRIAN sections:")
    n = 0
    passes = pg_rows(
        "SELECT id, goal_slug, look_id, collected_at, plan_text FROM "
        "successbrian_os.einstein_passes WHERE status='collected' "
        "ORDER BY id")
    for pid, slug, look_id, collected_at, plan_text in passes:
        ask = extract_for_brian(plan_text)
        if ask is None:
            continue
        if already_routed("einstein_passes", pid):
            print("  pass #%d (%s): already in inbox" % (pid, slug))
            continue
        context = (
            "Routed into Brian's inbox by brian_inbox_route.py "
            "(Brian 2026-11-23: one inbox for everything that needs "
            "him). Source: Einstein deep look at goal '%s' - "
            "successbrian_os.einstein_passes #%d (look %s), "
            "collected %s. Full plan: Atlas node goal:%s readme_md "
            "and einstein_passes.plan_text. %s"
            % (slug, pid, look_id, collected_at, slug,
               MARKER % ("einstein_passes", pid)))
        if file_question("einstein", ask, context, 2, dry_run):
            n += 1
        elif dry_run:
            n += 1
    print("  %d Einstein item(s) routed" % n)
    return n


def route_held_steps(dry_run):
    print("pm_steps held for Brian:")
    n = 0
    steps = pg_rows(
        "SELECT id, step_key, title, kind, created_at FROM "
        "successbrian_os.pm_steps WHERE status='held_brian' "
        "ORDER BY id")
    for sid, key, title, kind, created_at in steps:
        if already_routed("pm_steps", sid):
            print("  step #%d (%s): already in inbox" % (sid, key))
            continue
        context = (
            "Routed into Brian's inbox by brian_inbox_route.py "
            "(Brian 2026-11-23: one inbox). Source: pm_steps #%d "
            "(step_key '%s', kind '%s'), held for Brian since %s. "
            "The step keeps its held_brian state in pm_steps; this "
            "question is its Brian-facing copy. %s"
            % (sid, key, kind, created_at, MARKER % ("pm_steps", sid)))
        if file_question("spencer", title, context, 2, dry_run):
            n += 1
        elif dry_run:
            n += 1
    print("  %d held step(s) routed" % n)
    return n


def route_review_decisions(dry_run):
    print("Review decisions waiting:")
    n = 0
    rows = pg_rows(
        "SELECT id, item, context, first_surfaced FROM "
        "successbrian_os.review_decisions WHERE state='waiting' "
        "ORDER BY id")
    for did, item, orig_ctx, first_surfaced in rows:
        if already_routed("review_decisions", did):
            print("  decision #%d: already in inbox" % did)
            continue
        context = (
            "%s\nRouted into Brian's inbox by brian_inbox_route.py "
            "(Brian 2026-11-23: one inbox). Source: review decisions "
            "queue #%d, waiting since %s - the review passes' "
            "working queue (review_decisions keeps its record and "
            "state; this question is the Brian-facing copy). %s"
            % (orig_ctx or "", did, first_surfaced,
               MARKER % ("review_decisions", did)))
        if file_question("spencer", item, context, 2, dry_run):
            n += 1
        elif dry_run:
            n += 1
    print("  %d decision(s) routed" % n)
    return n


def do_run(dry_run):
    total = 0
    total += route_einstein(dry_run)
    total += route_held_steps(dry_run)
    total += route_review_decisions(dry_run)
    open_n = pg_one(
        "SELECT count(*) FROM successbrian_os.pending_questions "
        "WHERE status='open'")
    print("ROUTED %d new item(s); inbox open count now %s"
          % (total, open_n))
    return 0


def do_selftest():
    fails = []

    def check(name, cond):
        print("  [%s] %s" % ("ok" if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    plan = ("VERIFIED STATE: x. PLAN: 1. do it. FOR BRIAN: Confirm "
            "whether the 100 is a data error; decide the date.")
    check("extracts FOR BRIAN tail",
          extract_for_brian(plan) ==
          "Confirm whether the 100 is a data error; decide the date.")
    check("explicit none yields None",
          extract_for_brian("PLAN: x. FOR BRIAN: none.") is None)
    check("missing section yields None",
          extract_for_brian("VERIFIED STATE: only this.") is None)
    check("empty plan yields None", extract_for_brian("") is None)
    check("marker format stable",
          (MARKER % ("einstein_passes", 4)) ==
          "[inbox-route: source=einstein_passes id=4]")
    print("SELFTEST %s (%d failures)" % ("PASS" if not fails else "FAIL",
                                         len(fails)))
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["run", "selftest"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.mode == "selftest":
        return do_selftest()
    return do_run(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
