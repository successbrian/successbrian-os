#!/usr/bin/env python3
"""podcast_friday_kickoff.py — Friday 19:00: start Saturday podcast production.
Brian 2026-10-17: the Oct 17 episode failed because nothing kicked off the
Friday overnight run. This ensures the pipeline starts every Friday.
"""
import subprocess
from datetime import date

PSQL = ["psql", "-h", "localhost", "-U", "postgres", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A"]
ENV = {"PATH": "/usr/bin:/bin", "PGPASSWORD": "postgres"}


def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True,
                       timeout=30, env=ENV)
    return r.stdout.strip()


def pq(s):
    return "'" + str(s).replace("'", "''") + "'"


def main():
    sat = date.today().isoformat()
    label = "Saturday podcast (%s)" % sat
    # Don't double-queue if this week's tasks already exist
    existing = q("SELECT count(*) FROM successbrian_os.tasks "
                 "WHERE title LIKE %s;" % pq("%" + label + "%"))
    if existing.strip().isdigit() and int(existing.strip()) >= 5:
        print("podcast tasks already exist for %s — skip" % sat)
        return 0
    steps = [
        "Dialogue packet written",
        "TTS audio generated",
        "QA pass: glitches, speed shifts, mispronunciations fixed",
        "Episode assembled + posted",
        "Meme created",
    ]
    for step in steps:
        q("INSERT INTO successbrian_os.tasks (title, status) VALUES (%s, 'pending');"
          % pq("[%s] %s" % (label, step)))
    print("created %d podcast tasks for %s" % (len(steps), sat))
    # Queue the dialogue-writing handoff: the Lyra fleet picks it up,
    # researches the week's biggest threads, writes the Alex/Jordan script.
    q("INSERT INTO successbrian_os.v4pro_handoffs "
      "(requested_by, task_kind, task_summary, context, ask, constraints, status) "
      "VALUES ('podcast-kickoff', 'atlas-research', "
      "%s, %s, %s, %s, 'queued');"
      % (pq("Saturday podcast (%s) dialogue packet" % sat),
         pq("Write the dialogue packet for this week's Saturday podcast "
            "(Brian's private learning feed). Research the week's biggest "
            "ecosystem threads from the second brain, Atlas, and recent "
            "handoffs. Write ~1300-1500 words as Alex/Jordan dialogue "
            "(Alex: / Jordan: labeled lines). Check the pronunciation log "
            "at /home/successbrian/tts-clone/pronunciation.md first."),
         pq("Dialogue packet only. Output the full script as dialogue lines."),
         pq("Private learning feed, never audience content. File the script "
            "where the TTS step can find it.")))
    print("queued dialogue handoff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
