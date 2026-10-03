#!/usr/bin/env python3
"""Migrate lead_scraper.oliabo_leads -> people.people (people_unified).

PURPOSE:
    Move the 1.09M-row scraped Oliabo lead pool out of the scraper-local table
    (ecosystem_central.lead_scraper.oliabo_leads) into the unified people store
    (people_unified.people.people), with mandatory dedup checking. The target
    holds 211M+ people; blind inserts are not an option.

WHY:
    Brian 2026-10-02: the oliabo_leads table was slated for deletion, but the
    data must be preserved in the unified store instead. Dedup checking is a
    hard requirement (Brian 2026-10-02) — every row is checked against the
    target before insert, per batch.

CALLED BY:
    An agent session (Spencer) or cron, run ON k11 (needs local Postgres
    sockets for both databases). Dry-run is the default; --run performs
    the migration. Resume-safe: reruns skip already-migrated rows via the
    same dedup checks.

NOTES:
    - CANONICAL: successbrian-os/tools/people_migrate/
    - Source: ecosystem_central.lead_scraper.oliabo_leads
    - Target: people_unified.people.people (+ people.phones for phone-only rows)
    - Dedup keys, checked per batch BEFORE insert:
        1. email: lower(primary_email) IN batch
           (uses idx_people_lower_primary_email)
        2. phone: digits-only phone IN people.phones
           (uses idx_phones_phone_digits; created CONCURRENTLY if missing)
    - Rows with neither email nor phone are SKIPPED here (reason=msv_queue):
      per Brian 2026-10-02 they go through the MSV scraper first.
    - Tags default to ['oliabo']; segment tags via --extra-tags
      (e.g. oliabo:medical, oliabo:influencer — convention pending Brian).
    - Name split is naive (first token -> first_name, rest -> last_name);
      matches the granularity of the source data. Flagged, not fixed.
    - Credentials: none in this file. Uses local peer auth via unix socket.
"""

import argparse
import json
import os
import re
import sys
import uuid

import psycopg2
import psycopg2.extras

SOCK = "/var/run/postgresql"
SRC = {"host": SOCK, "dbname": "ecosystem_central"}
TGT = {"host": SOCK, "dbname": "people_unified"}

BATCH = 5000
MIGRATION_TAG = "oliabo_migration_20261002"


def _conn(params):
    return psycopg2.connect(host=params["host"], dbname=params["dbname"])


def norm_email(e):
    if not e:
        return None
    e = e.strip().lower()
    if "@" not in e or "." not in e.split("@")[-1] or len(e) < 5:
        return None
    return e


def norm_phone(p):
    if not p:
        return None
    d = re.sub(r"\D", "", p)
    return d if len(d) >= 7 else None


def split_name(full):
    full = (full or "").strip()
    if not full:
        return "", ""
    parts = full.split()
    return parts[0], " ".join(parts[1:])


def ensure_phone_index(tgt):
    """Expression index for digits-only phone dedup. CONCURRENTLY = online."""
    tgt.autocommit = True
    with tgt.cursor() as c:
        c.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_phones_phone_digits "
            "ON people.phones ((regexp_replace(phone, '\\D', '', 'g')))"
        )
    tgt.autocommit = False
    print("phone dedup index ready")


def classify_batch(tgt, rows):
    """Return (to_insert, skipped) with per-row skip reasons.

    rows: list of dicts from the source table.
    Dedup checks hit the target in two indexed batch queries — no
    per-row round trips against the 211M-row table.
    """
    emails = {}
    phones = {}
    for r in rows:
        e = norm_email(r["email"])
        p = norm_phone(r["phone"])
        if e:
            emails.setdefault(e, []).append(r["id"])
        if p:
            phones.setdefault(p, []).append(r["id"])

    existing_emails = set()
    if emails:
        with tgt.cursor() as c:
            c.execute(
                "SELECT lower(primary_email) FROM people.people "
                "WHERE lower(primary_email) = ANY(%s)",
                (list(emails.keys()),),
            )
            existing_emails = {row[0] for row in c.fetchall()}

    existing_phones = set()
    if phones:
        with tgt.cursor() as c:
            c.execute(
                "SELECT regexp_replace(phone, '\\D', '', 'g') "
                "FROM people.phones "
                "WHERE regexp_replace(phone, '\\D', '', 'g') = ANY(%s)",
                (list(phones.keys()),),
            )
            existing_phones = {row[0] for row in c.fetchall()}

    to_insert, skipped = [], []
    for r in rows:
        e = norm_email(r["email"])
        p = norm_phone(r["phone"])
        if e and e in existing_emails:
            skipped.append((r["id"], "dup_email"))
        elif not e and p and p in existing_phones:
            skipped.append((r["id"], "dup_phone"))
        elif not e and not p:
            skipped.append((r["id"], "msv_queue"))
        else:
            to_insert.append(r)
    return to_insert, skipped


def build_person(r, tags, batch_id):
    first, last = split_name(r["full_name"])
    meta = r["metadata"] or {}
    extra = {
        "oliabo_lead_id": r["id"],
        "mirror_from": "lead_scraper.oliabo_leads",
        "migration_batch": batch_id,
        "source_url": r["source_url"],
        "notes": r["notes"],
        "search_keywords": r["search_keywords"],
        "original_metadata": meta,
    }
    return {
        "first_name": first,
        "last_name": last,
        "source": r["source"] or "oliabo_leads",
        "city": r["location_city"] or r["city"],
        "state": r["location_state"],
        "country": "US",
        "primary_email": norm_email(r["email"]),
        "occupation": meta.get("occupation"),
        "tags": tags,
        "extra_data": json.dumps(extra),
        "created_date": r["created_at"],
        "last_processed_by": MIGRATION_TAG,
        "_phone": norm_phone(r["phone"]),
        "_lead_id": r["id"],
    }


def insert_batch(tgt, persons, batch_id):
    """Insert people rows, then their phones. Returns (people_ids, phone_rows)."""
    with tgt.cursor() as c:
        psycopg2.extras.execute_values(
            c,
            "INSERT INTO people.people "
            "(first_name, last_name, source, city, state, country, "
            " primary_email, occupation, tags, extra_data, created_date, "
            " last_processed_by) "
            "VALUES %s",
            [
                (
                    p["first_name"], p["last_name"], p["source"], p["city"],
                    p["state"], p["country"], p["primary_email"],
                    p["occupation"], p["tags"], p["extra_data"],
                    p["created_date"], p["last_processed_by"],
                )
                for p in persons
            ],
        )
        c.execute(
            "SELECT id, extra_data->>'oliabo_lead_id' FROM people.people "
            "WHERE extra_data->>'migration_batch' = %s",
            (batch_id,),
        )
        id_map = {int(lead_id): pid for pid, lead_id in c.fetchall()}

    phone_rows = [
        (id_map[p["_lead_id"]], p["_phone"], "oliabo_leads_migration")
        for p in persons
        if p["_phone"] and p["_lead_id"] in id_map
    ]
    if phone_rows:
        with tgt.cursor() as c:
            psycopg2.extras.execute_values(
                c,
                "INSERT INTO people.phones (person_id, phone, source) "
                "VALUES %s ON CONFLICT DO NOTHING",
                phone_rows,
            )
    tgt.commit()
    return len(id_map), len(phone_rows)


def run(args):
    tags = ["oliabo"] + [t.strip() for t in args.extra_tags.split(",") if t.strip()]
    src = _conn(SRC)
    tgt = _conn(TGT)

    if not args.skip_index and not args.dry_run:
        ensure_phone_index(tgt)

    stats = {
        "scanned": 0, "inserted": 0, "phones_added": 0,
        "skipped": {"dup_email": 0, "dup_phone": 0, "msv_queue": 0},
    }
    skip_examples = {"dup_email": [], "dup_phone": [], "msv_queue": []}

    with src.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute(
            "SELECT id, full_name, email, phone, city, location_city, "
            "location_state, source, source_url, notes, search_keywords, "
            "status, quality_score, metadata, created_at "
            "FROM lead_scraper.oliabo_leads ORDER BY id"
            + (" LIMIT %s" % int(args.limit) if args.limit else "")
        )
        while True:
            rows = c.fetchmany(BATCH)
            if not rows:
                break
            rows = [dict(r) for r in rows]
            stats["scanned"] += len(rows)
            to_insert, skipped = classify_batch(tgt, rows)
            for lid, reason in skipped:
                stats["skipped"][reason] += 1
                if len(skip_examples[reason]) < 3:
                    skip_examples[reason].append(lid)
            if to_insert and not args.dry_run:
                batch_id = uuid.uuid4().hex
                persons = [build_person(r, tags, batch_id) for r in to_insert]
                n_people, n_phones = insert_batch(tgt, persons, batch_id)
                stats["inserted"] += n_people
                stats["phones_added"] += n_phones
            print(
                "batch: scanned=%d to_insert=%d dup_email=%d dup_phone=%d msv_queue=%d%s"
                % (
                    len(rows), len(to_insert),
                    sum(1 for _, r in skipped if r == "dup_email"),
                    sum(1 for _, r in skipped if r == "dup_phone"),
                    sum(1 for _, r in skipped if r == "msv_queue"),
                    " DRY-RUN" if args.dry_run else "",
                ),
                flush=True,
            )

    src.close()
    tgt.close()
    print(json.dumps({"dry_run": args.dry_run, "stats": stats,
                      "skip_examples": skip_examples}, indent=2, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Migrate lead_scraper.oliabo_leads into "
                    "people_unified.people.people with dedup checking.")
    ap.add_argument("--run", dest="dry_run", action="store_false",
                    help="perform the migration (default is dry-run)")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    default=True)
    ap.add_argument("--limit", default=None,
                    help="max source rows to process (testing)")
    ap.add_argument("--extra-tags", default="",
                    help="comma-separated segment tags, e.g. oliabo:medical")
    ap.add_argument("--skip-index", action="store_true",
                    help="skip the CONCURRENT phone-index build")
    args = ap.parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
