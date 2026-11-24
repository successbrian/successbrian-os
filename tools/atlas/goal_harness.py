#!/usr/bin/env python3
"""goal_harness.py - the GOAL HARNESS (Brian's order, 2026-11-23:
"build the harness so it can process and understand all this").

PURPOSE: wrap every goal in ONE loop and keep the loop turning:
  BRIEF (full context, compiled by einstein_planner) -> Einstein
  deep look -> plan written back (einstein_planner.write_back) ->
  steps + research items filed (pm_steps) -> steps CLAIMED and
  worked in harness order -> completion VERIFIED from the step
  ledger -> re-look. This module is the harness frame around the
  pieces that already exist (planner_rotation, einstein_planner,
  pm_core); it adds the four things Brian specified in captures
  #3108/#3109 that the pieces did not have:

  1. TIERED CADENCE - priority sets the heartbeat. sbos_goals
     priority maps to a look window: critical/high -> daily,
     medium -> 4 days, low -> 7 days; a goal behind a gate
     (gate_key on the goal row) drops to the gated window
     (14 days) - looking does not move a gate. Thresholds are CONFIG (TIER_WINDOWS
     below), not law: Brian has not yet ruled whether "high
     priority" means the priority value on the goal record or a
     list he names; v1 reads the record.
  2. MOVEMENT FIRST - every harness look opens with a MOVEMENT
     section: Einstein judges what actually completed / stalled
     since the goal's last look, measured from the pm_steps
     ledger by this module and fed to him as facts. The verdict
     is parsed back out and stored in harness_movements, so the
     movement record is true whether or not anyone reads the plan.
  2b. WORTH (Brian's ruling, 2026-11-23 18:14 CST) - every look
     also grades the goal against his four tests: (1) does it
     make sense for the ecosystem? (2) is it better than what we
     are currently doing? (3) how easy or hard is it to add?
     (4) is it more lucrative? - weighed against the scarcest
     resource, Brian's own bandwidth: Brian-hours cost a goal;
     work the fleet carries without him counts for it. A goal's
     ORIGIN is a label, not the gate ("the goals don't have to
     have 'me' in them... they just have to make sense for our
     ecosystem. I can only do so much."): provenance labeling
     stays exactly as the briefs built it - honesty about origin,
     verdict by merit. For an unadopted goal the WORTH section is
     its adoption brief; for an adopted goal, its periodic
     re-justification. The verdict is stored with the movement
     record (harness_movements.detail.worth).
  3. EVENT TRIGGERS - a research answer landing for a goal, or a
     capture landing that names the goal (subject-match, the
     brief compiler's attribution test), marks the goal due-early:
     replanning follows new intel, not just the clock.
  4. CONSOLIDATION - a periodic Einstein pass over the open
     goal-linked step pool clusters steps that are THE SAME WORK
     IN DIFFERENT WORDS (judgment, not string matching) and files
     consolidation_proposals: shared-task groups, their member
     steps, and the goals each group gates. Proposals are never
     merged or deleted silently; their effect in v1 is ORDERING:
     steps in a proposed group get a priority boost in the shared
     pm_steps queue (recorded in harness_claims) and sort first
     in the harness claim order, because a task inside many goals
     is a bigger gate than any one goal's priority says.

  CLAIM LOOP v1 (decision #15, under Brian's build order): claims
  queued goal-linked steps in harness order - consolidated/shared
  first, then research, then goal tier. Safe classes only:
  research steps are worked by Einstein over the gamma bus;
  steps carrying an engine_tier are handed to that engine's job
  queue; everything else is left for the existing workers, with
  the consolidation boost applied so the shared order is real in
  the queue they read. A step whose text asks for an outward act
  (send, publish, buy, contact, pay, deploy...) is NEVER claimed:
  it is held in the claim ledger as FOR BRIAN residue. The loop
  never leaves a step 'running' without an in-flight artifact
  (bus event or engine job) in the ledger, and a reaper returns
  stale harness claims to the queue.

  PAPERCLIP FOLD-INS (study capture #3121 / second_brain
  #103683, folded in 2026-11-23): (1) plan_decompositions -
  every written-back Einstein plan revision is fingerprinted
  with the exact step set it materialized, tracked to
  completion; materialization is exactly-once because
  pm_core.add_step is ON CONFLICT (step_key) DO NOTHING.
  (2) Blocker edges are first-class data on the existing
  pm_step_deps table: add_blocker enforces acyclicity, the
  claim loop never claims a blocked step, blocked_pass names
  each blocked step's blockers in the ledger, and wake_pass
  wakes dependents when a blocker clears (priority nudge +
  goal due-early). (3) Disposition guard: held_brian without
  a named reason, or a payload narrating waiting_on with no
  blocker edge, is flagged - a step must name its blocker or
  be claimable. (4) Claimed steps carry a heartbeat-context
  packet (item + goal/movement + relations + continuation).
  (5) Plan-writing restraint in both prompt contracts: split
  only at owner/parallel/prerequisite/review boundaries.
  (6) Exact-title dedup runs as the deterministic floor under
  the semantic sweep; fan-out cap 25 and depth cap 2 bound
  harness-created work. NOT copied from Paperclip (confirmed
  absences): goal metrics on the goal row, completion by
  self-report, no stall detection, no cross-goal dedup.

  FIELD-STUDY ADDENDUM (capture #3122, folded in 2026-11-23):
  (1) MAGENTIC stall counter - goal_harness_state.stall_count
  counts consecutive looks with zero verified completions; at
  STALL_LOOK_THRESHOLD the goal is marked due-early for a
  re-look/replan (Magentic-One's ablation: removing the stall
  mechanism cost 31% on GAIA). (2) METAGPT verification
  standard - a claim settles 'verified-done' only when its
  output passes a check, never on the worker's word: research
  answers must carry an ANSWER + EVIDENCE naming a checkable
  artifact (verify_research_answer), else the step is requeued
  with 'verification-failed-requeued' in the ledger. Context:
  Berkeley MAST measured 41-86.7% failure rates across 7 agent
  frameworks, specification/verification failures the largest
  category - verification is the layer this harness weights.

SAFETY (standing law, same as einstein_planner): the harness
never changes a goal's status/progress, never closes a goal,
never merges or deletes a step, never sends/publishes/buys.
Einstein's assessments are recorded as assessments; proposed
corrections stay flagged for a human.

Usage:
  goal_harness.py --selftest     pure-function checks + read-only
                                 probes (no writes)
  goal_harness.py --tiers        tier table for the rotation
  goal_harness.py --due          goals due for a harness look now
  goal_harness.py --cycle [N]    one harness cycle (the cron entry
                                 point): collect, scan events,
                                 maybe sweep, dispatch up to N
                                 looks, run the claim loop
  goal_harness.py --sweep        force a consolidation sweep now
  goal_harness.py --collect      collect landed sweeps / claims /
                                 movement verdicts only
  goal_harness.py --status       harness state summary

Cron: 50 */2 * * * (offset from the planner driver :05 and the
Einstein cycle :35). Registry: program_registry goal-harness-py.
QA: sbos-program-registry/goal-harness-proof-fresh +
    sbos-program-registry/goal-harness-outcomes-moving.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "pm"))
import sbos_common  # noqa: E402
import einstein_planner as ep  # noqa: E402
import goal_nodes as gn  # noqa: E402
import planner_rotation as pr  # noqa: E402
import pm_core  # noqa: E402

SOURCE = "goal-harness"
SEAT = "einstein"
BUS_PRIORITY = 2  # filler band, same as the Einstein cycle
MAX_TOKENS = 500  # REAP feeder-packet ceiling (sbos_common)
DISPATCH_PER_CYCLE = 4
MAX_INFLIGHT_LOOKS = 8
CLAIM_PER_CYCLE = 3
SWEEP_POOL_CAP = 50
SWEEP_MIN_AGE_H = 20
STALE_CLAIM_H = 6
# Paperclip fold-in (study capture #3121, 2026-11-23): caps on
# agent-created work - a consolidation group may not exceed 25
# member steps (fan-out), and harness-created steps nest at most
# 2 levels deep (look -> step; the claim loop refuses deeper).
FANOUT_CAP = 25
DEPTH_CAP = 2
EXACT_TITLE_MIN_AGE_H = 20
# Magentic stall threshold (field study addendum, capture
# #3122): consecutive looks without a verified completion that
# pull a re-look/replan forward. Magentic-One's ablation put
# the stall mechanism's worth at 31% of GAIA performance.
STALL_LOOK_THRESHOLD = 2

# Tier config (Brian's spec, capture #3108; thresholds are config,
# not law - see module docstring). sbos_goals.priority label ->
# (tier, look window in days). Gated goals override to GATED.
TIER_WINDOWS = {"daily": 1, "standard": 4, "slow": 7, "gated": 14}
PRIORITY_TIER = {"critical": "daily", "high": "daily",
                 "medium": "standard", "low": "slow"}
TIER_RANK = {"daily": 0, "standard": 1, "slow": 2, "gated": 3}

# Outward-action screen for the claim loop. Conservative on
# purpose: a false positive only holds a step for Brian, which is
# the safe side; a false negative could auto-work an outward act,
# which is the failure this screen exists to prevent.
OUTWARD_RE = re.compile(
    r"\b(send|email|e-mail|mail|publish|post|tweet|message|dm|buy|"
    r"purchase|order|pay|payment|subscribe|contact|call|phone|text|"
    r"deploy|release|ship|launch|advertise|promote|reply|forward|"
    r"invite|book|schedule a call|sign up|register for)\b",
    re.IGNORECASE)

HARNESS_BEGIN = "<!-- GOAL-HARNESS:BEGIN -->"
HARNESS_END = "<!-- GOAL-HARNESS:END -->"

SECTION_HEADERS = ("MOVEMENT", "WORTH", "VERIFIED STATE",
                   "CLAIMED vs VERIFIED", "BLOCKERS", "PLAN",
                   "RESEARCH NEEDS", "FOR BRIAN")

PROMPT_TEMPLATE = """You are Einstein, the deep-planning engine in a solo operator's goal system. Below is one goal's MOVEMENT DATA (measured by the goal harness from the work ledger since your last look at this goal), then its standing brief - compiled from everything the operator's ecosystem holds about this goal: his own recorded words (quoted verbatim, attributed, dated), the goal's origin and provenance, its connected work, the standing rulings that constrain it, and its measured state - followed by its live record. Judge ONLY from this record. Where the record is silent, say UNKNOWN - never invent a fact, a date, or a person's intent. Weigh provenance: a goal whose brief shows an agent-assembled origin and no words of Brian's is an unadopted proposal, not his directive - plan accordingly and say so where it matters.

Write a planning assessment with EXACTLY these eight sections, in this order, plain text, no preamble, no closing remarks. CRITICAL FORMAT RULE: write the ENTIRE assessment as one single unbroken block of text - NO blank lines anywhere, NO paragraph breaks. The channel that carries your answer back keeps only the first block, so a blank line ends your answer and the rest is lost. Start immediately with "MOVEMENT:" and run each section's header inline, like this: MOVEMENT: <text> WORTH: <text> VERIFIED STATE: <text> CLAIMED vs VERIFIED: <text> BLOCKERS: <text> PLAN: 1. <step> 2. <step> RESEARCH NEEDS: <items> FOR BRIAN: <text>

MOVEMENT: Judge the MOVEMENT DATA below: since the last look, what pieces and subtasks actually got completed, what is stuck, and is this goal moving at the pace its priority deserves? Name the counts you are judging from. At most 35 words.
WORTH: Grade this goal against Brian's four tests (his ruling, 2026-11-23): (1) Does it make sense for the ecosystem? (2) Is it better than what we are currently doing? (3) How easy or hard is it to add? (4) Is it more lucrative? - weighed against the scarcest resource in the system, Brian's own time: a goal that costs Brian-hours weighs against itself; work the fleet can carry without him weighs in its favor. A goal does NOT need Brian's authorship to pass - origin is a label, not a gate; judge by merit against these tests. For an unadopted (agent-assembled) goal this section is its adoption brief; for an adopted goal it is the periodic re-justification. End with a verdict word: STRONG, SOUND, WEAK, or FAILING. At most 55 words.
VERIFIED STATE: What the evidence in the record actually proves about this goal today, each claim tied to the record item it rests on. At most 60 words.
CLAIMED vs VERIFIED: Where the goal's claimed state (status, progress, dates) disagrees with the evidence, say so plainly and name the correction you propose. These are flagged for a human - you are not applying them. At most 50 words.
BLOCKERS: What is actually stopping progress, from the record. "none proven" if the record shows none. At most 30 words.
PLAN: The concrete next steps, in order, numbered "1." "2." "3." inline - each step a single executable action a worker could claim and finish, at most 25 words per step. At most 4 steps. RESTRAINT (Paperclip doctrine): a plan's steps do not each need to be a task - split only where the owner changes, work can run in parallel, a prerequisite boundary falls, or a review gate sits; merge micro-actions into the step that owns them. A step that only Brian can perform does not belong here - it belongs in FOR BRIAN.
RESEARCH NEEDS: What is UNKNOWN that research could settle, each item in exactly this shape: NEED: <the question> | WHY: <why it matters to this goal> | WHERE: <where the answer likely lives>. At most 2 items. A question only Brian can answer is NOT a research need - it belongs in FOR BRIAN. "none" if nothing is missing.
FOR BRIAN: Only what the operator himself must decide or supply - the residue no research and no worker can settle. At most 25 words. "none" if there is none.

Keep the whole answer under 460 tokens - the channel truncates at 500, and a plan whose tail is cut off is a failed plan. Be concrete and brief; a short true plan beats a long vague one.

GOAL RECORD:
{context}"""

SWEEP_PROMPT_TEMPLATE = """You are Einstein, the deep-planning engine in a solo operator's goal system. Below is a numbered pool of OPEN work steps drawn from across all of the operator's goals, each tagged with the goal it belongs to. Your job: find steps that are THE SAME WORK IN DIFFERENT WORDS - the same underlying task serving several goals, even when the wording differs. Completing such a shared task moves every goal that contains it, so it is a bigger gate than any single step looks.

Reply as ONE single unbroken block of text - NO blank lines, NO paragraph breaks (the channel keeps only the first block). Use EXACTLY this shape: GROUPS: GROUP 1: <the shared task, at most 8 words> | STEPS: <comma-separated step ids from the pool> | WHY: <why these are the same work, at most 10 words> ;; GROUP 2: <same shape> ;; ... Only include groups of 2 or more steps that span 2 or more DIFFERENT goals. Do not group steps that merely share a topic or a tool - the test is: would finishing one piece of work finish, or directly unblock, the others? If no such group exists, reply exactly: GROUPS: none. Keep the whole reply under 460 tokens - fewer, well-chosen groups beat many weak ones.

STEP POOL:
{pool}"""


# ---------------------------------------------------------------- schema

def ensure_schema(cur):
    cur.execute(
        "CREATE TABLE IF NOT EXISTS successbrian_os.goal_harness_state ("
        "goal_slug text PRIMARY KEY, "
        "tier text NOT NULL, "
        "window_days int NOT NULL, "
        "priority_label text, "
        "gated boolean NOT NULL DEFAULT false, "
        "due_early boolean NOT NULL DEFAULT false, "
        "due_early_reason text, "
        "due_early_at timestamptz, "
        "last_movement_at timestamptz, "
        "updated_at timestamptz NOT NULL DEFAULT now())")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS successbrian_os.harness_movements ("
        "id serial PRIMARY KEY, "
        "goal_slug text NOT NULL, "
        "pass_id int, "
        "look_id int, "
        "measured_at timestamptz NOT NULL DEFAULT now(), "
        "since_at timestamptz, "
        "completed int NOT NULL DEFAULT 0, "
        "failed int NOT NULL DEFAULT 0, "
        "running int NOT NULL DEFAULT 0, "
        "queued int NOT NULL DEFAULT 0, "
        "stuck int NOT NULL DEFAULT 0, "
        "verdict text, "
        "detail jsonb NOT NULL DEFAULT '{}'::jsonb)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS successbrian_os.harness_meta ("
        "key text PRIMARY KEY, "
        "value jsonb NOT NULL DEFAULT '{}'::jsonb, "
        "updated_at timestamptz NOT NULL DEFAULT now())")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS successbrian_os.consolidation_sweeps ("
        "id serial PRIMARY KEY, "
        "probe_id text NOT NULL UNIQUE, "
        "bus_event_id bigint, "
        "ran_at timestamptz NOT NULL DEFAULT now(), "
        "collected_at timestamptz, "
        "steps_scanned int NOT NULL DEFAULT 0, "
        "pool_ids jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "status text NOT NULL DEFAULT 'dispatched', "
        "note text)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS successbrian_os.consolidation_proposals ("
        "id serial PRIMARY KEY, "
        "sweep_id int NOT NULL, "
        "group_key text NOT NULL, "
        "title text NOT NULL, "
        "rationale text, "
        "step_ids jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "step_keys jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "goal_slugs jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "gate_count int NOT NULL DEFAULT 0, "
        "status text NOT NULL DEFAULT 'proposed', "
        "created_at timestamptz NOT NULL DEFAULT now(), "
        "UNIQUE (sweep_id, group_key))")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS successbrian_os.harness_claims ("
        "id serial PRIMARY KEY, "
        "step_id bigint NOT NULL, "
        "step_key text NOT NULL, "
        "goal_slug text, "
        "route text NOT NULL, "
        "action text NOT NULL, "
        "bus_event_id bigint, "
        "engine_job_id bigint, "
        "claimed_at timestamptz NOT NULL DEFAULT now(), "
        "finished_at timestamptz, "
        "outcome text, "
        "detail jsonb NOT NULL DEFAULT '{}'::jsonb)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS harness_claims_step_idx "
        "ON successbrian_os.harness_claims (step_id, action)")
    # Paperclip fold-in: accepted-plan decomposition bookkeeping
    # (their issue_plan_decompositions). One row per Einstein look
    # whose plan was written back: the plan fingerprint + the
    # exact step set it materialized, tracked to completion.
    # Materialization itself is exactly-once by construction:
    # pm_core.add_step is ON CONFLICT (step_key) DO NOTHING, so a
    # revision's steps can never duplicate on re-look/re-collect.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS "
        "successbrian_os.plan_decompositions ("
        "id serial PRIMARY KEY, "
        "look_id bigint NOT NULL UNIQUE, "
        "pass_id bigint, "
        "goal_slug text NOT NULL, "
        "fingerprint text NOT NULL, "
        "step_keys jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "steps_total integer NOT NULL DEFAULT 0, "
        "steps_done integer NOT NULL DEFAULT 0, "
        "depth integer NOT NULL DEFAULT 1, "
        "materialized_at timestamptz NOT NULL DEFAULT now(), "
        "completed_at timestamptz, "
        "updated_at timestamptz NOT NULL DEFAULT now())")
    # Magentic stall counter columns (capture #3122).
    cur.execute(
        "ALTER TABLE successbrian_os.goal_harness_state "
        "ADD COLUMN IF NOT EXISTS stall_count integer NOT NULL "
        "DEFAULT 0")
    cur.execute(
        "ALTER TABLE successbrian_os.goal_harness_state "
        "ADD COLUMN IF NOT EXISTS last_progress_at timestamptz")
    # Brian's additions, 2026-11-23 19:05: decomposition assist
    # for weaker seats + effectiveness follow-up on completed
    # tasks.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS "
        "successbrian_os.breakdown_drafts ("
        "id serial PRIMARY KEY, "
        "goal_slug text NOT NULL, "
        "author_seat text NOT NULL, "
        "status text NOT NULL DEFAULT 'drafting', "
        "engine_job_id bigint, "
        "review_event_id bigint, "
        "brief_fingerprint text, "
        "draft_text text, "
        "review_count integer NOT NULL DEFAULT 0, "
        "review_verdict text, "
        "review_notes text, "
        "intended_effect text, "
        "fingerprint text, "
        "materialized_step_keys jsonb, "
        "created_at timestamptz NOT NULL DEFAULT now(), "
        "updated_at timestamptz NOT NULL DEFAULT now())")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS "
        "successbrian_os.effect_followups ("
        "id serial PRIMARY KEY, "
        "step_id bigint NOT NULL UNIQUE, "
        "step_key text NOT NULL, "
        "goal_slug text, "
        "kind text, "
        "author_seat text, "
        "intended_effect text, "
        "completed_at timestamptz, "
        "due_at timestamptz, "
        "status text NOT NULL DEFAULT 'pending', "
        "verdict text, "
        "evidence text, "
        "checked_at timestamptz, "
        "created_at timestamptz NOT NULL DEFAULT now())")
    cur.execute(
        "CREATE OR REPLACE VIEW "
        "successbrian_os.effectiveness_rollup AS "
        "SELECT author_seat, kind, verdict, count(*) AS n "
        "FROM successbrian_os.effect_followups "
        "WHERE verdict IS NOT NULL "
        "GROUP BY author_seat, kind, verdict")


# ---------------------------------------------------------------- tiers

def rotation_slugs():
    rows = pr.fetch_rotation()
    return [r[0] for r in rows] if rows else []


def goal_priority(cur, slug):
    """(priority_label, gate_key) for one goal: sbos_goals is the
    record; the Atlas node's numeric priority is the fallback."""
    cur.execute(
        "SELECT priority, gate_key FROM successbrian_os.sbos_goals "
        "WHERE goal_slug = %s", [slug])
    row = cur.fetchone()
    if row and row[0]:
        return (str(row[0]).lower(), row[1])
    cur.execute(
        "SELECT details FROM atlas.nodes WHERE node_key = %s "
        "AND node_type = 'goal'", [gn.node_key_for_slug(slug)])
    row = cur.fetchone()
    prio = int((row[0] or {}).get("priority") or 50) if row else 50
    label = ("critical" if prio >= 90 else "high" if prio >= 60
             else "medium" if prio >= 40 else "low")
    return (label, None)


def goal_gated(cur, slug, gate_key):
    """A goal is gated when its own record names a gate (gate_key).
    The latest coverage look's blocker field is NOT a gate signal:
    measured 2026-11-23, 33 of 42 goals carry planner bookkeeping
    text there ('dispatch: look N named no spawnable work',
    'no-work:blocker-held') - treating it as a gate put nearly
    every critical goal on the 14-day window and defeated the
    daily heartbeat Brian specified. gate_key is the record's own
    gate: 4 goals carry one."""
    return bool(gate_key)


def compute_tiers(cur, slugs):
    """Refresh goal_harness_state for the whole rotation. Existing
    due_early flags are preserved; tier/window are recomputed."""
    out = {}
    for slug in slugs:
        label, gate_key = goal_priority(cur, slug)
        gated = goal_gated(cur, slug, gate_key)
        tier = "gated" if gated else PRIORITY_TIER.get(label, "standard")
        window = TIER_WINDOWS[tier]
        cur.execute(
            "INSERT INTO successbrian_os.goal_harness_state "
            "(goal_slug, tier, window_days, priority_label, gated) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (goal_slug) DO UPDATE SET "
            "tier = EXCLUDED.tier, window_days = EXCLUDED.window_days, "
            "priority_label = EXCLUDED.priority_label, "
            "gated = EXCLUDED.gated, updated_at = now()",
            [slug, tier, window, label, gated])
        out[slug] = {"tier": tier, "window_days": window,
                     "priority_label": label, "gated": gated}
    return out


def set_due_early(cur, slug, reason):
    cur.execute(
        "UPDATE successbrian_os.goal_harness_state SET "
        "due_early = true, due_early_reason = %s, due_early_at = now(), "
        "updated_at = now() WHERE goal_slug = %s", [reason[:300], slug])


def clear_due_early(cur, slug):
    cur.execute(
        "UPDATE successbrian_os.goal_harness_state SET "
        "due_early = false, due_early_reason = NULL, "
        "due_early_at = NULL, updated_at = now() WHERE goal_slug = %s",
        [slug])


# ---------------------------------------------------------------- movement

def linked_steps(cur, slug):
    """All pm_steps that belong to one goal: filed from its looks
    (source goal_coverage:<look>) or carrying its slug in payload."""
    cur.execute(
        "SELECT s.id, s.step_key, s.title, s.kind, s.status, "
        "s.priority, s.created_at, s.started_at, s.finished_at, "
        "s.payload FROM successbrian_os.pm_steps s "
        "LEFT JOIN successbrian_os.goal_coverage gc "
        "ON s.source = 'goal_coverage:' || gc.id::text "
        "WHERE gc.goal_slug = %s OR s.payload->>'goal_slug' = %s "
        "ORDER BY s.id", [slug, slug])
    cols = ["id", "step_key", "title", "kind", "status", "priority",
            "created_at", "started_at", "finished_at", "payload"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def last_einstein_look(cur, slug):
    cur.execute(
        "SELECT max(looked_at) FROM successbrian_os.goal_coverage "
        "WHERE goal_slug = %s AND planner_seat = %s", [slug, SEAT])
    row = cur.fetchone()
    return row[0] if row else None


def movement_for(cur, slug):
    """Measured movement since the goal's last Einstein look, from
    the step ledger. Facts only - the verdict is Einstein's job."""
    since = last_einstein_look(cur, slug)
    steps = linked_steps(cur, slug)
    now = datetime.now(timezone.utc)
    done = [s for s in steps if s["status"] == "done"
            and (since is None or (s["finished_at"] and
                                   s["finished_at"] > since))]
    failed = [s for s in steps if s["status"] == "failed"
              and (since is None or (s["finished_at"] and
                                     s["finished_at"] > since))]
    running = [s for s in steps if s["status"] == "running"]
    queued = [s for s in steps if s["status"] == "queued"]
    stuck = [s for s in running
             if s["started_at"] and (now - s["started_at"]).days >= 1]
    stuck += [s for s in queued
              if s["created_at"] and (now - s["created_at"]).days >= 7]
    eff = []
    try:
        cur.execute(
            "SELECT step_key, verdict FROM "
            "successbrian_os.effect_followups WHERE goal_slug "
            "= %s AND verdict IS NOT NULL ORDER BY checked_at "
            "DESC LIMIT 3", [slug])
        eff = [f"{r[0]}: {r[1]}" for r in cur.fetchall()]
    except Exception:
        eff = []
    return {"since": since, "completed": len(done), "failed": len(failed),
            "running": len(running), "queued": len(queued),
            "stuck": len(stuck), "total": len(steps),
            "done_keys": [s["step_key"] for s in done][:10],
            "stuck_keys": [s["step_key"] for s in stuck][:10],
            "effectiveness": eff}


def movement_block(mv):
    since = (mv["since"].isoformat(timespec="seconds")
             if mv["since"] else "never (this is the first deep look)")
    lines = [f"MOVEMENT DATA (measured from the work ledger; "
             f"last deep look: {since}):",
             f"steps linked to this goal: {mv['total']}; "
             f"completed since last look: {mv['completed']}; "
             f"failed since last look: {mv['failed']}; "
             f"running now: {mv['running']}; queued now: "
             f"{mv['queued']}; stuck (running >1d or queued >7d): "
             f"{mv['stuck']}."]
    if mv["done_keys"]:
        lines.append("completed: " + ", ".join(mv["done_keys"]))
    if mv["stuck_keys"]:
        lines.append("stuck: " + ", ".join(mv["stuck_keys"]))
    if mv.get("effectiveness"):
        lines.append("EFFECTIVENESS FOLLOW-UPS (verdicts on this "
                     "goal's completed work - weigh them): "
                     + "; ".join(mv["effectiveness"]))
    return "\n".join(lines)


def parse_movement(text):
    """Extract the MOVEMENT section from a harness plan (it runs up
    to the WORTH or VERIFIED STATE header). '' when absent."""
    if not text:
        return ""
    flat = " ".join(str(text).split())
    m = re.search(r"MOVEMENT\s*:\s*(.*?)\s*(?:WORTH|VERIFIED STATE)"
                  r"\s*:", flat, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def parse_worth(text):
    """Extract the WORTH section (Brian's four tests, ruling
    2026-11-23) from a harness plan. '' when absent (plans written
    before the ruling carry none)."""
    if not text:
        return ""
    flat = " ".join(str(text).split())
    m = re.search(r"WORTH\s*:\s*(.*?)\s*VERIFIED STATE\s*:", flat,
                  re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------- dispatch

def inflight_look(cur, slug=None):
    if slug:
        cur.execute(
            "SELECT count(*) FROM successbrian_os.einstein_passes "
            "WHERE status = 'dispatched' AND goal_slug = %s", [slug])
    else:
        cur.execute(
            "SELECT count(*) FROM successbrian_os.einstein_passes "
            "WHERE status = 'dispatched'")
    return cur.fetchone()[0]


def dispatch_harness_look(cur, slug, dry_run=False, force=False):
    """Dispatch one harness look: Einstein's context packet (brief +
    live record, via einstein_planner.build_context) with the
    harness MOVEMENT DATA in front of it, under the 7-section
    contract. Recorded in einstein_passes so the shared write-back
    (einstein_planner.collect, whichever cycle gets there first)
    files the plan exactly like a planner look; this module parses
    the MOVEMENT verdict back out on its own collect pass.
    Returns (bus_event_id_or_None, probe_id)."""
    mv = movement_for(cur, slug)
    context = movement_block(mv) + "\n\n" + ep.build_context(cur, slug)
    prompt = PROMPT_TEMPLATE.format(context=context)
    probe_id = (f"harness-look-{slug}-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%d')}")
    if force:
        probe_id += ("-r" + datetime.now(timezone.utc).strftime("%H%M%S"))
    cur.execute(
        "SELECT id FROM successbrian_os.einstein_passes "
        "WHERE probe_id = %s", [probe_id])
    if cur.fetchone():
        return None, probe_id
    packet = sbos_common.build_reap_packet(
        prompt, source=SOURCE, probe_id=probe_id, item_ref=slug,
        max_tokens=MAX_TOKENS, thinking=False)
    if dry_run:
        print(f"  {slug}: DRY-RUN packet ready "
              f"(~{sbos_common.estimate_tokens(prompt)} prompt tokens, "
              f"probe {probe_id})")
        return None, probe_id
    event_id = sbos_common.dispatch_reap_packet(
        packet, source=SOURCE, priority=BUS_PRIORITY)
    cur.execute(
        "INSERT INTO successbrian_os.einstein_passes "
        "(goal_slug, probe_id, bus_event_id, status) "
        "VALUES (%s, %s, %s, 'dispatched') RETURNING id",
        [slug, probe_id, event_id])
    pass_id = cur.fetchone()[0]
    # Snapshot the movement Einstein is about to judge, keyed by
    # the pass: the collect pass attaches his verdict to THIS row,
    # so the stored counts are the exact numbers he saw - not a
    # re-measurement taken after his own write-back filed new
    # steps into the same ledger.
    cur.execute(
        "INSERT INTO successbrian_os.harness_movements "
        "(goal_slug, pass_id, since_at, completed, failed, running, "
        "queued, stuck, detail) VALUES (%s, %s, %s, %s, %s, %s, %s, "
        "%s, %s::jsonb)",
        [slug, pass_id, mv["since"], mv["completed"], mv["failed"],
         mv["running"], mv["queued"], mv["stuck"],
         json.dumps({"done_keys": mv["done_keys"],
                     "stuck_keys": mv["stuck_keys"],
                     "total": mv["total"],
                     "snapshot": "at-dispatch"})])
    print(f"  {slug}: harness look dispatched (bus event {event_id}, "
          f"probe {probe_id})")
    return event_id, probe_id


def due_goals(cur, slugs, limit):
    """Harness due set: due-early goals first, then by overdue
    ratio (age of last look / tier window) descending. A goal with
    a look already in flight is skipped - a second deep look at
    the same goal buys nothing."""
    cur.execute(
        "SELECT goal_slug, tier, window_days, due_early, "
        "due_early_reason FROM successbrian_os.goal_harness_state")
    state = {r[0]: {"tier": r[1], "window_days": r[2],
                    "due_early": r[3], "due_early_reason": r[4]}
             for r in cur.fetchall()}
    now = datetime.now(timezone.utc)
    due = []
    for slug in slugs:
        st = state.get(slug)
        if not st or inflight_look(cur, slug):
            continue
        seen = last_einstein_look(cur, slug)
        age_days = 9999.0 if seen is None else (now - seen).total_seconds() / 86400.0
        ratio = age_days / max(st["window_days"], 1)
        if st["due_early"] or ratio >= 1.0:
            due.append({"slug": slug, "tier": st["tier"],
                        "due_early": st["due_early"],
                        "reason": st["due_early_reason"],
                        "ratio": round(ratio, 2), "age_days": round(age_days, 1)})
    due.sort(key=lambda d: (0 if d["due_early"] else 1, -d["ratio"],
                            TIER_RANK.get(d["tier"], 9)))
    return due[:limit]


# ---------------------------------------------------------------- collect

def collect_movements(cur):
    """For every collected harness pass with no movement row yet:
    measure the movement Einstein was shown, parse his MOVEMENT
    verdict out of the plan text, and store both. The movement
    record is true even if his verdict is missing (verdict '')."""
    cur.execute(
        "SELECT p.id, p.goal_slug, p.look_id, p.plan_text "
        "FROM successbrian_os.einstein_passes p "
        "WHERE p.probe_id LIKE 'harness-look-%' "
        "AND p.status = 'collected' AND NOT EXISTS ("
        "SELECT 1 FROM successbrian_os.harness_movements m "
        "WHERE m.pass_id = p.id AND m.verdict IS NOT NULL) "
        "ORDER BY p.id")
    rows = cur.fetchall()
    n = 0
    for pass_id, slug, look_id, plan_text in rows:
        mv = movement_for(cur, slug)
        verdict = parse_movement(plan_text)
        cur.execute(
            "SELECT detail FROM successbrian_os.harness_movements "
            "WHERE pass_id = %s ORDER BY id LIMIT 1", [pass_id])
        snap = cur.fetchone()
        if snap:
            # Dispatch-time snapshot exists: attach the verdict and
            # the WORTH grade to the numbers Einstein actually saw.
            detail = dict(snap[0] or {})
            detail["worth"] = parse_worth(plan_text)
            cur.execute(
                "UPDATE successbrian_os.harness_movements SET "
                "look_id = %s, verdict = %s, detail = %s::jsonb "
                "WHERE pass_id = %s",
                [look_id, verdict[:600] if verdict else None,
                 json.dumps(detail), pass_id])
        else:
            cur.execute(
                "INSERT INTO successbrian_os.harness_movements "
                "(goal_slug, pass_id, look_id, since_at, completed, "
                "failed, running, queued, stuck, verdict, detail) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s::jsonb)",
                [slug, pass_id, look_id, mv["since"], mv["completed"],
                 mv["failed"], mv["running"], mv["queued"],
                 mv["stuck"], verdict[:600] if verdict else None,
                 json.dumps({"done_keys": mv["done_keys"],
                             "stuck_keys": mv["stuck_keys"],
                             "total": mv["total"],
                             "worth": parse_worth(plan_text),
                             "snapshot": "at-collect (no dispatch "
                                         "snapshot - pre-fix pass)"})])
        # Magentic stall counter (field study addendum, capture
        # #3122): a look with zero verified completions increments
        # the goal's stall counter; any verified completion resets
        # it. At the threshold the next re-look/replan is pulled
        # forward (due-early) - stalling triggers replanning, it
        # does not wait for the cadence clock.
        cur.execute(
            "SELECT stall_count FROM successbrian_os."
            "goal_harness_state WHERE goal_slug = %s", [slug])
        srow = cur.fetchone()
        new_stall, progressed = stall_update(
            srow[0] if srow and srow[0] is not None else 0,
            mv["completed"])
        cur.execute(
            "UPDATE successbrian_os.goal_harness_state SET "
            "last_movement_at = now(), stall_count = %s, "
            "last_progress_at = CASE WHEN %s THEN now() ELSE "
            "last_progress_at END, updated_at = now() "
            "WHERE goal_slug = %s", [new_stall, progressed, slug])
        if not progressed and new_stall >= STALL_LOOK_THRESHOLD:
            set_due_early(
                cur, slug,
                f"stall counter {new_stall}: no verified "
                f"completion across {new_stall} consecutive "
                f"looks - replan pulled forward (Magentic)")
            print(f"  {slug}: STALL {new_stall} - re-look pulled "
                  f"forward")
        n += 1
        print(f"  {slug}: movement recorded (pass {pass_id}: "
              f"+{mv['completed']} done, {mv['stuck']} stuck; "
              f"verdict {'present' if verdict else 'MISSING'})")
    return n


# ---------------------------------------------------------------- events

def get_meta(cur, key, default=None):
    cur.execute("SELECT value FROM successbrian_os.harness_meta "
                "WHERE key = %s", [key])
    row = cur.fetchone()
    return row[0] if row else default


def set_meta(cur, key, value):
    cur.execute(
        "INSERT INTO successbrian_os.harness_meta (key, value) "
        "VALUES (%s, %s::jsonb) ON CONFLICT (key) DO UPDATE SET "
        "value = EXCLUDED.value, updated_at = now()",
        [key, json.dumps(value)])


def scan_capture_events(cur, slugs):
    """Event trigger (Brian #3108): a capture landing that NAMES a
    goal - subject-match, the brief compiler's attribution test -
    marks that goal due-early for its next look. Watermarked in
    harness_meta; the first run only sets the watermark (history
    is not an event)."""
    wm = get_meta(cur, "capture_scan_watermark")
    cur.execute(
        "SELECT id, title, raw_text, context, created_at "
        "FROM atlas.scattered_captures WHERE created_at > %s "
        "ORDER BY created_at LIMIT 200",
        [wm["at"] if wm else "1900-01-01"])
    rows = cur.fetchall()
    if not wm:
        newest = max((r[4] for r in rows), default=None)
        set_meta(cur, "capture_scan_watermark",
                 {"at": (newest or datetime.now(timezone.utc)).isoformat(),
                  "note": "initialised by first harness scan"})
        print(f"  capture scan: watermark initialised "
              f"({len(rows)} historical captures skipped)")
        return 0
    terms = {s: ep._goal_terms(cur, s) for s in slugs}
    marked = 0
    newest = None
    for cap_id, title, raw, context, created in rows:
        newest = created
        text = " ".join(x for x in (title, raw, context) if x)
        for slug in slugs:
            if ep._subject_match(text, terms[slug]):
                set_due_early(cur, slug,
                              f"capture #{cap_id} landed naming this goal")
                marked += 1
                print(f"  capture #{cap_id}: {slug} marked due-early")
    if newest:
        set_meta(cur, "capture_scan_watermark",
                 {"at": newest.isoformat()})
    return marked


# ---------------------------------------------------------------- consolidation

def open_goal_steps(cur, limit=SWEEP_POOL_CAP):
    """The consolidation pool: open (queued) steps linked to a
    rotation goal, most valuable first (priority + age)."""
    slugs = rotation_slugs()
    cur.execute(
        "SELECT s.id, s.step_key, s.title, s.kind, s.priority, "
        "s.created_at, s.payload, "
        "COALESCE(gc.goal_slug, s.payload->>'goal_slug') AS goal_slug "
        "FROM successbrian_os.pm_steps s "
        "LEFT JOIN successbrian_os.goal_coverage gc "
        "ON s.source = 'goal_coverage:' || gc.id::text "
        "WHERE s.status = 'queued' "
        "AND COALESCE(gc.goal_slug, s.payload->>'goal_slug') = ANY(%s) "
        "ORDER BY s.priority DESC, s.created_at ASC LIMIT %s",
        [slugs, limit])
    cols = ["id", "step_key", "title", "kind", "priority",
            "created_at", "payload", "goal_slug"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def step_instruction(step):
    p = step.get("payload") or {}
    return (p.get("instruction") or p.get("question") or "")[:110]


def parse_groups(text, pool_ids):
    """Parse Einstein's consolidation reply into validated groups:
    [{title, step_ids, why}] - ids outside the pool are dropped,
    groups spanning <2 goals are dropped by the caller (it owns
    the id->goal map)."""
    if not text:
        return []
    flat = " ".join(str(text).split())
    m = re.search(r"GROUPS\s*:\s*(.*)$", flat, re.IGNORECASE)
    if not m or m.group(1).strip().lower() == "none":
        return []
    body = m.group(1)
    groups = []
    for chunk in body.split(";;"):
        gm = re.search(
            r"GROUP\s*\d+\s*:\s*(.*?)\s*\|\s*STEPS\s*:\s*([\d,\s]+)"
            r"\s*\|\s*WHY\s*:\s*(.*)", chunk, re.IGNORECASE)
        if not gm:
            continue
        ids = [int(x) for x in re.findall(r"\d+", gm.group(2))]
        ids = [i for i in ids if i in pool_ids]
        why = gm.group(3).strip()[:200]
        if len(ids) > FANOUT_CAP:
            why = (why + f" [fan-out capped at {FANOUT_CAP} of "
                   f"{len(ids)} members]").strip()
            ids = ids[:FANOUT_CAP]
        if len(ids) >= 2:
            groups.append({"title": gm.group(1).strip()[:120],
                           "step_ids": ids,
                           "why": why})
    return groups


def run_sweep(cur, force=False):
    """Dispatch one consolidation sweep if due (or forced) and
    none is in flight. Returns the bus event id or None."""
    cur.execute(
        "SELECT id, status, ran_at FROM "
        "successbrian_os.consolidation_sweeps ORDER BY id DESC LIMIT 1")
    last = cur.fetchone()
    if last and last[1] == "dispatched":
        print(f"  sweep: #{last[0]} still in flight, skipping")
        return None
    if last and not force:
        age_h = (datetime.now(timezone.utc) - last[2]).total_seconds() / 3600.0
        if age_h < SWEEP_MIN_AGE_H:
            print(f"  sweep: last sweep {age_h:.1f}h ago "
                  f"(< {SWEEP_MIN_AGE_H}h), skipping")
            return None
    pool = open_goal_steps(cur)
    if len(pool) < 4:
        print(f"  sweep: pool too small ({len(pool)} steps), skipping")
        return None
    lines = []
    for s in pool:
        instr = step_instruction(s)
        lines.append(f"[{s['id']}] ({s['goal_slug']}) {s['kind']}: "
                     f"{s['title'][:80]}"
                     + (f" - {instr}" if instr else ""))
    prompt = SWEEP_PROMPT_TEMPLATE.format(pool="\n".join(lines))
    probe_id = (f"harness-sweep-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    packet = sbos_common.build_reap_packet(
        prompt, source=SOURCE, probe_id=probe_id, item_ref="step-pool",
        max_tokens=MAX_TOKENS, thinking=False)
    event_id = sbos_common.dispatch_reap_packet(
        packet, source=SOURCE, priority=BUS_PRIORITY)
    cur.execute(
        "INSERT INTO successbrian_os.consolidation_sweeps "
        "(probe_id, bus_event_id, steps_scanned, pool_ids) "
        "VALUES (%s, %s, %s, %s::jsonb)",
        [probe_id, event_id, len(pool),
         json.dumps([s["id"] for s in pool])])
    print(f"  sweep: dispatched over {len(pool)} open steps "
          f"(bus event {event_id}, probe {probe_id})")
    return event_id


def _set_harness_note(cur, slug, body):
    """Insert/replace the GOAL-HARNESS section of a goal node's
    readme, preserving the GOAL-BRIEF and EINSTEIN-PLAN sections
    the other machinery owns."""
    node_key = gn.node_key_for_slug(slug)
    cur.execute("SELECT readme_md FROM atlas.nodes WHERE node_key = %s",
                [node_key])
    row = cur.fetchone()
    readme = (row[0] if row else None) or ""
    block = f"{HARNESS_BEGIN}\n{body.rstrip()}\n{HARNESS_END}"
    span = ep._section_span(readme, HARNESS_BEGIN, HARNESS_END)
    if span:
        new = readme[:span[0]] + block + readme[span[1]:]
    else:
        new = (readme.rstrip() + "\n\n" + block) if readme else block
    cur.execute("UPDATE atlas.nodes SET readme_md = %s "
                "WHERE node_key = %s", [new, node_key])


def collect_sweeps(cur):
    """Collect landed sweep results: validate Einstein's groups
    against the pool, file consolidation_proposals, and note each
    proposal in the affected goals' readmes. Proposals only -
    nothing is merged or deleted here, ever."""
    cur.execute(
        "SELECT id, bus_event_id, pool_ids FROM "
        "successbrian_os.consolidation_sweeps "
        "WHERE status = 'dispatched' ORDER BY id")
    n = 0
    for sweep_id, event_id, pool_ids in cur.fetchall():
        env = ep._result_for_event(event_id)
        if env is None:
            st = sbos_common.pg_one(
                "SELECT status FROM bus.events WHERE id = %s", (event_id,))
            if st in ("dead_letter", "failed"):
                cur.execute(
                    "UPDATE successbrian_os.consolidation_sweeps SET "
                    "status = 'failed', note = %s WHERE id = %s",
                    [f"bus event {st}", sweep_id])
            continue
        res = env.get("result") or {}
        text = res.get("text") if isinstance(res, dict) else None
        if not (env.get("ok") and text):
            cur.execute(
                "UPDATE successbrian_os.consolidation_sweeps SET "
                "status = 'failed', note = %s WHERE id = %s",
                [f"gamma result ok={env.get('ok')}, text "
                 f"{'present' if text else 'missing'}", sweep_id])
            continue
        pool = open_goal_steps(cur, limit=10000)
        by_id = {s["id"]: s for s in pool}
        # pool membership for validation is the sweep's own pool,
        # but a member step may have left 'queued' since dispatch;
        # fall back to a direct read for those.
        groups = parse_groups(text, set(pool_ids or []))
        filed = 0
        for gi, g in enumerate(groups, start=1):
            members = []
            for sid in g["step_ids"]:
                s = by_id.get(sid)
                if s is None:
                    cur.execute(
                        "SELECT id, step_key, title, "
                        "payload->>'goal_slug' FROM "
                        "successbrian_os.pm_steps WHERE id = %s", [sid])
                    r = cur.fetchone()
                    if not r:
                        continue
                    s = {"id": r[0], "step_key": r[1], "title": r[2],
                         "goal_slug": r[3]}
                members.append(s)
            goals = sorted({s["goal_slug"] for s in members
                            if s.get("goal_slug")})
            if len(members) < 2 or len(goals) < 2:
                continue
            group_key = f"sweep{sweep_id}-group{gi}"
            cur.execute(
                "INSERT INTO successbrian_os.consolidation_proposals "
                "(sweep_id, group_key, title, rationale, step_ids, "
                "step_keys, goal_slugs, gate_count) VALUES "
                "(%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s) "
                "ON CONFLICT (sweep_id, group_key) DO NOTHING",
                [sweep_id, group_key, g["title"], g["why"],
                 json.dumps([s["id"] for s in members]),
                 json.dumps([s["step_key"] for s in members]),
                 json.dumps(goals), len(goals)])
            filed += 1
            note = (f"# Harness consolidation note "
                    f"({datetime.now(timezone.utc).date()})\n"
                    f"Proposed shared task: \"{g['title']}\" - this "
                    f"goal is one of {len(goals)} goals gated on the "
                    f"same work (sweep {sweep_id}, group {gi}). "
                    f"Why: {g['why']} Member steps: "
                    + ", ".join(s["step_key"] for s in members)
                    + ". PROPOSAL only: nothing merged or deleted; "
                      "the ordering effect (shared work first) is "
                      "applied by the goal harness claim loop.")
            for slug in goals:
                _set_harness_note(cur, slug, note)
        cur.execute(
            "UPDATE successbrian_os.consolidation_sweeps SET "
            "status = 'collected', collected_at = now(), note = %s "
            "WHERE id = %s",
            [f"{filed} proposal group(s) filed from "
             f"{len(groups)} parsed", sweep_id])
        print(f"  sweep #{sweep_id}: collected - {filed} shared-task "
              f"group(s) filed as proposals")
        n += 1
    return n


# ---------------------------------------------------------------- claim loop

RESEARCH_PROMPT_TEMPLATE = """You are Einstein, the deep-research engine in a solo operator's goal system. A goal plan produced this research need. Answer it from evidence you can reason about, and say UNKNOWN plainly where the record or your knowledge is thin - never invent a fact, a price, a date, or a person's intent. Reply as ONE single unbroken block of text - NO blank lines (the channel keeps only the first block). Shape: ANSWER: <what the research settles, concrete and brief> EVIDENCE: <what the answer rests on> STILL UNKNOWN: <what remains open, or 'none'>. Under 460 tokens.

GOAL: {slug}
QUESTION: {question}
WHY IT MATTERS: {why}
WHERE THE ANSWER LIKELY LIVES: {where}"""


def ledger_has(cur, step_id, action):
    cur.execute(
        "SELECT 1 FROM successbrian_os.harness_claims "
        "WHERE step_id = %s AND action = %s LIMIT 1", [step_id, action])
    return cur.fetchone() is not None


def group_gates(cur):
    """step_id -> (max gate_count, proposal_id) over proposed
    consolidation groups."""
    cur.execute(
        "SELECT id, step_ids, gate_count FROM "
        "successbrian_os.consolidation_proposals "
        "WHERE status = 'proposed'")
    out = {}
    for pid, step_ids, gates in cur.fetchall():
        for sid in (step_ids or []):
            if sid not in out or gates > out[sid][0]:
                out[sid] = (gates, pid)
    return out


def is_outward(step):
    text = f"{step['title']} {step_instruction(step)}"
    return bool(OUTWARD_RE.search(text))


def claim_step(cur, step_id):
    cur.execute(
        "UPDATE successbrian_os.pm_steps SET status = 'running', "
        "actor = 'goal-harness', location = 'goal-harness', "
        "started_at = now(), heartbeat_at = now(), updated_at = now() "
        "WHERE id = %s AND status = 'queued' RETURNING id", [step_id])
    return cur.fetchone() is not None


def requeue_step(cur, step_id):
    cur.execute(
        "UPDATE successbrian_os.pm_steps SET status = 'queued', "
        "actor = NULL, started_at = NULL, updated_at = now() "
        "WHERE id = %s AND status = 'running' "
        "AND actor = 'goal-harness'", [step_id])


def apply_boosts(cur):
    """Ordering effect of consolidation (the only effect v1
    applies): a queued step inside a proposed shared-task group
    gets +5 priority per goal it gates (cap +25) in the shared
    pm_steps queue, once per (step, proposal), recorded in the
    claim ledger. Reversible: the ledger holds old/new values."""
    n = 0
    cur.execute(
        "SELECT id, step_ids, gate_count FROM "
        "successbrian_os.consolidation_proposals "
        "WHERE status = 'proposed' ORDER BY gate_count DESC")
    for pid, step_ids, gates in cur.fetchall():
        boost = min(25, 5 * gates)
        for sid in (step_ids or []):
            if ledger_has(cur, sid, "priority-boost"):
                continue
            cur.execute(
                "SELECT step_key, priority, status FROM "
                "successbrian_os.pm_steps WHERE id = %s", [sid])
            row = cur.fetchone()
            if not row or row[2] != "queued":
                continue
            cur.execute(
                "UPDATE successbrian_os.pm_steps SET priority = %s, "
                "updated_at = now() WHERE id = %s",
                [row[1] + boost, sid])
            cur.execute(
                "INSERT INTO successbrian_os.harness_claims "
                "(step_id, step_key, route, action, outcome, detail) "
                "VALUES (%s, %s, 'queue-order', 'priority-boost', "
                "'applied', %s::jsonb)",
                [sid, row[0], json.dumps(
                    {"proposal_id": pid, "gate_count": gates,
                     "old_priority": row[1], "new_priority": row[1] + boost})])
            n += 1
    return n


# ------------------------------------------------- Paperclip fold-ins
# Study: capture #3121 / second_brain #103683 (Paperclip's
# decomposition bookkeeping, blockedBy edges, disposition guard,
# heartbeat-context packet, plan-to-task restraint, exact-title
# floor). Confirmed Paperclip absences NOT copied: no goal
# metrics on the goal row, completion by self-report, no stall
# detection/re-look, no cross-goal consolidation - the harness
# already supplies those; Paperclip supplies the bookkeeping.

def normalize_title(title):
    """Exact-title floor key: strip the leading [goal] bracket,
    lowercase, drop punctuation, collapse whitespace."""
    t = re.sub(r"^\s*\[[^\]]*\]\s*", "", str(title or ""))
    t = re.sub(r"[^a-z0-9 ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def stall_update(stall_count, completed):
    """Magentic stall counter transition: any verified
    completion is progress (reset); a look without one stalls
    (+1). Returns (new_count, progressed)."""
    if completed and completed > 0:
        return 0, True
    return (stall_count or 0) + 1, False


# A research answer is checkable when its EVIDENCE names
# something the system can re-check: a URL, a file, a
# second_brain entry, a capture, a schema.table, a QA check, a
# date. (MetaGPT verification standard, capture #3122.)
CHECKABLE_RE = re.compile(
    r"https?://|\w+\.(?:py|md|sql|json|csv|txt)\b|second_brain|"
    r"capture\s+#?\d+|\b\w+\.\w+\b|QA\s*\d+|\b\d{4}-\d{2}-\d{2}\b")


def verify_research_answer(text):
    """MetaGPT gate (field study addendum, capture #3122): a
    worker's self-report is never 'done'. Where the output is
    checkable, verify by checking: a research answer settles
    only if it carries a substantive ANSWER and an EVIDENCE
    section naming at least one checkable artifact. Returns
    (ok, reason)."""
    if not text or len(str(text).strip()) < 40:
        return False, "answer empty or trivially short"
    flat = " ".join(str(text).split())
    am = re.search(r"ANSWER\s*:\s*(.*?)\s*EVIDENCE\s*:", flat,
                   re.IGNORECASE)
    if not am:
        return False, "no ANSWER/EVIDENCE structure to verify"
    if len(am.group(1).strip()) < 30:
        return False, "ANSWER section too thin to settle the question"
    em = re.search(r"EVIDENCE\s*:\s*(.*?)\s*STILL UNKNOWN\s*:",
                   flat, re.IGNORECASE)
    evidence = em.group(1) if em else flat.split("EVIDENCE:")[-1]
    if not CHECKABLE_RE.search(evidence):
        return False, ("EVIDENCE names nothing checkable (no URL, "
                       "file, entry, table, or dated record)")
    return True, "answer carries checkable evidence"


def step_depth(step_key):
    """Nesting depth of a step: Einstein-filed steps sit under a
    look (depth 2); planner dispatch steps and everything else
    are depth 1."""
    if str(step_key or "").startswith("einstein-look-"):
        return 2
    return 1


def would_cycle(adj, step_id, dep_id):
    """True if adding edge step_id -> dep_id (step depends on
    dep) would close a cycle in the depends-on graph adj
    {step_id: {dep_ids}}: dep can already reach step."""
    seen, stack = set(), [dep_id]
    while stack:
        node = stack.pop()
        if node == step_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adj.get(node, ()))
    return False


def _deps_adjacency(cur):
    cur.execute("SELECT step_id, depends_on_id FROM "
                "successbrian_os.pm_step_deps")
    adj = {}
    for a, b in cur.fetchall():
        adj.setdefault(a, set()).add(b)
    return adj


def step_blockers(cur, step_id):
    """The step's blocker edges as data: [{dep_id, dep_key,
    dep_status}] from pm_step_deps joined to the blocking step."""
    cur.execute(
        "SELECT d.depends_on_id, s.step_key, s.status FROM "
        "successbrian_os.pm_step_deps d JOIN "
        "successbrian_os.pm_steps s ON s.id = d.depends_on_id "
        "WHERE d.step_id = %s ORDER BY d.depends_on_id", [step_id])
    return [{"dep_id": r[0], "dep_key": r[1], "dep_status": r[2]}
            for r in cur.fetchall()]


def add_blocker(cur, step_key, blocked_by_key, reason="", by="operator"):
    """Record a first-class blocker edge (Paperclip blockedBy):
    step_key cannot proceed until blocked_by_key is done.
    Acyclicity is enforced - a cycle-closing edge is refused.
    Returns (ok, message)."""
    cur.execute("SELECT id FROM successbrian_os.pm_steps "
                "WHERE step_key = %s", [step_key])
    a = cur.fetchone()
    cur.execute("SELECT id FROM successbrian_os.pm_steps "
                "WHERE step_key = %s", [blocked_by_key])
    b = cur.fetchone()
    if not a or not b:
        return False, "step key not found"
    if a[0] == b[0]:
        return False, "a step cannot block itself"
    adj = _deps_adjacency(cur)
    if would_cycle(adj, a[0], b[0]):
        return False, "edge would close a dependency cycle - refused"
    cur.execute(
        "INSERT INTO successbrian_os.pm_step_deps "
        "(step_id, depends_on_id) VALUES (%s, %s) "
        "ON CONFLICT DO NOTHING", [a[0], b[0]])
    cur.execute(
        "INSERT INTO successbrian_os.harness_claims "
        "(step_id, step_key, route, action, outcome, detail) "
        "VALUES (%s, %s, 'blockers', 'blocker-added', 'recorded', "
        "%s::jsonb)",
        [a[0], step_key, json.dumps(
            {"blocked_by": blocked_by_key, "reason": reason,
             "by": by})])
    return True, f"{step_key} is blocked by {blocked_by_key}"


def collect_decompositions(cur):
    """Fingerprint every collected Einstein plan revision and
    record the exact step set it materialized, tracked to
    completion (Paperclip's issue_plan_decompositions shape)."""
    cur.execute(
        "SELECT p.id, p.goal_slug, p.look_id, p.plan_text FROM "
        "successbrian_os.einstein_passes p WHERE p.status = "
        "'collected' AND p.look_id IS NOT NULL ORDER BY p.id")
    n = 0
    for pass_id, slug, look_id, plan_text in cur.fetchall():
        src = f"goal_coverage:{look_id}"
        cur.execute(
            "SELECT step_key, status FROM successbrian_os.pm_steps "
            "WHERE source = %s ORDER BY id", [src])
        steps = cur.fetchall()
        keys = [r[0] for r in steps]
        done = sum(1 for r in steps if r[1] == "done")
        # depth: 2 when this look was itself dispatched by a step
        # an earlier Einstein look filed (chain), else 1.
        depth = 1
        cur.execute(
            "SELECT source FROM successbrian_os.pm_steps "
            "WHERE step_key = %s", [f"goal-look-{look_id}-dispatch"])
        drow = cur.fetchone()
        if drow and str(drow[0] or "").startswith("goal_coverage:"):
            depth = 2
        fp = hashlib.sha256(
            (plan_text or "").encode("utf-8")).hexdigest()[:16]
        cur.execute(
            "SELECT id FROM successbrian_os.plan_decompositions "
            "WHERE look_id = %s", [look_id])
        if cur.fetchone():
            cur.execute(
                "UPDATE successbrian_os.plan_decompositions SET "
                "step_keys = %s::jsonb, steps_total = %s, "
                "steps_done = %s, updated_at = now(), "
                "completed_at = CASE WHEN %s > 0 AND %s = %s "
                "THEN COALESCE(completed_at, now()) ELSE "
                "completed_at END WHERE look_id = %s",
                [json.dumps(keys), len(keys), done, len(keys), done,
                 len(keys), look_id])
        else:
            cur.execute(
                "INSERT INTO successbrian_os.plan_decompositions "
                "(look_id, pass_id, goal_slug, fingerprint, "
                "step_keys, steps_total, steps_done, depth, "
                "completed_at) VALUES (%s, %s, %s, %s, %s::jsonb, "
                "%s, %s, %s, CASE WHEN %s > 0 AND %s = %s THEN now() "
                "END)",
                [look_id, pass_id, slug, fp, json.dumps(keys),
                 len(keys), done, depth, len(keys), done, len(keys)])
            n += 1
    return n


def blocked_pass(cur):
    """Name the blockers of queued goal steps that carry blocker
    edges (the disposition guard's positive side): a waiting step
    must name its blocker in the ledger, once per step."""
    n = 0
    for s in open_goal_steps(cur, limit=400):
        blockers = [b for b in step_blockers(cur, s["id"])
                    if b["dep_status"] != "done"]
        if blockers and not ledger_has(cur, s["id"], "held-blocked"):
            cur.execute(
                "INSERT INTO successbrian_os.harness_claims "
                "(step_id, step_key, goal_slug, route, action, "
                "outcome, detail) VALUES (%s, %s, %s, 'blockers', "
                "'held-blocked', 'held', %s::jsonb)",
                [s["id"], s["step_key"], s["goal_slug"],
                 json.dumps({"blocked_by": [
                     b["dep_key"] for b in blockers]})])
            n += 1
    return n


def wake_pass(cur):
    """Resolution wakes (Paperclip blockedBy semantics): when a
    blocking step finished in the last 26h and a dependent's
    blockers are now ALL clear, the dependent wakes - priority
    nudge, ledger record, and its goal marked due-early."""
    n = 0
    goals = {s["id"]: s["goal_slug"]
             for s in open_goal_steps(cur, limit=1000)}
    cur.execute(
        "SELECT id, step_key FROM successbrian_os.pm_steps WHERE "
        "status = 'done' AND finished_at > now() - interval "
        "'26 hours'")
    for dep_id, dep_key in cur.fetchall():
        cur.execute(
            "SELECT step_id FROM successbrian_os.pm_step_deps "
            "WHERE depends_on_id = %s", [dep_id])
        for (sid,) in cur.fetchall():
            cur.execute(
                "SELECT step_key, status, priority FROM "
                "successbrian_os.pm_steps WHERE id = %s", [sid])
            srow = cur.fetchone()
            if not srow or srow[1] != "queued":
                continue
            if any(b["dep_status"] != "done"
                   for b in step_blockers(cur, sid)):
                continue
            cur.execute(
                "SELECT 1 FROM successbrian_os.harness_claims "
                "WHERE step_id = %s AND action = 'wake' AND "
                "detail->>'wake_on' = %s LIMIT 1", [sid, dep_key])
            if cur.fetchone():
                continue
            cur.execute(
                "UPDATE successbrian_os.pm_steps SET priority = %s, "
                "updated_at = now() WHERE id = %s",
                [srow[2] + 5, sid])
            cur.execute(
                "INSERT INTO successbrian_os.harness_claims "
                "(step_id, step_key, goal_slug, route, action, "
                "outcome, detail) VALUES (%s, %s, %s, "
                "'queue-order', 'wake', 'applied', %s::jsonb)",
                [sid, srow[0], goals.get(sid),
                 json.dumps({"wake_on": dep_key,
                             "old_priority": srow[2],
                             "new_priority": srow[2] + 5})])
            if goals.get(sid):
                set_due_early(cur, goals[sid],
                              f"blocker cleared: {dep_key}")
            n += 1
    return n


def disposition_audit(cur):
    """Paperclip's disposition guard: the system refuses narrated
    waiting states. A step in a waiting disposition must NAME its
    blocker - held_brian without a reason in payload, or a queued
    step whose payload narrates waiting_on with no blocker edge,
    is flagged in the ledger (visibility; no state is changed)."""
    n = 0
    cur.execute(
        "SELECT id, step_key, payload FROM successbrian_os.pm_steps "
        "WHERE status = 'held_brian'")
    for sid, skey, payload in cur.fetchall():
        payload = payload or {}
        named = any(k in payload for k in
                    ("reason", "decision", "blocker", "why", "note"))
        if not named and not ledger_has(cur, sid, "disposition-guard"):
            cur.execute(
                "INSERT INTO successbrian_os.harness_claims "
                "(step_id, step_key, route, action, outcome, detail) "
                "VALUES (%s, %s, 'brian', 'disposition-guard', "
                "'flagged', %s::jsonb)",
                [sid, skey, json.dumps(
                    {"issue": "held_brian without a named reason "
                              "or blocker in payload"})])
            n += 1
    for s in open_goal_steps(cur, limit=400):
        payload = s.get("payload") or {}
        if "waiting_on" in payload:
            if step_blockers(cur, s["id"]):
                continue
            if ledger_has(cur, s["id"], "disposition-guard"):
                continue
            cur.execute(
                "INSERT INTO successbrian_os.harness_claims "
                "(step_id, step_key, goal_slug, route, action, "
                "outcome, detail) VALUES (%s, %s, %s, 'blockers', "
                "'disposition-guard', 'flagged', %s::jsonb)",
                [s["id"], s["step_key"], s["goal_slug"],
                 json.dumps({"issue": "payload narrates waiting_on "
                                       "but no blocker edge names "
                                       "the blocker",
                             "waiting_on": str(
                                 payload.get("waiting_on"))[:200]})])
            n += 1
    return n


def exact_title_pass(cur):
    """The deterministic floor under the semantic sweep
    (Paperclip's exact-title dedup): open goal steps whose
    normalized titles are IDENTICAL across >=2 goals are the
    same work by construction. Files proposals like the sweep's
    (ordering effect only), watermark-gated to ~daily."""
    cur.execute("SELECT value FROM successbrian_os.harness_meta "
                "WHERE key = 'exact_title_last_at'")
    row = cur.fetchone()
    now_ts = datetime.now(timezone.utc).timestamp()
    if row and row[0]:
        try:
            age_h = (now_ts - float(row[0])) / 3600.0
            if age_h < EXACT_TITLE_MIN_AGE_H:
                return 0
        except ValueError:
            pass
    pool = open_goal_steps(cur, limit=200)
    groups = {}
    for s in pool:
        key = normalize_title(s["title"])
        if len(key) >= 12:
            groups.setdefault(key, []).append(s)
    cur.execute(
        "SELECT step_ids FROM successbrian_os.consolidation_proposals")
    existing = [set(r[0] or []) for r in cur.fetchall()]
    candidates = []
    for key, members in groups.items():
        goals = {m["goal_slug"] for m in members}
        if len(members) < 2 or len(goals) < 2:
            continue
        ids = [m["id"] for m in members][:FANOUT_CAP]
        idset = set(ids)
        if any(len(idset & e) / max(1, len(idset)) >= 0.8
               or len(idset & e) / max(1, len(e)) >= 0.8
               for e in existing):
            continue
        candidates.append((key, ids, goals))
        existing.append(idset)
    filed = 0
    if candidates:
        cur.execute(
            "INSERT INTO successbrian_os.consolidation_sweeps "
            "(probe_id, bus_event_id, steps_scanned, pool_ids, "
            "status, note) VALUES (%s, NULL, %s, %s::jsonb, "
            "'collected', %s) RETURNING id",
            [f"harness-exact-{int(now_ts)}", len(pool),
             json.dumps([m["id"] for m in pool]),
             "exact-title floor pass (deterministic; no Einstein "
             "packet)"])
        sweep_id = cur.fetchone()[0]
        for i, (key, ids, goals) in enumerate(candidates, 1):
            cur.execute(
                "INSERT INTO successbrian_os.consolidation_proposals "
                "(sweep_id, group_key, title, step_ids, goal_slugs, "
                "gate_count, rationale) VALUES (%s, %s, %s, "
                "%s::jsonb, %s::jsonb, %s, %s)",
                [sweep_id, f"exact-{sweep_id}-{i}", key[:120],
                 json.dumps(ids), json.dumps(sorted(goals)),
                 len(goals),
                 "exact-title match across goals (deterministic "
                 "floor under the semantic sweep)"])
            filed += 1
    cur.execute(
        "INSERT INTO successbrian_os.harness_meta (key, value) "
        "VALUES ('exact_title_last_at', %s) ON CONFLICT (key) DO "
        "UPDATE SET value = EXCLUDED.value, updated_at = now()",
        [str(now_ts)])
    if filed:
        print(f"  exact-title floor: {filed} group(s) filed")
    return filed


def step_context_packet(cur, s):
    """Heartbeat-context packet for a claimed step (Paperclip's
    heartbeat shape): the item, its goal/ancestor summary, its
    relations, and the continuation summary of prior touches -
    one block the working seat can act on without re-digging."""
    blockers = step_blockers(cur, s["id"])
    cur.execute("SELECT source FROM successbrian_os.pm_steps "
                "WHERE id = %s", [s["id"]])
    srow = cur.fetchone()
    step_source = srow[0] if srow else None
    cur.execute(
        "SELECT count(*) FROM successbrian_os.pm_step_deps "
        "WHERE depends_on_id = %s", [s["id"]])
    dependents = cur.fetchone()[0]
    gates = group_gates(cur)
    gate = gates.get(s["id"], (0, None))[0]
    cur.execute(
        "SELECT verdict FROM successbrian_os.harness_movements "
        "WHERE goal_slug = %s AND verdict IS NOT NULL ORDER BY id "
        "DESC LIMIT 1", [s["goal_slug"]])
    mv = cur.fetchone()
    cur.execute(
        "SELECT action, outcome, claimed_at FROM "
        "successbrian_os.harness_claims WHERE step_id = %s ORDER "
        "BY id DESC LIMIT 3", [s["id"]])
    prior = cur.fetchall()
    bl = "; ".join(f"{b['dep_key']} ({b['dep_status']})"
                   for b in blockers) or "none"
    pr = "; ".join(f"{a} -> {o or 'open'} at {str(t)[:16]}"
                   for a, o, t in prior) or "none - first touch"
    return (
        "STEP CONTEXT (goal harness heartbeat packet)\n"
        f"ITEM: [{s['step_key']}] {s['title']} "
        f"(kind {s['kind']}, priority {s.get('priority')})\n"
        f"GOAL: {s['goal_slug']} - last movement verdict: "
        f"{(mv[0] if mv else 'no look yet')}\n"
        f"SOURCE: {step_source}\n"
        f"RELATIONS: blocked by [{bl}]; steps depending on this "
        f"one: {dependents}; consolidation gate_count: {gate}\n"
        f"CONTINUATION: prior harness touches: {pr}")


# --------------------------------- Brian's additions (2026-11-23 19:05)
# ADDITION 1 - DECOMPOSITION ASSIST for weaker seats. Penny /
# Morpheus / Chuck-class seats cannot freehand breakdowns the
# way Einstein can, and Paperclip's failure #3307 is what
# unassisted freehand decomposition produces. So a weaker seat
# never freehands: it works inside a scaffold (the standing
# brief as MANDATORY input - no brief, no breakdown; the plan
# template; the restraint doctrine; depth cap 2 / fan-out cap
# 25), with Einstein's collected plans as few-shot exemplars.
# Its output is a DRAFT until Einstein reviews it against the
# brief + Brian's four tests; an approved draft materializes
# exactly once (deterministic step keys + the plan fingerprint
# rule); a draft that fails review twice escalates to a full
# Einstein look. Author seat + review outcome are recorded on
# every draft - that data feeds Addition 2's rollup.
#
# ADDITION 2 - EFFECTIVENESS FOLLOW-UP. Completion is not the
# end. Every harness-era completed step carries an INTENDED
# EFFECT (from its plan); beat (a) at completion is the
# MetaGPT gate already in the claim loop; beat (b) is this
# follow-up: after an interval suited to the kind, the harness
# checks whether the intended effect actually happened and
# records EFFECTIVE / INEFFECTIVE / TOO-EARLY / UNCHECKABLE
# with evidence. Verdicts land on the goal's harness note,
# feed Einstein's next look through the movement block, and
# aggregate in effectiveness_rollup (per seat, per kind).

BRIEF_SLICE = 6000  # brief chars in a scaffold packet

SCAFFOLD_TEMPLATE = """You are {seat}, a planning seat in a solo operator's goal system, drafting a task breakdown for ONE goal. You are not working freehand - work inside this scaffold exactly.
THE GOAL'S STANDING BRIEF (mandatory input - everything known about this goal; judge only from it, say UNKNOWN where it is silent):
{brief}
EXEMPLARS - two breakdowns the senior planner (Einstein) wrote for other goals. Match their shape and restraint:
{exemplars}
YOUR DRAFT - reply as ONE single unbroken block of text, NO blank lines, with EXACTLY these sections inline, in this order: MOVEMENT: <what has already moved on this goal, from the brief; 'first breakdown' if nothing> WORTH: <grade the goal against the operator's four tests: (1) makes sense for the ecosystem? (2) better than what we are currently doing? (3) how easy or hard to add? (4) more lucrative? - weighed against the operator's own time, the scarcest resource; end with STRONG, SOUND, WEAK, or FAILING> VERIFIED STATE: <what the brief proves today, at most 60 words> CLAIMED vs VERIFIED: <where the goal's claimed state disagrees with the brief, or 'none'> BLOCKERS: <what is actually stopping progress, or 'none proven'> PLAN: <numbered steps 1. 2. 3. - at most 4> RESEARCH NEEDS: <items shaped NEED: <question> | WHY: <why> | WHERE: <where the answer lives> - at most 2, or 'none'> FOR BRIAN: <only what the operator himself must decide, or 'none'>
RESTRAINT DOCTRINE (binding): a plan's steps do not each need to be a task - split only where the owner changes, work can run in parallel, a prerequisite boundary falls, or a review gate sits; merge micro-actions into the step that owns them. At most 4 plan steps and 2 research items. Each step is ONE executable action, at most 25 words. If this breakdown is beyond you, say so plainly in FOR BRIAN ('ESCALATE: beyond this seat') instead of guessing."""

REVIEW_TEMPLATE = """You are Einstein, reviewing a task breakdown drafted by a weaker seat ({seat}) for one goal. Judge the draft against the goal's standing brief and the operator's rules. Reply as ONE single unbroken block of text, NO blank lines. Shape: VERDICT: <APPROVE, REVISE, or ESCALATE> EFFECT: <one line: what should be different in the world or the goal when this plan's work succeeds> NOTES: <what is wrong or missing, concrete, at most 60 words; 'none' if approving clean>
Approve only if: the draft matches the brief (no invented facts, dates, or intents), its WORTH grade applies the four tests honestly (ecosystem fit; better than current; ease of adding; more lucrative - weighed against the operator's own time), the steps obey the restraint doctrine (split only at owner/parallel/prerequisite/review boundaries; at most 4 steps + 2 research), and nothing in it asks for an outward act (sending, publishing, buying, contacting) as a worker step. REVISE for fixable defects; ESCALATE when the goal itself needs your full look (thin or contradictory brief, judgment the draft cannot carry).
GOAL: {slug}
BRIEF (first part): {brief}
DRAFT: {draft}"""


def get_brief_md(cur, slug):
    cur.execute("SELECT brief_md FROM successbrian_os.goal_briefs "
                "WHERE goal_slug = %s", [slug])
    row = cur.fetchone()
    return row[0] if row else None


def exemplar_plans(cur, exclude_slug, n=2):
    cur.execute(
        "SELECT goal_slug, plan_text FROM "
        "successbrian_os.einstein_passes WHERE status = "
        "'collected' AND plan_text IS NOT NULL AND "
        "length(plan_text) > 200 AND goal_slug <> %s "
        "ORDER BY id DESC LIMIT %s", [exclude_slug, n])
    out = []
    for slug, text in cur.fetchall():
        out.append(f"--- exemplar (goal {slug}):\n{text[:1100]}")
    return "\n".join(out) if out else "(no exemplars on record)"


def draft_breakdown(cur, slug, seat="morpheus"):
    """Start an assisted breakdown: scaffold packet -> the
    weaker seat's engine queue. No brief, no breakdown."""
    brief = get_brief_md(cur, slug)
    if not brief:
        meta = ep.ensure_brief(cur, slug)
        brief = get_brief_md(cur, slug) if meta else None
    if not brief:
        print(f"  assist: {slug}: NO BRIEF - breakdown refused "
              f"(the brief is mandatory input)")
        return None
    packet = SCAFFOLD_TEMPLATE.format(
        seat=seat, brief=brief[:BRIEF_SLICE],
        exemplars=exemplar_plans(cur, slug))
    cur.execute(
        "INSERT INTO successbrian_os.breakdown_drafts "
        "(goal_slug, author_seat, status, brief_fingerprint) "
        "VALUES (%s, %s, 'drafting', %s) RETURNING id",
        [slug, seat,
         hashlib.sha256(brief.encode("utf-8")).hexdigest()[:16]])
    draft_id = cur.fetchone()[0]
    job_id = sbos_common.engine_job_enqueue(
        seat, "goal-harness", "chat",
        f"assisted breakdown: {slug}",
        payload={"prompt": packet, "draft_id": draft_id,
                 "goal_slug": slug},
        source_ref=f"decomp-assist:{draft_id}", priority=100)
    cur.execute(
        "UPDATE successbrian_os.breakdown_drafts SET "
        "engine_job_id = %s, updated_at = now() WHERE id = %s",
        [job_id, draft_id])
    print(f"  assist: draft #{draft_id} for {slug} -> {seat} "
          f"job {job_id} (scaffold + brief + exemplars)")
    return draft_id


def collect_drafts(cur):
    """Settle drafting jobs; a finished draft goes straight to
    Einstein review (it is a DRAFT until checked)."""
    n = 0
    cur.execute(
        "SELECT id, goal_slug, author_seat, engine_job_id FROM "
        "successbrian_os.breakdown_drafts WHERE status = "
        "'drafting' ORDER BY id")
    for draft_id, slug, seat, job_id in cur.fetchall():
        table = sbos_common.ENGINE_JOB_TABLES.get(seat)
        if not table or not job_id:
            continue
        cur.execute(f"SELECT status, result FROM {table} "
                    f"WHERE id = %s", [job_id])
        jrow = cur.fetchone()
        if not jrow:
            continue
        if jrow[0] == "failed":
            cur.execute(
                "UPDATE successbrian_os.breakdown_drafts SET "
                "status = 'draft-failed', updated_at = now() "
                "WHERE id = %s", [draft_id])
            n += 1
            continue
        if jrow[0] != "done":
            continue
        res = jrow[1]
        text = ""
        if isinstance(res, str):
            try:
                text = json.loads(res).get("text", "") or ""
            except Exception:
                text = res
        if not text:
            cur.execute(
                "UPDATE successbrian_os.breakdown_drafts SET "
                "status = 'draft-failed', review_notes = 'seat "
                "returned empty text', updated_at = now() "
                "WHERE id = %s", [draft_id])
            n += 1
            continue
        brief = get_brief_md(cur, slug) or ""
        prompt = REVIEW_TEMPLATE.format(
            seat=seat, slug=slug, brief=brief[:2500],
            draft=text[:3500])
        probe_id = f"assist-review-{draft_id}"
        packet = sbos_common.build_reap_packet(
            prompt, source=SOURCE, probe_id=probe_id,
            item_ref=slug, max_tokens=MAX_TOKENS, thinking=False)
        event_id = sbos_common.dispatch_reap_packet(
            packet, source=SOURCE, priority=BUS_PRIORITY)
        cur.execute(
            "UPDATE successbrian_os.breakdown_drafts SET "
            "status = 'reviewing', draft_text = %s, "
            "review_event_id = %s, updated_at = now() "
            "WHERE id = %s", [text, event_id, draft_id])
        print(f"  assist: draft #{draft_id} ({slug}, by {seat}) "
              f"drafted -> Einstein review (bus event {event_id})")
        n += 1
    return n


def parse_review(text):
    """(verdict, effect, notes) from an Einstein review reply."""
    if not text:
        return None, "", ""
    flat = " ".join(str(text).split())
    vm = re.search(r"VERDICT\s*:\s*(APPROVE|REVISE|ESCALATE)",
                   flat, re.IGNORECASE)
    if not vm:
        return None, "", flat[:300]
    em = re.search(r"EFFECT\s*:\s*(.*?)\s*NOTES\s*:", flat,
                   re.IGNORECASE)
    nm = re.search(r"NOTES\s*:\s*(.*)$", flat, re.IGNORECASE)
    return (vm.group(1).upper(),
            em.group(1).strip()[:400] if em else "",
            nm.group(1).strip()[:600] if nm else "")


def escalate_draft(cur, draft_id, slug, why):
    cur.execute(
        "UPDATE successbrian_os.breakdown_drafts SET status = "
        "'escalated', review_notes = %s, updated_at = now() "
        "WHERE id = %s", [why[:600], draft_id])
    try:
        cur.execute("SAVEPOINT esc")
        eid, _p = dispatch_harness_look(cur, slug, force=True)
        cur.execute("RELEASE SAVEPOINT esc")
        print(f"  assist: draft #{draft_id} escalated -> full "
              f"Einstein look for {slug} (bus event {eid})")
    except Exception as e:
        cur.execute("ROLLBACK TO SAVEPOINT esc")
        print(f"  assist: draft #{draft_id} escalation dispatch "
              f"failed: {e}")


def materialize_draft(cur, draft_id, slug, seat, draft_text,
                      effect):
    """An approved draft materializes exactly once: its steps
    file under deterministic keys (add_step is ON CONFLICT DO
    NOTHING) and the draft records the plan fingerprint + the
    step set, same rule as Einstein's own plans."""
    parsed = ep.parse_plan(draft_text)
    source = f"decomp_assist:{draft_id}"
    keys = []
    for i, st in enumerate(parsed["plan_steps"], 1):
        key = f"assist-{draft_id}-step-{i}"
        pm_core.add_step(
            cur, key, st[:200], kind="task", source=source,
            payload={"goal_slug": slug, "author_seat": seat,
                     "intended_effect": effect})
        keys.append(key)
    for i, r in enumerate(parsed["research"], 1):
        key = f"assist-{draft_id}-research-{i}"
        pm_core.add_step(
            cur, key, f"{r['question']}", kind="research",
            source=source,
            payload={"goal_slug": slug, "author_seat": seat,
                     "question": r["question"], "why": r["why"],
                     "where_answer_lives": r["where"],
                     "intended_effect": effect})
        keys.append(key)
    fp = hashlib.sha256(
        draft_text.encode("utf-8")).hexdigest()[:16]
    cur.execute(
        "UPDATE successbrian_os.breakdown_drafts SET status = "
        "'materialized', fingerprint = %s, "
        "materialized_step_keys = %s::jsonb, updated_at = now() "
        "WHERE id = %s", [fp, json.dumps(keys), draft_id])
    print(f"  assist: draft #{draft_id} APPROVED -> materialized "
          f"{len(keys)} step(s) for {slug} (fingerprint {fp})")
    return keys


def collect_reviews(cur):
    n = 0
    cur.execute(
        "SELECT id, goal_slug, author_seat, draft_text, "
        "review_event_id, review_count FROM "
        "successbrian_os.breakdown_drafts WHERE status = "
        "'reviewing' ORDER BY id")
    for (draft_id, slug, seat, draft_text, event_id,
         rcount) in cur.fetchall():
        env = ep._result_for_event(event_id)
        if env is None:
            continue
        res = env.get("result") or {}
        text = res.get("text") if isinstance(res, dict) else None
        verdict, effect, notes = parse_review(text or "")
        if verdict is None:
            verdict, notes = "REVISE", ("review unparseable: "
                                        + notes)[:600]
        rcount += 1
        if verdict == "APPROVE":
            cur.execute(
                "UPDATE successbrian_os.breakdown_drafts SET "
                "review_count = %s, review_verdict = 'APPROVE', "
                "review_notes = %s, intended_effect = %s, "
                "updated_at = now() WHERE id = %s",
                [rcount, notes, effect, draft_id])
            materialize_draft(cur, draft_id, slug, seat,
                              draft_text, effect)
        elif verdict == "ESCALATE" or rcount >= 2:
            cur.execute(
                "UPDATE successbrian_os.breakdown_drafts SET "
                "review_count = %s, review_verdict = %s, "
                "review_notes = %s, intended_effect = %s "
                "WHERE id = %s",
                [rcount, verdict, notes, effect, draft_id])
            escalate_draft(
                cur, draft_id, slug,
                f"{verdict} after {rcount} review(s): {notes}")
        else:
            cur.execute(
                "UPDATE successbrian_os.breakdown_drafts SET "
                "status = 'revise-returned', review_count = %s, "
                "review_verdict = 'REVISE', review_notes = %s, "
                "intended_effect = %s, updated_at = now() "
                "WHERE id = %s", [rcount, notes, effect, draft_id])
            print(f"  assist: draft #{draft_id} REVISE (review "
                  f"{rcount}) - returned with notes; a second "
                  f"failure escalates")
        n += 1
    return n


def followup_interval_days(kind, step_key):
    if "dispatch" in str(step_key):
        return 3
    return 7 if kind == "research" else 14


def create_followups(cur):
    """One follow-up row per harness-era completed step that
    lacks one: intended effect from its plan, due date by
    kind. Harness era = finished on/after 2026-11-20."""
    n = 0
    cur.execute(
        "SELECT s.id, s.step_key, s.kind, s.source, s.payload, "
        "s.finished_at, COALESCE(gc.goal_slug, "
        "s.payload->>'goal_slug') FROM successbrian_os.pm_steps s "
        "LEFT JOIN successbrian_os.goal_coverage gc ON "
        "s.source = 'goal_coverage:' || gc.id::text "
        "WHERE s.status = 'done' AND s.finished_at >= "
        "'2026-11-20' AND (s.source LIKE 'goal_coverage:%' OR "
        "s.source LIKE 'decomp_assist:%') AND NOT EXISTS ("
        "SELECT 1 FROM successbrian_os.effect_followups f "
        "WHERE f.step_id = s.id) ORDER BY s.finished_at LIMIT 50")
    for (sid, skey, kind, source, payload, fin, slug) \
            in cur.fetchall():
        payload = payload or {}
        seat = "einstein"
        effect = payload.get("intended_effect") or ""
        if source.startswith("decomp_assist:"):
            did = source.split(":", 1)[1]
            cur.execute(
                "SELECT author_seat, intended_effect FROM "
                "successbrian_os.breakdown_drafts WHERE id = %s",
                [int(did)])
            drow = cur.fetchone()
            if drow:
                seat, effect = drow[0], effect or (drow[1] or "")
        elif "dispatch" in skey:
            effect = effect or ("the deep look this step "
                                "dispatches happens and writes "
                                "back a plan with follow-up steps")
        if not effect and source.startswith("goal_coverage:"):
            look_id = source.split(":", 1)[1]
            cur.execute(
                "SELECT plan_text FROM "
                "successbrian_os.einstein_passes WHERE look_id "
                "= %s AND plan_text IS NOT NULL ORDER BY id DESC "
                "LIMIT 1", [int(look_id)])
            prow = cur.fetchone()
            if prow:
                effect = ep.parse_plan(
                    prow[0])["verified"][:300]
        days = followup_interval_days(kind, skey)
        cur.execute(
            "INSERT INTO successbrian_os.effect_followups "
            "(step_id, step_key, goal_slug, kind, author_seat, "
            "intended_effect, completed_at, due_at) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s + (%s || ' days')"
            "::interval) ON CONFLICT (step_id) DO NOTHING",
            [sid, skey, slug, kind, seat, effect[:400], fin,
             fin, days])
        n += 1
    return n


def _append_harness_note(cur, slug, line):
    node_key = gn.node_key_for_slug(slug)
    cur.execute("SELECT readme_md FROM atlas.nodes WHERE "
                "node_key = %s", [node_key])
    row = cur.fetchone()
    readme = (row[0] if row else None) or ""
    span = ep._section_span(readme, HARNESS_BEGIN, HARNESS_END)
    body = ""
    if span:
        body = readme[span[0] + len(HARNESS_BEGIN):
                      span[1] - len(HARNESS_END)].strip()
    _set_harness_note(cur, slug,
                      (body + "\n" + line).strip() if body else line)


def run_followups(cur, limit=5):
    """Beat (b): for due follow-ups, judge from the record
    whether the intended effect happened. Deterministic
    evidence first - a verdict names what it rests on."""
    n = 0
    cur.execute(
        "SELECT id, step_id, step_key, goal_slug, kind, "
        "intended_effect, completed_at FROM "
        "successbrian_os.effect_followups WHERE status = "
        "'pending' AND due_at <= now() ORDER BY due_at LIMIT %s",
        [limit])
    for (fid, sid, skey, slug, kind, effect, fin) \
            in cur.fetchall():
        verdict, evidence = "UNCHECKABLE", ""
        if "dispatch" in skey:
            m = re.search(r"goal-look-(\d+)-dispatch", skey)
            look_id = int(m.group(1)) if m else None
            cur.execute(
                "SELECT count(*) FROM successbrian_os.pm_steps "
                "WHERE source = %s",
                [f"goal_coverage:{look_id}"])
            filed = cur.fetchone()[0]
            cur.execute(
                "SELECT id FROM successbrian_os.einstein_passes "
                "WHERE look_id = %s AND plan_text IS NOT NULL "
                "ORDER BY id DESC LIMIT 1", [look_id])
            prow = cur.fetchone()
            if prow or filed > 1:
                verdict = "EFFECTIVE"
                evidence = (f"look {look_id} produced "
                            f"{filed} filed step(s)"
                            + (f"; einstein pass {prow[0]} "
                               f"wrote a plan" if prow else ""))
            else:
                verdict = "INEFFECTIVE"
                evidence = (f"look {look_id} filed no follow-up "
                            f"steps and no einstein plan exists")
        elif kind == "research":
            cur.execute(
                "SELECT id FROM successbrian_os.einstein_passes "
                "WHERE goal_slug = %s AND status = 'collected' "
                "AND collected_at > %s ORDER BY id LIMIT 1",
                [slug, fin])
            crow = cur.fetchone()
            if crow:
                verdict = "EFFECTIVE"
                evidence = (f"a later collected look (pass "
                            f"{crow[0]}) consumed the goal's "
                            f"record after this answer landed")
            elif (datetime.now(timezone.utc) - fin).days < 30:
                verdict = "TOO-EARLY"
                evidence = ("no consuming look yet; under 30 "
                            "days since completion")
            else:
                evidence = ("no consuming look on record 30+ "
                            "days after completion")
        else:
            cur.execute(
                "SELECT s.step_key FROM successbrian_os.pm_steps s "
                "LEFT JOIN successbrian_os.goal_coverage gc ON "
                "s.source = 'goal_coverage:' || gc.id::text "
                "WHERE s.status = 'done' AND s.finished_at > %s "
                "AND s.id <> %s AND COALESCE(gc.goal_slug, "
                "s.payload->>'goal_slug') = %s LIMIT 1",
                [fin, sid, slug or ""])
            grow = cur.fetchone()
            if grow:
                verdict = "EFFECTIVE"
                evidence = (f"follow-on work for the goal "
                            f"completed afterwards ({grow[0]})")
            elif (datetime.now(timezone.utc) - fin).days < 28:
                verdict = "TOO-EARLY"
                evidence = "no follow-on completion yet; early"
            else:
                evidence = ("no follow-on completion on record "
                            "28+ days after completion")
        cur.execute(
            "UPDATE successbrian_os.effect_followups SET "
            "status = 'done', verdict = %s, evidence = %s, "
            "checked_at = now() WHERE id = %s",
            [verdict, evidence[:500], fid])
        if slug:
            _append_harness_note(
                cur, slug,
                f"EFFECTIVENESS {verdict}: step {skey} - "
                f"intended: {(effect or '')[:160]} | evidence: "
                f"{evidence[:220]}")
        print(f"  followup: {skey} -> {verdict} ({evidence[:80]})")
        n += 1
    return n


def claim_cycle(cur, limit=CLAIM_PER_CYCLE):
    """One claim pass in harness order: consolidated/shared steps
    first, then research, then goal tier. Safe classes only -
    see the module docstring. Returns (claimed, held, noted)."""
    gates = group_gates(cur)
    cur.execute(
        "SELECT goal_slug, tier FROM successbrian_os.goal_harness_state")
    tiers = {r[0]: r[1] for r in cur.fetchall()}
    tier_bonus = {"daily": 30, "standard": 20, "slow": 10, "gated": 0}
    pool = open_goal_steps(cur, limit=400)

    def score(s):
        g = gates.get(s["id"], (0, None))[0]
        return (g * 20 + tier_bonus.get(tiers.get(s["goal_slug"]), 10)
                + (10 if s["kind"] == "research" else 0)
                + (s["priority"] or 50) / 10.0)
    pool.sort(key=score, reverse=True)
    claimed = held = noted = 0
    for s in pool:
        if claimed >= limit:
            break
        if step_depth(s["step_key"]) > DEPTH_CAP:
            if not ledger_has(cur, s["id"], "depth-cap-refused"):
                cur.execute(
                    "INSERT INTO successbrian_os.harness_claims "
                    "(step_id, step_key, goal_slug, route, action, "
                    "outcome, detail) VALUES (%s, %s, %s, 'none', "
                    "'depth-cap-refused', 'held', %s::jsonb)",
                    [s["id"], s["step_key"], s["goal_slug"],
                     json.dumps({"reason": f"step depth exceeds "
                                           f"the {DEPTH_CAP}-level "
                                           f"cap on harness-created "
                                           f"work"})])
            continue
        if any(b["dep_status"] != "done"
               for b in step_blockers(cur, s["id"])):
            continue  # blocked: named in the ledger by blocked_pass
        if is_outward(s):
            if not ledger_has(cur, s["id"], "held-for-brian"):
                cur.execute(
                    "INSERT INTO successbrian_os.harness_claims "
                    "(step_id, step_key, goal_slug, route, action, "
                    "outcome, detail) VALUES (%s, %s, %s, 'brian', "
                    "'held-for-brian', 'held', %s::jsonb)",
                    [s["id"], s["step_key"], s["goal_slug"],
                     json.dumps({"reason": "outward-action screen: "
                                           "step text asks for an "
                                           "outward act; never "
                                           "auto-claimed"})])
                held += 1
            continue
        payload = s.get("payload") or {}
        if s["kind"] == "research":
            if not claim_step(cur, s["id"]):
                continue
            prompt = RESEARCH_PROMPT_TEMPLATE.format(
                slug=s["goal_slug"], question=payload.get("question")
                or s["title"], why=payload.get("why", ""),
                where=payload.get("where_answer_lives", ""))
            prompt += "\n\n" + step_context_packet(cur, s)
            probe_id = f"harness-research-{s['id']}"
            packet = sbos_common.build_reap_packet(
                prompt, source=SOURCE, probe_id=probe_id,
                item_ref=s["step_key"], max_tokens=MAX_TOKENS,
                thinking=False)
            event_id = sbos_common.dispatch_reap_packet(
                packet, source=SOURCE, priority=BUS_PRIORITY)
            cur.execute(
                "INSERT INTO successbrian_os.harness_claims "
                "(step_id, step_key, goal_slug, route, action, "
                "bus_event_id, detail) VALUES (%s, %s, %s, 'reap', "
                "'claimed', %s, %s::jsonb)",
                [s["id"], s["step_key"], s["goal_slug"], event_id,
                 json.dumps({"probe_id": probe_id,
                             "gate_count": gates.get(s["id"], (0,))[0]})])
            claimed += 1
            print(f"  claim: research step {s['step_key']} "
                  f"({s['goal_slug']}) -> Einstein (bus event {event_id})")
        elif payload.get("engine_tier") in sbos_common.ENGINE_JOB_TABLES:
            engine = payload["engine_tier"]
            if not claim_step(cur, s["id"]):
                continue
            job_id = sbos_common.engine_job_enqueue(
                engine, "goal-harness", "goal-step", s["title"][:120],
                payload={"step_key": s["step_key"],
                         "instruction": payload.get("instruction", ""),
                         "goal_slug": s["goal_slug"],
                         "context": step_context_packet(cur, s)},
                source_ref=s["step_key"], priority=100)
            cur.execute(
                "INSERT INTO successbrian_os.harness_claims "
                "(step_id, step_key, goal_slug, route, action, "
                "engine_job_id, detail) VALUES (%s, %s, %s, 'engine', "
                "'claimed', %s, %s::jsonb)",
                [s["id"], s["step_key"], s["goal_slug"], job_id,
                 json.dumps({"engine": engine})])
            claimed += 1
            print(f"  claim: step {s['step_key']} ({s['goal_slug']}) "
                  f"-> {engine} job {job_id}")
        else:
            if not ledger_has(cur, s["id"], "unrouted-noted"):
                cur.execute(
                    "INSERT INTO successbrian_os.harness_claims "
                    "(step_id, step_key, goal_slug, route, action, "
                    "outcome, detail) VALUES (%s, %s, %s, 'none', "
                    "'unrouted-noted', 'noted', %s::jsonb)",
                    [s["id"], s["step_key"], s["goal_slug"],
                     json.dumps({"reason": "no safe harness route in "
                                           "v1 (not research, no "
                                           "engine_tier); left queued "
                                           "for the existing workers, "
                                           "in harness-boosted order"})])
                noted += 1
    return claimed, held, noted


def collect_claims(cur):
    """Settle harness claims whose artifact landed; requeue on
    failure; reap stale claims. A research answer landing marks
    its goal due-early (event trigger)."""
    cur.execute(
        "SELECT id, step_id, step_key, goal_slug, route, bus_event_id, "
        "engine_job_id, claimed_at, detail FROM "
        "successbrian_os.harness_claims WHERE action = 'claimed' "
        "AND outcome IS NULL ORDER BY id")
    settled = 0
    for (cid, step_id, step_key, slug, route, event_id, job_id,
         claimed_at, detail) in cur.fetchall():
        stale = (datetime.now(timezone.utc) - claimed_at).total_seconds() \
            > STALE_CLAIM_H * 3600
        if route == "reap":
            env = ep._result_for_event(event_id)
            if env is not None:
                res = env.get("result") or {}
                text = res.get("text") if isinstance(res, dict) else None
                if env.get("ok") and text:
                    # MetaGPT gate: never settle on the worker's
                    # word - the answer must carry checkable
                    # evidence, or the step goes back to the
                    # queue with the failure recorded.
                    vok, vwhy = verify_research_answer(text)
                    if not vok:
                        requeue_step(cur, step_id)
                        cur.execute(
                            "UPDATE successbrian_os.harness_claims "
                            "SET outcome = "
                            "'verification-failed-requeued', "
                            "finished_at = now(), detail = "
                            "detail || %s::jsonb WHERE id = %s",
                            [json.dumps({"verification": vwhy}),
                             cid])
                        settled += 1
                        print(f"  claim NOT settled: {step_key} "
                              f"failed verification ({vwhy}); "
                              f"requeued")
                        continue
                    pm_core.finish(cur, step_key, "done", {
                        "answer": text[:1500],
                        "via": "goal-harness research (Einstein REAP)",
                        "verification": vwhy,
                        "bus_event_id": event_id})
                    cur.execute(
                        "UPDATE successbrian_os.harness_claims SET "
                        "outcome = 'verified-done', "
                        "finished_at = now() WHERE id = %s", [cid])
                    if slug:
                        set_due_early(
                            cur, slug,
                            f"research answer landed: {step_key}")
                    settled += 1
                    print(f"  claim settled: {step_key} "
                          f"verified-done (research answer "
                          f"landed; {slug} due-early)")
                else:
                    requeue_step(cur, step_id)
                    cur.execute(
                        "UPDATE successbrian_os.harness_claims SET "
                        "outcome = 'reap-result-unusable-requeued', "
                        "finished_at = now() WHERE id = %s", [cid])
                    settled += 1
                continue
            st = sbos_common.pg_one(
                "SELECT status FROM bus.events WHERE id = %s", (event_id,))
            if st in ("dead_letter", "failed"):
                requeue_step(cur, step_id)
                cur.execute(
                    "UPDATE successbrian_os.harness_claims SET "
                    "outcome = 'reap-failed-requeued', "
                    "finished_at = now() WHERE id = %s", [cid])
                settled += 1
                continue
        elif route == "engine":
            engine = (detail or {}).get("engine")
            table = sbos_common.ENGINE_JOB_TABLES.get(engine or "")
            if table:
                jrow = sbos_common.pg_one(
                    f"SELECT status FROM {table} WHERE id = %s",
                    (job_id,))
                if jrow in ("done", "completed"):
                    pm_core.finish(cur, step_key, "done", {
                        "via": f"goal-harness -> {engine} job {job_id}",
                        "engine_job_id": job_id})
                    cur.execute(
                        "UPDATE successbrian_os.harness_claims SET "
                        "outcome = 'done', finished_at = now() "
                        "WHERE id = %s", [cid])
                    settled += 1
                    continue
                if jrow in ("failed", "error"):
                    requeue_step(cur, step_id)
                    cur.execute(
                        "UPDATE successbrian_os.harness_claims SET "
                        "outcome = 'engine-failed-requeued', "
                        "finished_at = now() WHERE id = %s", [cid])
                    settled += 1
                    continue
        if stale:
            requeue_step(cur, step_id)
            cur.execute(
                "UPDATE successbrian_os.harness_claims SET "
                "outcome = 'reaped-stale-requeued', "
                "finished_at = now() WHERE id = %s", [cid])
            settled += 1
            print(f"  claim reaped: {step_key} stale "
                  f"(>{STALE_CLAIM_H}h, no result) - requeued")
    return settled


# ---------------------------------------------------------------- cycle

def cycle(limit=DISPATCH_PER_CYCLE):
    got = ep.collect()
    if got:
        print(f"cycle: einstein collect wrote back {got} plan(s)")
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        conn.commit()
        slugs = rotation_slugs()
        tiers = compute_tiers(cur, slugs)
        conn.commit()
        dist = {}
        for t in tiers.values():
            dist[t["tier"]] = dist.get(t["tier"], 0) + 1
        print(f"cycle: tiers over {len(slugs)} goals: {dist}")
        cur.execute("BEGIN")
        nmv = collect_movements(cur)
        conn.commit()
        cur.execute("BEGIN")
        nsw = collect_sweeps(cur)
        conn.commit()
        cur.execute("BEGIN")
        ncl = collect_claims(cur)
        conn.commit()
        cur.execute("BEGIN")
        ndec = collect_decompositions(cur)
        nblk = blocked_pass(cur)
        nwak = wake_pass(cur)
        ndsp = disposition_audit(cur)
        conn.commit()
        cur.execute("BEGIN")
        nex = exact_title_pass(cur)
        conn.commit()
        cur.execute("BEGIN")
        ndr = collect_drafts(cur)
        nrv = collect_reviews(cur)
        nfu = create_followups(cur)
        nfv = run_followups(cur)
        conn.commit()
        cur.execute("BEGIN")
        nev = scan_capture_events(cur, slugs)
        conn.commit()
        cur.execute("BEGIN")
        run_sweep(cur)
        conn.commit()
        # dispatch due looks, honoring the in-flight cap
        cur.execute("BEGIN")
        room = max(0, MAX_INFLIGHT_LOOKS - inflight_look(cur))
        due = due_goals(cur, slugs, min(limit, room))
        sent = 0
        for d in due:
            try:
                cur.execute("BEGIN")
                meta = ep.ensure_brief(cur, d["slug"])
                conn.commit()
                if meta is not None:
                    print(f"  {d['slug']}: brief refreshed "
                          f"(origin {meta['origin_class']})")
            except Exception as e:
                conn.rollback()
                print(f"  {d['slug']}: BRIEF REFRESH FAILED {e}")
            try:
                cur.execute("BEGIN")
                eid, _probe = dispatch_harness_look(cur, d["slug"])
                if eid is not None:
                    clear_due_early(cur, d["slug"])
                    sent += 1
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"  {d['slug']}: DISPATCH FAILED {e}")
        conn.commit()
        cur.execute("BEGIN")
        boosts = apply_boosts(cur)
        claimed, held, noted = claim_cycle(cur)
        conn.commit()
        print(f"cycle: movements {nmv}, sweeps collected {nsw}, "
              f"claims settled {ncl}, capture events {nev}, "
              f"looks dispatched {sent}, boosts {boosts}, "
              f"claimed {claimed}, held-for-brian {held}, "
              f"unrouted-noted {noted}")
        print(f"cycle: paperclip passes: decompositions +{ndec}, "
              f"blocked-named {nblk}, wakes {nwak}, disposition "
              f"flags {ndsp}, exact-title groups {nex}")
        print(f"cycle: assist drafts settled {ndr}, reviews "
              f"settled {nrv}, followups created {nfu}, "
              f"followup verdicts {nfv}")
        return 0
    finally:
        conn.close()


def status():
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        conn.commit()
        cur.execute(
            "SELECT tier, count(*), count(*) FILTER (WHERE due_early) "
            "FROM successbrian_os.goal_harness_state GROUP BY tier")
        print("tiers (tier: goals, due-early):")
        for tier, n, de in cur.fetchall():
            print(f"  {tier}: {n} goals, {de} due-early")
        cur.execute(
            "SELECT count(*) FROM successbrian_os.harness_movements")
        print(f"movement records: {cur.fetchone()[0]}")
        cur.execute(
            "SELECT count(*), coalesce(sum(gate_count),0) FROM "
            "successbrian_os.consolidation_proposals "
            "WHERE status = 'proposed'")
        np_, gates = cur.fetchone()
        print(f"consolidation proposals: {np_} groups gating "
              f"{gates} goal-slots")
        cur.execute(
            "SELECT action, outcome, count(*) FROM "
            "successbrian_os.harness_claims GROUP BY 1, 2 ORDER BY 3 DESC")
        for a, o, n in cur.fetchall():
            print(f"claims: {a}/{o}: {n}")
        cur.execute(
            "SELECT status, count(*) FROM "
            "successbrian_os.consolidation_sweeps GROUP BY 1")
        for s, n in cur.fetchall():
            print(f"sweeps: {s}: {n}")
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------- selftest

def selftest():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")

    check("tier map: critical/high daily, medium standard, low slow",
          PRIORITY_TIER["critical"] == "daily"
          and PRIORITY_TIER["high"] == "daily"
          and PRIORITY_TIER["medium"] == "standard"
          and PRIORITY_TIER["low"] == "slow")
    check("windows: daily 1, gated 14",
          TIER_WINDOWS["daily"] == 1 and TIER_WINDOWS["gated"] == 14)
    sample = ("MOVEMENT: 2 of 5 steps completed since last look; 1 "
              "stuck; moving too slowly for a daily goal. VERIFIED "
              "STATE: record shows x. CLAIMED vs VERIFIED: none. "
              "BLOCKERS: none proven. PLAN: 1. Do the thing. "
              "RESEARCH NEEDS: none FOR BRIAN: none")
    check("parse_movement extracts the verdict",
          parse_movement(sample).startswith("2 of 5 steps completed"))
    check("parse_movement empty on section-less text",
          parse_movement("just some prose") == "")
    worth_sample = ("MOVEMENT: nothing completed; 3 queued. WORTH: "
                    "Makes sense for the ecosystem; fleet carries it "
                    "without Brian-hours; verdict SOUND. VERIFIED "
                    "STATE: record shows x. BLOCKERS: none proven.")
    check("parse_movement stops at WORTH",
          parse_movement(worth_sample) == "nothing completed; 3 queued.")
    check("parse_worth extracts the four-tests grade",
          parse_worth(worth_sample).endswith("verdict SOUND."))
    check("parse_worth empty on pre-ruling plans",
          parse_worth(sample) == "")
    pool = {11, 12, 13, 21, 22}
    gtext = ("GROUPS: GROUP 1: Warm a sending domain | STEPS: 11, 12, "
             "99 | WHY: same warm-up work ;; GROUP 2: Count signups | "
             "STEPS: 21, 22 | WHY: same instrumentation")
    groups = parse_groups(gtext, pool)
    check("parse_groups validates ids against the pool",
          len(groups) == 2 and groups[0]["step_ids"] == [11, 12])
    check("parse_groups: GROUPS none -> []",
          parse_groups("GROUPS: none", pool) == [])
    big_pool = set(range(100, 140))
    big = ("GROUPS: GROUP 1: Big shared task | STEPS: "
           + ", ".join(str(i) for i in range(100, 132))
           + " | WHY: same work")
    bgroups = parse_groups(big, big_pool)
    check("parse_groups fan-out cap holds at 25",
          len(bgroups) == 1
          and len(bgroups[0]["step_ids"]) == FANOUT_CAP
          and "fan-out capped" in bgroups[0]["why"])
    check("normalize_title strips goal bracket + punctuation",
          normalize_title("[gotbackup] Confirm whether this goal "
                          "is complete or needs re-targeting:")
          == "confirm whether this goal is complete or needs "
             "re targeting")
    check("normalize_title equates case/punctuation variants",
          normalize_title("Count Signups, Weekly!")
          == normalize_title("count signups weekly"))
    adj = {1: {2}, 2: {3}}
    check("would_cycle catches a cycle-closing edge",
          would_cycle(adj, 3, 1))
    check("would_cycle allows an acyclic edge",
          not would_cycle(adj, 1, 3))
    check("step_depth: einstein-filed steps are depth 2",
          step_depth("einstein-look-271-step-1") == 2
          and step_depth("goal-look-271-dispatch") == 1)
    check("stall_update: completion resets, silence increments",
          stall_update(3, 2) == (0, True)
          and stall_update(1, 0) == (2, False)
          and stall_update(0, 0) == (1, False))
    good = ("ANSWER: The count lives in public.keyword_inventory "
            "and 19 phrases were filed 2026-11-21. EVIDENCE: "
            "second_brain entry 103641 and keyword_inventory ids "
            "15741-15759. STILL UNKNOWN: none")
    check("verify_research_answer passes checkable evidence",
          verify_research_answer(good)[0])
    check("verify_research_answer rejects bare self-report",
          not verify_research_answer(
              "ANSWER: It is definitely handled and fine now. "
              "EVIDENCE: I checked carefully and it works. "
              "STILL UNKNOWN: none")[0])
    check("verify_research_answer rejects empty output",
          not verify_research_answer("")[0]
          and not verify_research_answer("ANSWER: x")[0])
    rv = parse_review("VERDICT: APPROVE EFFECT: Signup counting "
                      "exists and is read weekly. NOTES: none")
    check("parse_review reads an approval + effect",
          rv[0] == "APPROVE"
          and rv[1].startswith("Signup counting"))
    check("parse_review reads an escalation",
          parse_review("VERDICT: ESCALATE EFFECT: x NOTES: thin "
                       "brief")[0] == "ESCALATE")
    check("parse_review: garbage -> no verdict",
          parse_review("some prose without structure")[0] is None)
    check("followup intervals: dispatch 3d, research 7d, task 14d",
          followup_interval_days("task", "goal-look-9-dispatch") == 3
          and followup_interval_days("research", "r-1") == 7
          and followup_interval_days("build", "b-1") == 14)

    class FakeStep(dict):
        pass

    def fs(title, instr=""):
        return {"title": title, "payload": {"instruction": instr}}
    check("outward screen holds a send step",
          is_outward(fs("Send the outreach email to the leads")))
    check("outward screen holds a publish step",
          is_outward(fs("Publish the drafted post to the blog")))
    check("outward screen passes a research-style step",
          not is_outward(fs("Create task list for evaluating vision "
                             "models on the A2000")))
    check("outward screen passes a documentation step",
          not is_outward(fs("Document the local deployment "
                             "architecture for clients")))
    mv = {"since": None, "completed": 0, "failed": 0, "running": 0,
          "queued": 3, "stuck": 1, "total": 3, "done_keys": [],
          "stuck_keys": ["k1"]}
    check("movement block renders counts",
          "queued now: 3" in movement_block(mv)
          and "first deep look" in movement_block(mv))
    prompt = PROMPT_TEMPLATE.format(context="CTX")
    check("harness prompt carries all seven sections in order",
          [prompt.find(h + ":") for h in SECTION_HEADERS] ==
          sorted(prompt.find(h + ":") for h in SECTION_HEADERS)
          and all(prompt.find(h + ":") >= 0 for h in SECTION_HEADERS))
    slugs = rotation_slugs()
    check("rotation readable and non-empty", len(slugs) >= 40)
    failed = [n for n, ok in checks if not ok]
    print(f"selftest: {len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--tiers", action="store_true")
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--cycle", nargs="?", const=DISPATCH_PER_CYCLE,
                    type=int, metavar="N")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--slug", metavar="SLUG",
                    help="with --cycle: dispatch one named goal "
                         "(force re-look)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--add-blocker", metavar="STEP_KEY",
                    help="record a blocker edge: STEP_KEY cannot "
                         "proceed until --blocked-by is done")
    ap.add_argument("--blocked-by", metavar="STEP_KEY")
    ap.add_argument("--draft", metavar="SLUG",
                    help="start an assisted breakdown for a goal "
                         "by a weaker seat (see --seat)")
    ap.add_argument("--seat", default="morpheus",
                    help="drafting seat for --draft "
                         "(morpheus/penny)")
    ap.add_argument("--effectiveness", action="store_true",
                    help="print follow-up verdicts + the per-seat "
                         "rollup")
    ap.add_argument("--reason", default="",
                    help="with --add-blocker: why the edge exists")
    args = ap.parse_args()
    if args.draft or args.effectiveness:
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            ensure_schema(cur)
            conn.commit()
            if args.draft:
                cur.execute("BEGIN")
                did = draft_breakdown(cur, args.draft,
                                      seat=args.seat)
                conn.commit()
                return 0 if did else 1
            cur.execute(
                "SELECT verdict, count(*) FROM "
                "successbrian_os.effect_followups WHERE verdict "
                "IS NOT NULL GROUP BY 1 ORDER BY 1")
            print("follow-up verdicts:",
                  dict(cur.fetchall()) or "none yet")
            cur.execute(
                "SELECT author_seat, kind, verdict, n FROM "
                "successbrian_os.effectiveness_rollup ORDER BY "
                "1, 2, 3")
            for r in cur.fetchall():
                print(f"  seat {r[0]} / {r[1]}: {r[2]} x{r[3]}")
            cur.execute(
                "SELECT status, count(*) FROM "
                "successbrian_os.breakdown_drafts GROUP BY 1")
            print("breakdown drafts:", dict(cur.fetchall())
                  or "none yet")
            return 0
        finally:
            conn.close()
    if args.add_blocker:
        if not args.blocked_by:
            print("--add-blocker needs --blocked-by STEP_KEY")
            return 2
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            ensure_schema(cur)
            conn.commit()
            cur.execute("BEGIN")
            ok, msg = add_blocker(cur, args.add_blocker,
                                  args.blocked_by, args.reason,
                                  by="cli")
            conn.commit() if ok else conn.rollback()
            print(("blocker recorded: " if ok else "refused: ")
                  + msg)
            return 0 if ok else 1
        finally:
            conn.close()
    if args.selftest:
        return selftest()
    if args.status:
        return status()
    if args.tiers or args.due:
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            ensure_schema(cur)
            conn.commit()
            slugs = rotation_slugs()
            tiers = compute_tiers(cur, slugs)
            conn.commit()
            if args.tiers:
                for slug in slugs:
                    t = tiers[slug]
                    print(f"{slug}: tier {t['tier']} "
                          f"(window {t['window_days']}d, priority "
                          f"{t['priority_label']}"
                          f"{', GATED' if t['gated'] else ''})")
            if args.due:
                for d in due_goals(cur, slugs, 50):
                    print(f"{d['slug']}: tier {d['tier']}, "
                          f"age {d['age_days']}d, ratio {d['ratio']}"
                          + (f", DUE-EARLY: {d['reason']}"
                             if d["due_early"] else ""))
            return 0
        finally:
            conn.close()
    if args.sweep or args.collect:
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            ensure_schema(cur)
            conn.commit()
            cur.execute("BEGIN")
            collect_movements(cur)
            n = collect_sweeps(cur)
            m = collect_claims(cur)
            conn.commit()
            if args.sweep:
                cur.execute("BEGIN")
                run_sweep(cur, force=True)
                conn.commit()
            print(f"collect: sweeps {n}, claims settled {m}")
            return 0
        finally:
            conn.close()
    if args.cycle is not None:
        if args.slug:
            conn = sbos_common.connect()
            try:
                cur = conn.cursor()
                ensure_schema(cur)
                conn.commit()
                slugs = rotation_slugs()
                compute_tiers(cur, slugs)
                conn.commit()
                try:
                    cur.execute("BEGIN")
                    meta = ep.ensure_brief(cur, args.slug)
                    conn.commit()
                    if meta is not None:
                        print(f"  {args.slug}: brief refreshed "
                              f"(origin {meta['origin_class']})")
                except Exception as e:
                    conn.rollback()
                    print(f"  {args.slug}: BRIEF REFRESH FAILED {e}")
                cur.execute("BEGIN")
                eid, _p = dispatch_harness_look(
                    cur, args.slug, force=args.force)
                if eid is not None:
                    clear_due_early(cur, args.slug)
                conn.commit()
                return 0
            finally:
                conn.close()
        return cycle(args.cycle)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
