#!/usr/bin/env python3
"""podcast_friday_kickoff.py — Friday 19:00: start Saturday podcast production.
Brian 2026-10-17: the Oct 17 episode failed because nothing kicked off the
Friday overnight run. This ensures the pipeline starts every Friday.

Fixed 2026-10-24 (Brian's go, after live diagnosis):
- tasks inserts now set assigned_to/assigned_by (both NOT NULL in
  successbrian_os.tasks; the old insert failed on every row).
- The episode date is the upcoming Saturday, not the Friday run date
  (the old code labeled the Oct 24 episode "2026-10-23").
- q() raises on psql failure (ON_ERROR_STOP + returncode check) and main
  verifies row counts before printing success — the old code ignored
  insert errors and printed "created 5 podcast tasks" unconditionally,
  so the Oct 23 log claimed success while zero tasks were created.
- Task creation and the dialogue handoff are idempotent independently:
  existing life_ops tasks for the episode no longer suppress the handoff,
  and a re-run queues neither duplicate tasks nor a duplicate handoff.
- Password literal removed (Brian, 2026-10-24 "take the passwords out"):
  psql authenticates via ~/.pgpass (mode 600, outside this public repo),
  which already covers localhost:5432:ecosystem_central:postgres. No
  credential lives in this file.

Usage:
    podcast_friday_kickoff.py [YYYY-MM-DD]
    Optional argument overrides the target Saturday (manual re-runs/tests).
"""
import os
import subprocess
import sys
from datetime import date, timedelta

# SBOS common routines — Batch C migration (2026-10-27).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402

PSQL = ["psql", "-h", "localhost", "-U", "postgres", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A"]
# No PGPASSWORD here: libpq reads ~/.pgpass (outside the repo). HOME must
# be passed explicitly so psql can find it under cron's minimal env.
ENV = {"PATH": "/usr/bin:/bin",
       "HOME": os.environ.get("HOME", "/home/successbrian")}

STEPS = [
    "Dialogue packet written",
    "TTS audio generated",
    "QA pass: glitches, speed shifts, mispronunciations fixed",
    "Episode assembled + posted",
    "Meme created",
]


def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True,
                       timeout=30, env=ENV)
    if r.returncode != 0:
        raise RuntimeError("psql failed: %s | sql: %s"
                           % (r.stderr.strip()[:300], sql[:120]))
    return r.stdout.strip()


def pq(s):
    return "'" + str(s).replace("'", "''") + "'"


def next_saturday(today):
    """The Saturday this kickoff is for: today if Saturday, else the
    coming Saturday (Friday -> tomorrow)."""
    return today + timedelta(days=(5 - today.weekday()) % 7)


def main(argv):
    if len(argv) > 1:
        sat = date.fromisoformat(argv[1])
    else:
        sat = next_saturday(date.today())
    label = "Saturday podcast (%s)" % sat.isoformat()

    # --- Tasks (idempotent, per step) ---
    created = 0
    for step in STEPS:
        title = "[%s] %s" % (label, step)
        exists = q("SELECT count(*) FROM successbrian_os.tasks "
                   "WHERE title=%s;" % pq(title))
        if exists.isdigit() and int(exists) >= 1:
            continue
        q("INSERT INTO successbrian_os.tasks "
          "(assigned_to, assigned_by, title, status) VALUES "
          "('altair', 'podcast-kickoff', %s, 'pending');" % pq(title))
        created += 1
    total = q("SELECT count(*) FROM successbrian_os.tasks "
              "WHERE title LIKE %s;" % pq("%" + label + "%"))
    if not total.isdigit() or int(total) < len(STEPS):
        raise RuntimeError("task verification failed for %s: found %s, "
                           "expected at least %d" % (label, total, len(STEPS)))
    print("podcast tasks for %s: %d present (%d created this run)"
          % (sat, int(total), created))

    # --- Dialogue handoff (idempotent) ---
    summary = "%s dialogue packet" % label
    existing_h = q("SELECT count(*) FROM successbrian_os.v4pro_handoffs "
                   "WHERE task_summary=%s AND status IN ('queued', 'done');"
                   % pq(summary))
    if existing_h.isdigit() and int(existing_h) >= 1:
        print("dialogue handoff already queued/done for %s — skip" % sat)
        return 0
    # Batch C migration (2026-10-27): the insert delegates to
    # sbos_common.handoff_enqueue (the dedupe check above stays local).
    sbos_common.handoff_enqueue(
        "podcast-kickoff", "atlas-research", summary,
        context=("Write the dialogue packet for this week's Saturday podcast "
                 "(Brian's private learning feed). Research the week's biggest "
                 "ecosystem threads from the second brain, Atlas, and recent "
                 "handoffs. Write ~1300-1500 words as Alex/Jordan dialogue "
                 "(Alex: / Jordan: labeled lines). Check the pronunciation log "
                 "at /home/successbrian/tts-clone/pronunciation.md first."),
        ask="Dialogue packet only. Output the full script as dialogue lines.",
        constraints=("Private learning feed, never audience content. File the "
                     "script where the TTS step can find it."))
    queued = q("SELECT count(*) FROM successbrian_os.v4pro_handoffs "
               "WHERE task_summary=%s AND status='queued';" % pq(summary))
    if not queued.isdigit() or int(queued) < 1:
        raise RuntimeError("handoff verification failed for %s" % label)
    print("queued dialogue handoff for %s" % sat)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as e:  # noqa: BLE001 — cron log must show the failure
        print("podcast_friday_kickoff FAILED: %s" % e, file=sys.stderr)
        raise SystemExit(1)
