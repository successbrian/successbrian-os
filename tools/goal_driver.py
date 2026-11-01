#!/usr/bin/env python3
"""goal_driver.py — the three clear monthly goals, in code.

Brian's rulings (2026-11-01):
  * Clear monthly goals: GotBackup 40 paid enrollments, Oliabo 30 new paid
    customers, systeme.io 50 new paid customers.
  * "These goals are pieces that every layer and piece of the ecosystem have
    to help drive."
  * REFINEMENT, same sitting: "careful not to piece every asset to each and
    every goal. only when appropriate."

So this tool does two things and refuses a third:
  1. It holds the goals and their monthly scorecard (counts entered from the
     programs' own back offices — never estimated).
  2. It records asset -> goal links, but a link REQUIRES a written fit reason
     of at least 20 characters, sourced to who established the fit. There is
     deliberately NO bulk-link verb: blanket mapping every asset to every
     goal is the failure Brian named, and the tool will not do it.

Verbs:
  goals                      the three goals and targets
  link --asset-type T --asset REF --goal KEY --fit "..." --source S
  links [--goal KEY]         recorded links
  unlink --asset-type T --asset REF --goal KEY
  score --goal KEY --month YYYY-MM --achieved N --source S
  board [--month YYYY-MM]    targets vs entered counts (missing = NOT REPORTED)
  check                      QA sentinel: prints GOAL_DRIVER_OK or the defect
"""
import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sbos_common import pg_rows, pg_exec, pg_one  # noqa: E402

MIN_FIT = 20


def cmd_goals(_):
    for key, product, target, unit in pg_rows(
        "SELECT goal_key, product, target, unit FROM successbrian_os.monthly_goals ORDER BY target DESC"
    ):
        print(f"{key:14s} {product:12s} {target:>3d} {unit} / month")
    return 0


def cmd_link(a):
    if len(a.fit.strip()) < MIN_FIT:
        print(f"REFUSED: a link needs a real fit reason (>= {MIN_FIT} chars). "
              "If the fit cannot be said in words, it is not a fit — Brian's rule.")
        return 2
    pg_exec(
        "INSERT INTO successbrian_os.goal_asset_links (asset_type, asset_ref, goal_key, fit_note, source) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (asset_type, asset_ref, goal_key) DO NOTHING",
        (a.asset_type, a.asset, a.goal, a.fit.strip(), a.source),
    )
    print(f"linked {a.asset_type}:{a.asset} -> {a.goal}")
    return 0


def cmd_links(a):
    q = ("SELECT asset_type, asset_ref, goal_key, fit_note FROM successbrian_os.goal_asset_links "
         "WHERE status='active'")
    params = ()
    if a.goal:
        q += " AND goal_key=%s"
        params = (a.goal,)
    rows = pg_rows(q + " ORDER BY goal_key, asset_type, asset_ref", params)
    if not rows:
        print("(no links recorded)")
    for t, ref, g, fit in rows:
        print(f"{g:14s} {t}:{ref}\n{'':14s}   fit: {fit}")
    return 0


def cmd_unlink(a):
    pg_exec(
        "UPDATE successbrian_os.goal_asset_links SET status='retired' "
        "WHERE asset_type=%s AND asset_ref=%s AND goal_key=%s",
        (a.asset_type, a.asset, a.goal),
    )
    print(f"retired link {a.asset_type}:{a.asset} -> {a.goal}")
    return 0


def cmd_score(a):
    pg_exec(
        "INSERT INTO successbrian_os.goal_month_scores (goal_key, month, achieved, source) "
        "VALUES (%s, (%s || '-01')::date, %s, %s) "
        "ON CONFLICT (goal_key, month) DO UPDATE SET achieved=EXCLUDED.achieved, source=EXCLUDED.source, entered_at=now()",
        (a.goal, a.month, a.achieved, a.source),
    )
    print(f"scored {a.goal} {a.month}: {a.achieved}")
    return 0


def cmd_board(a):
    month = a.month
    if not month:
        month = pg_one("SELECT to_char(current_date, 'YYYY-MM')")
    rows = pg_rows(
        "SELECT g.goal_key, g.product, g.target, s.achieved, g.kind "
        "FROM successbrian_os.monthly_goals g "
        "LEFT JOIN successbrian_os.goal_month_scores s "
        "  ON s.goal_key = g.goal_key AND s.month = (%s || '-01')::date "
        "ORDER BY (g.kind = 'capture') DESC, g.target DESC",
        (month,),
    )
    print(f"Monthly goal board — {month}")
    for key, product, target, achieved, kind in rows:
        state = "NOT REPORTED" if achieved is None else f"{achieved} / {target}"
        tag = " [supply]" if kind == "capture" else ""
        print(f"  {product:18s} target {target:>5d}   {state}{tag}")
    return 0


def cmd_check(_):
    n = pg_one("SELECT count(*) FROM successbrian_os.monthly_goals WHERE kind='paid_conversion'")
    if n != 3:
        print(f"DEFECT: monthly_goals holds {n} paid-conversion goals, expected exactly 3")
        return 1
    cap = pg_one("SELECT target FROM successbrian_os.monthly_goals WHERE goal_key='captures-3000'")
    if cap != 3000:
        print(f"DEFECT: capture goal target is {cap}, expected 3000 (Brian, 2026-11-01)")
        return 1
    bad = pg_one(
        "SELECT count(*) FROM successbrian_os.goal_asset_links "
        "WHERE status='active' AND char_length(fit_note) < %s", (MIN_FIT,))
    if bad:
        print(f"DEFECT: {bad} active link(s) without a real fit reason")
        return 1
    targets = dict(pg_rows("SELECT goal_key, target FROM successbrian_os.monthly_goals WHERE kind='paid_conversion'"))
    if targets != {"gotbackup-40": 40, "oliabo-30": 30, "systeme-50": 50}:
        print(f"DEFECT: paid targets drifted: {targets}")
        return 1
    print("GOAL_DRIVER_OK")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="verb", required=True)
    sub.add_parser("goals").set_defaults(fn=cmd_goals)
    lp = sub.add_parser("link")
    lp.add_argument("--asset-type", required=True)
    lp.add_argument("--asset", required=True)
    lp.add_argument("--goal", required=True)
    lp.add_argument("--fit", required=True)
    lp.add_argument("--source", default="brian")
    lp.set_defaults(fn=cmd_link)
    kp = sub.add_parser("links")
    kp.add_argument("--goal")
    kp.set_defaults(fn=cmd_links)
    up = sub.add_parser("unlink")
    up.add_argument("--asset-type", required=True)
    up.add_argument("--asset", required=True)
    up.add_argument("--goal", required=True)
    up.set_defaults(fn=cmd_unlink)
    sp = sub.add_parser("score")
    sp.add_argument("--goal", required=True)
    sp.add_argument("--month", required=True)
    sp.add_argument("--achieved", type=int, required=True)
    sp.add_argument("--source", required=True)
    sp.set_defaults(fn=cmd_score)
    bp = sub.add_parser("board")
    bp.add_argument("--month")
    bp.set_defaults(fn=cmd_board)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
