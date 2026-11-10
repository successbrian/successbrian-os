#!/usr/bin/env python3
"""Daily QA probes for the clerk filing flow (2026-11-09 repair).

Registered as daily command checks under PM project
clerk-filing-flow-repair. Each mode prints a marker line only
when the repaired state still holds:

  unsorted   every document in the unsorted workspace is on
             the held list (the tray holds nothing unaccounted)
  unindexed  every embedded (workspace, base filename) pair
             has a knowledge_index row (delegates to the
             backfill's own dry-run count)
  raw-age    no capture has sat status='raw' for over 26
             hours (hourly sweep + daily triage bound, a
             machinery choice from the 2026-11-09 repair)
"""

import json
import os
import sqlite3
import sys

ALLM_DB = os.path.expanduser(
    "~/anything-llm/server/storage/anythingllm.db")
HELD = os.path.expanduser(
    "~/backups/clerk-filing-repair-20261109/held-list.json")


def mode_unsorted():
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    names = [r[0] for r in db.execute(
        "SELECT wd.filename FROM workspace_documents wd JOIN "
        "workspaces w ON w.id = wd.workspaceId WHERE "
        "w.slug = 'unsorted'")]
    db.close()
    held = set()
    if os.path.exists(HELD):
        held = {h["filename"]
                for h in json.load(open(HELD))}
    stray = [n for n in names if n not in held]
    if stray:
        print("UNSORTED STRAY: %d doc(s) not on the held list, "
              "e.g. %s" % (len(stray), stray[0]))
        return 1
    print("UNSORTED_HELD_ONLY_OK %d docs, all held-listed"
          % len(names))
    return 0


def mode_unindexed():
    sys.path.insert(0, os.path.expanduser(
        "~/successbrian-os/board"))
    import backfill_kindex_catalog as bf
    import kindex
    _c = kindex.conn()
    _cur = _c.cursor()
    covered = set()
    _cur.execute(
        "SELECT allm_workspace, allm_filename FROM "
        "successbrian_os.knowledge_index WHERE "
        "allm_filename IS NOT NULL AND allm_workspace "
        "IS NOT NULL")
    for ws, fn in _cur.fetchall():
        covered.add((ws, fn))
    _c.close()
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    pairs = set()
    for slug, filename in db.execute(
            "SELECT w.slug, wd.filename FROM "
            "workspace_documents wd JOIN workspaces w ON "
            "w.id = wd.workspaceId"):
        pairs.add((slug, bf.base_filename(filename)))
    db.close()
    missing = pairs - covered
    if missing:
        print("UNINDEXED %d pair(s), e.g. %s"
              % (len(missing), sorted(missing)[0]))
        return 1
    print("UNINDEXED_ZERO_OK %d pairs covered" % len(pairs))
    return 0


def mode_raw_age():
    sys.path.insert(0, os.path.expanduser(
        "~/successbrian-os/tools/pm"))
    sys.path.insert(0, os.path.expanduser(
        "~/successbrian-os/tools"))
    import sbos_common
    conn = sbos_common.connect(user="postgres")
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*), COALESCE(max(EXTRACT(EPOCH FROM "
        "(now() - created_at)) / 3600), 0) FROM "
        "atlas.scattered_captures WHERE status = 'raw' AND "
        "created_at < now() - interval '26 hours'")
    n, oldest = cur.fetchone()
    conn.close()
    if n:
        print("RAW_AGING %d capture(s) raw past 26h (oldest "
              "%.0fh)" % (n, float(oldest)))
        return 1
    print("RAW_AGE_OK no capture raw past 26h")
    return 0


if __name__ == "__main__":
    modes = {"unsorted": mode_unsorted,
             "unindexed": mode_unindexed,
             "raw-age": mode_raw_age}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        print("usage: filing_flow_qa.py {%s}"
              % "|".join(modes))
        sys.exit(2)
    sys.exit(modes[sys.argv[1]]())
