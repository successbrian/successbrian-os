#!/usr/bin/env python3
"""collect_infra.py — sample k11-alpha infra signals into ecosystem_signals.

PURPOSE: Turn tonight's manual sweep into a standing feed: cpu temp, load,
  memory, swap, disk, and longest-running DB query.
WHY: Brian 2026-10-17 — the ecosystem's own strain signals must feed the
  screams, so needs get detected instead of discovered during outages.
CALLED BY: cron every 15 min (staggered off the derivation runner).
NOTES: stdlib + psycopg2 only, zero AI tokens. Upserts by signal_key —
  the table holds the latest observation per signal.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import psycopg2

SIGNALS = []


def sample_cmd(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ""


def collect():
    # CPU temp (AMD Tctl)
    out = sample_cmd(["sensors"])
    m = re.search(r"Tctl:\s*\+([\d.]+)", out)
    if m:
        SIGNALS.append(("k11.cpu_temp_c", "infra", float(m.group(1)), None, {}))

    # Load averages
    try:
        with open("/proc/loadavg") as f:
            l1, l5, l15 = f.read().split()[:3]
        SIGNALS.append(("k11.load_1m", "infra", float(l1), None, {"load_5m": l5, "load_15m": l15}))
        SIGNALS.append(("k11.load_15m", "infra", float(l15), None, {}))
    except Exception:
        pass

    # Memory / swap (GB)
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")
                mem[k.strip()] = int(v.split()[0]) // 1024 // 1024
        SIGNALS.append(("k11.mem_available_gb", "infra", float(mem.get("MemAvailable", 0)), None, {}))
        SIGNALS.append(("k11.swap_used_gb", "infra",
                        float(mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)), None, {}))
    except Exception:
        pass

    # Disk used % (root)
    try:
        du = shutil.disk_usage("/")
        SIGNALS.append(("k11.disk_used_pct", "infra",
                        round(du.used / du.total * 100, 1), None, {}))
    except Exception:
        pass

    # Longest active query (minutes) — the runaway detector's raw feed
    try:
        conn = psycopg2.connect(dbname="ecosystem_central", user="successbrian")
        cur = conn.cursor()
        cur.execute(
            """SELECT COALESCE(EXTRACT(EPOCH FROM max(now() - query_start))/60, 0)
               FROM pg_stat_activity
               WHERE state = 'active' AND pid <> pg_backend_pid()
                 AND query NOT LIKE '%pg_stat_activity%'""")
        longest = float(cur.fetchone()[0] or 0)
        SIGNALS.append(("db.longest_query_min", "infra", round(longest, 1), None, {}))
        conn.close()
    except Exception as e:
        SIGNALS.append(("db.longest_query_min", "infra", None,
                        f"collector db error: {e}"[:200], {}))


def store():
    conn = psycopg2.connect(dbname="ecosystem_central", user="successbrian")
    cur = conn.cursor()
    for key, cls, vnum, vtext, meta in SIGNALS:
        cur.execute(
            """INSERT INTO successbrian_os.ecosystem_signals
                   (signal_key, signal_class, source, value_num, value_text, meta, observed_at)
               VALUES (%s, %s, 'collect_infra', %s, %s, %s, now())
               ON CONFLICT (signal_key) DO UPDATE SET
                   value_num = EXCLUDED.value_num,
                   value_text = EXCLUDED.value_text,
                   meta = EXCLUDED.meta,
                   observed_at = now()""",
            (key, cls, vnum, vtext, json.dumps(meta)))
    conn.commit()
    conn.close()
    print(f"stored {len(SIGNALS)} infra signals")


if __name__ == "__main__":
    collect()
    store()
