#!/usr/bin/env python3
"""Atlas keystone digest — the searchable view of the model.

Brian, 2026-10-21: keystones and initiatives must be integrated into
PostgreSQL, CampaignsDesk, AnythingLLM, and the other systems. Atlas
(PostgreSQL) is authoritative; this digest is the readable rendering
other systems consume: it is written into the AnythingLLM ingest
tree (the pattern of the 2026-10-15 ingest) so the workspaces can
index it, and regenerated on demand.

Sources (single source of truth = PostgreSQL):
  atlas.keystones_v    gates / projects / plans / candidates
  atlas.initiatives_v  initiatives + their graph link state

Upload into AnythingLLM proper rides the decision_sync pattern and
needs ANYTHINGLLM_API_KEY (see tools/decision_sync/sync.py notes);
until then the digest lives in the ingest tree like the Oct-15 docs.

Usage: python3 keystone_digest.py [--out PATH]
"""

import argparse
import subprocess
import sys
from datetime import datetime

PSQL = ["psql", "-h", "localhost", "-U", "postgres", "-d",
        "ecosystem_central", "-t", "-A", "-F", "|"]
DEFAULT_OUT = ("/home/successbrian/anythingllm-ingest-20261015/"
               "atlas-keystones/atlas-keystones.md")


def q(sql):
    p = subprocess.run(PSQL + ["-c", sql], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("psql: " + p.stderr.strip())
    return [ln.split("|") for ln in p.stdout.split("\n") if ln]


def build():
    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    out = ["# Atlas — Keystones & Initiatives",
           "",
           "Generated %s by tools/atlas/keystone_digest.py. "
           "Authoritative source: PostgreSQL (atlas.keystones_v, "
           "atlas.initiatives_v). Keystones are the top-level things "
           "(gates, projects, plans, register systems/lines) that need "
           "healthy states; initiatives are the actions that move or "
           "operate them." % ts,
           ""]
    out.append("## Pending gates")
    for (name,) in q("SELECT name FROM atlas.keystones_v "
                     "WHERE kind='gate' AND status='pending' "
                     "ORDER BY node_key"):
        out.append("- %s" % name)
    out.append("")
    out.append("## Keystone counts")
    for kind, status, n in q(
            "SELECT kind, status, count(*) FROM atlas.keystones_v "
            "GROUP BY 1, 2 ORDER BY 1, 2"):
        out.append("- %s / %s: %s" % (kind, status, n))
    out.append("")
    out.append("## Candidate keystones & initiatives (proposed)")
    for name, kind, evidence in q(
            "SELECT name, details->>'kind', details->>'evidence' "
            "FROM atlas.nodes WHERE node_type='candidate' "
            "AND status='proposed' ORDER BY node_key"):
        out.append("- **%s** (%s) — %s" % (name, kind, evidence))
    out.append("")
    out.append("## Initiatives and their keystone links")
    for name, itype, status, link, match in q(
            "SELECT name, type, status, "
            "COALESCE(legacy_graph_name, 'UNLINKED'), "
            "COALESCE(atlas_match_by_name, '') "
            "FROM atlas.initiatives_v ORDER BY name"):
        extra = ("; Atlas name match: %s" % match) if match else ""
        out.append("- **%s** (%s, %s) — serves: %s%s"
                   % (name, itype, status, link, extra))
    out.append("")
    out.append("## Staff health flags (open)")
    rows = q("SELECT name FROM atlas.nodes "
             "WHERE node_key LIKE 'task:discovery:staff:%' "
             "AND status IN ('open','queued') ORDER BY node_key")
    if rows:
        for (name,) in rows:
            out.append("- %s" % name)
    else:
        out.append("- none")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    text = build()
    if a.out == "-":
        print(text)
        return 0
    import os
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w").write(text)
    print("wrote %s (%d chars)" % (a.out, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
