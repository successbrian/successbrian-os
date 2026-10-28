#!/usr/bin/env python3
"""Operator health log — the FITNESS pillar of Brian's life pillars.

Brian's frame (2026-10-28 18:56 CDT): his life pillars are his own F
set — FAMILY, FAITH, FITNESS, FINANCE (list left open by him). Health
tracking lives under FITNESS. Brian's directive: "health tracking in
successbrian os is also important to me. helping me get better sleep,
eat better.. continue the road to better health." The FITNESS
sub-domains are the five health pillars (standard life-coaching set,
Brian 2026-10-28; Brian-correctable): sleep, nutrition, movement,
stress_mindset, social_connection — each first-class (tracked /
trended / surfaced in chat). A1C + weight ride the metabolic thread
crossing nutrition + movement.

State home (R32): PostgreSQL table successbrian_os.health_log.
This tool only RECORDS and READS readings (Brian-reported or
device-synced). It sets no targets and gives no medical advice.

Verbs: init | add | list | status | selftest
"""
import argparse
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sbos_common  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.health_log (
    id            serial PRIMARY KEY,
    metric        text NOT NULL,
    pillar        text,
    value         numeric,
    unit          text,
    reading_date  date,
    reported_date date NOT NULL DEFAULT CURRENT_DATE,
    source        text NOT NULL,
    note          text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS health_log_metric_idx
    ON successbrian_os.health_log (metric, reading_date);
"""

PILLARS = ["sleep", "nutrition", "movement", "stress_mindset", "social_connection"]


def init():
    sbos_common.pg_exec(DDL)
    print("health_log ready: successbrian_os.health_log")


def add(args):
    sbos_common.pg_exec(
        "INSERT INTO successbrian_os.health_log"
        " (metric, pillar, value, unit, reading_date, reported_date, source, note)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (args.metric, args.pillar, args.value, args.unit,
         args.reading_date, args.reported_date, args.source, args.note))
    print(f"recorded: {args.metric} = {args.value} {args.unit or ''} "
          f"(pillar={args.pillar}, source={args.source})")


def list_rows(args):
    sql = ("SELECT id, metric, pillar, value, unit, reading_date,"
           " reported_date, source, note FROM successbrian_os.health_log")
    params = None
    if args.metric:
        sql += " WHERE metric = %s"
        params = (args.metric,)
    sql += " ORDER BY COALESCE(reading_date, reported_date), id"
    for r in sbos_common.pg_rows(sql, params):
        print(" | ".join("" if c is None else str(c) for c in r))


def status():
    n = sbos_common.pg_rows("SELECT count(*) FROM successbrian_os.health_log")[0][0]
    print(f"HEALTH LOG: {n} entries")
    for metric, cnt, latest in sbos_common.pg_rows(
            "SELECT metric, count(*), max(COALESCE(reading_date, reported_date))"
            " FROM successbrian_os.health_log GROUP BY metric ORDER BY metric"):
        print(f"  {metric}: {cnt} entries, latest {latest}")
    fresh = sbos_common.pg_rows(
        "SELECT max(reported_date) FROM successbrian_os.health_log")[0][0]
    print(f"freshness: last reported {fresh}")
    flowing = {r[0] for r in sbos_common.pg_rows(
        "SELECT DISTINCT pillar FROM successbrian_os.health_log"
        " WHERE pillar IS NOT NULL")}
    for p in PILLARS:
        state = "flowing" if (p in flowing or (p in ("nutrition", "movement")
                                               and "nutrition+movement" in flowing)) \
            else "NOT FLOWING"
        print(f"  fitness sub-domain {p}: {state}")


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and bool(cond)

    tbl = sbos_common.pg_rows(
        "SELECT count(*) FROM information_schema.tables"
        " WHERE table_schema='successbrian_os' AND table_name='health_log'")[0][0]
    check("table-exists", tbl == 1)
    a1c = sbos_common.pg_rows(
        "SELECT count(*) FROM successbrian_os.health_log WHERE metric='a1c'")[0][0]
    check("seed-a1c-rows>=3", a1c >= 3)
    nulls = sbos_common.pg_rows(
        "SELECT count(*) FROM successbrian_os.health_log"
        " WHERE metric='a1c' AND value=13.9 AND reading_date IS NULL")[0][0]
    check("seed-a1c-13.9-date-honestly-null", nulls == 1)
    wt = sbos_common.pg_rows(
        "SELECT count(*) FROM successbrian_os.health_log"
        " WHERE metric='weight_change_lb' AND value=-37")[0][0]
    check("seed-weight-change-minus-37", wt == 1)
    abs_wt = sbos_common.pg_rows(
        "SELECT count(*) FROM successbrian_os.health_log"
        " WHERE metric='weight_lb'")[0][0]
    check("no-invented-absolute-weight", abs_wt == 0)
    print("SELFTEST " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Operator health log (SBOS)")
    sub = ap.add_subparsers(dest="verb", required=True)
    sub.add_parser("init")
    a = sub.add_parser("add")
    a.add_argument("--metric", required=True)
    a.add_argument("--pillar")
    a.add_argument("--value", type=float)
    a.add_argument("--unit")
    a.add_argument("--reading-date")
    a.add_argument("--reported-date")
    a.add_argument("--source", required=True)
    a.add_argument("--note")
    l = sub.add_parser("list")
    l.add_argument("--metric")
    sub.add_parser("status")
    sub.add_parser("selftest")
    args = ap.parse_args()
    if args.verb == "init":
        init()
    elif args.verb == "add":
        add(args)
    elif args.verb == "list":
        list_rows(args)
    elif args.verb == "status":
        status()
    elif args.verb == "selftest":
        _sys.exit(selftest())


if __name__ == "__main__":
    main()
