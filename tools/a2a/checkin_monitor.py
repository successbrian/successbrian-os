#!/usr/bin/env python3
"""Lyra's health monitor for the Altair -> Spencer check-in pipeline.

PURPOSE: Verify each scheduled check-in actually landed in the database;
    alert Spencer (and thereby Brian) if the pipeline is silent or broken.
WHY: Lyra is the fleet's health monitor. The twice-daily check-in is a
    critical async link between Altair and Spencer — if it goes quiet,
    nobody notices until Brian asks why he hasn't heard from Altair.
    This closes that loop.
CALLED BY: Hermes --no-agent cron jobs on Lyra's profile:
    checkin-monitor-morning (weekdays 10:15 AM CDT, watches the 9:30 slot)
    checkin-monitor-afternoon (weekdays 3:15 PM CDT, watches the 2:30 slot)
NOTES:
    - CANONICAL SOURCE: successbrian-os/tools/a2a/checkin_monitor.py
    - End-to-end check: did a sender='altair' target='spencer' row land in
      altair.knowledge_bridge within the expected window? A row in the DB
      is proof the whole chain (cron -> script -> Morpheus -> DB) worked.
    - Also inspects Altair's cron jobs.json for recent failures (secondary).
    - On failure: inserts an urgency='important' alert row as sender='lyra'
      target='spencer' AND prints details (cron delivers stdout to Lyra).
    - On success: prints one quiet OK line. Silence is health.
"""
import json, os, sys, subprocess
from datetime import datetime, timedelta

PG = {"host": "localhost", "dbname": "ecosystem_central",
      "user": "successbrian", "password": "postgres"}
ALTAIR_JOBS = "/home/successbrian/.hermes/profiles/altair/cron/jobs.json"
# Check-in slots and the monitor runs that watch them
SLOTS = {
    "morning": {"checkin_hour": 9, "checkin_min": 30},
    "afternoon": {"checkin_hour": 14, "checkin_min": 30},
}
# How long after the scheduled check-in before we declare it missing
GRACE_MINUTES = 60


def _pg(query, params=()):
    """Run a read query, return rows. psycopg2 preferred, psql fallback."""
    try:
        import psycopg2
        dsn = "host=%s dbname=%s user=%s password=%s" % (
            PG["host"], PG["dbname"], PG["user"], PG["password"])
        conn = psycopg2.connect(dsn, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except ImportError:
        pass
    env = dict(os.environ, PGPASSWORD=PG["password"])
    # params are internal (slot windows), safe to inline
    r = subprocess.run(["psql", "-h", PG["host"], "-U", PG["user"],
                        "-d", PG["dbname"], "-t", "-A", "-F", "|", "-c", query],
                       capture_output=True, text=True, env=env, timeout=30)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr[:200])
    return [tuple(l.split("|")) for l in r.stdout.strip().splitlines() if l.strip()]


def _pg_write(subject, body, urgency="important"):
    try:
        import psycopg2
        dsn = "host=%s dbname=%s user=%s password=%s" % (
            PG["host"], PG["dbname"], PG["user"], PG["password"])
        conn = psycopg2.connect(dsn, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency)"
            " VALUES ('lyra','spencer',%s,%s,%s) RETURNING id",
            (subject, body, urgency))
        row_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return row_id
    except ImportError:
        pass
    env = dict(os.environ, PGPASSWORD=PG["password"])
    q = ("INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency) "
         "VALUES ('lyra','spencer',$$%s$$,$$%s$$,'%s') RETURNING id;"
         % (subject.replace("$$", ""), body.replace("$$", ""), urgency))
    r = subprocess.run(["psql", "-h", PG["host"], "-U", PG["user"],
                        "-d", PG["dbname"], "-t", "-A", "-c", q],
                       capture_output=True, text=True, env=env, timeout=30)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr[:200])
    return r.stdout.strip().split()[0]


def check_slot(slot):
    """Did the expected check-in row land? Returns (ok, detail)."""
    now = datetime.now()
    cfg = SLOTS[slot]
    scheduled = now.replace(hour=cfg["checkin_hour"], minute=cfg["checkin_min"],
                            second=0, microsecond=0)
    window_start = scheduled.strftime("%Y-%m-%d %H:%M:%S")
    # Row must have landed between scheduled time and now (monitor runs after)
    rows = _pg(
        "SELECT id, subject, urgency, created_at FROM altair.knowledge_bridge "
        "WHERE sender='altair' AND target='spencer' "
        "AND created_at >= %s::timestamp "
        "ORDER BY created_at DESC LIMIT 3",
        (window_start,))
    if rows:
        r = rows[0]
        return True, "row %s landed at %s (urgency=%s): %s" % (r[0], r[3], r[2], r[1][:80])
    return False, "no altair->spencer row since %s" % window_start


def check_cron_health():
    """Secondary: are Altair's check-in cron jobs themselves healthy?"""
    try:
        d = json.load(open(ALTAIR_JOBS))
        jobs = d.get("jobs", d) if isinstance(d, dict) else d
        if isinstance(jobs, dict):
            jobs = list(jobs.values())
        problems = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            name = j.get("name", "")
            if "spencer-checkin" not in name:
                continue
            if not j.get("enabled", True):
                problems.append("%s is DISABLED" % name)
            last = j.get("last_run") or {}
            if isinstance(last, dict) and last.get("status") == "failed":
                problems.append("%s last run FAILED: %s"
                                % (name, str(last.get("error"))[:120]))
        return problems
    except Exception as e:
        return ["could not read Altair jobs.json: %s" % e]


def main():
    hour = datetime.now().hour
    slot = "morning" if hour < 12 else "afternoon"
    # Skip weekends: check-ins only run weekdays
    if datetime.now().weekday() >= 5:
        print("OK: weekend, no check-in expected")
        return

    ok, detail = check_slot(slot)
    problems = check_cron_health()
    if ok and not problems:
        print("OK: %s check-in healthy — %s" % (slot, detail))
        return

    # Pipeline is degraded — alert via knowledge_bridge + stdout
    bits = []
    if not ok:
        bits.append("MISSING %s check-in: %s" % (slot, detail))
    bits.extend(problems)
    body = ("Lyra check-in monitor (%s slot, %s):\n- %s\n\n"
            "The Altair->Spencer async standup is not landing. "
            "Check: Altair's cron ticker, ~/.hermes/scripts/spencer_checkin.py, "
            "Morpheus :11437, and the ecosystem_central DB."
            % (slot, datetime.now().strftime("%Y-%m-%d %H:%M"), "\n- ".join(bits)))
    subject = "Check-in pipeline %s: %s" % (
        slot, "missing check-in" if not ok else "cron unhealthy")
    try:
        row_id = _pg_write(subject, body)
        print("ALERT row %s: %s" % (row_id, " | ".join(bits)))
    except Exception as e:
        print("ALERT (db write failed: %s): %s" % (e, " | ".join(bits)),
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
