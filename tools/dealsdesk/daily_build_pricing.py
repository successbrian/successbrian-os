#!/usr/bin/env python3
"""daily_build_pricing.py — daily price snapshots for every serious DealsDesk build.

PURPOSE: Brian 2026-10-01: snapshot the priced cost of every serious build
         once a day into dealsdesk.build_price_daily so daily price trends
         are visible in dealsdesk.build_price_trend (day-over-day change).
WHY:     A build's sticker price drifts as parts get priced and market prices
         move. Without daily snapshots there is no trend — only today's
         number. This is the history the trend view reads.
CALLED BY: build-pricing-daily.timer (daily 06:30 America/Chicago).
NOTES:   Serious = status IN (planning, components_priced, researching,
         parts_ordered). 'dream' builds are excluded.
         total_priced = sum(price_ea * qty) — what is priced in the tracker.
         total_market = sum(coalesce(last_seen_price, price_ea) * qty) —
         fresher when the feed has observed the part.
         Re-running the same day refreshes the row (ON CONFLICT DO UPDATE).
         Never purchases; never changes prices. Snapshots only.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/daily_build_pricing.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/daily_build_pricing.py (k11-alpha; systemd timers).

"""

import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [pricing] %(message)s")
LOG = logging.getLogger("pricing")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"

SERIOUS = ("planning", "components_priced", "researching", "parts_ordered")


def psql(sql, write=False):
    cmd = ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return [] if not write else False
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return (s or "").replace("'", "''")


def main():
    statuses = ",".join(f"'{s}'" for s in SERIOUS)
    builds = psql(
        f"SELECT id, name FROM dealsdesk.builds WHERE status IN ({statuses}) ORDER BY id"
    )
    if not builds:
        LOG.error("no serious builds found — aborting")
        return 1
    done, failed = 0, 0
    for b in builds:
        build_id = b[0]
        agg = psql(
            f"""SELECT count(*),
                       count(price_ea),
                       count(*) - count(price_ea),
                       COALESCE(SUM(price_ea * quantity), 0),
                       COALESCE(SUM(COALESCE(last_seen_price, price_ea) * quantity), 0)
                FROM dealsdesk.build_items WHERE build_id = {int(build_id)}"""
        )
        if not agg:
            failed += 1
            continue
        total_items, priced, unpriced, t_priced, t_market = agg[0]
        ok = psql(
            f"""INSERT INTO dealsdesk.build_price_daily
                   (build_id, snapshot_date, total_priced, total_market,
                    priced_items, unpriced_items, total_items)
                VALUES ({int(build_id)}, CURRENT_DATE,
                        {float(t_priced)}, {float(t_market)},
                        {int(priced)}, {int(unpriced)}, {int(total_items)})
                ON CONFLICT (build_id, snapshot_date) DO UPDATE SET
                    total_priced = EXCLUDED.total_priced,
                    total_market = EXCLUDED.total_market,
                    priced_items = EXCLUDED.priced_items,
                    unpriced_items = EXCLUDED.unpriced_items,
                    total_items = EXCLUDED.total_items""",
            write=True,
        )
        if ok:
            done += 1
        else:
            failed += 1
    LOG.info("snapshots written: %d builds ok, %d failed", done, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
