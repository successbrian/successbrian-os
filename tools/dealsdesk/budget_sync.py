#!/usr/bin/env python3
"""budget_sync.py — budget spent sync + lapse rollover pass.

PURPOSE: Keep successbrian_os.project_budgets honest: a MASTER
         budget's spent is recomputed from the spend recorded on
         dealsdesk.builds, and a budget whose period has ended
         stops reading status 'active' (it reads 'lapsed').
WHY:     The budget package (Intel Bridge capture #1150) found
         the spent column was written by NOTHING — the October
         2026 hardware master read $0.00 while its builds
         recorded $625.37 — and every budget period on record
         had lapsed while still reading 'active'. The recompute
         and the lapse derivation live in sbos_common (shared,
         written once); this pass is the caller.
SCOPE:   Caps, amounts, and periods are NEVER changed here.
         Renewing a lapsed budget is Brian's ruling (review
         decisions queue item #3), not a sync's business.
         dealsdesk.budgets has no spent/status columns at all,
         so for those rows this pass only REPORTS the derived
         period state in words.
MODES:   (default)   apply the sync, print what changed.
         --dry-run   print what would change, write nothing.
         --verify    write nothing; assert agreement — master
                     spent == builds total AND no 'active' row
                     whose period has lapsed. Prints
                     BUDGET_SYNC_OK or BUDGET_SYNC_DRIFT and
                     exits 0/1 (the PM QA check runs this).
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/budget_sync.py
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sbos_common  # noqa: E402


def _money(v):
    return f"${float(v):,.2f}"


def report_dealsdesk_budgets():
    """dealsdesk.budgets carries no spent/status columns — its
    period state is a derivation, reported here in words."""
    rows = sbos_common.pg_rows(
        "SELECT id, name, amount, period_start, period_end "
        "FROM dealsdesk.budgets ORDER BY id")
    for bid, name, amount, p_start, p_end in rows:
        state = sbos_common.budget_period_state(p_start, p_end)
        print(f"  dealsdesk.budgets #{bid} '{name}': "
              f"cap {_money(amount)}, period {p_start} -> {p_end}, "
              f"derived state: {state} (no spent/status columns "
              f"on this table — nothing to sync)")


def verify():
    from decimal import Decimal
    total = sbos_common.budget_build_spend_total()
    rows = sbos_common.pg_rows(
        "SELECT id, budget_name, spent, status, period_start, "
        "period_end, is_master FROM successbrian_os.project_budgets "
        "ORDER BY id")
    drift = []
    for (bid, name, spent, status, p_start, p_end,
         is_master) in rows:
        state = sbos_common.budget_period_state(p_start, p_end)
        print(f"  project_budgets #{bid} '{name}': "
              f"spent {_money(spent)}, status '{status}', "
              f"period state: {state}"
              + (" (master)" if is_master else ""))
        if is_master:
            if Decimal(str(spent)) != total:
                drift.append(
                    f"master #{bid} spent {_money(spent)} != "
                    f"builds total {_money(total)}")
        if status == "active" and state == "lapsed":
            drift.append(
                f"#{bid} reads 'active' but its period lapsed "
                f"({p_end})")
    print(f"  builds recorded spend total: {_money(total)}")
    report_dealsdesk_budgets()
    if drift:
        for d in drift:
            print(f"  DRIFT: {d}")
        print("BUDGET_SYNC_DRIFT")
        return 1
    print("BUDGET_SYNC_OK")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Sync project_budgets spent + lapse status "
                    "from the builds record")
    ap.add_argument("--dry-run", action="store_true",
                    help="report changes without writing")
    ap.add_argument("--verify", action="store_true",
                    help="assert agreement, write nothing")
    args = ap.parse_args()

    if args.verify:
        return verify()

    changes = sbos_common.sync_project_budgets(apply=not args.dry_run)
    if not changes:
        print("budget sync: already in agreement — nothing to write")
    for ch in changes:
        verb = "would update" if args.dry_run else "updated"
        print(f"  {verb} project_budgets #{ch['id']} "
              f"'{ch['budget_name']}': spent "
              f"{_money(ch['old_spent'])} -> {_money(ch['new_spent'])}, "
              f"status '{ch['old_status']}' -> '{ch['new_status']}' "
              f"(period state: {ch['period_state']})")
    report_dealsdesk_budgets()
    print("BUDGET_SYNC_" + ("DRYRUN" if args.dry_run else "APPLIED"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
