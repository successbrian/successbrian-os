#!/usr/bin/env python3
"""feed_watchdog.py — price-feed freshness watchdog.

PURPOSE: Detect when the price data feeding DealsDesk goes stale and raise
         at most one alert per day per feed, so a dead feed never fails
         silent again.
WHY:     On 2026-10-01 the alert loop ran fine while public.price_history
         sat 9 days stale (eBay refresh 0/56 failing) — and nobody was told.
         A watchdog on the feed itself closes that hole.
CALLED BY: systemd timer feed-watchdog.timer (06:30, 18:30 daily).
NOTES:   Checks public.price_history (checked_at) and, only if the table
         exists, dealsdesk.market_price_history (observed_at). Stale means
         the newest row is older than STALE_AFTER_H (36h). Dedupes through
         dealsdesk.watchdog_state: one outbox post per check per 24h max.
         --dry-run prints what it would do without posting or writing state.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/feed_watchdog.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/feed_watchdog.py (k11-alpha; systemd timers).

"""

import argparse
import logging
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [feed_watchdog] %(message)s")
LOG = logging.getLogger("feed_watchdog")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"
STALE_AFTER_H = 36
ALERT_COOLDOWN_H = 24
LOCAL_TZ = ZoneInfo("America/Chicago")  # server local; naive timestamps are server time


def parse_ts(s):
    """Parse a DB timestamp; naive values are assumed server-local."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt


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


def ensure_state():
    # Tables are provisioned via the altair role (successbrian lacks schema
    # CREATE). Only attempt DDL when the table is genuinely missing.
    rows = psql("SELECT to_regclass('dealsdesk.watchdog_state')")
    if not rows or not rows[0][0]:
        LOG.warning("dealsdesk.watchdog_state missing — attempting create (needs privileges)")
        psql("""CREATE TABLE IF NOT EXISTS dealsdesk.watchdog_state (
                check_name TEXT PRIMARY KEY,
                last_alert_at TIMESTAMPTZ,
                last_ok_at TIMESTAMPTZ)""", write=True)
def table_exists(fqtn):
    rows = psql(f"SELECT to_regclass('{fqtn}')")
    return bool(rows and rows[0][0] not in ("", None))


def check_feed(check_name, fqtn, ts_col, dry_run):
    """Returns True if fresh, False if stale (and alert posted or due)."""
    if not table_exists(fqtn):
        LOG.warning("%s: table %s missing — treating as stale", check_name, fqtn)
        newest = None
    else:
        rows = psql(f"SELECT MAX({ts_col}) FROM {fqtn}")
        newest = rows[0][0] if rows and rows[0][0] else None
    now = datetime.now(timezone.utc)
    if newest:
        age_h = (now - parse_ts(newest)).total_seconds() / 3600
    else:
        age_h = float("inf")
    fresh = age_h <= STALE_AFTER_H
    if fresh:
        LOG.info("%s: fresh (newest %s, %.1fh ago)", check_name, newest, age_h)
        if not dry_run:
            psql(f"""INSERT INTO dealsdesk.watchdog_state (check_name, last_ok_at)
                     VALUES ('{check_name}', NOW())
                     ON CONFLICT (check_name) DO UPDATE
                     SET last_ok_at = NOW()""", write=True)
        return True
    # stale — dedupe: one alert per 24h
    rows = psql(f"SELECT last_alert_at FROM dealsdesk.watchdog_state "
                f"WHERE check_name = '{check_name}'")
    last_alert = rows[0][0] if rows and rows[0][0] else None
    if last_alert:
        since_h = (now - parse_ts(last_alert)).total_seconds() / 3600
    else:
        since_h = float("inf")
    age_txt = "never" if age_h == float("inf") else f"{age_h:.0f}h ago (newest {newest})"
    if since_h < ALERT_COOLDOWN_H:
        LOG.info("%s: stale (%s) but alerted %.1fh ago — suppressed",
                 check_name, age_txt, since_h)
        return False
    msg = (f"PRICE FEED STALE: {check_name} newest data {age_txt} "
           f"(threshold {STALE_AFTER_H}h). DealsDesk alerts are starved until "
           f"the feed is repaired. Brian decides; nothing auto-buys.")
    LOG.warning("%s: STALE — %s", check_name, msg)
    if dry_run:
        print(f"[dry-run] would post: {msg}")
        return False
    psql(f"""INSERT INTO public.successbrian_outbox (agent, message_text, priority)
             VALUES ('dealsdesk', '{esc(msg)}', 1)""", write=True)
    psql(f"""INSERT INTO dealsdesk.watchdog_state (check_name, last_alert_at)
             VALUES ('{check_name}', NOW())
             ON CONFLICT (check_name) DO UPDATE
             SET last_alert_at = NOW()""", write=True)
    return False


def main():
    ap = argparse.ArgumentParser(description="Watch price-feed freshness")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only; no outbox posts, no state writes")
    a = ap.parse_args()
    ensure_state()
    check_feed("public.price_history", "public.price_history",
               "checked_at", a.dry_run)
    check_feed("market_price_history", "dealsdesk.market_price_history",
               "observed_at", a.dry_run)
    LOG.info("done (dry_run=%s)", a.dry_run)


if __name__ == "__main__":
    main()
