#!/usr/bin/env python3
"""Affiliate competition graph checker.

PURPOSE:
    Before recommending an affiliate product for Brian's blogs, check whether
    its category competes with any MLM product he sells (or may sell).
    Competition is a GRAPH, not a tree — products compete by actual similarity,
    not by sharing a broad category. MyFreshMeals (meal delivery) does NOT
    compete with Slimmer (botanical supplement).

WHY:
    Brian 2026-10-08: "I dont want affiliate products to directly compete with
    a known or potential known mlm product." He also said "remember graph not
    tree" after Spencer incorrectly lumped MyFreshMeals and Slimmer together.
    This hard-codes the graph so the mistake can't repeat.

CALLED BY:
    CLI (`python3 check_competition.py "<category>"`) run by an agent before
    recommending affiliate products. Returns exit 0 if clear, exit 1 if it
    competes (with details).

NOTES:
    - DB: successbrian_os.aff_competition_graph on k11 Postgres.
    - Matching is substring-based and deliberately broad: if the affiliate
      category contains any competes_with phrase (or vice versa), it flags.
      When in doubt, it flags — Brian decides, not the script.
    - Gated MLM products (Le-Vel) still count as competition: even though
      Brian can't promote them now, he may later, so affiliates must not
      undercut that future lane.
"""

import os
import subprocess
import sys

KSSH = os.path.expanduser("~/workspace/bin/kssh")


def _psql(sql):
    out = subprocess.run(
        [KSSH, "psql -h localhost -U successbrian -d ecosystem_central -t -A -F '|' -c \"%s\"" % sql],
        capture_output=True, text=True, shell=False)
    # kssh takes the full command as one arg
    return out


def _rows(sql):
    # shell out via bash -c to keep quoting simple
    cmd = "%s %s" % (KSSH, subprocess.list2cmdline(
        ["psql", "-h", "localhost", "-U", "successbrian", "-d",
         "ecosystem_central", "-t", "-A", "-F", "|", "-c", sql]))
    out = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        print("db error: %s" % out.stderr.strip()[:200], file=sys.stderr)
        sys.exit(2)
    return [l for l in out.stdout.splitlines() if l.strip()]


def check(category):
    """Return list of (mlm_product, company, competes_with, gated) hits."""
    cat = category.lower()
    hits = []
    for r in _rows("SELECT mlm_product, mlm_company, competes_with, is_gated"
                   " FROM successbrian_os.aff_competition_graph;"):
        prod, comp, cw, gated = (r.split("|") + ["", "", "", ""])[:4]
        cw_low = cw.lower()
        if cw_low in cat or cat in cw_low:
            hits.append((prod, comp, cw, gated == "t"))
    return hits


def main():
    if len(sys.argv) < 2:
        print("usage: check_competition.py \"<affiliate product category>\"")
        sys.exit(2)
    category = sys.argv[1]
    hits = check(category)
    if not hits:
        print("CLEAR: '%s' does not compete with any MLM product." % category)
        sys.exit(0)
    print("COMPETES: '%s' hits %d edge(s):" % (category, len(hits)))
    for prod, comp, cw, gated in hits:
        print("  - %s (%s) vs '%s'%s" %
              (prod, comp, cw, " [GATED]" if gated else ""))
    print("Do not affiliate this category.")
    sys.exit(1)


if __name__ == "__main__":
    main()
