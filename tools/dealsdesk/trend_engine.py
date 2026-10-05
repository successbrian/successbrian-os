#!/usr/bin/env python3
"""trend_engine.py — price-trend signals + expected-drop waker.

PURPOSE: (1) For each component with >=5 observations in the last 60 days,
         compare the latest price against the 30-day median baseline and
         emit 'drop' (<= -10%) or 'spike' (>= +15%) signals into
         dealsdesk.deal_signals. (2) Wake builds whose buy_timing is
         'wait_for_drop' when a buy_trigger is satisfied: explicit
         trigger_price met by latest market price, or a >=15% trend drop
         when trigger_price is NULL.
WHY:     Brian wants percentage-change detection against a smart baseline,
         not fixed targets — and purchase timing that waits for expected
         drops (e.g. 2nd/3rd EPYC builds on 7402/SP3 pricing) then wakes
         the build when the drop arrives.
CALLED BY: systemd timer trend-engine.timer (daily 06:00 America/Chicago)
           as successbrian; or manually.
NOTES:   Never auto-buys: it flips buy_timing to 'buy_now', appends the
         reason to timing_rationale, posts to the outbox, and marks the
         trigger fired. Brian still makes every purchase decision.
         Signals dedupe: no second unconsumed identical signal
         (same key+type) within 7 days. --dry-run prints what it would do.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/trend_engine.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/trend_engine.py (k11-alpha; systemd timers).

"""

import argparse
import logging
import subprocess
import sys

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [trend_engine] %(message)s")
LOG = logging.getLogger("trend_engine")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"

DROP_PCT = -10.0    # latest <= 10% below 30d median -> 'drop'
SPIKE_PCT = 15.0    # latest >= 15% above 30d median -> 'spike'
MIN_OBS = 5         # need at least this many obs in last 60 days


def esc(s):
    return s.replace("'", "''")


def psql(sql, write=False):
    cmd = ["psql", "-U", DB_USER, "-d", DB_NAME]
    if write:
        cmd += ["-v", "ON_ERROR_STOP=1", "-c", sql]
    else:
        cmd += ["-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return None if write else []
    return True if write else [
        l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def trend_stats():
    """Latest price + 30d median baseline + 60d observation count per key."""
    return psql("""
        WITH m30 AS (
          SELECT component_key,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) AS med30
          FROM dealsdesk.market_price_history
          WHERE observed_at >= NOW() - INTERVAL '30 days'
          GROUP BY component_key
        ),
        c60 AS (
          SELECT component_key, COUNT(*) AS n60
          FROM dealsdesk.market_price_history
          WHERE observed_at >= NOW() - INTERVAL '60 days'
          GROUP BY component_key
        ),
        latest AS (
          SELECT DISTINCT ON (component_key) component_key, price
          FROM dealsdesk.market_price_history
          ORDER BY component_key, observed_at DESC
        )
        SELECT l.component_key, l.price, m.med30, c.n60
        FROM latest l
        JOIN m30 m USING (component_key)
        JOIN c60 c USING (component_key)
    """) or []


def open_signal(key, sig_type):
    rows = psql(f"""SELECT 1 FROM dealsdesk.deal_signals
                    WHERE component_key = '{esc(key)}'
                      AND signal_type = '{sig_type}'
                      AND NOT consumed
                      AND observed_at >= NOW() - INTERVAL '7 days' LIMIT 1""")
    return bool(rows)


def emit_signals(dry_run):
    made = 0
    for r in trend_stats():
        r = (r + [""] * 4)[:4]
        key, latest, med, n = r[0], float(r[1]), float(r[2]), int(r[3])
        if n < MIN_OBS or not med:
            continue
        pct = (latest - med) / med * 100
        sig = None
        if pct <= DROP_PCT:
            sig = "drop"
        elif pct >= SPIKE_PCT:
            sig = "spike"
        if not sig or open_signal(key, sig):
            continue
        note = (f"latest ${latest:.2f} vs 30d median ${med:.2f} "
                f"({pct:+.1f}%) over {n} observations")
        LOG.info("%s: %s %s", key, sig.upper(), note)
        if dry_run:
            continue
        ok = psql(f"""INSERT INTO dealsdesk.deal_signals
                        (component_key, signal_type, pct_vs_trend, price, note)
                      VALUES ('{esc(key)}', '{sig}', {pct:.2f}, {latest},
                              '{esc(note)}')""", write=True)
        made += 1 if ok else 0
    return made


def check_triggers(dry_run):
    """Wake wait_for_drop builds whose triggers are satisfied."""
    woke = 0
    rows = psql("""
        SELECT t.id, t.build_id, b.name, t.component_key, t.trigger_price,
               mp.price AS latest, t.note
        FROM dealsdesk.buy_triggers t
        JOIN dealsdesk.builds b ON b.id = t.build_id
        LEFT JOIN dealsdesk.market_prices mp
          ON mp.component_key = t.component_key
        WHERE NOT t.fired AND b.buy_timing = 'wait_for_drop'
    """) or []
    for r in rows:
        r = (r + [None] * 7)[:7]
        tid, build_id, bname, key, tprice, latest, note = r
        tprice = float(tprice) if tprice not in (None, "") else None
        latest = float(latest) if latest not in (None, "") else None
        reason = None
        if tprice is not None and latest is not None and latest <= tprice:
            reason = (f"trigger met: {key} latest ${latest:.2f} "
                      f"<= trigger ${tprice:.2f}")
        elif tprice is None:
            s = psql(f"""SELECT pct_vs_trend FROM dealsdesk.deal_signals
                         WHERE component_key = '{esc(key)}'
                           AND signal_type = 'drop' AND NOT consumed
                         ORDER BY observed_at DESC LIMIT 1""")
            if s and float(s[0][0]) <= -15.0:
                reason = (f"trend drop {float(s[0][0]):.1f}% on {key} "
                          f"(no explicit trigger price)")
        if not reason:
            continue
        msg = (f"BUY TIMING WAKE — build '{bname}': {reason}. "
               f"Note: {note or 'n/a'}. Brian decides; nothing auto-buys.")
        LOG.info(msg)
        if dry_run:
            continue
        psql(f"""UPDATE dealsdesk.builds
                    SET buy_timing = 'buy_now',
                        timing_rationale = COALESCE(timing_rationale || ' | ', '')
                                           || '{esc(reason)}',
                        updated_at = NOW()
                  WHERE id = {build_id}""", write=True)
        psql(f"UPDATE dealsdesk.buy_triggers SET fired = TRUE WHERE id = {tid}",
             write=True)
        psql(f"""INSERT INTO public.successbrian_outbox (agent, message_text, priority)
                  VALUES ('dealsdesk', '{esc(msg)}', 3)""", write=True)
        woke += 1
    return woke


def main():
    ap = argparse.ArgumentParser(description="Trend signals + drop waker")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    signals = emit_signals(a.dry_run)
    woke = check_triggers(a.dry_run)
    LOG.info("done: %d signal(s), %d build(s) woken%s",
             signals, woke, " (dry run)" if a.dry_run else "")


if __name__ == "__main__":
    main()
