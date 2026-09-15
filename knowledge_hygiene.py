#!/usr/bin/env python3
"""
Second-brain hygiene — keep an agent's knowledge store from rotting.

A knowledge store decays three ways: facts go stale, topics get duplicated, and
operational noise buries the signal. This tool keeps it clean.

  --expire   soft-expire facts whose expires_at has passed
  --dedupe   list duplicate topics (keep the highest-confidence copy)
  --report   summarize the store by category + confidence

DB config via env vars (defaults to unix-socket local peer auth):
  SB_DB_HOST  (default: /var/run/postgresql)
  SB_DB_PORT  (default: 5432)
  SB_DB_NAME  (default: postgres)
  SB_DB_USER  (default: current user)
  SB_TABLE    (default: second_brain)

Requires: psycopg2  (pip install psycopg2-binary)
"""
import argparse
import os
import sys

import psycopg2

DB = dict(
    host=os.environ.get("SB_DB_HOST", "/var/run/postgresql"),
    port=int(os.environ.get("SB_DB_PORT", "5432")),
    dbname=os.environ.get("SB_DB_NAME", "postgres"),
    user=os.environ.get("SB_DB_USER", os.environ.get("USER", "")),
)
TABLE = os.environ.get("SB_TABLE", "second_brain")


def _conn():
    return psycopg2.connect(**DB)


def expire():
    c = _conn()
    cur = c.cursor()
    cur.execute(
        f"UPDATE {TABLE} SET confidence = 'expired' "
        f"WHERE expires_at IS NOT NULL AND expires_at <= now() "
        f"AND confidence != 'expired'"
    )
    n = cur.rowcount
    c.commit()
    cur.close()
    c.close()
    print(f"expired: {n} facts past their expires_at")


def dedupe():
    c = _conn()
    cur = c.cursor()
    cur.execute(
        f"SELECT topic, count(*) FROM {TABLE} "
        f"WHERE confidence != 'expired' "
        f"GROUP BY topic HAVING count(*) > 1 ORDER BY 2 DESC"
    )
    rows = cur.fetchall()
    for topic, n in rows:
        print(f"dup topic ({n}x): {topic}")
    cur.close()
    c.close()
    print(f"duplicate topics: {len(rows)}")


def report():
    c = _conn()
    cur = c.cursor()
    cur.execute(
        f"SELECT category, confidence, count(*) FROM {TABLE} "
        f"WHERE confidence != 'expired' GROUP BY 1, 2 ORDER BY 1, 2"
    )
    rows = cur.fetchall()
    for cat, conf, n in rows:
        print(f"{cat:20s} {conf:10s} {n}")
    cur.close()
    c.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Second-brain hygiene")
    ap.add_argument("--expire", action="store_true")
    ap.add_argument("--dedupe", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if not (a.expire or a.dedupe or a.report):
        ap.print_help()
        sys.exit(1)
    if a.expire:
        expire()
    if a.dedupe:
        dedupe()
    if a.report:
        report()
