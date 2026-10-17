#!/usr/bin/env python3
"""
gap_watch — the wiring for the interview triggers.

Runs on cron:
  - weekly:  gap check -> files a pending_question per tenant with gaps
  - monthly: staleness check -> "has anything changed?" for fully-mapped
             tenants whose map hasn't been touched in 30+ days

Silent when the map is clean: no gaps, no staleness, no inbox noise.
Deduped: never files a second open question for the same tenant+reason.

stdlib + psql CLI only.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from interview import coverage, questions  # noqa: E402
from core import lit  # noqa: E402


def _pg_env():
    env = dict(os.environ)
    env.update({
        "PGHOST": os.environ.get("PGHOST", "localhost"),
        "PGPORT": os.environ.get("PGPORT", "5432"),
        "PGDATABASE": os.environ.get("PGDATABASE", "ecosystem_central"),
        "PGUSER": os.environ.get("PGUSER", "successbrian"),
    })
    return env


def pg_query(sql):
    p = subprocess.run(["psql", "-t", "-A", "-F", "\t", "-c", sql],
                       capture_output=True, text=True,
                       env=_pg_env(), timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"pg_query failed: {p.stderr.strip()[:300]}")
    return [l.split("\t") for l in p.stdout.strip().split("\n") if l.strip()]


def pg_exec(sql):
    p = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t"],
                       input=sql, capture_output=True, text=True,
                       env=_pg_env(), timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"pg_exec failed: {p.stderr.strip()[:300]}")


ASKED_BY = "gap_watch"


def tenants():
    rows = pg_query("SELECT id FROM business_core.tenants ORDER BY id;")
    return [r[0] for r in rows]


def open_question_exists(tenant_id, reason):
    rows = pg_query(
        "SELECT 1 FROM successbrian_os.pending_questions "
        f"WHERE asked_by={lit(ASKED_BY)} AND status='open' "
        f"AND context={lit(f'tenant={tenant_id} reason={reason}')} LIMIT 1;")
    return bool(rows)


def file_question(tenant_id, reason, question, context_extra=""):
    ctx = f"tenant={tenant_id} reason={reason} {context_extra}".strip()
    if open_question_exists(tenant_id, reason):
        return False
    pg_exec(
        "INSERT INTO successbrian_os.pending_questions "
        "(asked_by, question, context, priority) VALUES "
        f"({lit(ASKED_BY)}, {lit(question)}, {lit(ctx)}, 3);")
    return True


def check_gaps():
    """Weekly: tenants with unmapped areas get an interview question."""
    filed = []
    for t in tenants():
        qs = questions(t)
        if qs:
            areas = ", ".join(q["area"] for q in qs)
            q = (f"Your business map has {len(qs)} unmapped area(s): "
                 f"{areas}. Want me to interview you to fill them in?")
            if file_question(t, "gaps", q, f"areas={areas}"):
                filed.append(t)
    return filed


def check_staleness(max_age_days=30):
    """Monthly: fully-mapped but untouched maps get a check-in."""
    filed = []
    for t in tenants():
        if questions(t):
            continue  # gaps handled by check_gaps
        rows = pg_query(
            "SELECT MAX(ts) FROM ("
            " SELECT MAX(created_at) AS ts FROM business_core.tenants "
            f"WHERE id={lit(t)}"
            " UNION ALL SELECT MAX(built_at) FROM "
            "business_core.context_packets "
            f"WHERE tenant_id={lit(t)}) s;")
        newest = rows[0][0] if rows and rows[0][0] else None
        if not newest:
            continue
        age = pg_query(f"SELECT now() - {lit(newest)}::timestamptz "
                       f"> INTERVAL '{max_age_days} days';")
        if age and age[0][0] == "t":
            q = (f"It's been over {max_age_days} days since your business "
                 f"map was updated. Has anything changed — new products, "
                 f"new income, new rules? A quick check-in keeps the map "
                 f"honest.")
            if file_question(t, "staleness", q):
                filed.append(t)
    return filed


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gaps", action="store_true")
    ap.add_argument("--staleness", action="store_true")
    ap.add_argument("--max-age-days", type=int, default=30)
    args = ap.parse_args()
    if args.gaps:
        filed = check_gaps()
        print(f"gap check: filed for {filed or 'none'}")
    elif args.staleness:
        filed = check_staleness(args.max_age_days)
        print(f"staleness check: filed for {filed or 'none'}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
