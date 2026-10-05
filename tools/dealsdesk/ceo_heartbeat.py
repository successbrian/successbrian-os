#!/usr/bin/env python3
"""ceo_heartbeat.py — Meghan's deterministic 30-minute CEO pass.

PURPOSE: Proof-of-life + snapshot for the CEO agent. Runs every 30 min.
         Does the *deterministic* half of the CEO job; judgment stays with
         Meghan's OpenClaw wake (meghan-ceo-heartbeat cron), which reads
         successbrian_os.intel_buffer and writes decisions back.
WHY:     Meghan's old pipeline was stale re-dumps with no heartbeat and a dead
         model endpoint. This is the rebuilt, stripped-down CEO loop:
         local model, event-driven intel, one decision per item.
CALLED BY: ceo-heartbeat.timer (every 30 min).
NOTES:   Never messages Brian. Never purchases. Writes only to
         ceo_heartbeats and intel_buffer.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/ceo_heartbeat.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/ceo_heartbeat.py (k11-alpha; systemd timers).

"""

import logging
import subprocess

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [ceo] %(message)s")
LOG = logging.getLogger("ceo")


def psql(sql):
    r = subprocess.run(["psql", "-U", "successbrian", "-d", "ecosystem_central",
                        "-t", "-A", "-F\x1f", "-c", sql],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:150])
        return []
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def one(sql):
    rows = psql(sql)
    return rows[0][0] if rows else "0"


def main():
    # snapshot
    untriaged = one("""SELECT COUNT(*) FROM successbrian_os.pending_questions
                       WHERE status='open' AND triaged=FALSE""")
    open_q = one("""SELECT COUNT(*) FROM successbrian_os.pending_questions
                    WHERE status='open'""")
    uncovered = one("""SELECT COUNT(DISTINCT n.title) FROM successbrian_os.ecosystem_needs n
                       WHERE n.status='open'
                       AND NOT EXISTS (SELECT 1 FROM dealsdesk.build_solves s
                                       WHERE s.need_id = n.id)""")
    stale_work = one("""SELECT COUNT(*) FROM successbrian_os.work_queue
                        WHERE status='claimed' AND claimed_at < NOW() - INTERVAL '24 hours'""")
    intel_waiting = one("""SELECT COUNT(*) FROM successbrian_os.intel_buffer
                           WHERE addressed_to IN ('meghan-alpha','all') AND read_at IS NULL""")
    # liveness: has Meghan's wake written anything in the last 2h?
    alive = one("""SELECT COUNT(*) FROM successbrian_os.ceo_heartbeats
                   WHERE source='wake' AND ran_at > NOW() - INTERVAL '2 hours'""")
    decisions = one("""SELECT COUNT(*) FROM successbrian_os.intel_buffer
                       WHERE source_agent='meghan-alpha' AND category='decision'
                       AND created_at > NOW() - INTERVAL '24 hours'""")

    actions = (f"snapshot: {open_q} open questions ({untriaged} untriaged), "
               f"{uncovered} uncovered needs, {stale_work} stale work claims, "
               f"{intel_waiting} intel items waiting for CEO")
    notes = f"CEO wake alive (2h): {'yes' if int(alive) > 0 else 'NO'}; decisions 24h: {decisions}"

    if int(stale_work) > 0:
        psql(f"""INSERT INTO successbrian_os.intel_buffer
                 (addressed_to, source_agent, category, subject, body)
                 VALUES ('meghan-alpha','ceo-heartbeat','nudge',
                         '{stale_work} work items claimed >24h with no result',
                         'Review successbrian_os.work_queue and reassign or resolve.')""")
        actions += f"; nudged {stale_work} stale claims to intel_buffer"

    esc = lambda s: s.replace("'", "''")
    psql(f"""INSERT INTO successbrian_os.ceo_heartbeats (source, actions_taken, notes)
             VALUES ('script','{esc(actions)}','{esc(notes)}')""")
    LOG.info(actions)
    LOG.info(notes)


if __name__ == "__main__":
    main()
