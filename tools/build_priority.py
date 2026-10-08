#!/usr/bin/env python3
"""
build_priority.py — Rank what Brian should build first.

PURPOSE: Deterministic build prioritization for the SuccessBrian ecosystem. Scores open
         build candidates from successbrian_os.build_candidates and writes the ranked list
         to successbrian_os.build_ranking. Spencer reads the ranking and brings the top
         item to Brian one at a time.
WHY: Brian 2026-10-07: "i want YOU to build it. we are not going to keep asking dealsdesk
     to code. we need code. we are moving to having YOU and a Coding Box." DealsDesk is out
     of the coding loop; this tool (running on the Coding Box) owns the ranking.
     The weights encode Brian's philosophy: money first, unblocking second, effort last.
     Factor scores are set by whoever proposes the candidate (judgment); the math is
     deterministic (no judgment). New candidates go in the table — never in this code.
CALLED BY: Spencer directly; eventually a Coding Box cron (daily). Reads
           successbrian_os.build_candidates, writes successbrian_os.build_ranking.
NOTES: Score = 3*revenue_proximity + 2*unblocks + 2*directive_alignment + 1*effort_inverse
       (max 80). revenue_proximity: how directly it leads to money. unblocks: downstream
       work it unlocks. directive_alignment: matches Brian's explicit directives.
       effort_inverse: 10 = trivial, 0 = massive. Only status='open' candidates are ranked.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone

WEIGHTS = {
    "revenue_proximity": 3,
    "unblocks": 2,
    "directive_alignment": 2,
    "effort_inverse": 1,
}

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A"]


def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"psql failed: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def main():
    rows = q(
        "SELECT id, title, revenue_proximity, unblocks, directive_alignment, effort_inverse "
        "FROM successbrian_os.build_candidates WHERE status='open' ORDER BY id;"
    )
    if not rows:
        print("no open candidates")
        return 0

    scored = []
    for line in rows.splitlines():
        cid, title, rev, unb, dirc, eff = line.split("|")
        factors = {
            "revenue_proximity": int(rev),
            "unblocks": int(unb),
            "directive_alignment": int(dirc),
            "effort_inverse": int(eff),
        }
        score = sum(factors[k] * WEIGHTS[k] for k in WEIGHTS)
        scored.append((score, int(cid), title, factors))
    scored.sort(reverse=True)

    ranked_at = datetime.now(timezone.utc).isoformat()
    for rank, (score, cid, title, factors) in enumerate(scored, 1):
        breakdown = json.dumps({"factors": factors, "weights": WEIGHTS}).replace("'", "''")
        q(
            "INSERT INTO successbrian_os.build_ranking (ranked_at, rank, candidate_id, score, breakdown) "
            f"VALUES ('{ranked_at}', {rank}, {cid}, {score:.2f}, '{breakdown}');"
        )
        print(f"{rank}. [{score:.0f}] {title}")

    print(f"ranked {len(scored)} candidates at {ranked_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
