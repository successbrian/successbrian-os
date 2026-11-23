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
EINSTEIN_PER_CYCLE = 1
STALE_PASS_HOURS = 24

SECTION_HEADERS = ("VERIFIED STATE", "CLAIMED vs VERIFIED", "BLOCKERS",
                   "PLAN", "RESEARCH NEEDS", "FOR BRIAN")

PROMPT_TEMPLATE = """You are Einstein, the deep-planning engine in a solo operator's goal system. Below is one goal's live record, assembled from its goal row, its Atlas node, its recent planner looks, its tasks, and recent captures. Judge ONLY from this record. Where the record is silent, say UNKNOWN - never invent a fact, a date, or a person's intent.

Write a planning assessment with EXACTLY these six sections, in this order, plain text, no preamble, no closing remarks. CRITICAL FORMAT RULE: write the ENTIRE assessment as one single unbroken block of text - NO blank lines anywhere, NO paragraph breaks. The channel that carries your answer back keeps only the first block, so a blank line ends your answer and the rest is lost. Start immediately with "VERIFIED STATE:" and run each section's header inline, like this: VERIFIED STATE: <text> CLAIMED vs VERIFIED: <text> BLOCKERS: <text> PLAN: 1. <step> 2. <step> RESEARCH NEEDS: <items> FOR BRIAN: <text>

VERIFIED STATE: What the evidence in the record actually proves about this goal today, each claim tied to the record item it rests on. At most 80 words.
CLAIMED vs VERIFIED: Where the goal's claimed state (status, progress, dates) disagrees with the evidence, say so plainly and name the correction you propose. These are flagged for a human - you are not applying them. At most 60 words.
BLOCKERS: What is actually stopping progress, from the record. "none proven" if the record shows none. At most 40 words.
PLAN: The concrete next steps, in order, numbered "1." "2." "3." inline - each step a single executable action a worker could claim and finish, at most 25 words per step. At most 5 steps. A step that only Brian can perform does not belong here - it belongs in FOR BRIAN.
RESEARCH NEEDS: What is UNKNOWN that research could settle, each item in exactly this shape: NEED: <the question> | WHY: <why it matters to this goal> | WHERE: <where the answer likely lives>. At most 3 items. A question only Brian can answer is NOT a research need - it belongs in FOR BRIAN. "none" if nothing is missing.
FOR BRIAN: Only what the operator himself must decide or supply - the residue no research and no worker can settle. At most 30 words. "none" if there is none.

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


# ---------------------------------------------------------------- context

def _trim(text, max_chars=350):
    return sbos_common.trim_fact_whole(str(text or ""), max_chars)


def build_context(cur, slug):
    """Assemble one goal's context packet (<= CONTEXT_BUDGET_CHARS)
    from its live record. Every line is a fact from a store; long
    free-text fields are trimmed whole-sentence by trim_fact_whole,
    never cut mid-thought."""
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


# ---------------------------------------------------------------- parsing

def parse_plan(text):
    """Split Einstein's reply into the six contract sections.
    Tolerant: a missing section comes back empty; the raw text is
    always preserved by the caller. Returns dict with keys
    verified, claimed, blockers, plan_steps (list), research
    (list of {question, why, where}), for_brian."""
    out = {"verified": "", "claimed": "", "blockers": "",
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
        r"(VERIFIED STATE|CLAIMED vs VERIFIED|BLOCKERS|PLAN|"
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

def dispatch_look(cur, slug, dry_run=False):
    """Build the context packet for one goal and put it on the bus
    for Einstein. Returns (bus_event_id_or_None, probe_id). The
    einstein_passes insert runs on the caller's transaction; the bus
    insert commits on its own connection (the planner_rotation
    dispatch convention), so a crash between the two leaves the
    pass undispatched-marked and a retry re-sends with the same
    deterministic probe_id."""
    context = build_context(cur, slug)
    prompt = build_prompt(context)
    probe_id = (f"einstein-look-{slug}-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%d')}")
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


def run(limit, dry_run=False, slugs=None):
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
            try:
                cur.execute("BEGIN")
                eid, _probe = dispatch_look(cur, slug, dry_run=dry_run)
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
    cur.execute(
        "UPDATE atlas.nodes SET readme_md = %s, summary = %s "
        "WHERE node_key = %s",
        [header + text,
         (f"Einstein plan {datetime.now(timezone.utc).date()}: "
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
    a = ap.parse_args()
    if a.selftest:
        return selftest()
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
                 slugs=[a.slug] if a.slug else None)
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
