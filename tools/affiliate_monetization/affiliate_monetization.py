#!/usr/bin/env python3
"""Affiliate program monetization strategy system.

PURPOSE:
    For each affiliate program Brian promotes, track HOW to earn with it:
    the program terms, the distinct revenue lanes (review SEO, tutorials,
    email, bonuses, done-for-you services, ...), reusable playbooks
    (email sequences, review templates, video scripts), monthly metrics,
    and strategy notes. A program record answers "should I promote it";
    this system answers "how do I earn with it, and which lane is working?"

WHY:
    Brian 2026-10-04: "use this deep dig to help us start building an
    affiliate program monetization strategy system." The Kinsta deep dig
    showed one program has 15+ distinct earning lanes -- without a system
    those ideas rot in chat history. Lanes turn a program into a portfolio
    of bets; playbooks turn what works into reusable assets; metrics turn
    hope into data.

CALLED BY:
    CLI (`python3 affiliate_monetization.py <command>`) run by an agent
    session or the entrepreneur directly. Report summaries can feed
    digests. Importable as a library too.

NOTES:
    - CANONICAL: successbrian-os/tools/affiliate_monetization/
    - DB: successbrian_os.aff_programs + aff_lanes + aff_playbooks +
      aff_metrics + aff_notes. Runs against the k11 Postgres the same way
      tools/audience does (localhost psql from k11).
    - Generic schema on purpose: no entrepreneur-specific data is
      hard-coded. Brian's Kinsta program is seeded data, not schema.
    - Complements tools/affiliate_program_check.py (promote-vs-build
      filter = SHOULD I promote) with monetization strategy (HOW).
    - status conventions: programs: active | paused | dropped;
      lanes: idea | planned | active | paused.
    - lane_type conventions: review | comparison | tutorial | video |
      email | bonus | service | agency | coupon | community | paid |
      leadmagnet | webinar | case-study | social | partnership | other.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import pg_password

PG = {"host": "localhost", "dbname": "ecosystem_central",
      "user": "successbrian"}
PG["password"] = pg_password(PG["host"], PG["dbname"], PG["user"])


def _psql(sql, variables=None, field_sep="\t"):
    """Run SQL via the psql CLI. Values go through -v variables so nothing
    is interpolated into SQL by hand."""
    env = dict(os.environ, PGPASSWORD=PG["password"])
    cmd = ["psql", "-h", PG["host"], "-U", PG["user"], "-d", PG["dbname"],
           "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", field_sep]
    for k, v in (variables or {}).items():
        cmd += ["-v", "%s=%s" % (k, v)]
    p = subprocess.run(cmd, input=sql, capture_output=True, text=True,
                       env=env)
    if p.returncode != 0:
        raise RuntimeError("psql failed: " + p.stderr.strip()[-400:])
    return p.stdout


def _rows(sql, variables=None):
    return [l for l in _psql(sql, variables).split("\n") if l.strip()]


def _program_id(slug):
    rows = _rows("SELECT id FROM successbrian_os.aff_programs "
                 "WHERE slug=:'slug';", {"slug": slug})
    if not rows:
        raise SystemExit("no affiliate program with slug '%s'" % slug)
    return rows[0]


# ---------------------------------------------------------------- commands

def cmd_init_db(_args):
    _psql(open(os.path.join(HERE, "schema.sql")).read())
    print("affiliate_monetization schema ready")


def cmd_new_program(args):
    _psql(
        "INSERT INTO successbrian_os.aff_programs"
        " (slug, name, terms, commission_summary, cookie_days,"
        "  payout_minimum, status, my_role, notes,"
        "  commission_type, commission_rate_pct, commission_flat_usd,"
        "  commission_flat_max_usd, is_recurring, recurring_period) VALUES"
        " (:'slug', :'name', :'terms', :'comm', :'cookie'::int,"
        "  :'payout'::numeric, :'status', :'role', :'notes',"
        "  :'ctype', :'rate'::numeric, :'flat'::numeric,"
        "  :'flatmax'::numeric, :'recur'::boolean, :'period')"
        " ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name,"
        " terms=EXCLUDED.terms,"
        " commission_summary=EXCLUDED.commission_summary,"
        " cookie_days=EXCLUDED.cookie_days,"
        " payout_minimum=EXCLUDED.payout_minimum,"
        " status=EXCLUDED.status, my_role=EXCLUDED.my_role,"
        " notes=EXCLUDED.notes,"
        " commission_type=EXCLUDED.commission_type,"
        " commission_rate_pct=EXCLUDED.commission_rate_pct,"
        " commission_flat_usd=EXCLUDED.commission_flat_usd,"
        " commission_flat_max_usd=EXCLUDED.commission_flat_max_usd,"
        " is_recurring=EXCLUDED.is_recurring,"
        " recurring_period=EXCLUDED.recurring_period;",
        {"slug": args.slug, "name": args.name, "terms": args.terms or "",
         "comm": args.commission_summary or "",
         "cookie": args.cookie_days or "",
         "payout": args.payout_minimum or "",
         "status": args.status or "active", "role": args.my_role or "",
         "notes": args.notes or "",
         "ctype": args.commission_type or "unknown",
         "rate": args.commission_rate_pct or "",
         "flat": args.commission_flat_usd or "",
         "flatmax": args.commission_flat_max_usd or "",
         "recur": args.is_recurring or "false",
         "period": args.recurring_period or ""})
    print("program upserted: %s" % args.slug)


def _fmt_commission(r):
    """Standardized one-line commission rendering from structured fields."""
    ctype, rate, flat, flatmax, recur, period, summary = r
    parts = []
    if ctype == "percentage" and rate:
        parts.append("%s%%" % rate)
    elif ctype == "flat" and flat:
        parts.append("$%s" % flat)
    elif ctype == "hybrid":
        if flat:
            parts.append("$%s%s/sale" % (flat, ("-$%s" % flatmax) if flatmax else ""))
        if rate:
            parts.append("%s%%" % rate)
    elif ctype == "tiered":
        parts.append("tiered")
    if recur == "t" or recur is True:
        parts.append("recurring%s" % (" (%s)" % period if period else ""))
    if parts:
        return " ".join(parts)
    return summary or "?"


def cmd_compare(_args):
    rows = _rows("SELECT slug, name, status, commission_type,"
                " commission_rate_pct, commission_flat_usd,"
                " commission_flat_max_usd, is_recurring, recurring_period,"
                " commission_summary, cookie_days, payout_minimum,"
                " (SELECT COALESCE(SUM(earnings),0) FROM"
                "  successbrian_os.aff_metrics m"
                "  WHERE m.program_id = p.id)"
                " FROM successbrian_os.aff_programs p ORDER BY slug;")
    if not rows:
        print("no programs yet -- run new-program first")
        return
    print("%-18s %-8s %-28s %6s %7s %s" %
          ("program", "status", "commission", "cookie", "earned", "recurring"))
    for r in rows:
        f = (r.split("\t") + [""] * 13)[:13]
        slug, name, status = f[0], f[1], f[2]
        comm = _fmt_commission((f[3], f[4], f[5], f[6], f[7], f[8], f[9]))
        cookie, earned = f[10] or "?", f[12] or "0"
        recur = "yes" if f[7] in ("t", True) else "-"
        print("%-18s %-8s %-28s %6s $%6s %s" %
              (slug, status, comm[:28], cookie, earned, recur))
    print("(%d programs, standardized commission view)" % len(rows))


def cmd_list_programs(_args):
    rows = _rows("SELECT slug, name, status, cookie_days, payout_minimum,"
                 " commission_summary FROM successbrian_os.aff_programs"
                 " ORDER BY slug;")
    if not rows:
        print("no programs yet -- run new-program first")
        return
    for r in rows:
        slug, name, status, cookie, payout, comm = (r.split("\t") + [""] * 6)[:6]
        print("%-22s %-30s %-8s cookie=%sd min=$%s" %
              (slug, name, status, cookie or "?", payout or "?"))
        if comm:
            print("    %s" % comm)
    print("(%d programs)" % len(rows))


def cmd_add_lane(args):
    pid = _program_id(args.program)
    _psql(
        "INSERT INTO successbrian_os.aff_lanes"
        " (program_id, lane_name, lane_type, description, effort,"
        "  expected_payoff, why_it_works, rule_notes, status) VALUES"
        " (:'pid', :'name', :'ltype', :'desc', :'effort', :'payoff',"
        "  :'why', :'rules', :'status')"
        " ON CONFLICT (program_id, lane_name) DO UPDATE SET"
        " lane_type=EXCLUDED.lane_type, description=EXCLUDED.description,"
        " effort=EXCLUDED.effort, expected_payoff=EXCLUDED.expected_payoff,"
        " why_it_works=EXCLUDED.why_it_works,"
        " rule_notes=EXCLUDED.rule_notes, status=EXCLUDED.status;",
        {"pid": pid, "name": args.name, "ltype": args.lane_type or "other",
         "desc": args.description or "", "effort": args.effort or "medium",
         "payoff": args.expected_payoff or "medium",
         "why": args.why_it_works or "", "rules": args.rule_notes or "",
         "status": args.status or "idea"})
    print("lane upserted: %s [%s]" % (args.name, args.program))


def cmd_list_lanes(args):
    pid = _program_id(args.program)
    filt = "" if not args.status else " AND status=:'status'"
    rows = _rows(
        "SELECT lane_name, lane_type, status, effort, expected_payoff,"
        " earnings_to_date FROM successbrian_os.aff_lanes"
        " WHERE program_id=:'pid'" + filt + " ORDER BY lane_name;",
        {"pid": pid, "status": args.status or ""})
    if not rows:
        print("no lanes on program '%s'" % args.program)
        return
    for r in rows:
        name, ltype, status, effort, payoff, earn = (r.split("\t") + [""] * 6)[:6]
        print("%-32s %-12s %-8s effort=%s payoff=%s earned=$%s" %
              (name, ltype, status, effort, payoff, earn or "0"))
    print("(%d lanes)" % len(rows))


def cmd_update_lane(args):
    pid = _program_id(args.program)
    sets, v = [], {"pid": pid, "name": args.name}
    if args.status:
        sets.append("status=:'status'"); v["status"] = args.status
    if args.earnings is not None:
        sets.append("earnings_to_date=:'earn'"); v["earn"] = str(args.earnings)
    if args.referrals is not None:
        sets.append("referrals_to_date=:'ref'::int"); v["ref"] = str(args.referrals)
    if not sets:
        raise SystemExit("nothing to update -- pass --status, --earnings, or --referrals")
    _psql("UPDATE successbrian_os.aff_lanes SET " + ", ".join(sets) +
          " WHERE program_id=:'pid' AND lane_name=:'name';", v)
    print("lane updated: %s" % args.name)


def cmd_add_playbook(args):
    pid = _program_id(args.program)
    lane_id = None
    if args.lane:
        rows = _rows("SELECT id FROM successbrian_os.aff_lanes "
                     "WHERE program_id=:'pid' AND lane_name=:'lane';",
                     {"pid": pid, "lane": args.lane})
        if not rows:
            raise SystemExit("no lane '%s' on program '%s'" % (args.lane, args.program))
        lane_id = rows[0]
    body = args.body
    if body == "-":
        body = sys.stdin.read()
    _psql(
        "INSERT INTO successbrian_os.aff_playbooks"
        " (program_id, lane_id, title, playbook_type, body)"
        " VALUES (:'pid', NULLIF(:'laneid','')::int, :'title', :'ptype', :'body');",
        {"pid": pid, "laneid": lane_id or "", "title": args.title,
         "ptype": args.playbook_type or "other", "body": body})
    print("playbook added: %s" % args.title)


def cmd_list_playbooks(args):
    pid = _program_id(args.program)
    rows = _rows(
        "SELECT p.title, p.playbook_type, l.lane_name FROM"
        " successbrian_os.aff_playbooks p LEFT JOIN"
        " successbrian_os.aff_lanes l ON l.id=p.lane_id"
        " WHERE p.program_id=:'pid' ORDER BY p.title;",
        {"pid": pid})
    if not rows:
        print("no playbooks on program '%s'" % args.program)
        return
    for r in rows:
        title, ptype, lane = (r.split("\t") + [""] * 3)[:3]
        print("%-40s %-12s %s" % (title, ptype, ("lane: " + lane) if lane else ""))
    print("(%d playbooks)" % len(rows))


def cmd_add_note(args):
    pid = _program_id(args.program)
    note = args.note
    if note == "-":
        note = sys.stdin.read()
    _psql("INSERT INTO successbrian_os.aff_notes (program_id, note)"
          " VALUES (:'pid', :'note');", {"pid": pid, "note": note})
    print("note added to %s" % args.program)


def cmd_log_metrics(args):
    pid = _program_id(args.program)
    lane_id = None
    if args.lane:
        rows = _rows("SELECT id FROM successbrian_os.aff_lanes "
                     "WHERE program_id=:'pid' AND lane_name=:'lane';",
                     {"pid": pid, "lane": args.lane})
        if not rows:
            raise SystemExit("no lane '%s' on program '%s'" % (args.lane, args.program))
        lane_id = rows[0]
    _psql(
        "INSERT INTO successbrian_os.aff_metrics"
        " (program_id, lane_id, period_month, clicks, conversions, earnings)"
        " VALUES (:'pid', NULLIF(:'laneid','')::int, :'month',"
        "         :'clicks'::int, :'convs'::int, :'earn'::numeric)"
        " ON CONFLICT (program_id, lane_id, period_month) DO UPDATE SET"
        " clicks=EXCLUDED.clicks, conversions=EXCLUDED.conversions,"
        " earnings=EXCLUDED.earnings;",
        {"pid": pid, "laneid": lane_id or "", "month": args.month,
         "clicks": str(args.clicks or 0), "convs": str(args.conversions or 0),
         "earn": str(args.earnings or 0)})
    print("metrics logged: %s %s" % (args.program, args.month))


def cmd_report(args):
    pid = _program_id(args.program)
    prog = _rows("SELECT name, status, commission_summary, cookie_days,"
                 " payout_minimum, my_role FROM successbrian_os.aff_programs"
                 " WHERE id=:'pid';", {"pid": pid})[0].split("\t")
    print("== %s ==" % prog[0])
    print("status: %s | cookie: %s days | min payout: $%s | role: %s" %
          (prog[1], prog[3] or "?", prog[4] or "?", prog[5] or "-"))
    print("commission: %s" % (prog[2] or "-"))
    print("\nlanes:")
    for r in _rows("SELECT lane_name, status, effort, expected_payoff,"
                   " earnings_to_date FROM successbrian_os.aff_lanes"
                   " WHERE program_id=:'pid' ORDER BY expected_payoff DESC,"
                   " lane_name;", {"pid": pid}):
        name, status, effort, payoff, earn = r.split("\t")
        print("  %-30s [%s] payoff=%s effort=%s earned=$%s" %
              (name, status, payoff, effort, earn))
    tot = _rows("SELECT COALESCE(SUM(earnings),0), COALESCE(SUM(clicks),0),"
                " COALESCE(SUM(conversions),0) FROM successbrian_os.aff_metrics"
                " WHERE program_id=:'pid';", {"pid": pid})[0].split("\t")
    print("\nlifetime tracked: $%s earned from %s clicks / %s conversions" %
          (tot[0], tot[1], tot[2]))
    notes = _rows("SELECT note FROM successbrian_os.aff_notes"
                  " WHERE program_id=:'pid' ORDER BY id DESC LIMIT 3;",
                  {"pid": pid})
    if notes:
        print("\nlatest notes:")
        for n in notes:
            print("  - %s" % n[:200])


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="create the affiliate_monetization tables")\
        .set_defaults(func=cmd_init_db)

    p = sub.add_parser("new-program", help="register an affiliate program")
    p.add_argument("slug"); p.add_argument("--name", required=True)
    p.add_argument("--terms"); p.add_argument("--commission-summary")
    p.add_argument("--commission-type",
                   choices=["percentage", "flat", "tiered", "recurring", "hybrid"])
    p.add_argument("--commission-rate-pct"); p.add_argument("--commission-flat-usd")
    p.add_argument("--commission-flat-max-usd"); p.add_argument("--is-recurring")
    p.add_argument("--recurring-period")
    p.add_argument("--cookie-days"); p.add_argument("--payout-minimum")
    p.add_argument("--status"); p.add_argument("--my-role"); p.add_argument("--notes")
    p.set_defaults(func=cmd_new_program)

    sub.add_parser("compare", help="standardized commission comparison")\
        .set_defaults(func=cmd_compare)

    sub.add_parser("list-programs", help="list affiliate programs")\
        .set_defaults(func=cmd_list_programs)

    p = sub.add_parser("add-lane", help="add or update a revenue lane")
    p.add_argument("program"); p.add_argument("name")
    p.add_argument("--lane-type"); p.add_argument("--description")
    p.add_argument("--effort"); p.add_argument("--expected-payoff")
    p.add_argument("--why-it-works"); p.add_argument("--rule-notes")
    p.add_argument("--status")
    p.set_defaults(func=cmd_add_lane)

    p = sub.add_parser("list-lanes", help="list lanes on a program")
    p.add_argument("program"); p.add_argument("--status")
    p.set_defaults(func=cmd_list_lanes)

    p = sub.add_parser("update-lane", help="update a lane's status or results")
    p.add_argument("program"); p.add_argument("name")
    p.add_argument("--status"); p.add_argument("--earnings", type=float)
    p.add_argument("--referrals", type=int)
    p.set_defaults(func=cmd_update_lane)

    p = sub.add_parser("add-playbook", help="save a reusable playbook ('-' reads stdin)")
    p.add_argument("program"); p.add_argument("--title", required=True)
    p.add_argument("--playbook-type"); p.add_argument("--lane"); p.add_argument("--body", required=True)
    p.set_defaults(func=cmd_add_playbook)

    p = sub.add_parser("list-playbooks", help="list playbooks on a program")
    p.add_argument("program")
    p.set_defaults(func=cmd_list_playbooks)

    p = sub.add_parser("add-note", help="add a strategy note ('-' reads stdin)")
    p.add_argument("program"); p.add_argument("note")
    p.set_defaults(func=cmd_add_note)

    p = sub.add_parser("log-metrics", help="log monthly metrics for a program or lane")
    p.add_argument("program"); p.add_argument("--lane")
    p.add_argument("--month", required=True)
    p.add_argument("--clicks", type=int); p.add_argument("--conversions", type=int)
    p.add_argument("--earnings", type=float)
    p.set_defaults(func=cmd_log_metrics)

    p = sub.add_parser("report", help="program summary: lanes, metrics, notes")
    p.add_argument("program")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
