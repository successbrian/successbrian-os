#!/usr/bin/env python3
"""feedback_log.py — record what Brian actually chose vs the solver's pick.

PURPOSE: Log solver recommendations vs Brian's real decisions into
         dealsdesk.solver_feedback, so the adequacy math can be audited and
         improved over time.
WHY:     If the solver keeps recommending K11s and Brian keeps buying
         Aoostars, the math is wrong somewhere. Without a record of the
         divergence, it can never learn.
CALLED BY: manually: python3 feedback_log.py --need-id N --recommended X
           --chosen Y [--note Z] [--source brian]
NOTES:   Recording only. Nothing here changes recommendations; analysis of
         the feedback (re-tuning the solver) is a separate, Brian-approved
         step. No chat model decides.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/feedback_log.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/feedback_log.py (k11-alpha; systemd timers).

"""

import argparse
import logging
import subprocess
import sys

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [feedback_log] %(message)s")
LOG = logging.getLogger("feedback_log")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def esc(s):
    return str(s).replace("'", "''")


def main():
    ap = argparse.ArgumentParser(description="Log solver recommendation vs actual choice")
    ap.add_argument("--need-id", type=int, required=True)
    ap.add_argument("--recommended", required=True, help="what the solver recommended")
    ap.add_argument("--chosen", required=True, help="what Brian actually chose")
    ap.add_argument("--note", default="", help="why / outcome note")
    ap.add_argument("--source", default="brian")
    a = ap.parse_args()

    sql = (f"""INSERT INTO dealsdesk.solver_feedback
               (need_id, recommended_label, chosen_label, outcome_note, source)
               VALUES ({a.need_id}, '{esc(a.recommended)}', '{esc(a.chosen)}',
                       '{esc(a.note)}', '{esc(a.source)}') RETURNING id""")
    r = subprocess.run(["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-c", sql],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("insert failed: %s", r.stderr.strip()[:200])
        sys.exit(1)
    fid = r.stdout.strip()
    match = "MATCH" if a.recommended.strip().lower() == a.chosen.strip().lower() else "DIVERGED"
    print(f"feedback #{fid}: need {a.need_id} — solver said '{a.recommended}', "
          f"Brian chose '{a.chosen}' [{match}]")


if __name__ == "__main__":
    main()
