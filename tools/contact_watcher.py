#!/usr/bin/env python3
"""
PURPOSE:
    Poll the Outlook inbox, flag new senders, track repeat senders —
    Brian's new-contact alert feed.

WHY:
    Unknown senders to Brian's inbox are opportunities (leads, recruiters)
    or noise (promos). Nobody watches the inbox for him while he's
    heads-down at CREW2, so this watcher keeps a baseline of known
    contacts and prints JSON alerts for anything new or repeating.

CALLED BY:
    - contact-alert cron (activates when Brian says "start contact alerts"
      from WhatsApp; alert channel = WhatsApp)
    - manual runs for spot checks

NOTES:
    Moved 2026-09-28 from ~/workspace/contacts/watcher.py (night-shift
    consolidation). DATA STAYS in ~/workspace/contacts/ (baseline.db,
    tracking.db) — only the code moved. Reads email, writes only its own
    tracking.db; never deletes anything. Skips own addresses + noreply/
    postmaster patterns.

Reads:
  ~/workspace/contacts/baseline.db   known contacts (email -> name/company/source)
Writes:
  ~/workspace/contacts/tracking.db   sender stats + watermark
Prints JSON: {"alerts": [...], "summary": {...}}
"""
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

BASE = "/home/hatch/workspace/contacts"
BASELINE_DB = f"{BASE}/baseline.db"
TRACKING_DB = f"{BASE}/tracking.db"

OWN_ADDRESSES = {"brian.lathe@outlook.com", "brian.lathe@crew2.com"}
AUTO_PATTERNS = ("noreply", "no-reply", "donotreply", "postmaster",
                 "mailer-daemon", "bounce")


def parse_sender(from_field):
    """'Name <email>' -> (name, email); 'email' -> (None, email)."""
    if not from_field:
        return None, None
    m = re.search(r"<([^>]+)>", from_field)
    if m:
        email = m.group(1).strip()
        name = from_field[:m.start()].strip().strip('"') or None
    elif "@" in from_field:
        email, name = from_field.strip(), None
    else:
        return None, None
    return name, email.lower()


def is_automated(email):
    local = email.split("@")[0]
    return any(p in local for p in AUTO_PATTERNS)


def outlook_recent(since_iso):
    r = subprocess.run(["outlook-mail", "list", "--page-size", "50"],
                       capture_output=True, text=True, timeout=90)
    d = json.loads(r.stdout)
    if not d.get("ok"):
        raise RuntimeError(f"outlook-mail list failed: {r.stdout[:300]}")
    out = []
    for m in d.get("messages", []):
        ts = m.get("date")  # plain ISO string, e.g. "2026-09-26T22:54:05Z"
        if ts and ts >= since_iso:
            out.append(m)
    return out


def main():
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    tdb = sqlite3.connect(TRACKING_DB)
    tdb.execute("""CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)""")
    tdb.execute("""CREATE TABLE IF NOT EXISTS sender_stats (
        email TEXT PRIMARY KEY, name TEXT, company TEXT,
        first_seen TEXT, last_seen TEXT, count INTEGER DEFAULT 0,
        in_baseline INTEGER DEFAULT 0)""")
    row = tdb.execute("SELECT v FROM meta WHERE k='watermark'").fetchone()
    if row:
        since = row[0]
    else:
        since = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tdb.execute("INSERT INTO meta VALUES ('watermark', ?)", (since,))

    bdb = sqlite3.connect(BASELINE_DB)

    messages = outlook_recent(since)
    seen_this_run = {}
    alerts = []

    for m in messages:
        name, email = parse_sender(m.get("from"))
        if not email or email in OWN_ADDRESSES or is_automated(email):
            continue
        key = email
        if key in seen_this_run:
            seen_this_run[key]["count"] += 1
            continue
        seen_this_run[key] = {"name": name,
                              "subject": m.get("subject"),
                              "received": (m.get("message_received_at") or {}).get("user_local")
                                          or m.get("date"),
                              "count": 1}

    for email, info in seen_this_run.items():
        known = bdb.execute(
            "SELECT name, company, source FROM known_contacts WHERE email=?",
            (email,)).fetchone()
        prev = tdb.execute(
            "SELECT count, in_baseline FROM sender_stats WHERE email=?",
            (email,)).fetchone()

        if known:
            kname, company, _ = known
            in_baseline, is_new = 1, False
        else:
            # domain-level known senders (e.g. ISP, employer)
            domain = email.split("@")[1] if "@" in email else None
            dknown = bdb.execute(
                "SELECT company FROM known_domains WHERE domain=?",
                (domain,)).fetchone() if domain else None
            if dknown:
                kname, company, _ = info["name"], dknown[0], "known_domain"
                in_baseline, is_new = 1, False
            else:
                kname, company, _ = info["name"], None, None
                in_baseline, is_new = 0, prev is None

        # domain hint for unknown senders ("people and companies")
        domain = email.split("@")[1] if "@" in email else None
        if not company and domain and not any(
                domain.endswith(d) for d in
                ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
                 "aol.com", "icloud.com", "proton.me", "protonmail.com")):
            company = domain

        first = stamp if prev is None else None
        tdb.execute("""INSERT INTO sender_stats
                       (email, name, company, first_seen, last_seen, count, in_baseline)
                       VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(email) DO UPDATE SET
                         last_seen=excluded.last_seen,
                         count=count+excluded.count,
                         name=COALESCE(sender_stats.name, excluded.name),
                         company=COALESCE(sender_stats.company, excluded.company)""",
                    (email, kname or info["name"], company,
                     first or tdb.execute(
                         "SELECT first_seen FROM sender_stats WHERE email=?",
                         (email,)).fetchone()[0],
                     stamp, info["count"], in_baseline))

        if is_new:
            alerts.append({"email": email,
                           "name": kname or info["name"],
                           "company": company,
                           "subject": info["subject"],
                           "received": info["received"]})

    tdb.execute("UPDATE meta SET v=? WHERE k='watermark'", (stamp,))
    tdb.commit()

    repeaters = tdb.execute(
        "SELECT COUNT(*) FROM sender_stats WHERE count > 1").fetchone()[0]
    total = tdb.execute("SELECT COUNT(*) FROM sender_stats").fetchone()[0]

    print(json.dumps({
        "alerts": alerts,
        "summary": {
            "messages_checked": len(messages),
            "unique_senders": len(seen_this_run),
            "new_senders": len(alerts),
            "tracked_senders_total": total,
            "repeat_senders": repeaters,
            "window_since": since,
        }}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        sys.exit(1)
