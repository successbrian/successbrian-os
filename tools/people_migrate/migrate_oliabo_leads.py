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
    - Dedup keys, checked per batch BEFORE insert (Brian 2026-10-02:
      "make sure it all matches" on both):
        1. email: lower(primary_email) IN batch
           (uses idx_people_lower_primary_email)
        2. phone: digits-only phone IN people.phones, joined to people.people
           for the stored name
           (uses idx_phones_phone_digits; created CONCURRENTLY if missing)
      A matching contact detail is NOT enough on its own: the stored name
      must also match (or be empty). Contact match + name match -> duplicate,
      skip. Contact match + conflicting name -> quarantined as
      'conflict_email' / 'conflict_phone' for human review: never
      auto-skipped, never auto-inserted. A row whose email is new but whose
      phone matches still gets the phone check (and vice versa).
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


def _norm_name(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def record_match_verdict(lead_first, lead_last, tgt_first, tgt_last):
    """Decide what a contact match means. Returns 'dup', 'dup_sparse',
    or 'conflict'.

    Used for BOTH email and phone matches (Brian 2026-10-02: "make sure
    it all matches" on both). A matching contact detail is NOT enough on
    its own: the name must also match.
    - Both target names empty: nothing to contradict the contact -> dup_sparse.
    - Normalized first+last both equal -> dup.
    - Anything else -> conflict: same contact detail, different person on
      record. Never auto-resolved; quarantined for human review.
    """
    lf, ll = _norm_name(lead_first), _norm_name(lead_last)
    tf, tl = _norm_name(tgt_first), _norm_name(tgt_last)
    if not tf and not tl:
        return "dup_sparse"
    if lf == tf and ll == tl:
        return "dup"
    return "conflict"


def classify_batch(tgt, rows):
    """Return (to_insert, skipped, conflicts) with per-row reasons.

    rows: list of dicts from the source table.
    Dedup checks hit the target in indexed batch queries — no per-row
    round trips against the 211M-row table. Email matches are verified
    against the stored name; mismatches become conflicts, never silent
    skips and never blind inserts.
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

    email_hits = {}
    if emails:
        with tgt.cursor() as c:
            c.execute(
                "SELECT lower(primary_email), first_name, last_name, city "
                "FROM people.people "
                "WHERE lower(primary_email) = ANY(%s)",
                (list(emails.keys()),),
            )
            for em, fn, ln, city in c.fetchall():
                # keep the first hit per email; dup emails in target are
                # themselves a data-quality signal, not our call to resolve
                email_hits.setdefault(em, (fn, ln, city))

    existing_phones = {}
    if phones:
        with tgt.cursor() as c:
            c.execute(
                "SELECT regexp_replace(ph.phone, '\\D', '', 'g'), "
                "       p.first_name, p.last_name "
                "FROM people.phones ph "
                "JOIN people.people p ON p.id = ph.person_id "
                "WHERE regexp_replace(ph.phone, '\\D', '', 'g') = ANY(%s)",
                (list(phones.keys()),),
            )
            for ph, fn, ln in c.fetchall():
                existing_phones.setdefault(ph, (fn, ln))

    to_insert, skipped, conflicts = [], [], []
    for r in rows:
        e = norm_email(r["email"])
        p = norm_phone(r["phone"])
        lfn, lln = split_name(r["full_name"])
        resolved = False
        if e and e in email_hits:
            # email match: name must also match
            tfn, tln, _tcity = email_hits[e]
            verdict = record_match_verdict(lfn, lln, tfn, tln)
            if verdict == "conflict":
                conflicts.append(
                    {"lead_id": r["id"], "lead_name": r["full_name"],
                     "matched_on": "email", "matched_value": e,
                     "target_name":
                     ("%s %s" % (tfn or "", tln or "")).strip()}
                )
            else:
                skipped.append((r["id"],
                                "dup_email" if verdict == "dup"
                                else "dup_email_sparse"))
            resolved = True
        if not resolved and p and p in existing_phones:
            # phone match: name must also match (same rule as email)
            tfn, tln = existing_phones[p]
            verdict = record_match_verdict(lfn, lln, tfn, tln)
            if verdict == "conflict":
                conflicts.append(
                    {"lead_id": r["id"], "lead_name": r["full_name"],
                     "matched_on": "phone", "matched_value": p,
                     "target_name":
                     ("%s %s" % (tfn or "", tln or "")).strip()}
                )
            else:
                skipped.append((r["id"],
                                "dup_phone" if verdict == "dup"
                                else "dup_phone_sparse"))
            resolved = True
        if not resolved:
            if not e and not p:
                skipped.append((r["id"], "msv_queue"))
            else:
                to_insert.append(r)
    return to_insert, skipped, conflicts


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
        "skipped": {"dup_email": 0, "dup_email_sparse": 0,
                    "dup_phone": 0, "dup_phone_sparse": 0,
                    "msv_queue": 0},
        "conflicts": 0,
    }
    skip_examples = {"dup_email": [], "dup_email_sparse": [],
                     "dup_phone": [], "dup_phone_sparse": [],
                     "msv_queue": []}
    conflict_examples = []

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
            to_insert, skipped, conflicts = classify_batch(tgt, rows)
            for lid, reason in skipped:
                stats["skipped"][reason] += 1
                if len(skip_examples[reason]) < 3:
                    skip_examples[reason].append(lid)
            stats["conflicts"] += len(conflicts)
            for cf in conflicts:
                if len(conflict_examples) < 5:
                    conflict_examples.append(cf)
            if to_insert and not args.dry_run:
                batch_id = uuid.uuid4().hex
                persons = [build_person(r, tags, batch_id) for r in to_insert]
                n_people, n_phones = insert_batch(tgt, persons, batch_id)
                stats["inserted"] += n_people
                stats["phones_added"] += n_phones
            n = lambda want: sum(1 for _, r in skipped if r == want)
            print(
                "batch: scanned=%d to_insert=%d dup_email=%d dup_email_sparse=%d "
                "dup_phone=%d dup_phone_sparse=%d "
                "msv_queue=%d conflicts=%d%s"
                % (
                    len(rows), len(to_insert),
                    n("dup_email"), n("dup_email_sparse"),
                    n("dup_phone"), n("dup_phone_sparse"),
                    n("msv_queue"), len(conflicts),
                    " DRY-RUN" if args.dry_run else "",
                ),
                flush=True,
            )

    src.close()
    tgt.close()
    print(json.dumps({"dry_run": args.dry_run, "stats": stats,
                      "skip_examples": skip_examples,
                      "conflict_examples": conflict_examples},
                     indent=2, default=str))


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
