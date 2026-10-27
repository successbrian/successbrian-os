#!/usr/bin/env python3
"""sync_match.py — the sync routines that match everything
together.

Brian's ruling (2026-10-27): his chats with Spencer grow the
system, his chats with Altair grow the system, the RoadChat
Hermes agents are stand-ins for both, and RoadChat is another
input to the one system (AGENT_CONTRACT rule 23). For that to
be true, the stores that hold what Brian said must AGREE with
each other — and stay matched. Brian: "we need to build sync
routines that match everything together."

This is the matching routine, v1. Deterministic. It checks
the copies of Brian's word against each other and against
their rhythms:

  DECISIONS   altair.brian_decisions (the record) vs the
              decision_sync digest that feeds AnythingLLM
              (the searchable view agents read). If Brian
              has decided things newer than the digest by
              more than a day, the view is behind the record:
              DRIFT.
  BRIDGE      atlas.scattered_captures: raw captures are
              Brian-side filings (chat rulings, intel) the
              clerk sorts hourly into board packets and
              AnythingLLM. A raw pile older than the sweep
              rhythm, or a big raw backlog, means what was
              said has not reached the other surfaces: DRIFT.
  ATLAS       atlas.currency_checks: Atlas's own picture of
              running / developing / planned refreshes 3x a
              day (atlas_currency). If the last check is
              older than 9 hours, Atlas's picture is stale:
              DRIFT.
  ROAD        the road leg: if a trip is on Brian's
              calendar within 21 days, the road snapshot
              sets are due a fresh export before it — flagged
              as WATCH until the snapshot machinery reports
              its own freshness (v1 reads no laptop state;
              the laptops are road-dark by design).

Every run is logged in atlas.sync_match_runs. DRIFT files
Atlas tasks with deterministic keys (task:sync:<slug>) the
way discovery.py and atlas_currency do — never twice, cap
10 per run. WATCH items are reported, not tasked. The
routine never edits Brian's words; it reports where the
copies disagree and lets the owning sync (decision_sync,
the clerk, atlas_currency, road_sync) do its own work.

CLI:
  sync_match.py check [--dry-run]
  sync_match.py selftest
"""

import datetime as dt
import json
import os
import sys

import psycopg2

DBNAME = "ecosystem_central"
DIGEST = os.path.expanduser(
    "~/successbrian-os/tools/decision_sync/staging/"
    "decisions-digest-latest.md")
DECISION_LAG_HOURS = 24
CAPTURE_STALE_HOURS = 3
CAPTURE_BACKLOG = 25
ATLAS_STALE_HOURS = 9
TRIP_WATCH_DAYS = 21


def connect():
    return psycopg2.connect(dbname=DBNAME, host="localhost",
                            user="postgres")


LOG_DDL = """
CREATE TABLE IF NOT EXISTS atlas.sync_match_runs (
    id       serial PRIMARY KEY,
    ran_at   timestamptz NOT NULL DEFAULT now(),
    report   jsonb NOT NULL
);
"""


def hours_between(a, b):
    return abs((a - b).total_seconds()) / 3600.0


def match(now, newest_decision, digest_mtime, raw_captures,
          oldest_raw_age_h, last_currency, next_trip_days):
    """Pure matching. Returns (report, drifts)."""
    report = {}
    drifts = []

    def drift(kind, why):
        drifts.append({"kind": kind, "why": why})

    if newest_decision is None:
        report["decisions"] = "no decisions on record"
    elif digest_mtime is None:
        report["decisions"] = "no digest found"
        drift("decisions-view-missing",
              "brian_decisions has records but no "
              "decision_sync digest exists — the searchable "
              "view of what Brian decided is missing.")
    else:
        lag = hours_between(newest_decision, digest_mtime)
        if digest_mtime >= newest_decision:
            report["decisions"] = ("digest current — covers "
                                   "decisions through %s"
                                   % newest_decision.date())
        else:
            report["decisions"] = ("digest %.1fh behind the "
                                   "newest decision" % lag)
        if newest_decision > digest_mtime and \
                lag > DECISION_LAG_HOURS:
            drift("decisions-view-behind",
                  "Brian's newest decision is %.0fh old in "
                  "the record but the AnythingLLM digest is "
                  "older still — agents reading the view are "
                  "missing what Brian said." % lag)

    report["bridge_raw"] = raw_captures
    if oldest_raw_age_h is not None and \
            oldest_raw_age_h > CAPTURE_STALE_HOURS:
        drift("bridge-captures-waiting",
              "The oldest unsorted Intel Bridge capture has "
              "waited %.0fh (clerk sweep is hourly) — what "
              "Brian said has not reached the board / "
              "AnythingLLM yet." % oldest_raw_age_h)
    if raw_captures > CAPTURE_BACKLOG:
        drift("bridge-backlog",
              "%d raw captures are waiting for the clerk — "
              "the filing rate is beating the sorting rate."
              % raw_captures)

    if last_currency is None:
        report["atlas"] = "no currency check on record"
        drift("atlas-never-checked",
              "atlas_currency has never logged a check — "
              "Atlas's picture of running / developing / "
              "planned has no freshness at all.")
    else:
        age = hours_between(now, last_currency)
        report["atlas"] = "last check %.1fh ago" % age
        if age > ATLAS_STALE_HOURS:
            drift("atlas-picture-stale",
                  "Atlas's last currency check was %.0fh ago "
                  "(rhythm is 3x a day) — its picture of what "
                  "is running / being built / planned is "
                  "stale." % age)

    if next_trip_days is not None and \
            next_trip_days <= TRIP_WATCH_DAYS:
        report["road"] = ("WATCH: trip in %dd — road "
                          "snapshot sets due a fresh export"
                          % next_trip_days)
    else:
        report["road"] = "no trip inside %dd" % TRIP_WATCH_DAYS
    return report, drifts


def gather(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT max(answered_at) FROM "
                    "altair.brian_decisions")
        newest_decision = cur.fetchone()[0]
        cur.execute("SELECT count(*), min(created_at) FROM "
                    "atlas.scattered_captures "
                    "WHERE status = 'raw'")
        raw_count, oldest_raw = cur.fetchone()
        cur.execute("SELECT max(ran_at) FROM "
                    "atlas.currency_checks")
        row = cur.fetchone()
        last_currency = row[0] if row else None
        cur.execute(
            "SELECT min(start_at) FROM life_calendar.events "
            "WHERE start_at >= now() AND (title ILIKE "
            "'%trip%' OR title ILIKE '%tardis%' OR title "
            "ILIKE '%philippines%' OR event_type = "
            "'convention')")
        row = cur.fetchone()
        next_trip = row[0] if row else None
    digest_mtime = None
    if os.path.exists(DIGEST):
        digest_mtime = dt.datetime.fromtimestamp(
            os.path.getmtime(DIGEST), tz=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    oldest_age = None
    if oldest_raw is not None:
        oldest_age = hours_between(now, oldest_raw)
    trip_days = None
    if next_trip is not None:
        trip_days = (next_trip - now).days
    return now, newest_decision, digest_mtime, raw_count, \
        oldest_age, last_currency, trip_days


def mint_tasks(conn, drifts, dry_run=False):
    import re
    minted = []
    with conn.cursor() as cur:
        for d in drifts[:10]:
            key = "task:sync:" + re.sub(
                r"[^a-z0-9]+", "-",
                d["kind"].lower()).strip("-")[:60]
            cur.execute("SELECT status FROM atlas.nodes "
                        "WHERE node_key = %s", (key,))
            row = cur.fetchone()
            if row and row[0] in ("queued", "open", "active"):
                continue
            minted.append(key)
            if dry_run:
                continue
            cur.execute(
                "INSERT INTO atlas.nodes (node_key, "
                "node_type, name, status, details) VALUES "
                "(%s, 'atlas_task', %s, 'queued', %s) "
                "ON CONFLICT (node_key) DO UPDATE SET "
                "status = 'queued', details = "
                "EXCLUDED.details, updated_at = now()",
                (key, "Sync match: " + d["why"][:120],
                 json.dumps({"why": d["why"],
                             "source": "sync-match",
                             "found_by": "sync-match",
                             "model": "sonic"})))
    if not dry_run:
        conn.commit()
    return minted


def check(dry_run=False):
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(LOG_DDL)
    conn.commit()
    report, drifts = match(*gather(conn))
    minted = mint_tasks(conn, drifts, dry_run)
    if not dry_run:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO atlas.sync_match_runs (report) "
                "VALUES (%s)",
                (json.dumps({"report": report,
                             "drifts": drifts}),))
        conn.commit()
    return report, drifts, minted


def selftest():
    fails = []

    def ck(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            fails.append(label)

    now = dt.datetime(2026, 10, 27, 12, 0,
                      tzinfo=dt.timezone.utc)
    old = now - dt.timedelta(hours=50)
    _r, drifts = match(now, old, old, 0, None, now, None)
    ck(any(d["kind"] == "decisions-view-behind"
           for d in drifts) is False and
       all(d["kind"] != "decisions-view-behind"
           for d in drifts),
       "a digest as fresh as the newest decision is matched")
    _r, drifts = match(now, now, old, 0, None, now, None)
    ck(any(d["kind"] == "decisions-view-behind"
           for d in drifts),
       "decisions newer than the digest by >24h is DRIFT")
    _r, drifts = match(now, None, None, 61, 30.0, now, None)
    ck(any(d["kind"] == "bridge-captures-waiting"
           for d in drifts) and
       any(d["kind"] == "bridge-backlog" for d in drifts),
       "a stale, deep raw-capture pile is DRIFT twice over")
    _r, drifts = match(now, None, None, 0, None,
                       now - dt.timedelta(hours=30), None)
    ck(any(d["kind"] == "atlas-picture-stale"
           for d in drifts),
       "an Atlas picture older than its rhythm is DRIFT")
    rep, drifts = match(now, None, None, 0, None, now, 5)
    ck("WATCH" in rep["road"] and not drifts,
       "a near trip is a WATCH, never a DRIFT task")
    print("SELFTEST %s: %d failure(s)"
          % ("FAILED" if fails else "OK", len(fails)))
    return 1 if fails else 0


def main(argv):
    if len(argv) > 1 and argv[1] == "selftest":
        return selftest()
    if len(argv) > 1 and argv[1] == "check":
        dry = "--dry-run" in argv
        report, drifts, minted = check(dry)
        for k, v in report.items():
            print("MATCH  %-14s %s" % (k, v))
        for d in drifts:
            print("DRIFT  %s — %s" % (d["kind"], d["why"]))
        for m in minted:
            print("%s task %s" % ("WOULD FILE" if dry
                                  else "FILED", m))
        if not drifts:
            print("All copies of what Brian said agree, "
                  "inside their rhythms.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
