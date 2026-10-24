#!/usr/bin/env python3
"""CLI: estimate a topic's visitor potential and store it.

PURPOSE: One command: topic + seed keywords -> keyword expansion -> Trends
    demand -> SERP beatability -> visit-range math -> 50K verdict -> DB.
WHY: This is the answer to Brian's 2026-10-16 question: "how do we determine
    how well the SEO searches will bring us visitors."
CALLED BY: agent on k11. Writes successbrian_os.blog_idea_ranking
    (est_monthly_visits, seo_search_volume, competition_level,
    seo_serp_analysis) and successbrian_os.blog_topics notes.

Usage:
    python3 cli.py estimate "moringa wellness" --seeds moringa,"moringa benefits"
    python3 cli.py estimate "moringa wellness" --seeds moringa --no-db
"""

import argparse
import json
import subprocess
import sys
import time

from estimate import cluster_estimate
from keywords import expand
from serp import analyze
from trends import get_interest


def _db(sql):
    # k11-local psql (this script runs ON k11)
    cmd = ["psql", "-h", "localhost", "-U", "successbrian",
           "-d", "ecosystem_central", "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print("db error: %s" % r.stderr.strip()[:200], file=sys.stderr)
        sys.exit(2)
    return r.stdout.strip()


def cmd_estimate(args):
    topic = args.topic
    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    print("topic: %s" % topic)
    print("expanding keywords...")
    kws = expand(seeds)[:20]
    print("  %d keywords in cluster" % len(kws))

    print("fetching Trends demand (batches of 5)...")
    trends = {}
    for i in range(0, len(kws), 5):
        batch = kws[i:i + 5]
        try:
            trends.update(get_interest(batch))
        except RuntimeError as e:
            print("  trends batch failed: %s" % e)
        time.sleep(2)

    print("analyzing SERPs (this takes a bit)...")
    kw_data = []
    serp_notes = []
    for kw in kws:
        t = trends.get(kw, {"avg": 0})
        try:
            a = analyze(kw)
            band = a["position_band"]
            serp_notes.append("%s: beatability %d (%s)" %
                              (kw, a["beatability"], band))
        except RuntimeError as e:
            print("  serp failed for %r: %s" % (kw, e))
            band = "page1"
            serp_notes.append("%s: serp fetch failed, assumed page1" % kw)
        kw_data.append((kw, t["avg"], band))
        time.sleep(1)

    result = cluster_estimate(topic, kw_data)
    print()
    print("estimated monthly visits: %s - %s (mid %s)" %
          (f"{result['visits_low']:,}", f"{result['visits_high']:,}",
           f"{result['visits_mid']:,}"))
    print("verdict: %s" % result["verdict"])
    print()
    print("top keywords by mid estimate:")
    for k in sorted(result["keywords"], key=lambda x: -x["visits_mid"])[:8]:
        print("  %-38s %7s visits/mo (pos ~%d)" %
              (k["keyword"][:38], f"{k['visits_mid']:,}",
               k["position_assumed"]))

    if args.no_db:
        print("(no-db: skipping database write)")
        return

    # write back to blog_topics (the vetting table Brian uses)
    esc = lambda s: s.replace("'", "''")  # noqa: E731
    _db("UPDATE successbrian_os.blog_topics SET "
        "est_visits_low=%d, est_visits_mid=%d, est_visits_high=%d, "
        "est_verdict='%s', est_scored_at=now(), "
        "notes = notes || ' | SEO estimate %s: %d-%d visits/mo' "
        "WHERE lower(topic) LIKE '%%%s%%';"
        % (result["visits_low"], result["visits_mid"], result["visits_high"],
           esc(result["verdict"]), time.strftime("%Y-%m-%d"),
           result["visits_low"], result["visits_high"],
           esc(topic.lower()[:40])))
    print("wrote estimate to blog_topics: %d-%d visits/mo" %
          (result["visits_low"], result["visits_high"]))

    with open("/tmp/seo_estimate_%s.json" %
              "".join(c if c.isalnum() else "_" for c in topic)[:30],
              "w") as f:
        json.dump(result, f, indent=1)
    print("full result saved to /tmp/seo_estimate_*.json")


def main():
    ap = argparse.ArgumentParser(description="SEO traffic estimator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("estimate", help="estimate a topic's visitor range")
    p.add_argument("topic")
    p.add_argument("--seeds", required=True,
                   help="comma-separated seed keywords")
    p.add_argument("--no-db", action="store_true",
                   help="skip database write")
    p.set_defaults(func=cmd_estimate)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
