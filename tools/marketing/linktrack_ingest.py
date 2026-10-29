#!/usr/bin/env python3
"""Ingest SuccessBrian OS tracked-link clicks into the database.

Chain (built 2026-10-28/29): campaignsdesk.outbound_links holds the
slugs; gamma (successbrianvps.com) nginx 302s /v/<slug> and writes a
JSON line per hit to /var/log/nginx/sbos-clicks.log (format
sbos_clicks). This ingester reads that log over the fleet SSH route
and inserts new clicks into campaignsdesk.outbound_clicks, deduped
on raw_hash (UNIQUE). Without it the clicks sit in a log file nobody
monitors - the gap found 2026-10-29 (last ingestion was the manual
2026-10-28 run, source gamma-nginx-log).

Run: python3 linktrack_ingest.py [--dry-run]
Cron (alpha): every 10 minutes.
"""
import hashlib
import json
import subprocess
import sys

GAMMA = "root@100.118.196.66"
LOGS = ["/var/log/nginx/sbos-clicks.log", "/var/log/nginx/sbos-clicks.log.1"]


def fetch_lines():
    out = []
    for path in LOGS:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=10", GAMMA,
                            "cat %s 2>/dev/null" % path],
                           capture_output=True, text=True, timeout=60)
        out += [ln for ln in r.stdout.split("\n") if ln.strip()]
    return out


def ua_class(ua):
    u = ua or ""
    if any(k in u for k in ("Mobile", "Android", "iPhone", "iPad")):
        return "mobile"
    if "Mozilla" in u or "curl" in u or "python" in u:
        return "desktop" if "Mozilla" in u else "other"
    return "other"


def main():
    dry = "--dry-run" in sys.argv
    sys.path.insert(0, "/home/successbrian/successbrian-os/tools/pm")
    import pm_core
    conn = pm_core.conn()
    known = set()
    with conn.cursor() as cur:
        cur.execute("select slug from campaignsdesk.outbound_links")
        known = {r[0] for r in cur.fetchall()}
    rows, skipped = [], 0
    for line in fetch_lines():
        try:
            rec = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        uri = rec.get("uri", "")
        if rec.get("s") != 302 or not uri.startswith("/v/"):
            skipped += 1
            continue
        slug = uri[len("/v/"):].split("?")[0]
        if slug not in known:
            skipped += 1
            continue
        rows.append((slug, rec.get("t"), rec.get("ref") or None,
                     ua_class(rec.get("ua")),
                     hashlib.sha256(line.encode()).hexdigest(),
                     "gamma-sbos-clicks-log"))
    inserted = 0
    if rows and not dry:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    "insert into campaignsdesk.outbound_clicks "
                    "(slug, clicked_at, referrer, ua_class, raw_hash, source) "
                    "values (%s, %s, %s, %s, %s, %s) "
                    "on conflict (raw_hash) do nothing", r)
                inserted += cur.rowcount
        conn.commit()
    print("linktrack_ingest: %d candidate clicks, %d new, %d skipped%s"
          % (len(rows), inserted, skipped, " (dry-run)" if dry else ""))


if __name__ == "__main__":
    main()
