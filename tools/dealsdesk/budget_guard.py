#!/usr/bin/env python3
"""budget_guard.py — build budget overrun detector.

PURPOSE: For every build with a budget_target, compare the projected total
         (spent + target_price x quantity of everything not yet in hand)
         against the budget, log the check, and alert when over.
WHY:     Builds carry budget_target/spent but nothing watched them — a
         build could quietly blow past its budget with no flag. Brian's
         rule is start low-cost and expand; the guardrail enforces it.
CALLED BY: systemd timer budget-guard.timer (weekly, Monday 08:00).
NOTES:   "Not yet in hand" = item_status NOT IN ('in_hand','delivered',
         'complete') — adapted 2026-10-01 to the actual status values in
         the DB (priced/needed/in_hand). Every run is logged to
         dealsdesk.budget_checks. Outbox posts are deduped: at most one
         BUDGET RISK post per build per 7 days. --dry-run prints without
         posting or logging. Never auto-buys anything.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/budget_guard.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/budget_guard.py (k11-alpha; systemd timers).

"""

import argparse
import logging
import subprocess
import sys

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [budget_guard] %(message)s")
LOG = logging.getLogger("budget_guard")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"
ALERT_COOLDOWN_DAYS = 7


def psql(sql, write=False):
    r = subprocess.run(["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A",
                        "-F\x1f", "-c", sql],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return []
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return str(s).replace("'", "''")


def ensure_tables():
    # Tables are provisioned via the altair role (successbrian lacks schema
    # CREATE). Only attempt DDL when the table is genuinely missing.
    rows = psql("SELECT to_regclass('dealsdesk.budget_checks')")
    if not rows or not rows[0][0]:
        LOG.warning("dealsdesk.budget_checks missing — attempting create (needs privileges)")
        psql("""CREATE TABLE IF NOT EXISTS dealsdesk.budget_checks (
                id SERIAL PRIMARY KEY,
                build_id INT NOT NULL REFERENCES dealsdesk.builds(id),
                checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                projected NUMERIC,
                budget NUMERIC,
                over_by NUMERIC,
                alerted BOOLEAN NOT NULL DEFAULT FALSE)""", write=True)
def main():
    ap = argparse.ArgumentParser(description="Check build budgets vs projections")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only; no outbox posts, no log rows")
    a = ap.parse_args()
    ensure_tables()

    builds = psql("""SELECT id, name, COALESCE(budget_target,0), COALESCE(spent,0)
                     FROM dealsdesk.builds WHERE budget_target IS NOT NULL""")
    for b in builds:
        b = (b + [""] * 4)[:4]
        build_id, name, budget, spent = int(b[0]), b[1], float(b[2]), float(b[3])
        rows = psql(f"""SELECT COALESCE(SUM(target_price * quantity), 0)
                        FROM dealsdesk.build_items
                        WHERE build_id = {build_id}
                          AND item_status NOT IN ('in_hand','delivered','complete')""")
        remaining = float(rows[0][0]) if rows and rows[0][0] else 0.0
        projected = spent + remaining
        over_by = projected - budget
        over = over_by > 0
        LOG.info("build '%s': projected $%.2f vs budget $%.2f (over by $%.2f)",
                 name, projected, budget, max(0.0, over_by))

        alerted = False
        if over:
            recent = psql(f"""SELECT 1 FROM dealsdesk.budget_checks
                              WHERE build_id = {build_id} AND alerted
                                AND checked_at > NOW() - INTERVAL '{ALERT_COOLDOWN_DAYS} days'
                              LIMIT 1""")
            if recent:
                LOG.info("build '%s': over budget but alerted within %d days — suppressed",
                         name, ALERT_COOLDOWN_DAYS)
            else:
                msg = (f"BUDGET RISK: build '{name}' projected ${projected:,.2f} "
                       f"vs budget ${budget:,.2f} (over by ${over_by:,.2f}). "
                       f"Brian decides; nothing auto-buys.")
                if a.dry_run:
                    print(f"[dry-run] would post: {msg}")
                else:
                    psql(f"""INSERT INTO public.successbrian_outbox
                             (agent, message_text, priority)
                             VALUES ('dealsdesk', '{esc(msg)}', 1)""", write=True)
                    alerted = True
                    LOG.warning(msg)
        if not a.dry_run:
            psql(f"""INSERT INTO dealsdesk.budget_checks
                     (build_id, projected, budget, over_by, alerted)
                     VALUES ({build_id}, {projected}, {budget}, {over_by}, {alerted})""",
                 write=True)
    LOG.info("done (dry_run=%s)", a.dry_run)


if __name__ == "__main__":
    main()
