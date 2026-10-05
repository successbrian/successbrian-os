#!/usr/bin/env python3
"""question_sweeper.py — surface queued questions to Brian one at a time.

PURPOSE: Brian's rule (2026-10-01): agents only ask him what they cannot
         answer themselves. Open questions live in
         successbrian_os.pending_questions; this sweeper surfaces the single
         most important one not asked in the last 24h via the outbox (which
         feeds his digest). Never batches multiple questions.
WHY:     Respects his one-thing-at-a-time preference and scarce message
         budget; Altair draws from the same queue via knowledge_bridge.
CALLED BY: question-sweeper.timer (09:00, 13:00, 17:00 America/Chicago).
NOTES:   Research on open questions happens in Spencer/Altair passes, not
         here — this script surfaces; agents solve. 'act' severity only.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/question_sweeper.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/question_sweeper.py (k11-alpha; systemd timers).

"""

import json
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [question_sweeper] %(message)s")
LOG = logging.getLogger("question_sweeper")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def psql(sql, write=False):
    cmd = ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql]
    if write:
        cmd = ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return [] if not write else False
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return (s or "").replace("'", "''")


def main():
    dry = "--dry-run" in sys.argv
    rows = psql("""SELECT id, asked_by, question, context, options::text
                   FROM successbrian_os.pending_questions
                   WHERE status = 'open' AND triaged = TRUE
                     AND (surfaced_at IS NULL OR surfaced_at < NOW() - INTERVAL '24 hours')
                   ORDER BY priority ASC, created_at ASC LIMIT 1""")
    if not rows:
        LOG.info("no open questions due for surfacing")
        return
    qid, asked_by, question, context, options = (rows[0] + [""] * 5)[:5]
    msg = f"QUESTION FOR BRIAN ({asked_by}): {question}"
    if context:
        msg += f" Context: {context}"
    try:
        opts = json.loads(options) if options else None
    except Exception:
        opts = None
    if opts:
        msg += " Options: " + " / ".join(opts)
    if dry:
        LOG.info("dry-run would surface: %s", msg[:160])
        return
    ok = psql(f"""INSERT INTO public.successbrian_outbox (agent, message_text, priority)
                  VALUES ('spencer', '{esc(msg)}', 2)""", write=True)
    if ok:
        psql(f"""UPDATE successbrian_os.pending_questions
                 SET surfaced_at = NOW(), surfaced_by = 'spencer', updated_at = NOW() WHERE id = {qid}""",
             write=True)
        LOG.info("surfaced question %s", qid)


if __name__ == "__main__":
    main()
