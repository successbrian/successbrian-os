#!/usr/bin/env python3
"""briefing_table.py — CLI for the shared briefing intake table.

PURPOSE
    Add / list / consume items in ecosystem_central.public.briefing_items —
    the "table" Brian described 2026-09-27: "throughout the day, the ecosystem
    can add pieces to the table that Altair draws from for the briefs."
    altair_briefing.py (on k11-alpha) pulls pending items at generation time
    and injects them into the DeepSeek prompt as TABLE CONTRIBUTIONS.

WHY this exists
    Before this, each briefing was generated from static context files plus
    live state — anything the ecosystem noticed during the day had no place
    to land. The briefing table gives every component (affiliate checker,
    marketer watcher, monitors, humans) one append-only intake that briefings
    drain. Dedup on (source, title) keeps one noisy producer from spamming it.

CALLED BY
    - Humans / driver agents: --add, --pending, --consume
    - tools/affiliate_program_check.py --record (auto-adds PROMOTE /
      build-candidate verdicts)
    - /home/successbrian/bin/altair_briefing.py (reads pending at generation;
      consumes after successful --write)

NOTES
    - Unconsumed + unexpired = pending. Expired items stay in the table but
      are never served to the generator.
    - --consume marks pending items consumed with a briefing date. Only the
      generator (or a human) calls this — dry-run generations must NOT eat
      the table.
    - SQL goes through the same base64-via-kssh pg_exec pattern as
      second_brain.py (shell metacharacters in titles/details are safe).
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KSSH = Path.home() / "workspace" / "bin" / "kssh"

CATEGORIES = ("operational", "blog_idea", "build_idea",
              "ecosystem_knowledge", "decision")
PRIORITIES = ("high", "medium", "low")


def pg_exec(sql: str) -> str:
    import base64
    b64 = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    out = subprocess.run(
        [str(KSSH), "psql -h localhost -U successbrian -d ecosystem_central "
                    f"-t -A -c \"$(echo {b64} | base64 -d)\""],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return out.stdout.strip()


def esc(s: str) -> str:
    return s.replace("'", "''")


def cmd_add(a) -> int:
    if a.category not in CATEGORIES:
        print(f"bad category: {a.category} (want {', '.join(CATEGORIES)})",
              file=sys.stderr)
        return 1
    if a.priority not in PRIORITIES:
        print(f"bad priority: {a.priority}", file=sys.stderr)
        return 1
    # Dedup: same source+title still pending -> skip, report existing id.
    existing = pg_exec(
        "SELECT id FROM briefing_items "
        f"WHERE consumed_at IS NULL AND source = '{esc(a.source)}' "
        f"AND title = '{esc(a.title)}' LIMIT 1;")
    if existing:
        print(f"duplicate: item {existing} already pending "
              f"({a.source}: {a.title})")
        return 0
    exp = (f", expires_at = now() + interval '{a.expires_days} days'"
           if a.expires_days else ", expires_at = NULL")
    detail = f"'{esc(a.detail)}'" if a.detail else "NULL"
    row = pg_exec(
        "INSERT INTO briefing_items (source, category, title, detail, priority"
        f"{', expires_at' if a.expires_days else ''}) "
        f"VALUES ('{esc(a.source)}', '{a.category}', '{esc(a.title)}', "
        f"{detail}, '{a.priority}'"
        f"{f', now() + interval \'{a.expires_days} days\'' if a.expires_days else ''}) "
        "RETURNING id;").splitlines()[0]
    print(f"added: item {row} [{a.category}/{a.priority}] {a.title}")
    return 0


def cmd_pending(a) -> int:
    rows = pg_exec(
        "SELECT id, source, category, priority, title, "
        "to_char(created_at, 'YYYY-MM-DD HH24:MI') "
        "FROM briefing_items "
        "WHERE consumed_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > now()) "
        "ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 "
        "ELSE 2 END, created_at;")
    if not rows:
        print("no pending items")
        return 0
    for line in rows.splitlines():
        rid, src, cat, pri, title, ts = line.split("|", 5)
        print(f"#{rid} [{pri}] {cat} — {title} (from {src}, {ts})")
    return 0


def cmd_consume(a) -> int:
    try:
        datetime.strptime(a.date, "%Y-%m-%d")
    except ValueError:
        print(f"bad date: {a.date} (want YYYY-MM-DD)", file=sys.stderr)
        return 1
    tag = pg_exec(
        "UPDATE briefing_items SET consumed_at = now(), "
        f"briefing_date = '{a.date}' "
        "WHERE consumed_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > now());")
    n = tag.split()[-1] if tag.split() else "0"
    print(f"consumed {n} item(s) into briefing {a.date}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Shared briefing intake table (briefing_items).")
    p.add_argument("--add", action="store_true", help="add an item")
    p.add_argument("--source", help="contributing component name")
    p.add_argument("--category", choices=CATEGORIES)
    p.add_argument("--title", help="item title")
    p.add_argument("--detail", default=None, help="item detail text")
    p.add_argument("--priority", choices=PRIORITIES, default="medium")
    p.add_argument("--expires-days", type=int, default=None,
                   help="item expires N days after creation")
    p.add_argument("--pending", action="store_true", help="list pending items")
    p.add_argument("--consume", action="store_true",
                   help="mark pending items consumed")
    p.add_argument("--date", metavar="YYYY-MM-DD",
                   help="briefing date for --consume")
    a = p.parse_args()

    if a.add:
        if not (a.source and a.category and a.title):
            p.error("--add needs --source, --category, --title")
        return cmd_add(a)
    if a.pending:
        return cmd_pending(a)
    if a.consume:
        if not a.date:
            p.error("--consume needs --date YYYY-MM-DD")
        return cmd_consume(a)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
