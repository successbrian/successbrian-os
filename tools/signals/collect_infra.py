#!/usr/bin/env python3
"""collect_infra.py — slow-cadence infra signals (hourly).

PURPOSE: The "capacity planning" signals: load, memory, swap, disk. These move
  over hours/days, not minutes — hourly sampling is plenty.
  Brian 2026-10-17: "some things don't need to run every 15 minutes."
  Fast signals (cpu temp, runaway queries) live in collect_watchdog.py (15 min).
WHY: Split for cadence optimization; was 15-min for everything.
CALLED BY: cron 13 * * * * (hourly, staggered clear of derive + need_reader).
NOTES: stdlib + psycopg2 only, zero AI tokens. Upserts by signal_key —
  the table holds the latest observation per signal.
"""
import json
import shutil

import psycopg2

SIGNALS = []


def collect():
    # Load averages — capacity signal, hourly is plenty
    try:
        with open("/proc/loadavg") as f:
            l1, l5, l15 = f.read().split()[:3]
        SIGNALS.append(("k11.load_1m", "infra", float(l1), None, {"load_5m": l5, "load_15m": l15}))
        SIGNALS.append(("k11.load_15m", "infra", float(l15), None, {}))
    except Exception:
        pass

    # Memory / swap (GB) — moves over hours
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

    # Disk used % (root) — fills over days
    try:
        du = shutil.disk_usage("/")
        SIGNALS.append(("k11.disk_used_pct", "infra",
                        round(du.used / du.total * 100, 1), None, {}))
    except Exception:
        pass


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
