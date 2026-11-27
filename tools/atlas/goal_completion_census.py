#!/usr/bin/env python3
"""goal_completion_census.py — per-goal completion census (gap C6,
QA 800 / friction #69).

QA 800 fails, correctly, while any goal sits at progress_pct>=100
without a terminal status: 47 such goals at build time, and the
100 reads as a registration default, not a measurement. Nobody may
bulk-edit them away (adjudication runs through harness looks, one
goal at a time) — but adjudication was starved of evidence. This
census is the evidence: for every claimed-complete goal it joins
the harness record (looks, movements, decompositions, stalls) and
classifies what the record supports:

  evidence-complete   decompositions exist, all steps done, and
                      movements record completions — a harness
                      confirmation look can close this honestly.
  looked-no-completion looks happened but 0 completions ever —
                      the 100 is contradicted by the movement
                      record; needs a re-look / retarget.
  active-not-done     recent movement with work still queued —
                      progress claim is stale, not terminal.
  never-looked        no looks, no decompositions, no movements —
                      the 100 was never measured; registration
                      default suspected.

Output: successbrian_os.goal_completion_census (one snapshot row
per goal per run) + a markdown report in
tools/atlas/cycle_reviews/. The census changes NO goal state.

--check mode (for QA): exit 0 iff a census snapshot exists from
the last 40 days. Cron: monthly, 06:40 on the 1st.
"""
import argparse
import json
import os
import sys

import psycopg2

OUT_DIR = os.path.expanduser(
    "~/successbrian-os/tools/atlas/cycle_reviews")

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.goal_completion_census (
    id serial PRIMARY KEY,
    run_at timestamptz NOT NULL DEFAULT now(),
    goal_slug text NOT NULL,
    goal_name text,
    progress_pct integer,
    status text,
    class text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb
)
"""


def classify(ev):
    if (ev["plans"] > 0 and ev["steps_total"] > 0
            and ev["steps_done"] >= ev["steps_total"]
            and ev["completed"] > 0):
        return "evidence-complete"
    if ev["looks"] == 0 and ev["plans"] == 0:
        return "never-looked"
    if ev["recent_queued"] > 0:
        return "active-not-done"
    return "looked-no-completion"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = psycopg2.connect(dbname="ecosystem_central")
    cur = conn.cursor()
    cur.execute(DDL)
    if args.check:
        cur.execute("""SELECT count(*) FROM
            successbrian_os.goal_completion_census
            WHERE run_at > now() - interval '40 days'""")
        n = cur.fetchone()[0]
        print(f"CENSUS_FRESH rows={n}" if n else "CENSUS_STALE")
        return 0 if n else 1
    cur.execute("""
        SELECT coalesce(g.goal_slug, 'name:' || g.goal_name), g.goal_name, g.progress_pct, g.status,
               coalesce(m.looks,0), coalesce(m.completed,0),
               coalesce(m.queued_recent,0),
               coalesce(d.plans,0), coalesce(d.steps_total,0),
               coalesce(d.steps_done,0),
               h.stall_count
        FROM successbrian_os.sbos_goals g
        LEFT JOIN (SELECT goal_slug, count(*) looks,
                          sum(completed) completed,
                          sum(case when measured_at > now()
                              - interval '28 days'
                              then queued else 0 end) queued_recent
                   FROM successbrian_os.harness_movements
                   GROUP BY 1) m ON m.goal_slug = g.goal_slug
        LEFT JOIN (SELECT goal_slug, count(*) plans,
                          sum(steps_total) steps_total,
                          sum(steps_done) steps_done
                   FROM successbrian_os.plan_decompositions
                   GROUP BY 1) d ON d.goal_slug = g.goal_slug
        LEFT JOIN successbrian_os.goal_harness_state h
               ON h.goal_slug = g.goal_slug
        WHERE g.progress_pct >= 100
          AND g.status NOT IN ('done','completed','closed')
        ORDER BY g.goal_slug""")
    rows = cur.fetchall()
    counts = {}
    report = ["# Goal completion census — progress_pct>=100, "
              "no terminal status", ""]
    for r in rows:
        ev = {"looks": r[4], "completed": int(r[5] or 0),
              "recent_queued": int(r[6] or 0), "plans": r[7],
              "steps_total": int(r[8] or 0),
              "steps_done": int(r[9] or 0),
              "stall_count": r[10]}
        cls = classify(ev)
        counts[cls] = counts.get(cls, 0) + 1
        report.append(f"- **{r[0]}** ({r[1]}): status={r[3]}, "
                      f"class={cls}, evidence={json.dumps(ev)}")
        if not args.dry_run:
            cur.execute(
                """INSERT INTO successbrian_os.goal_completion_census
                   (goal_slug, goal_name, progress_pct, status,
                    class, evidence)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
                (r[0], r[1], r[2], r[3], cls, json.dumps(ev)))
    if not args.dry_run:
        conn.commit()
        os.makedirs(OUT_DIR, exist_ok=True)
        from datetime import date
        path = os.path.join(
            OUT_DIR, f"completion-census-{date.today().isoformat()}.md")
        with open(path, "w") as fh:
            fh.write("\n".join(report) + "\n")
    print(f"census: {len(rows)} claimed-complete goals classified: "
          + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
