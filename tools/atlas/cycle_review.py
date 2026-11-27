#!/usr/bin/env python3
"""cycle_review.py — goal cycle-review producer (gap C6, QA 422).

The goal harness looks at goals continuously, but nothing ever
stepped back and wrote a CYCLE REVIEW: score vs target, stage
conversion, and improvement tasks drafted into the next cycle.
QA 422 asked for exactly that artifact and failed from birth
because no producer existed.

For each goal with harness movements in the cycle window
(default 28 days), this writes a review built ONLY from measured
record — sbos_goals (score/target), harness_movements (stage
conversion), plan_decompositions (plan progress), einstein_passes
(latest look), goal_harness_state (stalls) — persists it to
successbrian_os.goal_cycle_reviews + a markdown file in
tools/atlas/cycle_reviews/, and drafts the improvement tasks the
review's own numbers call for as pm_steps (kind 'task',
origin 'cycle-review', deduped by step_key). It never edits goal
status or progress — adjudication stays with the harness and
Brian (friction #69 discipline).

Cron (weekly, keeps a review inside QA 422's 35-day freshness):
  10 7 * * 1 flock -n /tmp/cycle-review.lock \
    /usr/bin/python3 ~/successbrian-os/tools/atlas/cycle_review.py \
    >> ~/logs/cycle-review.log 2>&1

CLI: run (default, top --limit goals) / --dry-run / --goal SLUG
"""
import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
import psycopg2  # noqa: E402
import pm_core  # noqa: E402

OUT_DIR = os.path.expanduser(
    "~/successbrian-os/tools/atlas/cycle_reviews")
WINDOW_DAYS = 28

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.goal_cycle_reviews (
    id serial PRIMARY KEY,
    goal_slug text NOT NULL,
    cycle_start date NOT NULL,
    cycle_end date NOT NULL,
    review_md text NOT NULL,
    tasks_filed jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""


def q(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchall()


def build_review(cur, slug, window):
    g = q(cur, """SELECT goal_name, category, priority, status,
                         progress_pct, target_date, success_metrics,
                         current_revenue, current_month_deals
                  FROM successbrian_os.sbos_goals
                  WHERE goal_slug=%s""", (slug,))[0]
    mv = q(cur, """SELECT count(*), coalesce(sum(completed),0),
                          coalesce(sum(failed),0),
                          coalesce(sum(running),0),
                          coalesce(sum(queued),0),
                          coalesce(sum(stuck),0),
                          max(measured_at)
                   FROM successbrian_os.harness_movements
                   WHERE goal_slug=%s
                     AND measured_at > now() - %s::interval""",
           (slug, f"{window} days"))[0]
    looks, done, failed, running, queued, stuck, last_mv = mv
    dec = q(cur, """SELECT count(*), coalesce(sum(steps_total),0),
                           coalesce(sum(steps_done),0)
                    FROM successbrian_os.plan_decompositions
                    WHERE goal_slug=%s""", (slug,))[0]
    plans, steps_total, steps_done = dec
    st = q(cur, """SELECT stall_count, last_progress_at, tier
                   FROM successbrian_os.goal_harness_state
                   WHERE goal_slug=%s""", (slug,))
    stall_count, last_progress, tier = st[0] if st else (None, None, "?")
    ep = q(cur, """SELECT plan_text, collected_at
                   FROM successbrian_os.einstein_passes
                   WHERE goal_slug=%s AND plan_text IS NOT NULL
                   ORDER BY collected_at DESC NULLS LAST LIMIT 1""",
           (slug,))
    metrics = g[6] if isinstance(g[6], dict) else {}
    conv = (f"{done} completed / {failed} failed / {running} running "
            f"/ {queued} queued / {stuck} stuck across {looks} looks")
    share = (f"{100.0 * done / max(done + failed, 1):.0f}% of decided "
             f"steps completed") if (done + failed) else \
            "no step reached a decision in the window"
    lines = [
        f"# Cycle review — {g[0]} ({slug})",
        f"Cycle: last {window} days, ending {date.today().isoformat()}. "
        f"Tier {tier}; priority {g[2]}; status {g[3]}.",
        "",
        "## Score vs target",
        f"- Claimed progress: {g[4]}% (target date {g[5]}).",
        f"- Success metrics on record: "
        f"{json.dumps(metrics) if metrics else 'none recorded'}.",
        f"- Revenue on record: current_revenue={g[7]}, "
        f"current_month_deals={g[8]} (NULL = not reported).",
        "",
        "## Stage conversion (harness movements, measured)",
        f"- {conv}; last movement {last_mv}.",
        f"- Conversion: {share}.",
        f"- Plan decompositions: {plans} plan(s), {steps_done}/"
        f"{steps_total} steps done.",
        f"- Stall count: {stall_count}; last verified progress: "
        f"{last_progress}.",
    ]
    if ep:
        excerpt = (ep[0][0] or "")[:600].replace("\n", " ")
        lines += ["", "## Latest Einstein look (excerpt)",
                  f"- {excerpt}"]
    tasks = []
    if done == 0 and looks >= 2:
        tasks.append((
            "replan",
            f"Cycle review: {slug} had {looks} looks and 0 verified "
            f"completions this cycle — replan via an Einstein look "
            "with decomposition review before more steps queue."))
    if queued and queued >= 20:
        tasks.append((
            "queue-triage",
            f"Cycle review: {slug} carries {queued} queued steps — "
            "oldest-first disposition pass so new work is not buried "
            "under stale steps."))
    if (g[4] or 0) >= 100 and g[3] not in ("done", "completed",
                                           "closed"):
        tasks.append((
            "adjudicate-100",
            f"Cycle review: {slug} claims progress_pct={g[4]} with "
            f"non-terminal status '{g[3]}' while movements show "
            f"{done} completions — adjudicate against the completion "
            "census evidence (friction #69); do not bulk-edit."))
    if stall_count and stall_count >= 2:
        tasks.append((
            "stall-break",
            f"Cycle review: {slug} stall_count={stall_count} — "
            "surface the blocker in the next harness look."))
    if not tasks:
        tasks.append((
            "continue",
            f"Cycle review: {slug} is converting ({share}); no "
            "structural improvement task this cycle — keep cadence."))
    lines += ["", "## Improvement tasks drafted into the next cycle"]
    for kind, title in tasks:
        lines.append(f"- [{kind}] {title}")
    return "\n".join(lines) + "\n", tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--goal")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--window", type=int, default=WINDOW_DAYS)
    args = ap.parse_args()
    conn = psycopg2.connect(dbname="ecosystem_central")
    cur = conn.cursor()
    if args.goal:
        slugs = [args.goal]
    else:
        slugs = [r[0] for r in q(cur, """
            SELECT goal_slug FROM successbrian_os.harness_movements
            WHERE measured_at > now() - %s::interval
            GROUP BY 1 ORDER BY count(*) DESC LIMIT %s""",
            (f"{args.window} days", args.limit))]
    if not slugs:
        print("cycle-review: no goals with movements in window")
        return 0
    if not args.dry_run:
        cur.execute(DDL)
        os.makedirs(OUT_DIR, exist_ok=True)
    for slug in slugs:
        review, tasks = build_review(cur, slug, args.window)
        filed = []
        if not args.dry_run:
            for kind, title in tasks:
                key = (f"cycle-review-{slug}-"
                       f"{date.today().isoformat()}-{kind}")
                pm_core.add_step(
                    cur, key, title, kind="task", origin="ecosystem",
                    priority=40,
                    payload={"goal_slug": slug, "kind": kind,
                             "source": "cycle_review.py"})
                filed.append(key)
            cur.execute(
                """INSERT INTO successbrian_os.goal_cycle_reviews
                   (goal_slug, cycle_start, cycle_end, review_md,
                    tasks_filed)
                   VALUES (%s, current_date - %s, current_date, %s,
                           %s::jsonb)""",
                (slug, args.window, review, json.dumps(filed)))
            path = os.path.join(
                OUT_DIR, f"{slug}-{date.today().isoformat()}.md")
            with open(path, "w") as fh:
                fh.write(review)
            conn.commit()
        print(f"cycle-review {slug}: {len(tasks)} task(s)"
              f"{' (dry-run)' if args.dry_run else ' filed: ' + ', '.join(filed)}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
