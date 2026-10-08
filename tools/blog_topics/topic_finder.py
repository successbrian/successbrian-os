#!/usr/bin/env python3
"""Blog topic finder for Brian's 100-blog network.

PURPOSE:
    Score candidate blog niches against Brian's triage criteria so the right
    topics get built first: (1) hit hard and fast, (2) easy for Brian to get
    into, (3) not gated. Gated topics (e.g. Le-Vel-dependent) go to a gated
    queue — presented separately, never discarded, never mixed into the
    ungated ranking.

WHY:
    Brian 2026-10-08: "we need coded logic to help us find the right blog
    topics." His rules: blogs are niche lead magnets (never personal promo);
    Le-Vel-dependent blogs wait in a gated queue; affiliate lanes must not
    compete with MLM products (graph, not tree); present ungated, queue gated.

CALLED BY:
    CLI (`python3 topic_finder.py <command>`) run by an agent. Scoring is
    deterministic — no model calls.

NOTES:
    - DB: successbrian_os.blog_topics on k11 Postgres.
    - Gate check reads successbrian_os.aff_competition_graph.is_gated for the
      topic's mlm_company (Le-Vel = gated until corporate compliance lifts).
    - Affiliate lane check reuses the competition-graph logic: flags if the
      lane shares an edge with any MLM product.
    - Score = (demand x 2) + speed + ease (each high/fast=3, medium=2,
      low/slow=1). Demand is double-weighted per Brian 2026-10-08: "if the
      ease is low, but the seriousness is unbelievable i learn it."
      Max score 12.
"""

import argparse
import os
import subprocess
import sys

KSSH = os.path.expanduser("~/workspace/bin/kssh")

SCORE_MAP = {"high": 3, "medium": 2, "low": 1,
             "fast": 3, "slow": 1}


def _rows(sql):
    cmd = ("psql -h localhost -U successbrian -d ecosystem_central"
           " -t -A -F '|' -c \"%s\"" % sql.replace('"', '\\"'))
    out = subprocess.run(["bash", KSSH, cmd],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        print("db error: %s" % out.stderr.strip()[:200], file=sys.stderr)
        sys.exit(2)
    return [l for l in out.stdout.splitlines() if l.strip()]


def _psql(sql, params):
    _rows(sql)  # params inlined by caller via :'name' psql variables
    # simple version: caller builds full SQL safely (internal tool)


def cmd_init_db(_args):
    schema = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "schema.sql")).read()
    _rows(schema.replace("\n", " "))
    print("blog_topics table ready")


def _is_gated(mlm_company):
    """True if the company has any gated product in the competition graph."""
    if not mlm_company:
        return False
    rows = _rows(
        "SELECT COUNT(*) FROM successbrian_os.aff_competition_graph"
        " WHERE LOWER(mlm_company) = LOWER('%s') AND is_gated = true;"
        % mlm_company.replace("'", "''"))
    return rows and rows[0].split("|")[0].strip() != "0"


def _lane_competes(affiliate_lane):
    """Return list of competing MLM products for a proposed affiliate lane."""
    if not affiliate_lane:
        return []
    lane = affiliate_lane.lower()
    hits = []
    for r in _rows("SELECT mlm_product, mlm_company, competes_with"
                   " FROM successbrian_os.aff_competition_graph;"):
        prod, comp, cw = (r.split("|") + ["", "", ""])[:3]
        if cw.lower() in lane or lane in cw.lower():
            hits.append("%s (%s)" % (prod, comp))
    return hits


def cmd_score(_args):
    """Score all candidate topics; set gated status; compute scores."""
    topics = _rows("SELECT id, topic, demand, speed, brian_ease,"
                   " mlm_product, mlm_company, affiliate_lane"
                   " FROM successbrian_os.blog_topics"
                   " WHERE status = 'candidate';")
    scored, gated = 0, 0
    for t in topics:
        tid, topic, demand, speed, ease, prod, comp, lane = \
            (t.split("|") + [""] * 8)[:8]
        if _is_gated(comp):
            _rows("UPDATE successbrian_os.blog_topics SET status='gated',"
                  " gated_reason='MLM company %s is gated'"
                  " WHERE id=%s;" % (comp.replace("'", "''"), tid))
            gated += 1
            continue
        # Demand double-weighted: unbelievable seriousness beats low ease
        # (Brian 2026-10-08: "if the ease is low, but the seriousness is
        # unbelievable i learn it")
        s = (SCORE_MAP.get(demand, 2) * 2 + SCORE_MAP.get(speed, 2) +
             SCORE_MAP.get(ease, 2))
        lane_flag = ""
        hits = _lane_competes(lane)
        if hits:
            lane_flag = " | LANE CONFLICT: %s" % "; ".join(hits)
        _rows("UPDATE successbrian_os.blog_topics SET score=%d,"
              " status='candidate', gated_reason=''"
              " WHERE id=%s;" % (s, tid))
        scored += 1
        if lane_flag:
            print("  ! %s:%s" % (topic, lane_flag))
    print("scored %d ungated, %d moved to gated queue" % (scored, gated))


def cmd_list(_args):
    """Show ranked ungated topics (Brian sees these)."""
    rows = _rows("SELECT topic, niche, score, demand, speed, brian_ease,"
                 " mlm_product, affiliate_lane FROM successbrian_os.blog_topics"
                 " WHERE status = 'candidate' ORDER BY score DESC, topic;")
    if not rows:
        print("no ungated candidates -- add topics first")
        return
    print("%-32s %5s %-8s %-8s %-8s %s" %
          ("topic", "score", "demand", "speed", "ease", "funnels to"))
    for r in rows:
        f = (r.split("|") + [""] * 8)[:8]
        print("%-32s %5s %-8s %-8s %-8s %s" %
              (f[0][:32], f[2], f[3], f[4], f[5], f[6] or "-"))
    print("(%d ungated topics)" % len(rows))


def cmd_gated(_args):
    """Show the gated queue (held, not discarded)."""
    rows = _rows("SELECT topic, mlm_company, gated_reason"
                 " FROM successbrian_os.blog_topics"
                 " WHERE status = 'gated' ORDER BY topic;")
    if not rows:
        print("gated queue empty")
        return
    for r in rows:
        f = (r.split("|") + ["", "", ""])[:3]
        print("  %-32s [%s] %s" % (f[0][:32], f[1], f[2]))
    print("(%d gated, waiting for gates to lift)" % len(rows))


def cmd_add(args):
    _rows("INSERT INTO successbrian_os.blog_topics"
          " (topic, niche, demand, speed, brian_ease,"
          "  mlm_product, mlm_company, affiliate_lane, notes)"
          " VALUES ('%s','%s','%s','%s','%s','%s','%s','%s','%s')"
          " ON CONFLICT (topic) DO UPDATE SET"
          " niche=EXCLUDED.niche, demand=EXCLUDED.demand,"
          " speed=EXCLUDED.speed, brian_ease=EXCLUDED.brian_ease,"
          " mlm_product=EXCLUDED.mlm_product, mlm_company=EXCLUDED.mlm_company,"
          " affiliate_lane=EXCLUDED.affiliate_lane, notes=EXCLUDED.notes,"
          " status='candidate', gated_reason='';"
          % tuple(a.replace("'", "''") for a in
                  [args.topic, args.niche or "", args.demand or "medium",
                   args.speed or "medium", args.ease or "medium",
                   args.mlm_product or "", args.mlm_company or "",
                   args.affiliate_lane or "", args.notes or ""]))
    print("topic upserted: %s (run score next)" % args.topic)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="create the blog_topics table") \
        .set_defaults(func=cmd_init_db)
    sub.add_parser("score",
                   help="score candidates; move gated to gated queue") \
        .set_defaults(func=cmd_score)
    sub.add_parser("list", help="ranked ungated topics (what Brian sees)") \
        .set_defaults(func=cmd_list)
    sub.add_parser("gated", help="show the gated queue") \
        .set_defaults(func=cmd_gated)

    p = sub.add_parser("add", help="add or update a candidate topic")
    p.add_argument("topic")
    p.add_argument("--niche", default="")
    p.add_argument("--demand", choices=["high", "medium", "low"],
                   default="medium")
    p.add_argument("--speed", choices=["fast", "medium", "slow"],
                   default="medium")
    p.add_argument("--ease", choices=["high", "medium", "low"],
                   default="medium")
    p.add_argument("--mlm-product", default="")
    p.add_argument("--mlm-company", default="")
    p.add_argument("--affiliate-lane", default="")
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_add)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
