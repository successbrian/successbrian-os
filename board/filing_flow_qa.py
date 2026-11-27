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
  drainage   the unsorted tray is actually draining: every
             document past the clerk-tray age threshold is
             escalated, a true duplicate, or freshly examined
             (2026-11-27 successor gauge, friction #47). True
             duplicates deleted under Brian's 2026-11-27 ruling
             leave the tray entirely and are reported on the
             line as resolved_deleted (from the clerk's audit
             table), distinct from filed documents.
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




def mode_drainage():
    """The tray's DRAINAGE gauge (2026-11-27, successor to the
    held-list accounting of mode 'unsorted' — friction #47:
    check 532's green only ever meant 'nothing unaccounted',
    and it went green on a full tray). Drainage asks whether
    the tray is actually being worked down: every document
    past the clerk-tray age threshold (7 days) must be
    accounted as escalated (an open clerk-tray question in
    Brian's inbox covers its cluster), a true duplicate, or
    not yet examined by a loop run. Anything else — legacy
    holds, failed moves, strays — is unaccounted backlog and
    this check FAILS, which is the tray's true state until
    the loop and Brian's rulings drain it. The printed line
    always carries the tray count and median age so the level
    is visible even when the check passes."""
    import re as _re
    from datetime import datetime, timezone
    sys.path.insert(0, os.path.expanduser(
        "~/successbrian-os/tools"))
    import sbos_common
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    rows = db.execute(
        "SELECT wd.filename, wd.createdAt FROM "
        "workspace_documents wd JOIN workspaces w "
        "ON w.id = wd.workspaceId WHERE w.slug = 'unsorted'"
    ).fetchall()
    db.close()
    held = {}
    if os.path.exists(HELD):
        for h in json.load(open(HELD)):
            held[h["filename"]] = h.get("why", "")
    conn = sbos_common.connect(user="postgres")
    cur = conn.cursor()
    cur.execute(
        "SELECT context FROM successbrian_os.pending_questions "
        "WHERE status = 'open' AND asked_by = 'clerk-tray'")
    open_clusters = set()
    for (ctx,) in cur.fetchall():
        m = _re.search(r"\[clerk-tray cluster: ([^\]]+)\]",
                       ctx or "")
        if m:
            open_clusters.add(m.group(1))
    # True duplicates deleted under Brian's 2026-11-27 ruling
    # are resolved-by-deletion: gone from the tray (so absent
    # from the rows above) and counted here from the clerk's
    # audit table, distinct from filed documents.
    resolved_deleted = 0
    cur.execute(
        "SELECT to_regclass('atlas.clerk_tray_deletions')")
    if cur.fetchone()[0]:
        cur.execute(
            "SELECT count(*) FROM atlas.clerk_tray_deletions")
        resolved_deleted = cur.fetchone()[0]
    conn.close()
    now = datetime.now(timezone.utc)
    ages = []
    unaccounted = 0
    aged = 0
    for fn, created in rows:
        ts = created
        if isinstance(ts, (int, float)):
            ts = ts / 1000.0 if ts > 1e11 else ts
            dt = datetime.fromtimestamp(ts, timezone.utc)
        else:
            dt = datetime.fromisoformat(
                str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        age = (now - dt).days
        ages.append(age)
        if age < 7:
            continue
        aged += 1
        why = held.get(fn, "")
        m = _re.match(r"clerk-tray: (.+)$", why or "")
        cluster = m.group(1) if m else None
        if cluster == "true-duplicate":
            continue
        if cluster and cluster in open_clusters:
            continue
        unaccounted += 1
    ages.sort()
    median = ages[len(ages) // 2] if ages else 0
    print("TRAY_DRAINAGE tray=%d median_age_days=%d aged=%d "
          "unaccounted=%d resolved_deleted=%d"
          % (len(rows), median, aged, unaccounted,
             resolved_deleted))
    if unaccounted:
        return 1
    print("TRAY_DRAINAGE_OK tray=%d median_age_days=%d "
          "resolved_deleted=%d" % (len(rows), median,
                                   resolved_deleted))
    return 0


if __name__ == "__main__":
    modes = {"unsorted": mode_unsorted,
             "unindexed": mode_unindexed,
             "raw-age": mode_raw_age,
             "drainage": mode_drainage}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        print("usage: filing_flow_qa.py {%s}"
              % "|".join(modes))
        sys.exit(2)
    sys.exit(modes[sys.argv[1]]())
