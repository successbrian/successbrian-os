#!/usr/bin/env python3
"""Pick audience channels to focus on, log weekly numbers, get a growth report.

WHY:
    A home-business entrepreneur's scarcest resource is attention. This
    module makes the audience-building loop explicit and measurable: the
    entrepreneur declares which channels matter (focus), records one number
    per channel per week, and gets a deterministic week-over-week report.
    No model ever decides where effort goes; the report only proposes, by
    ranking what actually grew, and the entrepreneur decides.
    (Brian 2026-10-02: successbrian-os should help the entrepreneur choose
    focus channels, grow them, and track weekly growth.)

CALLED BY:
    CLI (`python3 audience.py <command>`) run by an agent session or the
    entrepreneur directly. A weekly cron can call `report` to feed the
    digest/outbox. Importable as a library too.

NOTES:
    - CANONICAL: successbrian-os/tools/audience/
    - DB: successbrian_os.audience_channels + audience_snapshots (+ the
      audience_weekly_growth view). Runs against the k11 Postgres the same
      way tools/ventures does (localhost psql from k11).
    - week_start is any date; the report treats it as "the week of".
      Consecutive rows per channel drive the deltas, so log weekly.
    - audience_size means subscribers/followers/email subs depending on
      the channel kind -- one comparable number per channel.
    - Never invents numbers: channels with a single logged week show as
      baseline (no delta) until a second week exists.
"""

import argparse
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

import os, sys
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


def cmd_init_db(_args):
    _psql(open(os.path.join(HERE, "schema.sql")).read())
    print("audience schema ready")


def cmd_add_channel(args):
    _psql(
        "INSERT INTO successbrian_os.audience_channels"
        " (slug, name, kind, url, notes) VALUES"
        " (:'slug', :'name', :'kind', :'url', :'notes')"
        " ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name,"
        " kind=EXCLUDED.kind, url=EXCLUDED.url, notes=EXCLUDED.notes;",
        {"slug": args.slug, "name": args.name, "kind": args.kind,
         "url": args.url or "", "notes": args.notes or ""})
    print("channel upserted: %s" % args.slug)


def cmd_list_channels(_args):
    rows = _rows(
        "SELECT slug, name, kind,"
        " CASE WHEN is_focus THEN 'FOCUS#' || focus_rank ELSE '-' END"
        " FROM successbrian_os.audience_channels ORDER BY is_focus DESC,"
        " focus_rank, slug;")
    if not rows:
        print("no channels yet -- add_channel first")
        return
    for r in rows:
        slug, name, kind, focus = r.split("\t")
        print("%-14s %-28s %-10s %s" % (slug, name, kind, focus))


def cmd_set_focus(args):
    """Mark an ordered list of channel slugs as the focus set.

    Order = priority. Everything not listed leaves the focus set.
    """
    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
    _psql("UPDATE successbrian_os.audience_channels"
          " SET is_focus=FALSE, focus_rank=0;")
    for rank, slug in enumerate(slugs, start=1):
        out = _psql(
            "UPDATE successbrian_os.audience_channels"
            " SET is_focus=TRUE, focus_rank=:'rank'::int"
            " WHERE slug=:'slug' RETURNING slug;",
            {"slug": slug, "rank": str(rank)}).strip()
        if not out:
            print("WARNING: unknown channel slug '%s' -- skipped" % slug)
    print("focus set: %s" % (", ".join(slugs) or "(none)"))


def cmd_log(args):
    """Log one weekly snapshot: audience size + posts published."""
    out = _psql(
        "INSERT INTO successbrian_os.audience_snapshots"
        " (channel_id, week_start, audience_size, posts_published, notes)"
        " SELECT id, :'week'::date, :'size'::int, :'posts'::int, :'notes'"
        " FROM successbrian_os.audience_channels WHERE slug=:'slug'"
        " ON CONFLICT (channel_id, week_start) DO UPDATE SET"
        " audience_size=EXCLUDED.audience_size,"
        " posts_published=EXCLUDED.posts_published,"
        " notes=EXCLUDED.notes RETURNING id;",
        {"slug": args.slug, "week": args.week, "size": str(args.size),
         "posts": str(args.posts), "notes": args.notes or ""}).strip()
    if not out:
        raise SystemExit("unknown channel slug '%s'" % args.slug)
    print("logged %s week %s: size=%d posts=%d"
          % (args.slug, args.week, args.size, args.posts))


def _latest_week():
    out = _psql("SELECT max(week_start)"
                " FROM successbrian_os.audience_snapshots;").strip()
    return out or None


def cmd_report(args):
    """Deterministic weekly growth report. Focus channels first, then rest.

    The closing SUGGESTION only ranks observed growth -- it never decides
    where effort goes. The entrepreneur decides.
    """
    week = args.week or _latest_week()
    if not week:
        print("no snapshots logged yet")
        return
    rows = _rows(
        "SELECT slug, name, is_focus, focus_rank, audience_size,"
        " posts_published, prev_size, delta, pct_change"
        " FROM successbrian_os.audience_weekly_growth"
        " WHERE week_start=:'week'::date"
        " ORDER BY is_focus DESC, focus_rank, slug;",
        {"week": week})
    base = _rows(
        "SELECT c.slug FROM successbrian_os.audience_channels c"
        " JOIN successbrian_os.audience_snapshots s"
        " ON s.channel_id=c.id AND s.week_start=:'week'::date"
        " LEFT JOIN successbrian_os.audience_weekly_growth g"
        " ON g.slug=c.slug AND g.week_start=:'week'::date"
        " WHERE g.slug IS NULL"
        " ORDER BY c.is_focus DESC, c.focus_rank;",
        {"week": week})
    print("audience growth -- week of %s" % week)
    print("-" * 64)
    if not rows and not base:
        print("no channels registered")
        return
    grown = []
    for r in rows:
        (slug, name, is_focus, rank, size, posts,
         prev, delta, pct) = r.split("\t")
        tag = ("FOCUS#%s" % rank) if is_focus == "t" else "      "
        arrow = "+" if int(delta) > 0 else ""
        print("%s %-14s %6s (%s%5s, %6s%%) posts=%s" % (
            tag, slug, size, arrow, delta,
            pct if pct else "n/a", posts))
        if is_focus == "t":
            eff = (int(delta) / int(posts)) if int(posts) > 0 else None
            grown.append((slug, int(delta), eff))
    for slug in base:
        print("       %-14s first week logged (deltas start next week)"
              % slug)
    print("-" * 64)
    if grown:
        grown.sort(key=lambda g: g[1], reverse=True)
        top = grown[0]
        print("SUGGESTION (proposes only): '%s' grew most this week"
              " (+%d). The entrepreneur decides where effort goes."
              % (top[0], top[1]))
    else:
        print("SUGGESTION: not enough focus-channel history yet --"
              " log weekly and the ranking appears on its own.")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Audience builder: focus channels + weekly growth.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init_db")

    p = sub.add_parser("add_channel")
    p.add_argument("--slug", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--kind", default="other",
                   choices=["newsletter", "blog", "video", "short_video",
                            "social", "email", "podcast", "community",
                            "other"])
    p.add_argument("--url", default="")
    p.add_argument("--notes", default="")

    sub.add_parser("list_channels")

    p = sub.add_parser("set_focus")
    p.add_argument("--slugs", required=True,
                   help="comma-separated, in priority order")

    p = sub.add_parser("log")
    p.add_argument("--slug", required=True)
    p.add_argument("--week", required=True, help="YYYY-MM-DD")
    p.add_argument("--size", required=True, type=int,
                   help="audience size: subs/followers")
    p.add_argument("--posts", default=0, type=int)
    p.add_argument("--notes", default="")

    p = sub.add_parser("report")
    p.add_argument("--week", default=None, help="YYYY-MM-DD, default latest")

    args = ap.parse_args(argv)
    {"init_db": cmd_init_db, "add_channel": cmd_add_channel,
     "list_channels": cmd_list_channels, "set_focus": cmd_set_focus,
     "log": cmd_log, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
