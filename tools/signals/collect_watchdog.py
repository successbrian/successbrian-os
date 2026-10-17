#!/usr/bin/env python3
"""collect_watchdog.py — fast-cadence watch signals (every 15 min).

PURPOSE: The "something is wrong RIGHT NOW" signals: CPU thermal and DB
  runaway queries. These can spike in minutes, so they stay on the 15-min
  cadence. Everything slower (load, mem, swap, disk) moved to collect_infra.py
  (hourly) — Brian 2026-10-17: "some things don't need to run every 15 minutes."
WHY: Split from collect_infra.py for cadence optimization.
CALLED BY: cron 3,18,33,48 * * * * (same staggered slots the old collector used).
NOTES: stdlib + psycopg2 only, zero AI tokens. Upserts by signal_key.
"""
import json
import re
import subprocess

import psycopg2


def sample_cmd(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ""


def store(signals):
    conn = psycopg2.connect(dbname="ecosystem_central", user="successbrian")
    cur = conn.cursor()
    for key, cls, vnum, vtext, meta in signals:
        cur.execute(
            """INSERT INTO successbrian_os.ecosystem_signals
                   (signal_key, signal_class, source, value_num, value_text, meta, observed_at)
               VALUES (%s, %s, 'collect_watchdog', %s, %s, %s, now())
               ON CONFLICT (signal_key) DO UPDATE SET
                   value_num = EXCLUDED.value_num,
                   value_text = EXCLUDED.value_text,
                   meta = EXCLUDED.meta,
                   observed_at = now()""",
            (key, cls, vnum, vtext, json.dumps(meta)))
    conn.commit()
    conn.close()
    print(f"stored {len(signals)} watchdog signals")


def main():
    signals = []

    # CPU temp (AMD Tctl) — thermal spikes matter in minutes
    out = sample_cmd(["sensors"])
    m = re.search(r"Tctl:\s*\+([\d.]+)", out)
    if m:
        signals.append(("k11.cpu_temp_c", "infra", float(m.group(1)), None, {}))

    # Longest active query (minutes) — runaway detector's raw feed
    try:
        conn = psycopg2.connect(dbname="ecosystem_central", user="successbrian")
        cur = conn.cursor()
        cur.execute(
            """SELECT COALESCE(EXTRACT(EPOCH FROM max(now() - query_start))/60, 0)
               FROM pg_stat_activity
               WHERE state = 'active' AND pid <> pg_backend_pid()
                 AND query NOT LIKE '%pg_stat_activity%'""")
        longest = float(cur.fetchone()[0] or 0)
        signals.append(("db.longest_query_min", "infra", round(longest, 1), None, {}))
        conn.close()
    except Exception as e:
        signals.append(("db.longest_query_min", "infra", None,
                        f"collector db error: {e}"[:200], {}))

    store(signals)


if __name__ == "__main__":
    main()
