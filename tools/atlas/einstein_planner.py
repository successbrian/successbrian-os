#!/usr/bin/env python3
"""einstein_planner.py - Einstein deep-look planner pass (Brian order
2026-11-23 09:23-09:27 CST: "planning likely needs Einstein" /
"can you get hamnas Einstein looking at them and writing plans back"
/ "also what needs to be researched").

The planner rotation's driver looks are shallow: they restate the
goal record and carry its claims forward unverified (the DealsDesk
"100% done" claim survived look after look). This module puts
Einstein - the DeepSeek V4 Flash REAP 150B, the fleet's deep-pass
engine - in the look seat. For each due goal it builds a context
packet from the goal's live record, dispatches it as a standard
feeder packet on the gamma bus (sbos_common.build_reap_packet /
dispatch_reap_packet), and when gamma's result lands in the outbox
it writes the plan BACK into the stores the planner already owns:

  - a goal_coverage look (seat 'einstein', via planner_rotation's
    do_look, so coverage counting is shared with the light driver -
    never forked), findings = the verified-state assessment;
  - the Atlas goal node's readme_md = the full plan, verbatim;
  - the plan's executable steps as pm_steps through the existing
    dispatch machinery (lead step via the look's work_spawned and
    planner_rotation --dispatch; remaining steps via pm_core.add_step
    with source goal_coverage:<look id>);
  - each RESEARCH NEED as a pm_steps row of kind 'research'
    (question / why it matters / where the answer likely lives),
    claimable by the harness loop, kept separate from executable
    steps, verified facts, and Brian-only residue (the FOR BRIAN
    section lives in the plan text only - it is never turned into
    a step).

AUTHORITY LIMIT (the DealsDesk lesson, encoded): Einstein assesses;
he does not decide. His verified-state assessment is recorded AS an
assessment. A state correction he proposes (a status flip, a
progress change, a blocker change) is written into the plan as
FLAGGED - NOT APPLIED, and never reaches the goal's status,
progress, or blocker fields from this module. He cannot close a
goal or mark work done: this module files looks and steps, nothing
else. do_look itself refuses done/cancelled goals.

BUS TIER: the gamma bus priority map (Brian, 2026-11-15, in
sbos_common.dispatch_reap_packet) assigns planning rounds and
backlog deep passes to the filler band, priority 1-2. Einstein
looks dispatch at priority 2 - the top of the filler band - chosen
on purpose: they never starve chat (30/20/10) or intake (5), and
they yield to project work with a waiting deliverable (4) and
recurring upkeep (3).

ROUTE (verified live 2026-11-23, probe bus events 1722/1728):
the Einstein route that answers today is the gamma bus REAP lane -
bus.events reap_infer -> gamma's REAP seat (the DeepSeek V4 Flash
REAP 150B) -> successbrian_os.outbox inference_result, subject
'gamma: event <id> done (reap_infer)'. Two handler behaviors shape
this module's contract:
  - thinking MUST be false. With thinking=true the returned text
    is a fragment of the reasoning, not the answer (event 1722:
    500 tokens generated, a 156-char reasoning preamble returned).
  - The return leg keeps only the FIRST text block of the answer:
    multi-paragraph replies come back as their first paragraph
    (event 1728: 465 tokens generated, the 15-char first line
    returned; the same prefix pattern holds across the outbox
    history). The prompt therefore demands ONE unbroken block with
    inline section headers, and parse_plan splits on the headers
    wherever they appear.
Generation runs ~1.8 tok/s on gamma's seat, so a 500-token plan
takes ~4-5 minutes once claimed; queue wait at priority 2 behind
the intake lane measured ~16 minutes on a busy morning (7-day
roundtrips: priority 5 avg 7.2 min, priority 3 avg 20.5 min).

CADENCE: one cron cycle every 2 hours (offset from the planner
driver) collects outstanding passes, then dispatches at most
EINSTEIN_PER_CYCLE new looks. At the measured latencies, 1 new
look per 2h cycle (12/day) turns the full 42-goal rotation over
in ~3.5 days - inside the 4-day coverage window, the same
turnover the light driver keeps - and a pass dispatched in one
cycle is collected the next, so the filler-tier queue wait never
blocks the rotation. A goal is due when it has no einstein-seat
look inside its coverage window (node details
coverage_window_days, default 4).

In-flight passes are tracked in successbrian_os.einstein_passes
(tools/atlas/2026-11-23_einstein_planner.sql) - the ledger for
dispatch/collect; the PLAN itself lives in goal_coverage + the
node readme, not in the ledger.

GOAL BRIEFS (Brian's diagnosis, 2026-11-23 17:44 CST: "we just
need to give Einstein more context. I believe we gave him a very
vague paragraph and expected magic"): the first version's packet
was a skeleton - goal row + node + last looks + task counts +
name-matched captures - and most goal records are themselves one
thin agent-written paragraph, so Einstein's generic plans were a
CONTEXT problem, not a model problem. This module now compiles a
rich standing brief per goal from everything the ecosystem holds
about it: Brian's own words where they exist (verbatim, attributed,
dated - from the ruling census, Brian's recorded decision answers,
ruled decision-queue items, and quoted spans in the second brain);
the goal's origin (created when, in what batch, owner on record,
and an honest origin class - BRIAN-DIRECTED / AGENT-ASSEMBLED /
UNKNOWN; a brief with no Brian-words and an agent-assembled origin
says so in plain words, per the rulings-provenance standard);
connected work (Atlas edges and subject-matched records, PM
projects and steps, open decision-queue items); standing
constraints and rulings touching it; and its current measured
state. A brief may only contain what the record holds - gaps are
labeled UNKNOWN, never filled - and compiling one never changes a
goal's status or progress. Briefs live in
successbrian_os.goal_briefs (system of record) and are mirrored
into the Atlas goal node's readme_md inside GOAL-BRIEF markers,
alongside (never overwriting) the EINSTEIN-PLAN section that
write_back maintains. The dispatch packet is now the full brief
plus the live record. Briefs refresh inside the same cycle: a
brief older than its goal's coverage window, or one with newer
captures/decisions/rulings landed since compilation, is recompiled
before the goal's next look is dispatched.

Usage:
  einstein_planner.py --selftest    parse checks + transactional
                                    write-back probe (rolled back)
  einstein_planner.py --plan [N]    next N goals due for an
                                    Einstein look (default 10)
  einstein_planner.py --run [N] [--wait S] [--dry-run] [--slug S]
                                    dispatch up to N Einstein looks
                                    (or one named goal with --slug);
                                    --wait also polls and collects
                                    for up to S seconds
  einstein_planner.py --collect [--wait S]
                                    collect any landed results and
                                    write their plans back
  einstein_planner.py --cycle [N]   collect, then dispatch up to N
                                    (the cron entry point)
  einstein_planner.py --status      passes by status + last plan
  einstein_planner.py --briefs [--slug S] [--force]
                                    compile/refresh goal briefs:
                                    all stale-or-missing briefs in
                                    the rotation, one goal with
                                    --slug, or every goal with
                                    --force
"""
import argparse
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
import goal_nodes as gn  # noqa: E402
import planner_rotation as pr  # noqa: E402
import pm_core  # noqa: E402

SEAT = "einstein"
SOURCE = "einstein-planner"
BUS_PRIORITY = 2  # filler band: planning rounds (bus map, 2026-11-15)
MAX_TOKENS = 500  # REAP feeder-packet ceiling (gamma 900s runway)
CONTEXT_BUDGET_CHARS = 5200
BRIEF_BUDGET_CHARS = 9000  # brief slice of the dispatch packet
BRIEF_STORE_BUDGET_CHARS = 12000  # stored brief ceiling
EINSTEIN_PER_CYCLE = 1
STALE_PASS_HOURS = 24

BRIEF_BEGIN = "<!-- GOAL-BRIEF:BEGIN -->"
BRIEF_END = "<!-- GOAL-BRIEF:END -->"
PLAN_BEGIN = "<!-- EINSTEIN-PLAN:BEGIN -->"
PLAN_END = "<!-- EINSTEIN-PLAN:END -->"

SECTION_HEADERS = ("VERIFIED STATE", "WORTH", "CLAIMED vs VERIFIED",
                   "BLOCKERS", "PLAN", "RESEARCH NEEDS", "FOR BRIAN")

PROMPT_TEMPLATE = """You are Einstein, the deep-planning engine in a solo operator's goal system. Below is one goal's standing brief - compiled from everything the operator's ecosystem holds about this goal: his own recorded words (quoted verbatim, attributed, dated), the goal's origin and provenance, its connected work, the standing rulings that constrain it, and its measured state - followed by its live record (goal row, Atlas node, recent planner looks, tasks, recent captures). Judge ONLY from this record. Where the record is silent, say UNKNOWN - never invent a fact, a date, or a person's intent. Weigh provenance: a goal whose brief shows an agent-assembled origin and no words of Brian's is an unadopted proposal, not his directive - say so where it matters. But origin is a label, not a gate (Brian's ruling, 2026-11-23): a goal does not need his authorship to be worth doing - grade its merit in the WORTH section on the same tests as any adopted goal.

Write a planning assessment with EXACTLY these seven sections, in this order, plain text, no preamble, no closing remarks. CRITICAL FORMAT RULE: write the ENTIRE assessment as one single unbroken block of text - NO blank lines anywhere, NO paragraph breaks. The channel that carries your answer back keeps only the first block, so a blank line ends your answer and the rest is lost. Start immediately with "VERIFIED STATE:" and run each section's header inline, like this: VERIFIED STATE: <text> WORTH: <text> CLAIMED vs VERIFIED: <text> BLOCKERS: <text> PLAN: 1. <step> 2. <step> RESEARCH NEEDS: <items> FOR BRIAN: <text>

VERIFIED STATE: What the evidence in the record actually proves about this goal today, each claim tied to the record item it rests on. At most 70 words.
WORTH: Grade this goal against Brian's four tests (his ruling, 2026-11-23): (1) Does it make sense for the ecosystem? (2) Is it better than what we are currently doing? (3) How easy or hard is it to add? (4) Is it more lucrative? - weighed against the scarcest resource in the system, Brian's own time: a goal that costs Brian-hours weighs against itself; work the fleet can carry without him weighs in its favor. For an unadopted (agent-assembled) goal this section is its adoption brief; for an adopted goal it is the periodic re-justification. End with a verdict word: STRONG, SOUND, WEAK, or FAILING. At most 55 words.
CLAIMED vs VERIFIED: Where the goal's claimed state (status, progress, dates) disagrees with the evidence, say so plainly and name the correction you propose. These are flagged for a human - you are not applying them. At most 50 words.
BLOCKERS: What is actually stopping progress, from the record. "none proven" if the record shows none. At most 40 words.
PLAN: The concrete next steps, in order, numbered "1." "2." "3." inline - each step a single executable action a worker could claim and finish, at most 25 words per step. At most 5 steps. A step that only Brian can perform does not belong here - it belongs in FOR BRIAN.
RESEARCH NEEDS: What is UNKNOWN that research could settle, each item in exactly this shape: NEED: <the question> | WHY: <why it matters to this goal> | WHERE: <where the answer likely lives>. At most 2 items. A question only Brian can answer is NOT a research need - it belongs in FOR BRIAN. "none" if nothing is missing.
FOR BRIAN: Only what the operator himself must decide or supply - the residue no research and no worker can settle. At most 25 words. "none" if there is none.

Keep the whole answer under 420 tokens - the channel truncates at 500, and a plan whose tail is cut off is a failed plan. Be concrete and brief; a short true plan beats a long vague one.

GOAL RECORD:
{context}"""


# ---------------------------------------------------------------- schema

def ensure_schema(cur):
    cur.execute(
        "CREATE TABLE IF NOT EXISTS successbrian_os.einstein_passes ("
        "id serial PRIMARY KEY, "
        "goal_slug text NOT NULL, "
        "probe_id text NOT NULL UNIQUE, "
        "bus_event_id bigint, "
        "status text NOT NULL DEFAULT 'dispatched', "
        "dispatched_at timestamptz NOT NULL DEFAULT now(), "
        "collected_at timestamptz, "
        "look_id integer, "
        "plan_text text, "
        "note text)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS successbrian_os.goal_briefs ("
        "goal_slug text PRIMARY KEY, "
        "brief_md text NOT NULL, "
        "compiled_at timestamptz NOT NULL DEFAULT now(), "
        "has_brian_words boolean NOT NULL DEFAULT false, "
        "origin_class text NOT NULL DEFAULT 'UNKNOWN', "
        "newest_source_at timestamptz, "
        "sources jsonb NOT NULL DEFAULT '{}'::jsonb)")


# ---------------------------------------------------------------- context

def _trim(text, max_chars=350):
    return sbos_common.trim_fact_whole(str(text or ""), max_chars)


def build_context(cur, slug):
    """Assemble one goal's dispatch packet: its standing brief
    (compiled from the whole record; see compile_brief) followed by
    its live record. Every line is a fact from a store; long
    free-text fields are trimmed whole-sentence by trim_fact_whole,
    never cut mid-thought."""
    brief = None
    cur.execute(
        "SELECT brief_md, compiled_at FROM successbrian_os.goal_briefs "
        "WHERE goal_slug = %s", [slug])
    brow = cur.fetchone()
    if brow:
        brief = brow[0]
        brief_head = (f"STANDING BRIEF (compiled {brow[1]} from the "
                      f"ecosystem record; provenance labels are facts "
                      f"to weigh, gaps are labeled UNKNOWN):")
    else:
        brief_head = ("STANDING BRIEF: none compiled yet - judge from "
                      "the live record alone and say where it is thin.")
    parts = [brief_head]
    if brief:
        parts.append(brief[:BRIEF_BUDGET_CHARS])
    parts.append("LIVE RECORD:\n" + _record_context(cur, slug))
    return "\n\n".join(parts)


def _record_context(cur, slug):
    """The live-record slice of the packet (<= CONTEXT_BUDGET_CHARS):
    goal row, Atlas node, task counts, recent looks, open steps,
    recent captures naming the goal."""
    cur.execute(
        "SELECT node_key, name, status, details, summary FROM atlas.nodes "
        "WHERE node_key = %s AND node_type = 'goal'",
        [gn.node_key_for_slug(slug)])
    node = cur.fetchone()
    if node is None:
        raise ValueError(f"no goal node for slug: {slug}")
    _key, name, node_status, details, _summary = node
    details = dict(details or {})
    lines = [f"Goal: {name} (slug {slug})",
             f"Atlas node status: {node_status}; priority "
             f"{details.get('priority')}; category "
             f"{details.get('category')}; target_date "
             f"{details.get('target_date')}; blocker on node: "
             f"{details.get('blocker') or 'none'}; looks so far: "
             f"{details.get('look_count') or 0}; last look: "
             f"{details.get('last_looked_at') or 'never'}"]
    cur.execute(
        "SELECT status, target_date, progress_pct, phase, owner_agent, "
        "description, success_metrics, notes, updated_at "
        "FROM successbrian_os.sbos_goals WHERE goal_slug = %s", [slug])
    grow = cur.fetchone()
    if grow is None:
        lines.append("Goal row (sbos_goals): NO ROW - the goal exists "
                     "only as an Atlas node.")
    else:
        (gstatus, target, pct, phase, owner, desc, metrics, notes,
         updated) = grow
        lines.append(
            f"Goal row: status {gstatus}; progress_pct {pct}; "
            f"target {target}; phase {phase}; owner_agent {owner}; "
            f"record updated {updated}")
        if desc:
            lines.append(f"Description: {_trim(desc, 500)}")
        if metrics:
            lines.append(f"Success metrics: {_trim(metrics, 300)}")
        if notes:
            lines.append(f"Notes: {_trim(notes, 300)}")
    cur.execute(
        "SELECT count(*), count(*) FILTER (WHERE status IN "
        "('done', 'completed', 'closed')) FROM atlas.goal_tasks "
        "WHERE goal_slug = %s", [slug])
    total, done = cur.fetchone()
    lines.append(f"Tasks: {done}/{total} done.")
    cur.execute(
        "SELECT name, status FROM atlas.goal_tasks WHERE goal_slug = %s "
        "AND status NOT IN ('done', 'completed', 'closed') "
        "ORDER BY name LIMIT 8", [slug])
    for tname, tstatus in cur.fetchall():
        lines.append(f"  open task: {_trim(tname, 120)} [{tstatus}]")
    cur.execute(
        "SELECT id, planner_seat, findings, work_spawned, looked_at "
        "FROM successbrian_os.goal_coverage WHERE goal_slug = %s "
        "ORDER BY id DESC LIMIT 3", [slug])
    looks = cur.fetchall()
    if looks:
        lines.append("Recent planner looks (newest first):")
        for lid, seat, findings, work, looked_at in looks:
            lines.append(
                f"  look {lid} ({seat}, {looked_at}): "
                f"{_trim(findings, 220)} | work: {_trim(work, 140)}")
    else:
        lines.append("Recent planner looks: none - never looked.")
    cur.execute(
        "SELECT s.step_key, s.kind, s.status, s.title "
        "FROM successbrian_os.pm_steps s "
        "JOIN successbrian_os.goal_coverage c "
        "ON s.source = 'goal_coverage:' || c.id "
        "WHERE c.goal_slug = %s AND s.status NOT IN ('done', 'cancelled') "
        "ORDER BY s.id DESC LIMIT 6", [slug])
    steps = cur.fetchall()
    if steps:
        lines.append("Open steps already filed from this goal's looks:")
        for skey, kind, status, title in steps:
            lines.append(f"  {skey} [{kind}/{status}]: "
                         f"{_trim(title, 120)}")
    cur.execute(
        "SELECT id, title, context FROM atlas.scattered_captures "
        "WHERE (title ILIKE %s OR context ILIKE %s) "
        "AND title NOT ILIKE 'HOURLY ORDER%%' "
        "ORDER BY id DESC LIMIT 3",
        [f"%{slug}%", f"%{slug}%"])
    caps = cur.fetchall()
    if caps:
        lines.append("Recent captures naming this goal:")
        for cid, ctitle, ccontext in caps:
            lines.append(f"  capture {cid}: {_trim(ctitle, 120)} "
                         f"{_trim(ccontext, 200)}")
    text = "\n".join(lines)
    if len(text) > CONTEXT_BUDGET_CHARS:
        text = text[:CONTEXT_BUDGET_CHARS]
    return text


def build_prompt(context):
    return PROMPT_TEMPLATE.format(context=context)


# ---------------------------------------------------------------- briefs
# A brief may only contain what the record holds. Collectors below
# return record items verbatim (trimmed whole-sentence); matching is
# deterministic token matching against the goal's slug/name, and
# every section that finds nothing says so plainly instead of
# filling the gap.

_BRIAN_QUOTE_RE = re.compile(
    r"Brian,\s*(\d{4}-\d{2}-\d{2})[^\"\n]{0,70}?[\"\u201c]"
    r"([^\"\n]{10,700})[\"\u201d]")
_BRIAN_SAID_RE = re.compile(r"Brian:\s*[\"\u201c]([^\"\n]{10,700})[\"\u201d]")


def _slug_tokens(slug):
    toks = []
    for t in re.split(r"[^a-z0-9]+", (slug or "").lower()):
        if len(t) < 3 or t.isdigit():
            continue
        toks.append(t)
    return toks


def _rotation_slugs(cur):
    cur.execute(
        "SELECT goal_slug FROM atlas.goal_nodes "
        "WHERE status NOT IN ('done', 'cancelled') ORDER BY goal_slug")
    return [r[0] for r in cur.fetchall()]


def _goal_terms(cur, slug):
    """Search terms for one goal: its slug, its recorded name, its
    distinctive slug tokens (length >= 4, appearing in at most 3 of
    the rotation's slugs - 'worker'/'revenue' class tokens that
    appear everywhere are not evidence of anything), and its slug
    bigrams ('local ai', 'agent stack') - a two-word phrase from
    the goal's own name is subject evidence a single common token
    never is."""
    cur.execute(
        "SELECT name FROM atlas.nodes WHERE node_key = %s "
        "AND node_type = 'goal'", [gn.node_key_for_slug(slug)])
    row = cur.fetchone()
    name = row[0] if row else slug
    from collections import Counter
    freq = Counter()
    for s in _rotation_slugs(cur):
        for t in set(_slug_tokens(s)):
            freq[t] += 1
    distinctive = [t for t in _slug_tokens(slug)
                   if len(t) >= 4 and freq.get(t, 0) <= 3]
    rare = [t for t in distinctive if freq.get(t, 0) == 1]
    raw = [t for t in re.split(r"[^a-z0-9]+", slug.lower())
           if len(t) >= 2 and not t.isdigit()]
    phrases = [f"{a} {b}" for a, b in zip(raw, raw[1:])]
    return {"slug": slug, "name": name, "distinctive": distinctive,
            "phrases": phrases, "rare": rare}


def _subject_match(text, terms):
    """The attribution test for Brian's-words and origin claims:
    is this text ABOUT this goal? True only on a subject anchor -
    the slug, the goal's full name, one of its name bigrams, a
    rare token (unique to this goal among the rotation's slugs)
    backed by another distinctive token, or >= 3 distinctive
    tokens. Two common tokens are NOT enough: 'local' + 'agent'
    appear in fleet-operations texts that have nothing to do with
    the local-ai-agent-stack goal, and attributing them to it is
    the provenance failure these briefs exist to prevent."""
    if not text:
        return False
    low = text.lower()
    if terms["slug"].lower() in low:
        return True
    flat = re.sub(r"[^a-z0-9]+", " ", low)
    name_flat = re.sub(r"[^a-z0-9]+", " ",
                       terms["name"].lower()).strip()
    if name_flat and f" {name_flat} " in f" {flat} ":
        return True
    if any(f" {p} " in f" {flat} " for p in terms.get("phrases", [])):
        return True
    hits = {t for t in terms["distinctive"]
            if re.search(r"\b" + re.escape(t) + r"\b", flat)}
    if len(hits) >= 3:
        return True
    return bool(hits & set(terms.get("rare", []))) and len(hits) >= 2


def _match_level(text, terms):
    """0 = no match, 1 = weak (one distinctive token - a hint, not
    evidence), 2 = strong (the slug, the goal's full name, one of
    its name bigrams, or >= 2 distinctive tokens). Brian's-words
    and origin classification accept STRONG only: a single common
    token ('local', 'agent') matches half the record and attributing
    it to this goal would be exactly the provenance failure the
    briefs exist to prevent."""
    if not text:
        return 0
    low = text.lower()
    if terms["slug"].lower() in low:
        return 2
    flat = re.sub(r"[^a-z0-9]+", " ", low)
    name_flat = re.sub(r"[^a-z0-9]+", " ",
                       terms["name"].lower()).strip()
    if name_flat and f" {name_flat} " in f" {flat} ":
        return 2
    if any(f" {p} " in f" {flat} " for p in terms.get("phrases", [])):
        return 2
    hits = sum(1 for t in terms["distinctive"]
               if re.search(r"\b" + re.escape(t) + r"\b", flat))
    if hits >= 2:
        return 2
    if hits == 1:
        return 1
    return 0


def _ilike_clause(fields, terms):
    """(sql_or_clause, params) matching any field against the slug
    or a distinctive token. Tokens are slug-derived [a-z0-9], and
    every value still goes through a bound parameter."""
    pats = [f"%{terms['slug']}%"] + [f"%{t}%" for t in terms["distinctive"]]
    parts, params = [], []
    for f in fields:
        for p in pats:
            parts.append(f"{f} ILIKE %s")
            params.append(p)
    return "(" + " OR ".join(parts) + ")", params


def _brian_word_items(cur, terms):
    """Brian's own words about this goal, from the attributed
    record only: ruling-census quotes (verbatim by construction),
    Brian's recorded decision answers, ruled decision-queue items,
    and dated verbatim quotes embedded in second-brain entries.
    Captures are NOT used here - their voice is mixed. Returns
    [{date, text, ref}] sorted by date, deduped, capped."""
    items = []

    def add(date, text, ref):
        text = " ".join(str(text or "").split())
        if len(text) < 10:
            return
        key = text[:80].lower()
        if any(i["text"][:80].lower() == key for i in items):
            return
        items.append({"date": date, "text": text, "ref": ref})

    clause, params = _ilike_clause(
        ["subject", "ruling", "quote"], terms)
    cur.execute(
        f"SELECT id, quote, ruled_on, subject, ruling FROM "
        f"successbrian_os.ruling_census WHERE {clause} "
        f"ORDER BY ruled_on NULLS LAST, id LIMIT 12", params)
    for rid, quote, ruled_on, subject, ruling in cur.fetchall():
        # The census is curated: a subject-level match counts, or a
        # subject anchor anywhere in the row. A lone common token
        # in the quote text does not attribute it to this goal.
        if quote and (_match_level(subject, terms) >= 1
                      or _subject_match(
                          f"{subject} {ruling} {quote}", terms)):
            add(ruled_on, quote,
                f"ruling census #{rid} (subject: {subject})")
    clause, params = _ilike_clause(
        ["question", "context", "answer"], terms)
    cur.execute(
        f"SELECT id, question, answer, answered_at FROM "
        f"altair.brian_decisions WHERE answer IS NOT NULL AND "
        f"{clause} ORDER BY answered_at NULLS LAST, id LIMIT 10",
        params)
    for did, question, answer, answered_at in cur.fetchall():
        if not _subject_match(f"{question} {answer}", terms):
            continue
        said = _BRIAN_SAID_RE.search(answer or "")
        if said:
            add(answered_at, said.group(1),
                f"Brian's answer, decision record #{did}")
        else:
            add(answered_at, _trim(answer, 400),
                f"Brian's recorded answer, decision record #{did} "
                f"(question: {_trim(question, 90)})")
    clause, params = _ilike_clause(
        ["title", "context::text", "ruling::text"], terms)
    cur.execute(
        f"SELECT id, title, ruling::text, ruled_at FROM "
        f"successbrian_os.decision_queue WHERE ruling IS NOT NULL "
        f"AND {clause} ORDER BY ruled_at NULLS LAST, id LIMIT 8",
        params)
    for qid, title, ruling, ruled_at in cur.fetchall():
        if _subject_match(f"{title} {ruling}", terms):
            add(ruled_at, ruling,
                f"Brian's ruling on decision #{qid} ({_trim(title, 80)})")
    clause, params = _ilike_clause(
        ["item", "context", "ruling"], terms)
    cur.execute(
        f"SELECT id, item, ruling, updated_at FROM "
        f"successbrian_os.review_decisions WHERE state = 'ruled' "
        f"AND ruling IS NOT NULL AND {clause} "
        f"ORDER BY updated_at, id LIMIT 8", params)
    for qid, item, ruling, updated_at in cur.fetchall():
        if _subject_match(f"{item} {ruling}", terms):
            add(updated_at, ruling,
                f"Brian's ruling on review decision #{qid} "
                f"({_trim(item, 80)})")
    clause, params = _ilike_clause(["content", "topic"], terms)
    cur.execute(
        f"SELECT id, topic, content FROM altair.second_brain "
        f"WHERE {clause} ORDER BY id DESC LIMIT 30", params)
    for sid, topic, content in cur.fetchall():
        # A long entry can touch a dozen subjects; a quote inside
        # it is attributed to this goal only when the quote's own
        # neighborhood (the quote plus ~300 chars around it)
        # carries the goal's subject anchor.
        if _match_level(f"{topic} {content}", terms) < 1:
            continue
        for m in _BRIAN_QUOTE_RE.finditer(content or ""):
            window = (content or "")[max(0, m.start() - 300):
                                     m.end() + 300]
            if not _subject_match(window, terms):
                continue
            add(m.group(1), m.group(2),
                f"second brain #{sid}, Brian quoted verbatim")
    items.sort(key=lambda i: str(i["date"] or ""))
    return items[:6]


def _ruling_items(cur, terms):
    """Standing rulings/constraints touching this goal (the census
    is the rulings record; a census row whose quote already appears
    in Brian's words still belongs here as a constraint)."""
    clause, params = _ilike_clause(
        ["subject", "ruling", "quote"], terms)
    cur.execute(
        f"SELECT id, ruling, ruled_on, subject, status FROM "
        f"successbrian_os.ruling_census WHERE {clause} "
        f"ORDER BY ruled_on NULLS LAST, id LIMIT 8", params)
    out = []
    for rid, ruling, ruled_on, subject, status in cur.fetchall():
        if (_match_level(subject, terms) >= 1
                or _subject_match(f"{subject} {ruling}", terms)):
            out.append({"date": ruled_on, "ref": f"census #{rid}",
                        "text": _trim(ruling, 260),
                        "subject": subject, "status": status})
    return out


def _connected_items(cur, slug, terms):
    """Connected work, honestly labeled: Atlas edges (the graph's
    own claims), subject-matched Atlas records and PM projects
    (record references, not edges), and open decision-queue items
    that reference the goal."""
    key = gn.node_key_for_slug(slug)
    out = {"edges": [], "records": [], "projects": [], "decisions": []}
    cur.execute(
        "SELECT from_node, to_node, edge_type FROM atlas.edges "
        "WHERE from_node = %s OR to_node = %s", [key, key])
    edges = cur.fetchall()
    others = {r[0] if r[1] == key else r[1] for r in edges}
    names = {}
    if others:
        cur.execute(
            "SELECT node_key, node_type, name, status FROM atlas.nodes "
            "WHERE node_key = ANY(%s)", [list(others)])
        names = {r[0]: r[1:] for r in cur.fetchall()}
    for frm, to, etype in edges:
        other = to if frm == key else frm
        n = names.get(other)
        arrow = "->" if frm == key else "<-"
        label = (f"{n[1]} [{n[0]}/{n[2]}]" if n else other)
        out["edges"].append(f"{arrow} {etype} {label} ({other})")
    cur.execute(
        "SELECT node_key, node_type, name, status, summary, readme_md "
        "FROM atlas.nodes WHERE node_key <> %s AND node_type <> 'goal' "
        "ORDER BY node_key", [key])
    recs = []
    for nkey, ntype, nname, nstatus, summary, readme in cur.fetchall():
        lvl = _match_level(f"{nname} {summary or ''}", terms)
        if lvl >= 1:
            # Excerpts are evidence; only a strong match earns one.
            # A weak match is listed by name so a reader can judge
            # the hint without the brief vouching for it.
            excerpt = (_trim(summary or readme or "", 420)
                       if lvl == 2 else "")
            recs.append({"key": nkey, "type": ntype, "name": nname,
                         "status": nstatus, "excerpt": excerpt,
                         "level": lvl,
                         "name_level": _match_level(nname, terms)})
    # A match in the record's NAME outranks one buried in its
    # summary: generic fleet proposals whose summaries happen to
    # contain two common tokens must not crowd out the project
    # whose name carries the goal's subject (the funnel, for the
    # agent-stack goal).
    recs.sort(key=lambda r: (-r["level"], -r["name_level"], r["key"]))
    out["records"] = recs[:8]
    cur.execute(
        "SELECT project_key, title, status, description, requested_by "
        "FROM successbrian_os.pm_projects ORDER BY project_key")
    for pkey, title, status, desc, req_by in cur.fetchall():
        if _match_level(f"{pkey} {title} {desc or ''}", terms) >= 1:
            out["projects"].append(
                {"key": pkey, "title": title, "status": status,
                 "excerpt": _trim(desc or "", 300),
                 "requested_by": req_by})
        if len(out["projects"]) >= 4:
            break
    clause, params = _ilike_clause(
        ["title", "context::text"], terms)
    cur.execute(
        f"SELECT id, title, status, created_at FROM "
        f"successbrian_os.decision_queue WHERE ruled_at IS NULL "
        f"AND status = 'pending' "
        f"AND {clause} ORDER BY id DESC LIMIT 8", params)
    for qid, title, status, created in cur.fetchall():
        if _match_level(title, terms) >= 1:
            out["decisions"].append(
                {"id": qid, "title": _trim(title, 140),
                 "status": status, "date": created})
        if len(out["decisions"]) >= 4:
            break
    clause, params = _ilike_clause(["item", "context"], terms)
    cur.execute(
        f"SELECT id, item, first_surfaced FROM "
        f"successbrian_os.review_decisions WHERE state = 'waiting' "
        f"AND {clause} ORDER BY id DESC LIMIT 8", params)
    for qid, item, surfaced in cur.fetchall():
        if _match_level(item, terms) >= 1:
            out["decisions"].append(
                {"id": qid, "title": _trim(item, 140),
                 "status": "waiting (review queue)",
                 "date": surfaced})
        if len(out["decisions"]) >= 4:
            break
    return out


def _newest_source_at(cur, terms):
    """Newest timestamp among the goal's matched source items -
    the brief's freshness watermark."""
    stamps = []
    for sql, fields in (
            ("SELECT max(created_at) FROM atlas.scattered_captures "
             "WHERE {c}", ["title", "context", "raw_text"]),
            ("SELECT max(greatest(created_at, coalesce(ruled_at, "
             "created_at))) FROM successbrian_os.decision_queue "
             "WHERE {c}", ["title", "context::text", "ruling::text"]),
            ("SELECT max(updated_at) FROM "
             "successbrian_os.review_decisions WHERE {c}",
             ["item", "context", "ruling"]),
            ("SELECT max(updated_at) FROM altair.second_brain "
             "WHERE {c}", ["content", "topic"]),
            ("SELECT max(created_at) FROM successbrian_os.ruling_census "
             "WHERE {c}", ["subject", "ruling", "quote"]),
            ("SELECT max(answered_at) FROM altair.brian_decisions "
             "WHERE answer IS NOT NULL AND {c}",
             ["question", "context", "answer"])):
        clause, params = _ilike_clause(fields, terms)
        cur.execute(sql.format(c=clause), params)
        row = cur.fetchone()
        if row and row[0]:
            stamps.append(row[0])
    return max(stamps) if stamps else None


def _origin(cur, slug, terms, brian_items):
    """The goal's origin from the record: creation timestamps, the
    registration-batch signature, the owner on record, and whether
    any words of Brian's predate or coincide with creation.
    Returns (origin_class, [evidence lines])."""
    cur.execute(
        "SELECT id, created_at, owner_agent, category FROM "
        "successbrian_os.sbos_goals WHERE goal_slug = %s", [slug])
    grow = cur.fetchone()
    cur.execute(
        "SELECT created_at FROM atlas.nodes WHERE node_key = %s",
        [gn.node_key_for_slug(slug)])
    nrow = cur.fetchone()
    node_created = nrow[0] if nrow else None
    lines = []
    if grow:
        gid, created, owner, _cat = grow
        lines.append(f"Goal row #{gid} created {created}; "
                     f"owner_agent on record: {owner or 'none'}; "
                     f"Atlas node created {node_created}.")
        cur.execute(
            "SELECT count(*) FROM successbrian_os.sbos_goals "
            "WHERE created_at::date = %s::date", [created])
        same_day = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM successbrian_os.sbos_goals "
            "WHERE created_at BETWEEN %s - interval '30 minutes' "
            "AND %s + interval '30 minutes'", [created, created])
        near = cur.fetchone()[0]
        batch = same_day >= 3 or near >= 2
        if batch:
            lines.append(
                f"Registration-batch signature: {same_day} goal(s) "
                f"created that day, {near} within 30 minutes of "
                f"this one.")
    else:
        created = node_created
        batch = False
        lines.append("No sbos_goals row - the goal exists only as "
                     f"an Atlas node (created {node_created}).")
    brian_before = False
    if created and brian_items:
        for i in brian_items:
            d = i["date"]
            if d is None:
                continue
            dstr = str(d)[:10]
            if dstr <= str(created)[:10]:
                brian_before = True
    if brian_before:
        cls = "BRIAN-DIRECTED"
        lines.append("Words of Brian's on record at or before "
                     "creation support a Brian-directed origin.")
    elif batch:
        cls = "AGENT-ASSEMBLED"
        lines.append("Batch-created with no words of Brian's at or "
                     "before creation in the attributed record.")
    else:
        cls = "UNKNOWN"
        lines.append("No batch signature and no words of Brian's "
                     "at or before creation - origin UNKNOWN.")
    return cls, lines, created


def _employment_track_block(cur, slug, terms, description):
    """The freelance_ai track of public.employment_criteria is a
    standing record several goals explicitly feed (their recorded
    descriptions name it). Include it verbatim for goals whose own
    record mentions the freelance/career/employment track."""
    blob = f"{slug} {terms['name']} {description or ''}".lower()
    if not any(w in blob for w in ("freelance", "employment", "career")):
        return None
    try:
        cur.execute(
            "SELECT criteria::text FROM public.employment_criteria "
            "ORDER BY updated_at DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return None
        crit = json.loads(row[0])
        track = crit.get("freelance_ai")
        if not track:
            return None
        return ("Standing record - public.employment_criteria, "
                "freelance_ai track (Brian's criteria, updated "
                f"{crit.get('_updated', 'on record')}): "
                + _trim(json.dumps(track), 700))
    except Exception:
        return None


def compile_brief(cur, slug):
    """Compile one goal's standing brief from the record and store
    it (goal_briefs + the node's readme BRIEF section), on the
    caller's transaction. Returns the meta dict. Never writes goal
    status/progress/blocker - a brief is context, not a decision."""
    terms = _goal_terms(cur, slug)
    key = gn.node_key_for_slug(slug)
    cur.execute(
        "SELECT name, status, details, summary FROM atlas.nodes "
        "WHERE node_key = %s AND node_type = 'goal'", [key])
    node = cur.fetchone()
    if node is None:
        raise ValueError(f"no goal node for slug: {slug}")
    name, node_status, details, _summary = node
    details = dict(details or {})
    cur.execute(
        "SELECT status, target_date, progress_pct, phase, owner_agent, "
        "description, success_metrics, notes, updated_at "
        "FROM successbrian_os.sbos_goals WHERE goal_slug = %s", [slug])
    grow = cur.fetchone()
    desc = grow[5] if grow else None

    brian_items = _brian_word_items(cur, terms)
    origin_class, origin_lines, _created = _origin(
        cur, slug, terms, brian_items)
    rulings = _ruling_items(cur, terms)
    connected = _connected_items(cur, slug, terms)
    newest = _newest_source_at(cur, terms)
    track_block = _employment_track_block(cur, slug, terms, desc)

    L = [f"## GOAL BRIEF - {name} (slug {slug})",
         f"Compiled {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
         f"by the einstein_planner brief compiler, from the ecosystem "
         f"record only. Gaps are labeled UNKNOWN, never filled.",
         "",
         "### Brian's own words"]
    if brian_items:
        for i in brian_items:
            L.append(f'- "{i["text"]}" - Brian, {i["date"]} '
                     f'(source: {i["ref"]})')
    else:
        L.append("NONE ON RECORD - no words of Brian's about this "
                 "goal were found in the attributed record (ruling "
                 "census, decision answers, ruled decisions, quoted "
                 "second-brain spans).")
        if origin_class == "AGENT-ASSEMBLED":
            L.append(f"origin: agent-assembled {_created} - no words "
                     f"of Brian's on record. This goal is an "
                     f"unadopted agent proposal until Brian rules "
                     f"otherwise.")
    L += ["", "### Origin", f"Origin class: {origin_class}."]
    L += [f"- {ln}" for ln in origin_lines]
    L += ["", "### The goal as recorded"]
    L.append(f"Atlas node: status {node_status}; priority "
             f"{details.get('priority')}; category "
             f"{details.get('category')}; blocker on node: "
             f"{details.get('blocker') or 'none'}.")
    if grow:
        (gstatus, target, pct, phase, owner, _d, metrics, notes,
         updated) = grow
        L.append(f"Goal row: status {gstatus}; progress_pct {pct}; "
                 f"target {target}; phase {phase}; owner_agent "
                 f"{owner}; record updated {updated}.")
        if desc:
            L.append(f"Description (verbatim): {_trim(desc, 600)}")
        if metrics:
            L.append(f"Success metrics: {_trim(metrics, 300)}")
        if notes:
            L.append(f"Notes (verbatim, incl. any constraints): "
                     f"{_trim(notes, 500)}")
    else:
        L.append("Goal row: NO ROW in sbos_goals - UNKNOWN beyond "
                 "the Atlas node.")
    if track_block:
        L += ["", "### Standing track record this goal feeds",
              track_block]
    L += ["", "### Connected work (record links, honestly labeled)"]
    if connected["edges"]:
        L.append("Atlas edges (the graph's own claims):")
        L += [f"- {e}" for e in connected["edges"]]
    else:
        L.append("Atlas edges: none on record.")
    if connected["records"]:
        L.append("Subject-matched Atlas records (references, not "
                 "edges):")
        for r in connected["records"]:
            L.append(f"- {r['key']} - {r['name']} "
                     f"[{r['type']}/{r['status']}]")
            if r["excerpt"]:
                L.append(f"  excerpt: {r['excerpt']}")
    else:
        L.append("Subject-matched Atlas records: none found.")
    if connected["projects"]:
        L.append("Subject-matched PM projects:")
        for p in connected["projects"]:
            L.append(f"- {p['key']} - {p['title']} [{p['status']}] "
                     f"(requested_by {p['requested_by']})")
            if p["excerpt"]:
                L.append(f"  excerpt: {p['excerpt']}")
    else:
        L.append("Subject-matched PM projects: none found.")
    if connected["decisions"]:
        L.append("Open decision-queue items referencing this goal "
                 "(waiting on Brian):")
        for d in connected["decisions"]:
            L.append(f"- decision #{d['id']}: {d['title']} "
                     f"[{d['status']}]")
    else:
        L.append("Open decision-queue items referencing this goal: "
                 "none found.")
    L += ["", "### Standing constraints & rulings touching this goal"]
    if rulings:
        for r in rulings:
            L.append(f"- {r['ref']} (ruled {r['date']}, subject: "
                     f"{r['subject']}, status {r['status']}): "
                     f"{r['text']}")
    else:
        L.append("None found in the ruling census - UNKNOWN whether "
                 "any ruling touches this goal outside the census.")
    L += ["", "### Current measured state"]
    cur.execute(
        "SELECT count(*), count(*) FILTER (WHERE status IN "
        "('done', 'completed', 'closed')) FROM atlas.goal_tasks "
        "WHERE goal_slug = %s", [slug])
    total, done = cur.fetchone()
    cur.execute(
        "SELECT count(*), max(looked_at) FROM "
        "successbrian_os.goal_coverage WHERE goal_slug = %s", [slug])
    nlooks, last_look = cur.fetchone()
    cur.execute(
        "SELECT status, count(*) FROM successbrian_os.pm_steps s "
        "JOIN successbrian_os.goal_coverage c "
        "ON s.source = 'goal_coverage:' || c.id "
        "WHERE c.goal_slug = %s GROUP BY status", [slug])
    step_counts = dict(cur.fetchall())
    cur.execute(
        "SELECT status, count(*) FROM "
        "successbrian_os.einstein_passes WHERE goal_slug = %s "
        "GROUP BY status", [slug])
    pass_counts = dict(cur.fetchall())
    L.append(f"Tasks: {done}/{total} done. Planner looks: {nlooks} "
             f"(last {last_look or 'never'}). Steps filed from this "
             f"goal's looks by status: "
             f"{step_counts or 'none'}. Einstein passes: "
             f"{pass_counts or 'none yet'}.")
    brief = "\n".join(L)
    if len(brief) > BRIEF_STORE_BUDGET_CHARS:
        slim = [ln for ln in L if not ln.startswith("  excerpt:")]
        brief = "\n".join(slim)
    if len(brief) > BRIEF_STORE_BUDGET_CHARS:
        brief = brief[:BRIEF_STORE_BUDGET_CHARS]
    meta = {"has_brian_words": bool(brian_items),
            "origin_class": origin_class,
            "newest_source_at": newest,
            "counts": {"brian_words": len(brian_items),
                       "rulings": len(rulings),
                       "edges": len(connected["edges"]),
                       "records": len(connected["records"]),
                       "projects": len(connected["projects"]),
                       "decisions": len(connected["decisions"])}}
    cur.execute(
        "INSERT INTO successbrian_os.goal_briefs "
        "(goal_slug, brief_md, compiled_at, has_brian_words, "
        "origin_class, newest_source_at, sources) VALUES "
        "(%s, %s, now(), %s, %s, %s, %s::jsonb) "
        "ON CONFLICT (goal_slug) DO UPDATE SET brief_md = "
        "EXCLUDED.brief_md, compiled_at = now(), has_brian_words = "
        "EXCLUDED.has_brian_words, origin_class = "
        "EXCLUDED.origin_class, newest_source_at = "
        "EXCLUDED.newest_source_at, sources = EXCLUDED.sources",
        [slug, brief, meta["has_brian_words"], origin_class,
         newest, json.dumps(meta["counts"])])
    _set_readme_section(cur, key, "brief", brief)
    return meta


def _section_span(readme, begin, end):
    if not readme:
        return None
    i = readme.find(begin)
    j = readme.find(end)
    if i < 0 or j < 0 or j < i:
        return None
    return (i, j + len(end))


def _set_readme_section(cur, node_key, kind, body):
    """Insert or replace one delimited section of a goal node's
    readme, preserving the other section. Order: BRIEF first, then
    PLAN. Unmarked legacy readme text (this morning's first
    write-backs) is a superseded plan: it is wrapped as the PLAN
    section when a brief first lands, and replaced when a new plan
    lands - the verbatim text also lives in einstein_passes."""
    cur.execute(
        "SELECT readme_md FROM atlas.nodes WHERE node_key = %s",
        [node_key])
    row = cur.fetchone()
    readme = (row[0] if row else None) or ""
    begin, end = ((BRIEF_BEGIN, BRIEF_END) if kind == "brief"
                  else (PLAN_BEGIN, PLAN_END))
    block = f"{begin}\n{body.rstrip()}\n{end}"
    span = _section_span(readme, begin, end)
    if span:
        new = readme[:span[0]] + block + readme[span[1]:]
    elif kind == "brief":
        plan_span = _section_span(readme, PLAN_BEGIN, PLAN_END)
        if plan_span:
            new = (readme[:plan_span[0]] + block + "\n\n"
                   + readme[plan_span[0]:])
        elif readme.strip():
            legacy = (f"{PLAN_BEGIN}\n{readme.strip()}\n{PLAN_END}")
            new = block + "\n\n" + legacy
        else:
            new = block
    else:  # plan
        brief_span = _section_span(readme, BRIEF_BEGIN, BRIEF_END)
        if brief_span:
            new = readme.rstrip() + "\n\n" + block
        else:
            new = block
    cur.execute(
        "UPDATE atlas.nodes SET readme_md = %s WHERE node_key = %s",
        [new, node_key])


def brief_is_stale(cur, slug):
    """A brief is stale when it does not exist, when it is older
    than the goal's coverage window, or when newer source items
    have landed since it was compiled."""
    cur.execute(
        "SELECT compiled_at FROM successbrian_os.goal_briefs "
        "WHERE goal_slug = %s", [slug])
    row = cur.fetchone()
    if row is None:
        return True
    compiled_at = row[0]
    cur.execute(
        "SELECT details FROM atlas.nodes WHERE node_key = %s",
        [gn.node_key_for_slug(slug)])
    nrow = cur.fetchone()
    window = int(((nrow[0] if nrow else None) or {}).get(
        "coverage_window_days") or 4)
    now = datetime.now(timezone.utc)
    if (now - compiled_at).days >= window:
        return True
    terms = _goal_terms(cur, slug)
    newest = _newest_source_at(cur, terms)
    return bool(newest and newest > compiled_at)


def ensure_brief(cur, slug, force=False):
    """Compile the goal's brief if missing or stale (or always,
    with force). Returns the meta dict, or None when the stored
    brief is already fresh. Runs on the caller's transaction."""
    if not force and not brief_is_stale(cur, slug):
        return None
    return compile_brief(cur, slug)


def briefs_cmd(slugs=None, force=False):
    """Compile/refresh briefs: every stale-or-missing brief in the
    rotation, or the named goals. Prints one line per compile plus
    the coverage summary the QA check and captures cite."""
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        conn.commit()
        targets = list(slugs) if slugs else _rotation_slugs(cur)
        compiled = skipped = 0
        for slug in targets:
            try:
                cur.execute("BEGIN")
                meta = ensure_brief(cur, slug, force=force)
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"  {slug}: BRIEF FAILED {e}")
                continue
            if meta is None:
                skipped += 1
            else:
                compiled += 1
                c = meta["counts"]
                print(f"  {slug}: brief compiled "
                      f"(origin {meta['origin_class']}, "
                      f"brian_words {c['brian_words']}, rulings "
                      f"{c['rulings']}, edges {c['edges']}, records "
                      f"{c['records']}, projects {c['projects']}, "
                      f"decisions {c['decisions']})")
        rows = sbos_common.pg_rows(
            "SELECT origin_class, count(*), "
            "count(*) FILTER (WHERE has_brian_words) FROM "
            "successbrian_os.goal_briefs GROUP BY origin_class "
            "ORDER BY origin_class")
        total = sbos_common.pg_one(
            "SELECT count(*) FROM successbrian_os.goal_briefs")
        print(f"briefs: {total} stored; compiled {compiled}, "
              f"already fresh {skipped}")
        for cls, n, with_words in rows:
            print(f"  origin {cls}: {n} briefs, {with_words} with "
                  f"Brian's words")
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------- parsing

def parse_plan(text):
    """Split Einstein's reply into the six contract sections.
    Tolerant: a missing section comes back empty; the raw text is
    always preserved by the caller. Returns dict with keys
    verified, claimed, blockers, plan_steps (list), research
    (list of {question, why, where}), for_brian."""
    out = {"verified": "", "worth": "", "claimed": "", "blockers": "",
           "plan_steps": [], "research": [], "for_brian": ""}
    if not text:
        return out
    # Gamma's return leg keeps only the first text block (measured
    # 2026-11-23, probe events 1722/1728: multi-paragraph answers
    # came back as their first paragraph), so the prompt demands one
    # unbroken block with inline headers - and this parser splits on
    # the headers wherever they appear, which also handles a reply
    # that arrives line-broken anyway.
    flat = " ".join(str(text).split())
    header_re = re.compile(
        r"(VERIFIED STATE|WORTH|CLAIMED vs VERIFIED|BLOCKERS|PLAN|"
        r"RESEARCH NEEDS|FOR BRIAN)\s*:", re.IGNORECASE)
    marks = list(header_re.finditer(flat))
    sections = {}
    for i, m in enumerate(marks):
        key = m.group(1).upper()
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(flat)
        if key not in sections:
            sections[key] = flat[start:end].strip()
    out["verified"] = sections.get("VERIFIED STATE", "")
    out["worth"] = sections.get("WORTH", "")
    out["claimed"] = sections.get("CLAIMED VS VERIFIED", "")
    out["blockers"] = sections.get("BLOCKERS", "")
    out["for_brian"] = sections.get("FOR BRIAN", "")
    plan_raw = sections.get("PLAN", "")
    step_marks = list(re.finditer(r"(?:^|\s)(\d+)[.)]\s+", plan_raw))
    for i, m in enumerate(step_marks):
        start = m.end()
        end = (step_marks[i + 1].start()
               if i + 1 < len(step_marks) else len(plan_raw))
        step = plan_raw[start:end].strip()
        if step:
            out["plan_steps"].append(step)
    if not out["plan_steps"] and plan_raw and plan_raw.lower() != "none":
        out["plan_steps"] = [plan_raw]
    research_raw = sections.get("RESEARCH NEEDS", "")
    if research_raw and research_raw.lower() != "none":
        item_re = re.compile(
            r"NEED:\s*(.*?)\s*\|\s*WHY:\s*(.*?)\s*\|\s*WHERE:\s*"
            r"(.*?)(?=\s*NEED:|$)", re.IGNORECASE)
        items = item_re.findall(research_raw)
        if items:
            for q, why, where in items:
                out["research"].append(
                    {"question": q.strip(), "why": why.strip(),
                     "where": where.strip()})
        else:
            out["research"].append(
                {"question": research_raw, "why": "", "where": ""})
    return out


# ---------------------------------------------------------------- due set

def due_goals(limit):
    """Goals due for an Einstein look, in rotation order: active
    goals with no einstein-seat look inside their coverage window.
    Rotation order comes from planner_rotation.fetch_rotation, so
    Einstein rides the same rotation as the light driver."""
    rows = pr.fetch_rotation()
    if not rows:
        return []
    slugs = [r[0] for r in rows]
    last = dict(sbos_common.pg_rows(
        "SELECT goal_slug, max(looked_at) FROM "
        "successbrian_os.goal_coverage WHERE planner_seat = %s "
        "AND goal_slug = ANY(%s) GROUP BY goal_slug", [SEAT, slugs]))
    windows = {}
    for slug, _node_key, det in sbos_common.pg_rows(
            "SELECT details->>'goal_slug', node_key, details "
            "FROM atlas.nodes WHERE node_type = 'goal' "
            "AND details->>'goal_slug' = ANY(%s)", [slugs]):
        windows[slug] = int((det or {}).get("coverage_window_days") or 4)
    now = datetime.now(timezone.utc)
    due = []
    for slug in slugs:
        seen = last.get(slug)
        if seen is None or (now - seen).days >= windows.get(slug, 4):
            due.append(slug)
        if len(due) >= limit:
            break
    return due


# ---------------------------------------------------------------- dispatch

def dispatch_look(cur, slug, dry_run=False, probe_suffix=""):
    """Build the context packet for one goal and put it on the bus
    for Einstein. Returns (bus_event_id_or_None, probe_id). The
    einstein_passes insert runs on the caller's transaction; the bus
    insert commits on its own connection (the planner_rotation
    dispatch convention), so a crash between the two leaves the
    pass undispatched-marked and a retry re-sends with the same
    deterministic probe_id. probe_suffix is the manual --force
    override: it lets a named goal be re-looked the same day (the
    proof-case path) without disturbing the daily dedupe the cron
    relies on."""
    context = build_context(cur, slug)
    prompt = build_prompt(context)
    probe_id = (f"einstein-look-{slug}-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%d')}"
                f"{probe_suffix}")
    cur.execute(
        "SELECT id, status FROM successbrian_os.einstein_passes "
        "WHERE probe_id = %s", [probe_id])
    existing = cur.fetchone()
    if existing:
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
        "VALUES (%s, %s, %s, 'dispatched')", [slug, probe_id, event_id])
    print(f"  {slug}: Einstein look dispatched (bus event {event_id}, "
          f"probe {probe_id}, priority {BUS_PRIORITY})")
    return event_id, probe_id


def run(limit, dry_run=False, slugs=None, force=False):
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        conn.commit()
        due = list(slugs) if slugs else due_goals(limit)
        if not due:
            print("run: no goals due for an Einstein look")
            return 0
        sent = 0
        for slug in due:
            # Brief maintenance rides the same cycle: a missing or
            # stale brief is recompiled BEFORE the look dispatches,
            # so Einstein never plans from a skeleton again. A brief
            # failure is reported but does not block the look - the
            # live record alone is the old behavior, never worse.
            try:
                cur.execute("BEGIN")
                meta = ensure_brief(cur, slug)
                conn.commit()
                if meta is not None:
                    print(f"  {slug}: brief refreshed "
                          f"(origin {meta['origin_class']})")
            except Exception as e:
                conn.rollback()
                print(f"  {slug}: BRIEF REFRESH FAILED {e}")
            try:
                cur.execute("BEGIN")
                suffix = ("-r" + datetime.now(timezone.utc).strftime(
                    "%H%M%S")) if force else ""
                eid, _probe = dispatch_look(
                    cur, slug, dry_run=dry_run, probe_suffix=suffix)
                conn.commit()
                if eid is not None:
                    sent += 1
            except Exception as e:
                conn.rollback()
                print(f"  {slug}: FAILED {e}")
        print(f"run: {sent} dispatched ({'dry-run' if dry_run else 'live'})")
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------- collect

def _result_for_event(event_id):
    """Gamma's result envelope for one bus event, or None. The
    outbox subject convention is gamma's own: 'gamma: event <id>
    done (reap_infer)' (ingest_worker / standing_compile)."""
    row = sbos_common.pg_one(
        "SELECT body FROM successbrian_os.outbox "
        "WHERE message_type = 'inference_result' AND subject = %s "
        "ORDER BY id DESC LIMIT 1",
        (f"gamma: event {event_id} done (reap_infer)",))
    if not row:
        return None
    try:
        env = json.loads(row)
    except (ValueError, TypeError):
        return {"ok": False, "result": {"text": str(row)}}
    return env


def write_back(cur, pass_row, text):
    """Write one landed Einstein plan back into the planner's
    stores, on the caller's transaction. Returns the look id.
    Einstein's assessment is recorded as an assessment; proposed
    corrections stay FLAGGED in the text - this function never
    writes goal status, progress, or blocker."""
    pass_id, slug, probe_id, event_id = pass_row
    parsed = parse_plan(text)
    node = cur.execute(
        "SELECT details FROM atlas.nodes WHERE node_key = %s "
        "AND node_type = 'goal'", [gn.node_key_for_slug(slug)])
    row = cur.fetchone()
    prio = int((row[0] or {}).get("priority") or 50) if row else 50

    findings_parts = [f"Einstein deep look (bus event {event_id}, "
                      f"probe {probe_id})."]
    if parsed["verified"]:
        findings_parts.append(f"VERIFIED STATE: {parsed['verified']}")
    if parsed.get("worth"):
        findings_parts.append(
            f"WORTH (Brian's four tests): {parsed['worth']}")
    if parsed["claimed"]:
        findings_parts.append(
            f"CLAIMED vs VERIFIED (corrections FLAGGED, not applied): "
            f"{parsed['claimed']}")
    if parsed["blockers"]:
        findings_parts.append(f"BLOCKERS (as assessed): "
                              f"{parsed['blockers']}")
    if not parsed["verified"] and not parsed["plan_steps"]:
        findings_parts.append(
            "Reply did not parse into the contract sections; full "
            "text preserved in the node readme and the pass ledger.")
    findings = " ".join(findings_parts)[:1900]

    steps = parsed["plan_steps"]
    if steps:
        work = steps[0]
    else:
        work = ("none - Einstein plan filed in the goal node readme; "
                "no executable step parsed this look")
    look_id = pr.do_look(cur, slug, findings, work, tier="planner",
                         seat=SEAT)

    context = (f"goal {slug} Einstein look {look_id} "
               f"(bus event {event_id})")
    for i, step in enumerate(steps[1:], start=2):
        pm_core.add_step(
            cur, f"einstein-look-{look_id}-step-{i}",
            f"[{slug}] {step[:100]}", kind="task",
            source=f"goal_coverage:{look_id}", priority=prio,
            payload={"instruction": step, "context": context,
                     "engine_tier": "planner",
                     "einstein_pass": pass_id})
    for i, item in enumerate(parsed["research"], start=1):
        pm_core.add_step(
            cur, f"einstein-look-{look_id}-research-{i}",
            f"[research][{slug}] {item['question'][:88]}",
            kind="research", source=f"goal_coverage:{look_id}",
            priority=prio,
            payload={"question": item["question"], "why": item["why"],
                     "where_answer_lives": item["where"],
                     "goal_slug": slug, "einstein_pass": pass_id,
                     "research_need": True})

    header = (f"# Einstein plan - {slug}\n"
              f"Filed {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
              f"by einstein_planner (seat einstein; bus event {event_id}; "
              f"probe {probe_id}; look {look_id}).\n"
              f"Assessment only: Einstein cannot close goals or mark "
              f"work done. State corrections in this plan are FLAGGED, "
              f"not applied.\n\n")
    # The plan lands in the node's EINSTEIN-PLAN section only; the
    # GOAL-BRIEF section beside it is preserved untouched.
    _set_readme_section(cur, gn.node_key_for_slug(slug), "plan",
                        header + text)
    cur.execute(
        "UPDATE atlas.nodes SET summary = %s WHERE node_key = %s",
        [(f"Einstein plan {datetime.now(timezone.utc).date()}: "
          + (parsed["verified"] or "see readme"))[:240],
         gn.node_key_for_slug(slug)])
    cur.execute(
        "UPDATE successbrian_os.einstein_passes SET status = 'collected', "
        "collected_at = now(), look_id = %s, plan_text = %s WHERE id = %s",
        [look_id, text, pass_id])
    return look_id


def collect(wait_s=0):
    """Collect landed Einstein results and write their plans back.
    With wait_s > 0, poll until all outstanding passes land or the
    deadline passes (the live-test path). Returns count collected."""
    deadline = time.time() + wait_s
    collected = 0
    while True:
        pending = sbos_common.pg_rows(
            "SELECT id, goal_slug, probe_id, bus_event_id "
            "FROM successbrian_os.einstein_passes "
            "WHERE status = 'dispatched' ORDER BY id")
        if not pending:
            return collected
        progressed = False
        for pass_row in pending:
            pass_id, slug, _probe, event_id = pass_row
            env = _result_for_event(event_id)
            if env is None:
                st = sbos_common.pg_one(
                    "SELECT status FROM bus.events WHERE id = %s",
                    (event_id,))
                if st in ("dead_letter", "failed"):
                    sbos_common.pg_rows(
                        "UPDATE successbrian_os.einstein_passes "
                        "SET status = 'failed', note = %s WHERE id = %s",
                        [f"bus event {st}", pass_id])
                    progressed = True
                continue
            res = env.get("result") or {}
            text = res.get("text") if isinstance(res, dict) else None
            conn = sbos_common.connect()
            try:
                cur = conn.cursor()
                cur.execute("BEGIN")
                try:
                    if env.get("ok") and text:
                        look_id = write_back(cur, pass_row, text)
                        conn.commit()
                        print(f"  {slug}: plan written back "
                              f"(look {look_id}, bus event {event_id})")
                    else:
                        cur.execute(
                            "UPDATE successbrian_os.einstein_passes "
                            "SET status = 'failed', note = %s "
                            "WHERE id = %s",
                            [f"gamma result ok={env.get('ok')}, "
                             f"text {'present' if text else 'missing'}",
                             pass_id])
                        conn.commit()
                        print(f"  {slug}: gamma result not usable "
                              f"(bus event {event_id})")
                    collected += 1
                    progressed = True
                except Exception as e:
                    conn.rollback()
                    print(f"  {slug}: WRITE-BACK FAILED {e}")
                    sbos_common.pg_rows(
                        "UPDATE successbrian_os.einstein_passes "
                        "SET note = %s WHERE id = %s",
                        [f"write-back failed: {e}"[:400], pass_id])
            finally:
                conn.close()
        if wait_s <= 0 or time.time() >= deadline:
            return collected
        if not progressed:
            time.sleep(20)


def cycle(limit):
    got = collect()
    if got:
        print(f"cycle: collected {got} landed plan(s)")
    return run(limit)


def plan_cmd(n):
    due = due_goals(n)
    active, looked, never, _oldest = pr.coverage()
    print(f"coverage: {looked}/{active} looked, {never} never looked")
    print(f"next {len(due)} due for an Einstein look:")
    for slug in due:
        print(f"  {slug}")
    return 0


def status():
    rows = sbos_common.pg_rows(
        "SELECT status, count(*) FROM successbrian_os.einstein_passes "
        "GROUP BY status ORDER BY status")
    print("einstein passes: " + (", ".join(f"{s}={c}" for s, c in rows)
                                 if rows else "none yet"))
    row = sbos_common.pg_one(
        "SELECT goal_slug || ' look ' || coalesce(look_id::text, '-') "
        "|| ' collected ' || coalesce(collected_at::text, '-') "
        "FROM successbrian_os.einstein_passes "
        "WHERE status = 'collected' ORDER BY collected_at DESC LIMIT 1")
    print(f"latest collected plan: {row or 'none'}")
    return 0


# ---------------------------------------------------------------- selftest

CANNED = """VERIFIED STATE:
The record proves the goal is active with 0 of 2 tasks done and no
dedicated box on the network (review capture 3042).

CLAIMED vs VERIFIED:
The goal row claims progress 100% while status is still active.
Proposed correction: progress should read 0% until evidence lands -
FLAGGED for a human, not applied.

BLOCKERS:
No box exists to migrate to; the migration question is unsettled.

PLAN:
1. Inventory the workloads still running on the main server for this goal.
2. File the box-evidence question as a research item with the review capture attached.
3. Draft the re-targeted goal statement for Brian's ruling.

RESEARCH NEEDS:
NEED: Does any machine on the tailnet already run this workload? | WHY: it decides whether a migration is needed at all | WHERE: the tailnet device list and the morning review capture
NEED: What did the original goal statement promise? | WHY: the re-target draft must match it | WHERE: the goal's Atlas node history

FOR BRIAN:
Rule whether this goal closes, re-targets, or waits for a box."""


def selftest():
    steps = []

    def check(name, cond):
        steps.append((name, bool(cond)))
        assert cond, f"selftest step failed: {name}"

    parsed = parse_plan(CANNED)
    check("canned reply: verified section parsed",
          "0 of 2 tasks done" in parsed["verified"])
    check("canned reply: claimed-vs-verified parsed",
          "progress 100%" in parsed["claimed"])
    check("canned reply: 3 plan steps parsed in order",
          len(parsed["plan_steps"]) == 3
          and parsed["plan_steps"][0].startswith("Inventory"))
    check("canned reply: 2 research needs parsed with why/where",
          len(parsed["research"]) == 2
          and parsed["research"][0]["why"].startswith("it decides")
          and "tailnet" in parsed["research"][0]["where"])
    check("canned reply: for-Brian residue parsed",
          "Rule whether" in parsed["for_brian"])
    empty = parse_plan("unstructured text with no headers")
    check("unstructured reply parses empty, never raises",
          empty["plan_steps"] == [] and empty["verified"] == "")

    packet = sbos_common.build_reap_packet(
        build_prompt("Goal: probe"), source=SOURCE,
        probe_id="einstein-selftest", item_ref="probe",
        max_tokens=MAX_TOKENS, thinking=False)
    check("packet builds at the feeder ceiling",
          packet["max_tokens"] == MAX_TOKENS == 500
          and packet["packet_standard"] == "feeder-packet-v1")

    # Transactional write-back probe: a disposable goal node, a fake
    # pass row, the canned plan written back - then ROLLBACK, so no
    # residue (successbrian has no DELETE on atlas.nodes).
    probe_slug = "__selftest__einstein__"
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        ensure_schema(cur)
        cur.execute(
            "INSERT INTO atlas.nodes "
            "(node_key, node_type, name, status, details, ref_kind, "
            "ref_id) VALUES (%s, 'goal', 'SELFTEST disposable', "
            "'planned', %s::jsonb, 'sbos_goal', '0')",
            [gn.node_key_for_slug(probe_slug),
             json.dumps({"goal_slug": probe_slug, "priority": 50,
                         "coverage_window_days": 4})])
        cur.execute(
            "INSERT INTO successbrian_os.einstein_passes "
            "(goal_slug, probe_id, bus_event_id, status) "
            "VALUES (%s, 'einstein-selftest-probe', 0, 'dispatched') "
            "RETURNING id", [probe_slug])
        pass_id = cur.fetchone()[0]
        look_id = write_back(
            cur, (pass_id, probe_slug, "einstein-selftest-probe", 0),
            CANNED)
        cur.execute(
            "SELECT planner_seat, engine_tier FROM "
            "successbrian_os.goal_coverage WHERE id = %s", [look_id])
        lrow = cur.fetchone()
        check("write-back: look filed under the einstein seat",
              lrow == ("einstein", "planner"))
        cur.execute(
            "SELECT readme_md FROM atlas.nodes WHERE node_key = %s",
            [gn.node_key_for_slug(probe_slug)])
        readme = cur.fetchone()[0]
        check("write-back: node readme holds the verbatim plan",
              "Does any machine on the tailnet" in readme
              and "FLAGGED, not applied" in readme)
        cur.execute(
            "SELECT kind, count(*) FROM successbrian_os.pm_steps "
            "WHERE source = %s GROUP BY kind",
            [f"goal_coverage:{look_id}"])
        kinds = dict(cur.fetchall())
        check("write-back: remaining plan steps filed as task steps",
              kinds.get("task") == 2)
        check("write-back: research needs filed as research steps",
              kinds.get("research") == 2)
        cur.execute(
            "SELECT status, look_id FROM "
            "successbrian_os.einstein_passes WHERE id = %s", [pass_id])
        prow = cur.fetchone()
        check("write-back: pass marked collected with its look",
              prow == ("collected", look_id))
        # Brief machinery on the same disposable node, same
        # transaction: compile must store the brief, mirror it into
        # the readme's BRIEF section, and leave the PLAN section
        # (written above) untouched - and a brief recompile after a
        # plan write-back must likewise preserve the plan.
        meta = compile_brief(cur, probe_slug)
        check("brief: origin class is one of the honest three",
              meta["origin_class"] in
              ("BRIAN-DIRECTED", "AGENT-ASSEMBLED", "UNKNOWN"))
        cur.execute(
            "SELECT brief_md FROM successbrian_os.goal_briefs "
            "WHERE goal_slug = %s", [probe_slug])
        brow = cur.fetchone()
        check("brief: stored in goal_briefs with the provenance "
              "sections", brow is not None
              and "Brian's own words" in brow[0]
              and "### Origin" in brow[0])
        cur.execute(
            "SELECT readme_md FROM atlas.nodes WHERE node_key = %s",
            [gn.node_key_for_slug(probe_slug)])
        readme = cur.fetchone()[0]
        check("brief + plan sections coexist in the readme",
              BRIEF_BEGIN in readme and PLAN_BEGIN in readme
              and "Does any machine on the tailnet" in readme)
        compile_brief(cur, probe_slug)
        cur.execute(
            "SELECT readme_md FROM atlas.nodes WHERE node_key = %s",
            [gn.node_key_for_slug(probe_slug)])
        readme2 = cur.fetchone()[0]
        check("brief recompile preserves the plan section",
              "Does any machine on the tailnet" in readme2
              and BRIEF_BEGIN in readme2)
        check("packet carries the standing brief",
              "STANDING BRIEF" in build_context(cur, probe_slug)
              and "GOAL BRIEF" in build_context(cur, probe_slug))
        check("match levels: slug is strong, one token is weak",
              _match_level("see goal:local-ai-agent-stack notes",
                           {"slug": "local-ai-agent-stack",
                            "name": "zzz", "distinctive": ["stack"]}) == 2
              and _match_level("a stack of pancakes",
                               {"slug": "local-ai-agent-stack",
                                "name": "zzz",
                                "distinctive": ["stack"]}) == 1)
        check("match levels: a name bigram is strong evidence",
              _match_level("we sell local ai servers",
                           {"slug": "local-ai-agent-stack",
                            "name": "zzz", "distinctive": ["local"],
                            "phrases": ["local ai", "agent stack"]}) == 2
              and _match_level("local plumbers available",
                               {"slug": "local-ai-agent-stack",
                                "name": "zzz", "distinctive": ["local"],
                                "phrases": ["local ai",
                                            "agent stack"]}) == 1)
        _st = {"slug": "local-ai-agent-stack", "name": "zzz",
               "distinctive": ["local", "agent", "stack"],
               "phrases": ["local ai", "ai agent", "agent stack"],
               "rare": ["stack"]}
        check("subject match: two common tokens are not attribution",
              not _subject_match(
                  "the local model fleet hosts agents for inference",
                  _st)
              and _subject_match(
                  "the agent stack runs local models", _st)
              and _subject_match("we sell local ai servers", _st))
        cur.execute("ROLLBACK")
        check("probe rolled back, no residue",
              sbos_common.pg_one(
                  "SELECT count(*) FROM atlas.nodes WHERE node_key = %s",
                  [gn.node_key_for_slug(probe_slug)]) == 0
              and sbos_common.pg_one(
                  "SELECT count(*) FROM successbrian_os.einstein_passes "
                  "WHERE probe_id = 'einstein-selftest-probe'") == 0)
    finally:
        conn.close()
    print(f"EINSTEIN_PLANNER_OK ({len(steps)} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--plan", nargs="?", const=10, type=int, metavar="N")
    ap.add_argument("--run", nargs="?", const=EINSTEIN_PER_CYCLE,
                    type=int, metavar="N")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--cycle", nargs="?", const=EINSTEIN_PER_CYCLE,
                    type=int, metavar="N")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--wait", type=int, default=0, metavar="S",
                    help="with --run or --collect: poll and collect "
                         "for up to S s")
    ap.add_argument("--slug", metavar="SLUG",
                    help="with --run: look at this one goal, "
                         "regardless of due order")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --run: build packets, send nothing")
    ap.add_argument("--briefs", action="store_true",
                    help="compile/refresh goal briefs (all stale or "
                         "missing in the rotation; one goal with "
                         "--slug; every goal with --force)")
    ap.add_argument("--force", action="store_true",
                    help="with --briefs: recompile every brief; "
                         "with --run --slug: re-look a goal already "
                         "looked today (fresh probe id)")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.briefs:
        return briefs_cmd(slugs=[a.slug] if a.slug else None,
                          force=a.force)
    if a.plan is not None:
        return plan_cmd(a.plan)
    if a.collect:
        got = collect(wait_s=a.wait)
        print(f"collect: {got} plan(s) written back")
        return 0
    if a.cycle is not None:
        return cycle(a.cycle)
    if a.run is not None:
        rc = run(a.run, dry_run=a.dry_run,
                 slugs=[a.slug] if a.slug else None, force=a.force)
        if a.wait and not a.dry_run:
            got = collect(wait_s=a.wait)
            print(f"run: {got} plan(s) collected within the wait")
        return rc
    if a.status:
        return status()
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
