#!/usr/bin/env python3
"""kalshi_watch.py — Kalshi prediction-dataset plumbing (alpha-native).

Migrated 2026-11-09 from the Muse-side crons kalshi-weather-dataset-
daily, kalshi-weather-midday-snapshot and kalshi-earnings-mentions-
weekly at Brian's order (pure scrape/check -> ecosystem). The dataset
collectors themselves (scripts/weather_collect.py,
scripts/earnings_mentions_collect.py — keyless, deterministic, no LLM)
moved unchanged from the goal workspace on the Muse VM to
./prediction-datasets/ beside this wrapper, seeded with their full
CSV history, so the datasets keep being fed identically.

This wrapper only: runs the collectors, verifies rows landed, checks
the morning divergence rule (model-median forecast vs the market's
favorite bracket, Minneapolis/Chicago), and files an Intel Bridge
capture ONLY on failure or a fired reporting rule — routine success
is silent, exactly as the Muse jobs were. Data collection only:
no trading, no accounts, no orders, ever.

Usage:
    python3 kalshi_watch.py morning    (settle + collect + divergence)
    python3 kalshi_watch.py midday     (collect)
    python3 kalshi_watch.py earnings   (earnings_mentions_collect)
Cron (alpha, America/Chicago): 41 7 * * * morning; 41 12 * * * midday;
41 8 * * 1 earnings.
"""
import csv
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

HERE = Path(__file__).resolve().parent
DS = HERE / "prediction-datasets"
SCRIPTS = DS / "scripts"
CT = timezone(timedelta(hours=-6))


def file_capture(title, context, raw):
    conn = psycopg2.connect(dbname="ecosystem_central",
                            user="successbrian",
                            cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("INSERT INTO atlas.scattered_captures (title, raw_text, "
                "context) VALUES (%s, %s, %s) RETURNING id",
                (title, raw, context))
    cid = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return cid


def run_script(name, *args):
    p = subprocess.run([sys.executable, str(SCRIPTS / name), *args],
                       capture_output=True, text=True, timeout=600)
    return p


def count_rows(path):
    if not path.exists():
        return 0
    with open(path) as f:
        return sum(1 for _ in f) - 1


def fail(mode, what, detail):
    cid = file_capture(
        "Kalshi dataset %s FAILED %s" % (mode,
                                         datetime.now(CT).date()),
        "TradesDesk kalshi_watch.py on alpha: %s failed — Spencer to "
        "surface. Data collection only." % what,
        detail[:1500])
    print("FAILED (%s): %s — capture %s" % (mode, what, cid))
    return 1


def divergence_check():
    """Model-median vs market favorite bracket for MSP/CHI, latest
    snapshot, today+tomorrow dates. Returns list of (city, date,
    median, favorite_center, diff) with diff >= 5."""
    path = DS / "weather" / "weather_log.csv"
    rows = list(csv.DictReader(open(path)))
    if not rows:
        return []
    latest = max(r["snapshot_utc"] for r in rows)
    snap = [r for r in rows if r["snapshot_utc"] == latest]
    out = []
    for city in ("Minneapolis", "Chicago"):
        dates = sorted({r["date"] for r in snap if r["city"] == city})
        for d in dates:
            rs = [r for r in snap if r["city"] == city and r["date"] == d]
            if not rs:
                continue
            fav = max(rs, key=lambda r: float(r["yes_bid"] or 0))
            try:
                center = float(fav["ticker"].rsplit("-B", 1)[1])
                median = float(fav["fc_median"])
            except Exception:
                continue
            diff = abs(median - center)
            if diff >= 5:
                out.append((city, d, median, center, diff))
    return out


def morning():
    wl, ac = DS / "weather" / "weather_log.csv", DS / "weather" / "actuals.csv"
    before_w, before_a = count_rows(wl), count_rows(ac)
    p = run_script("weather_collect.py", "settle")
    if p.returncode != 0:
        p2 = run_script("weather_collect.py", "settle")
        if p2.returncode != 0:
            return fail("morning", "weather_collect.py settle (twice)",
                        p2.stdout + p2.stderr)
    p = run_script("weather_collect.py", "collect")
    if p.returncode != 0:
        p2 = run_script("weather_collect.py", "collect")
        if p2.returncode != 0:
            return fail("morning", "weather_collect.py collect (twice)",
                        p2.stdout + p2.stderr)
    new_w, new_a = count_rows(wl), count_rows(ac)
    if new_w == before_w:
        return fail("morning", "weather collect returned no new rows",
                    "weather_log.csv unchanged at %d rows" % new_w)
    divs = divergence_check()
    print("morning ok: weather_log %d->%d rows, actuals %d->%d rows, "
          "divergences: %d" % (before_w, new_w, before_a, new_a,
                               len(divs)))
    for city, d, median, center, diff in divs:
        cid = file_capture(
            "Kalshi weather divergence: %s %s — models %.1f vs market "
            "%.1f" % (city, d, median, center),
            "TradesDesk kalshi_watch.py morning pass (alpha). Reporting "
            "rule from the dataset spec: model-median forecast and the "
            "market's favorite bracket differ by 5+ degrees for "
            "Minneapolis or Chicago. Tomorrow's actual will score it. "
            "Data collection only — not a trade signal to act on.",
            "%s %s: model-median forecast %.1fF vs market favorite "
            "bracket center %.1fF (difference %.1f). Source: Kalshi "
            "brackets + ECMWF/GFS/ICON via weather_collect.py."
            % (city, d, median, center, diff))
        print("divergence capture %s: %s %s %.1f vs %.1f"
              % (cid, city, d, median, center))
    return 0


def midday():
    wl = DS / "weather" / "weather_log.csv"
    before = count_rows(wl)
    p = run_script("weather_collect.py", "collect")
    if p.returncode != 0:
        return fail("midday", "weather_collect.py collect",
                    p.stdout + p.stderr)
    after = count_rows(wl)
    if after == before:
        return fail("midday", "weather collect returned zero new rows",
                    "weather_log.csv unchanged at %d rows" % after)
    print("midday ok: weather_log %d->%d rows" % (before, after))
    return 0


def earnings():
    p = run_script("earnings_mentions_collect.py")
    if p.returncode != 0:
        return fail("earnings", "earnings_mentions_collect.py",
                    p.stdout + p.stderr)
    snap = DS / "earnings_mentions" / "live_snapshot.csv"
    print("earnings ok: live_snapshot.csv %d rows, rebuilt %s"
          % (count_rows(snap), datetime.now(CT).isoformat()))
    print((p.stdout or "").strip().splitlines()[-1] if p.stdout else "")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"morning": morning, "midday": midday,
          "earnings": earnings}.get(mode)
    if fn is None:
        print(__doc__)
        sys.exit(2)
    sys.exit(fn())
