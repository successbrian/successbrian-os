#!/usr/bin/env python3
"""agent_board.py — AGENT COMMONS: the shared work board of SuccessBrian OS.

Brian's order (2026-11-11, Intel Bridge capture #1398): "build this as an
official successbrian os feature — where the user can tie in their own
agent (such as a muse agent, grok bot, dots, google aqua or even other
ecosystem agents) and these agents all share what they are currently
working on... like a common 'to do' list..."

This module is the ONE interface to the Commons (Brian's law: shared
functions are written once, in SuccessBrian OS, in a neat place). It is
deliberately vendor-neutral: the v1 tie-in protocol assumes nothing about
an agent's platform beyond the ability to run shell commands or SQL
against the operator's SBOS store. A Muse agent, a Grok bot, a Dots or
Google Aqua agent, or another ecosystem agent ties in the same way:

  1. register  — the operator (or the agent, once) registers the agent
                 under the operator's key with a display name and its
                 kind/source ('muse', 'grok', 'dots', 'google-aqua',
                 'ecosystem', ...). Idempotent.
  2. heartbeat — the agent publishes its presence + current focus on a
                 cadence; heartbeat also refreshes its claim leases.
  3. work      — post items to the common board, claim them (atomic,
                 leased — a live claim cannot be double-claimed), log
                 progress and attempts, complete them.

FLAGS — issues are first-class Commons objects (Brian's refinement,
2026-11-11, capture #1399): "if altair flags that such and such has an
issue — i want everyone to see that on their next heartbeat and together
the entire team figures out how to fix it." Any agent may raise a flag
(a work item of kind='issue'). Flags are NOT private per-agent findings:
list_board returns open flags FIRST, as their own section, before
presence and to-dos. THE PROTOCOL for every tied-in agent's cycle is:

    heartbeat -> read open flags -> work

One agent may claim LEAD on an issue, but team-solving is the design:
any registered agent can attach investigation notes and fix attempts to
the issue's shared log (agent_work_progress), and attempts are counted
on the issue itself. An issue sits in 'researching' until solved. The
operator is escalated to only under Brian's ask-gate: 5 logged TEAM
attempts on the issue AND the team's own ideas drying up — the board
read surfaces the attempt count and an ask_gate marker so every agent
can see when the gate is reached.

Raising a flag also starts a DeepSeek REAP 150B deep-investigation on
the live gamma bus (one per issue; it joins the reap queue as an
ordinary citizen and never preempts the road) — see "the 150B
investigator" in docs/agent-commons.md. Sized by the sender-owns-sizing
law: the report is a section chain (WHAT / EVIDENCE / TRIED / FIXES),
one 500-token pass per section; the issue carries the chain state and
the collector lands each section and dispatches the next.

Tables (DDL: tools/agent_commons.sql):
  successbrian_os.agent_presence     — who's here, working on what
  successbrian_os.agent_work_items   — the common to-do list
  successbrian_os.agent_work_progress— progress + attempt log per item
  successbrian_os.agent_board (view) — items + lifecycle flags
Plus the Agent Cycle Protocol family it extends: agent_registry,
agent_cycle_state (publish_state writes the notebook there).

Lifecycle law (Brian, 2026-10-29): statuses are open / claimed / doing /
researching / done. There is NO 'failed' status: a resisted item sits in
'researching', its attempts are logged, and flags rise at attempts>=5 or
14 days without progress. A flag is visibility, never a verdict.

Operator-agnostic: every row carries operator_key; the operator's own
agents are data, never schema.

Usage (CLI):
  python3 agent_board.py register --operator brian --agent my-agent \
      --name "My Agent" --kind muse [--node host] [--tier 0] [--notes ...]
  python3 agent_board.py publish-state --agent A [--operator OP] \
      (--state-json '{...}' | --state-file f.json) [--focus "..."] [--note "..."]
  python3 agent_board.py heartbeat --agent A [--operator OP] \
      [--focus "..."] [--note "..."] [--lease-min 90]
  python3 agent_board.py post --agent A --operator OP --title "..." [--detail "..."]
  python3 agent_board.py raise-flag --agent A --operator OP --title "..." [--detail "..."]
  python3 agent_board.py claim --agent A --item ID [--lease-min 90]
  python3 agent_board.py progress --agent A --item ID [--note "..."] \
      [--attempt] [--status doing|researching] [--lease-min 90]
  python3 agent_board.py complete --agent A --item ID [--note "..."]
  python3 agent_board.py release --agent A --item ID
  python3 agent_board.py board [--operator OP] [--json]
  python3 agent_board.py items [--operator OP] [--status S] [--agent A] [--json]
  python3 agent_board.py selftest
  python3 agent_board.py collect-investigations [--dry]

Exit codes: 0 ok; 1 refused / not permitted / not found; 2 usage or
store errors. Nothing in this module sends, buys, publishes, or contacts
anyone — it only reads and writes the operator's own board.
"""
import argparse
import json
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
from sbos_common import pg_exec, pg_one, pg_rows  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

SCHEMA = "successbrian_os"
DEFAULT_LEASE_MIN = 90
ACTIVE_ITEM_STATUSES = ("claimed", "doing", "researching")


# ------------------------------------------------------------------ helpers

def _operator_of(agent_key: str):
    return pg_one(
        f"select operator_key from {SCHEMA}.agent_registry where agent_key = %s",
        (agent_key,))


def _require_operator(agent_key: str, operator: str | None) -> str:
    op = operator or _operator_of(agent_key)
    if not op:
        raise ValueError(
            f"agent '{agent_key}' is not registered and no --operator given; "
            "register it first")
    return op


def _presence_upsert(agent_key: str, operator: str,
                     focus: str | None, note: str | None) -> None:
    pg_exec(
        f"""insert into {SCHEMA}.agent_presence
              (agent_key, operator_key, current_focus, status_note, updated_at)
            values (%s, %s, %s, %s, now())
            on conflict (agent_key) do update set
              operator_key  = excluded.operator_key,
              current_focus = coalesce(excluded.current_focus,
                                       {SCHEMA}.agent_presence.current_focus),
              status_note   = coalesce(excluded.status_note,
                                       {SCHEMA}.agent_presence.status_note),
              updated_at    = now()""",
        (agent_key, operator, focus, note))


# ------------------------------------------------------------------ verbs

def register(operator: str, agent_key: str, display_name: str,
             kind: str = "ecosystem", node: str | None = None,
             tier: int | None = None, cadence: str | None = None,
             notes: str | None = None) -> dict:
    """Idempotently register an agent under an operator. Re-registering
    updates identity fields; fields left unset keep their stored values
    (a fresh agent with no tier starts at tier 0 — sense only)."""
    existing = pg_one(
        f"""select operator_key, role, display_name, node, cadence,
                   authority_tier, notes
              from {SCHEMA}.agent_registry where agent_key = %s""",
        (agent_key,))
    if existing:
        _, e_role, e_name, e_node, e_cad, e_tier, e_notes = existing
        role = kind or e_role
        name = display_name or e_name
        node = node if node is not None else e_node
        cadence = cadence if cadence is not None else e_cad
        tier = tier if tier is not None else e_tier
        notes = notes if notes is not None else e_notes
    else:
        role, name = kind, display_name
        tier = tier if tier is not None else 0
    if node is None:
        node = "unspecified"  # agent_registry.node is NOT NULL
    pg_exec(
        f"""insert into {SCHEMA}.agent_registry
              (agent_key, operator_key, role, display_name, node, cadence,
               authority_tier, enabled, notes)
            values (%s, %s, %s, %s, %s, %s, %s, true, %s)
            on conflict (agent_key) do update set
              operator_key   = excluded.operator_key,
              role           = excluded.role,
              display_name   = excluded.display_name,
              node           = excluded.node,
              cadence        = excluded.cadence,
              authority_tier = excluded.authority_tier,
              enabled        = true,
              notes          = excluded.notes""",
        (agent_key, operator, role, name, node, cadence, tier, notes))
    _presence_upsert(agent_key, operator, None, None)
    return {"agent_key": agent_key, "operator": operator,
            "display_name": name, "kind": role, "tier": tier}


def publish_state(agent_key: str, state: dict,
                  current_focus: str | None = None,
                  status_note: str | None = None,
                  operator: str | None = None) -> dict:
    """Publish the agent's notebook (agent_cycle_state) and, when given,
    its current focus (agent_presence). This is how other agents see what
    this agent knows and what it is working on."""
    op = _require_operator(agent_key, operator)
    pg_exec(
        f"""insert into {SCHEMA}.agent_cycle_state (agent_key, state, updated_at)
            values (%s, %s, now())
            on conflict (agent_key) do update set
              state = excluded.state, updated_at = now()""",
        (agent_key, Json(state)))
    if current_focus is not None or status_note is not None:
        _presence_upsert(agent_key, op, current_focus, status_note)
    return {"agent_key": agent_key, "operator": op, "published": True}


def heartbeat(agent_key: str, current_focus: str | None = None,
              status_note: str | None = None,
              operator: str | None = None,
              lease_min: int = DEFAULT_LEASE_MIN) -> dict:
    """Presence heartbeat: 'I am here, this is my focus.' Also refreshes
    the claim leases on every item this agent currently holds, so an
    actively-heartbeating agent never loses work mid-flight."""
    op = _require_operator(agent_key, operator)
    _presence_upsert(agent_key, op, current_focus, status_note)
    refreshed = pg_exec(
        f"""update {SCHEMA}.agent_work_items
               set claim_lease_until = now() + make_interval(mins => %s),
                   updated_at = now()
             where claimed_by_agent = %s
               and status in ('claimed','doing','researching')""",
        (lease_min, agent_key))
    return {"agent_key": agent_key, "operator": op,
            "leases_refreshed": refreshed}


def post_item(operator: str, agent_key: str, title: str,
              detail: str | None = None, kind: str = "task") -> dict:
    """Post a work item to the common board. A task starts 'open'; an
    issue (a flag) starts 'researching' — it is under team investigation
    from the moment it is raised, per the lifecycle law."""
    if kind not in ("task", "issue"):
        raise ValueError("kind must be 'task' or 'issue'")
    _require_operator(agent_key, operator)
    status = "researching" if kind == "issue" else "open"
    row = pg_one(
        f"""insert into {SCHEMA}.agent_work_items
              (operator_key, title, detail, status, kind, created_by_agent,
               last_progress_at)
            values (%s, %s, %s, %s, %s, %s, now())
            returning id""",
        (operator, title, detail, status, kind, agent_key))
    return {"item_id": row, "status": status, "kind": kind,
            "created_by_agent": agent_key}


def raise_flag(operator: str, agent_key: str, title: str,
               detail: str | None = None, investigate=True) -> dict:
    """Raise a FLAG: a board-visible issue every agent sees on its next
    heartbeat (list_board returns open flags first). The raising agent
    is recorded as the item's creator; the subject is the title, the
    detail carries what is known. Status 'researching' until solved.

    Raising a flag also starts the 150B investigator (Brian, capture
    #1400): investigate=True enqueues a DeepSeek REAP deep-investigation
    on the live gamma bus; 'dry' records the request without touching
    the road (operations/testing); False skips the investigation."""
    out = post_item(operator, agent_key, title, detail, kind="issue")
    if investigate:
        inv = _start_investigation(out["item_id"], agent_key,
                                   dry=(investigate == "dry"))
        if inv:
            out.update(inv)
    return out


# ------------------------------------------------- the 150B investigator
# Brian's refinement 2 (2026-11-11, capture #1400): "whoever flags the
# issue starts a DeepSeek REAP 150B worker on it to do a deep
# investigate." The live gamma intake is the Postgres bus: producers
# insert bus.events rows (event_type 'reap_infer', target 'gamma') and
# gamma's bus agent claims them in queue order — the same contract the
# clerk queue-keeper uses (source 'spencer', priority 5, 48 jobs done
# 2026-11-11). An investigation is an ordinary citizen of that queue:
# same event type, same priority class. It JOINS the reap queue under
# the road's existing rules and never preempts paying REAP work — feed
# the road first. SIZING LAW (Brian, 2026-11-13: "let's not oversize
# jobs, even for reap 150b" — 1,600-token REAP passes completed 0/10,
# 500-token passes 16/16): an investigation is a SECTION CHAIN, not one
# 2,000-token run. The report is four sections — WHAT / EVIDENCE /
# TRIED / FIXES — one 500-token REAP pass per section, in order. The
# issue carries the chain state: investigation_job_ref points at the
# live section's bus event, investigation_result_note accumulates the
# landed sections ("SECTION:" headers), and missing sections are read
# off the note. Dispatch sends the FIRST section only; the collector
# (collect_investigation_sections, BUILD_QUEUE B1b) lands each finished
# section onto the note and dispatches the next one until the report is
# complete. Until the collector lands, the board reads the live
# section's status from bus.events.

INVESTIGATION_PROBE_ID = "agent-commons-investigation"
INVESTIGATION_PRIORITY = 5
REAP_MAX_TOKENS = 500
# REAP contract (verified live 2026-11-23, probe events 1722/1728;
# einstein_planner.py): thinking MUST be False — with thinking=true
# gamma returns a fragment of the model's reasoning, not the answer.
# Probe item 183 (events 2443/2450/2461/2467) proved it again: all
# four sections came back as reasoning preamble narrating the
# section instruction. The runner is clean; the flag was the defect.
INVESTIGATION_THINKING = False
INVESTIGATION_SECTIONS = ("WHAT", "EVIDENCE", "TRIED", "FIXES")
INVESTIGATION_SECTION_TASKS = {
    "WHAT": "what is actually wrong — the fault, in concrete terms",
    "EVIDENCE": "what evidence supports it — what was observed, where",
    "TRIED": "what has likely already been tried, and what it showed",
    "FIXES": "the most promising fixes, in order, each with its first step",
}


def _section_brief(item_id: int, title: str, detail: str | None,
                   operator: str, raised_by: str, section: str,
                   prior: str | None = None) -> str:
    """One section of the investigation brief. The REAP seat's run is
    time-boxed to REAP_MAX_TOKENS, so the prompt asks for ONLY the named
    section — nothing else, no preamble — 3-5 dense sentences."""
    focus = pg_one(
        f"select current_focus from {SCHEMA}.agent_presence "
        f"where agent_key = %s", (raised_by,))
    lines = [
        "DEEP INVESTIGATION — Agent Commons flag (SuccessBrian OS).",
        f"Issue (commons item #{item_id}, operator {operator}): {title}",
    ]
    if detail:
        lines.append(f"Detail from the flagging agent: {detail}")
    lines.append(f"Raised by: {raised_by}"
                 + (f" (their current focus: {focus})" if focus else ""))
    if prior:
        lines.append("SECTIONS SO FAR:")
        lines.append(prior)
    lines.append(
        f"Write ONLY the {section} section (start with '{section}:'). "
        f"{INVESTIGATION_SECTION_TASKS[section]}. 3-5 dense sentences, "
        "concrete, no filler. Your run is time-boxed to "
        f"{REAP_MAX_TOKENS} tokens — do not attempt any other section.")
    return "\n".join(lines)


def missing_investigation_sections(note: str | None) -> list[str]:
    """Sections the investigation still owes, read off the accumulated
    note (same shape as overdue_relevance.missing_sections)."""
    have = (note or "").upper()
    return [s for s in INVESTIGATION_SECTIONS if (s + ":") not in have]


def _dispatch_investigation_section(item_id: int, title: str,
                                    detail: str | None, op: str,
                                    creator: str, section: str,
                                    prior: str | None = None,
                                    note: str | None = None,
                                    dry: bool = False) -> dict:
    """Dispatch ONE section pass of an investigation on the live gamma
    bus at REAP_MAX_TOKENS (or record it dry). The caller owns the chain
    state: it lands finished sections on the note and calls this for the
    next missing one. When `note` is given, the accumulated note is saved
    with the dispatch, so a landed section and its follow-up dispatch are
    never separated."""
    if dry:
        ref = f"dry-run:item-{item_id}:{section.lower()}"
        pg_exec(
            f"""update {SCHEMA}.agent_work_items
                   set investigation_status = 'requested',
                       investigation_requested_at = now(),
                       investigation_requested_by = %s,
                       investigation_job_ref = %s,
                       investigation_result_note = coalesce(
                           %s, investigation_result_note),
                       updated_at = now()
                 where id = %s""",
            (creator, ref, note, item_id))
        return {"item_id": item_id, "investigation_status": "requested",
                "job_ref": ref, "started": True,
                "section": section,
                "sections_total": len(INVESTIGATION_SECTIONS)}
    brief = _section_brief(item_id, title, detail, op, creator, section,
                           prior=prior)
    payload = {"prompt": brief, "probe_id": INVESTIGATION_PROBE_ID,
               "commons_item_id": item_id, "section": section,
               "thinking": INVESTIGATION_THINKING, "max_tokens": REAP_MAX_TOKENS}
    ev = pg_one(
        "insert into bus.events (event_type, source, target, priority, payload) "
        "values ('reap_infer', %s, 'gamma', %s, %s) returning id",
        (creator, INVESTIGATION_PRIORITY, Json(payload)))
    ref = f"bus.events:{ev}"
    pg_exec(
        f"""update {SCHEMA}.agent_work_items
               set investigation_status = 'queued',
                   investigation_requested_at = now(),
                   investigation_requested_by = %s,
                   investigation_job_ref = %s,
                   investigation_result_note = coalesce(
                       %s, investigation_result_note),
                   updated_at = now()
             where id = %s""",
        (creator, ref, note, item_id))
    return {"item_id": item_id, "investigation_status": "queued",
            "job_ref": ref, "started": True,
            "section": section, "sections_total": len(INVESTIGATION_SECTIONS)}


def _start_investigation(item_id: int, by_agent: str, dry: bool = False,
                         force: bool = False) -> dict | None:
    """Start the REAP 150B investigation for an issue. ONE live
    investigation per issue: while one is queued/running, the existing
    job is returned unchanged (started=False) — notes, touches, and
    re-flags never spawn duplicates. Section-chained (B1a): only the
    FIRST section is dispatched here, at REAP_MAX_TOKENS, via
    _dispatch_investigation_section; the collector (B1b) lands it and
    dispatches the next missing section."""
    row = pg_one(
        f"""select title, detail, operator_key, created_by_agent,
                   investigation_status, investigation_job_ref
              from {SCHEMA}.agent_work_items
             where id = %s and kind = 'issue'""",
        (item_id,))
    if row is None:
        return None
    title, detail, op, creator, cur_status, cur_ref = row
    if cur_status in ("queued", "running") and cur_ref and not force:
        return {"item_id": item_id, "investigation_status": cur_status,
                "job_ref": cur_ref, "started": False}
    if dry and cur_status == "requested" and cur_ref and not force:
        return {"item_id": item_id, "investigation_status": "requested",
                "job_ref": cur_ref, "started": False}
    return _dispatch_investigation_section(
        item_id, title, detail, op, creator, INVESTIGATION_SECTIONS[0],
        dry=dry)


def _parse_reap_body(body):
    """Gamma's outbox body is a JSON envelope; the REAP text lives at
    result.text. Same envelope as overdue_relevance.parse_reap_body.
    Tolerates a pre-parsed dict. Returns None on anything unparseable."""
    if not body:
        return None
    try:
        data = body if isinstance(body, dict) else json.loads(body)
        text = (data.get("result") or {}).get("text")
        return text.strip() if text else None
    except Exception:
        return None


def _reset_investigation(item_id: int, agent_key: str, note: str) -> None:
    """Reset a stalled investigation so the issue can be re-investigated
    (raise-flag / reinvestigate): status back to 'none', live ref
    cleared, landed sections kept on the note, and the reason logged on
    the shared progress log so the team sees why the chain stopped."""
    pg_exec(
        f"""update {SCHEMA}.agent_work_items
               set investigation_status = 'none',
                   investigation_job_ref = null,
                   updated_at = now()
             where id = %s""",
        (item_id,))
    _log_progress(item_id, agent_key, note, False)


def collect_investigation_sections(dry: bool = False) -> dict:
    """Collector/advancer (BUILD_QUEUE B1b): land each finished
    investigation section from gamma's outbox onto the issue's
    investigation_result_note, dispatch the next missing section, and
    mark the investigation 'done' at 4/4. Mirrors the
    overdue_relevance section-chain collector: a finished bus event is
    followed by its outbox inference_result (subject 'gamma: event <id>
    done (reap_infer)'); a failed/dead-letter/missing event or an
    unparseable result resets the investigation (status 'none', ref
    cleared, reason on the shared log) so the team can re-trigger it; a
    live event with no outbox row yet is left alone. dry=True rehearses
    only: it reports what would land/dispatch/reset and writes nothing."""
    rows = pg_rows(
        f"""select id, title, detail, operator_key, created_by_agent,
                   investigation_status, investigation_job_ref,
                   investigation_result_note, investigation_requested_by
              from {SCHEMA}.agent_work_items
             where kind = 'issue'
               and investigation_status in ('requested', 'queued', 'running')
             order by id""")
    # 'requested' rows are dry-run records only (live dispatch sets
    # 'queued'); they are picked up here so the dry-ref skip below is
    # explicit and counted, never invisible.
    out = {"landed": 0, "dispatched": 0, "completed": 0, "reset": 0,
           "skipped_dry": 0, "still_running": 0, "waiting_outbox": 0}
    for (item_id, title, detail, op, creator, cur_status, cur_ref,
         note, requested_by) in rows:
        who = requested_by or creator or "spencer"
        if not cur_ref:
            # Chain-open recovery: a section was landed but the next
            # dispatch never recorded (crash / dry run). Advance from
            # the note alone.
            missing = missing_investigation_sections(note)
            if not missing:
                if not dry:
                    pg_exec(
                        f"""update {SCHEMA}.agent_work_items
                               set investigation_status = 'done',
                                   updated_at = now()
                             where id = %s""", (item_id,))
                out["completed"] += 1
                print(f"commons item #{item_id}: note already complete — "
                      f"marked done")
                continue
            if dry:
                out["dispatched"] += 1
                print(f"commons item #{item_id}: would dispatch "
                      f"{missing[0]} (chain-open)")
                continue
            _dispatch_investigation_section(
                item_id, title, detail, op, creator, missing[0],
                prior=note)
            out["dispatched"] += 1
            print(f"commons item #{item_id}: chain-open — dispatched "
                  f"{missing[0]}")
            continue
        if cur_ref.startswith("dry-run:"):
            out["skipped_dry"] += 1
            continue
        try:
            eid = int(cur_ref.split(":", 1)[1])
        except (ValueError, IndexError):
            if not dry:
                _reset_investigation(
                    item_id, who,
                    "150B investigation: job ref unreadable "
                    f"({cur_ref}) — investigation reset; re-flag or "
                    "reinvestigate to retry.")
            out["reset"] += 1
            print(f"commons item #{item_id}: unreadable job ref "
                  f"{cur_ref} — reset")
            continue
        estatus = pg_one("select status from bus.events where id = %s",
                         (eid,))
        if estatus is None or estatus in ("failed", "dead_letter"):
            if not dry:
                _reset_investigation(
                    item_id, who,
                    "150B investigation: REAP section "
                    + (f"bus event #{eid} no longer on the road"
                       if estatus is None
                       else f"failed on gamma (bus event #{eid}: "
                            f"{estatus})")
                    + " — investigation reset; re-flag or reinvestigate "
                      "to retry.")
            out["reset"] += 1
            print(f"commons item #{item_id}: bus event #{eid} "
                  f"{estatus} — reset")
            continue
        if estatus != "done":
            out["still_running"] += 1
            continue
        section = pg_one(
            "select payload->>'section' from bus.events where id = %s",
            (eid,))
        body = pg_one(
            "select body from successbrian_os.outbox "
            "where source_agent = 'gamma' "
            "and message_type = 'inference_result' and subject = %s",
            (f"gamma: event {eid} done (reap_infer)",))
        if not body:
            out["waiting_outbox"] += 1
            continue
        sec_text = _parse_reap_body(body)
        if not sec_text:
            if not dry:
                _reset_investigation(
                    item_id, who,
                    "150B investigation: gamma's outbox result for bus "
                    f"event #{eid} is unparseable — investigation reset; "
                    "re-flag or reinvestigate to retry.")
            out["reset"] += 1
            print(f"commons item #{item_id}: outbox result for event "
                  f"#{eid} unparseable — reset")
            continue
        missing_before = missing_investigation_sections(note)
        section = section or (missing_before[0] if missing_before else None)
        if section is None:
            # Note already complete; the finished event adds nothing.
            if not dry:
                pg_exec(
                    f"""update {SCHEMA}.agent_work_items
                           set investigation_status = 'done',
                               investigation_job_ref = null,
                               updated_at = now()
                         where id = %s""", (item_id,))
            out["completed"] += 1
            print(f"commons item #{item_id}: event #{eid} finished, "
                  f"note already complete — marked done")
            continue
        sec = sec_text.strip()
        if not sec.upper().startswith(section + ":"):
            sec = f"{section}: {sec}"
        new_note = ((note or "") + "\n\n" + sec).strip()
        missing = missing_investigation_sections(new_note)
        if not missing:
            if not dry:
                pg_exec(
                    f"""update {SCHEMA}.agent_work_items
                           set investigation_result_note = %s,
                               investigation_status = 'done',
                               investigation_job_ref = null,
                               updated_at = now()
                         where id = %s""", (new_note, item_id))
                _log_progress(
                    item_id, who,
                    "150B investigation complete — WHAT / EVIDENCE / "
                    "TRIED / FIXES all landed on the note.", False)
            out["landed"] += 1
            out["completed"] += 1
            print(f"commons item #{item_id}: REAP section {section} "
                  f"landed — investigation complete")
            continue
        if dry:
            out["landed"] += 1
            out["dispatched"] += 1
            print(f"commons item #{item_id}: would land {section} and "
                  f"dispatch {missing[0]} next")
            continue
        _dispatch_investigation_section(
            item_id, title, detail, op, creator, missing[0],
            prior=new_note, note=new_note)
        out["landed"] += 1
        out["dispatched"] += 1
        print(f"commons item #{item_id}: REAP section {section} landed "
              f"— dispatched {missing[0]} next")
    return out


def reinvestigate(agent_key: str, item_id: int,
                  dry: bool = False) -> dict | None:
    """Explicitly start a FRESH investigation on an issue — the only way
    to get a second one. Refused (current state returned, started=False)
    while the previous job is still live on the road: one per issue."""
    row = pg_one(
        f"""select investigation_status, investigation_job_ref
              from {SCHEMA}.agent_work_items
             where id = %s and kind = 'issue'""",
        (item_id,))
    if row is None:
        return None
    status, ref = row
    if ref and ref.startswith("bus.events:"):
        try:
            live = pg_one("select status from bus.events where id = %s",
                          (int(ref.split(":", 1)[1]),))
        except (ValueError, IndexError):
            live = None
        if live in ("pending", "claimed"):
            return {"item_id": item_id, "investigation_status": status,
                    "job_ref": ref, "started": False}
    if status == "requested" and ref and ref.startswith("dry-run"):
        return {"item_id": item_id, "investigation_status": status,
                "job_ref": ref, "started": False}
    return _start_investigation(item_id, agent_key, dry=dry, force=True)


def claim_item(agent_key: str, item_id: int,
               lease_min: int = DEFAULT_LEASE_MIN) -> dict | None:
    """Atomically claim an item. Succeeds only when the item is open,
    unclaimed (taking LEAD on a flag), already held by this same agent
    (lease renewal), or its previous claim's lease has expired. Returns
    the item row, or None when the claim is refused — a live claim can
    never be double-claimed."""
    rows = pg_rows(
        f"""update {SCHEMA}.agent_work_items
               set claimed_by_agent = %s,
                   claimed_at = case
                     when claimed_by_agent is distinct from %s then now()
                     else claimed_at end,
                   claim_lease_until = now() + make_interval(mins => %s),
                   status = case when status = 'open' then 'claimed'
                                 else status end,
                   last_progress_at = now(),
                   updated_at = now()
             where id = %s
               and status in ('open','claimed','doing','researching')
               and (claimed_by_agent is null
                    or claimed_by_agent = %s
                    or claim_lease_until < now())
             returning id, status, claimed_by_agent, claim_lease_until""",
        (agent_key, agent_key, lease_min, item_id, agent_key))
    if not rows:
        return None
    r = rows[0]
    return {"item_id": r[0], "status": r[1], "claimed_by_agent": r[2],
            "claim_lease_until": str(r[3])}


def _log_progress(item_id: int, agent_key: str,
                  note: str | None, is_attempt: bool) -> None:
    if note is not None or is_attempt:
        pg_exec(
            f"""insert into {SCHEMA}.agent_work_progress
                  (item_id, agent_key, note, is_attempt)
                values (%s, %s, %s, %s)""",
            (item_id, agent_key, note, is_attempt))


def progress_item(agent_key: str, item_id: int, note: str | None = None,
                  attempt: bool = False, status: str | None = None,
                  lease_min: int = DEFAULT_LEASE_MIN) -> dict | None:
    """Log progress on an item. Refreshes last_progress_at; --attempt
    logs one tried way and bumps the item's attempt counter (the board
    flags at 5 — visibility, not a verdict).

    TASKS are progressed only by the agent that holds the claim (its
    lease refreshes too). ISSUES are team property (Brian, capture
    #1399): ANY registered agent may attach investigation notes and fix
    attempts to the shared log, whether or not it holds the lead claim —
    the whole team figures it out together."""
    if status is not None and status not in ACTIVE_ITEM_STATUSES:
        raise ValueError(f"progress status must be one of {ACTIVE_ITEM_STATUSES}")
    meta = pg_one(
        f"select kind, claimed_by_agent from {SCHEMA}.agent_work_items "
        f"where id = %s and status in ('claimed','doing','researching','open')",
        (item_id,))
    if meta is None:
        return None
    kind, claimant = meta
    if kind == "issue":
        if _operator_of(agent_key) is None:
            return None  # unregistered agents cannot work the board
        is_lead = claimant == agent_key
        rows = pg_rows(
            f"""update {SCHEMA}.agent_work_items
                   set last_progress_at = now(),
                       updated_at = now(),
                       claim_lease_until = case
                         when %s then now() + make_interval(mins => %s)
                         else claim_lease_until end,
                       attempts = attempts + %s,
                       status = coalesce(%s, status)
                 where id = %s
                   and status in ('claimed','doing','researching','open')
                 returning id, status, attempts""",
            (is_lead, lease_min, 1 if attempt else 0, status, item_id))
    else:
        rows = pg_rows(
            f"""update {SCHEMA}.agent_work_items
                   set last_progress_at = now(),
                       updated_at = now(),
                       claim_lease_until = now() + make_interval(mins => %s),
                       attempts = attempts + %s,
                       status = coalesce(%s, status)
                 where id = %s and claimed_by_agent = %s
                   and status in ('claimed','doing','researching')
                 returning id, status, attempts""",
            (lease_min, 1 if attempt else 0, status, item_id, agent_key))
    if not rows:
        return None
    _log_progress(item_id, agent_key, note, attempt)
    r = rows[0]
    return {"item_id": r[0], "status": r[1], "attempts": r[2]}


def complete_item(agent_key: str, item_id: int,
                  note: str | None = None) -> dict | None:
    """Mark an item done. The claiming agent completes its own work; the
    creating agent may also close an item it posted. Returns None when
    the item is missing, already done, or held by someone else."""
    rows = pg_rows(
        f"""update {SCHEMA}.agent_work_items
               set status = 'done',
                   claim_lease_until = null,
                   last_progress_at = now(),
                   updated_at = now()
             where id = %s and status <> 'done'
               and (claimed_by_agent = %s or created_by_agent = %s)
             returning id, status""",
        (item_id, agent_key, agent_key))
    if not rows:
        return None
    _log_progress(item_id, agent_key, note, False)
    return {"item_id": rows[0][0], "status": "done"}


def release_item(agent_key: str, item_id: int) -> dict | None:
    """Release a claim: the item returns to 'open' for any agent."""
    rows = pg_rows(
        f"""update {SCHEMA}.agent_work_items
               set status = 'open', claimed_by_agent = null,
                   claimed_at = null, claim_lease_until = null,
                   updated_at = now()
             where id = %s and claimed_by_agent = %s
               and status in ('claimed','doing','researching')
             returning id, status""",
        (item_id, agent_key))
    if not rows:
        return None
    return {"item_id": rows[0][0], "status": "open"}


def list_items(operator: str | None = None, status: str | None = None,
               agent: str | None = None, kind: str | None = None) -> list[dict]:
    """Items from the board view (with lifecycle flags), filterable."""
    sql = (f"select id, operator_key, title, status, kind, created_by_agent, "
           f"claimed_by_agent, attempts, flag_reason, "
           f"to_char(created_at, 'YYYY-MM-DD HH24:MI') as created, "
           f"to_char(last_progress_at, 'YYYY-MM-DD HH24:MI') as last_progress "
           f"from {SCHEMA}.agent_board where 1 = 1")
    params: list = []
    if operator:
        sql += " and operator_key = %s"
        params.append(operator)
    if status:
        sql += " and status = %s"
        params.append(status)
    if kind:
        sql += " and kind = %s"
        params.append(kind)
    if agent:
        sql += " and (claimed_by_agent = %s or created_by_agent = %s)"
        params += [agent, agent]
    sql += " order by id"
    cols = ("id", "operator", "title", "status", "kind", "created_by",
            "claimed_by", "attempts", "flag", "created", "last_progress")
    return [dict(zip(cols, r)) for r in pg_rows(sql, tuple(params))]


def list_flags(operator: str | None = None) -> list[dict]:
    """OPEN FLAGS: issues (kind='issue') not yet solved, most-attempted
    first. Every agent reads these on its heartbeat. ask_gate is True
    once the team has logged 5 attempts — Brian's escalation gate (the
    operator is asked only at 5 logged team attempts AND ideas drying;
    the count is what the board guarantees)."""
    sql = (f"select id, operator_key, title, detail, status, created_by_agent, "
           f"claimed_by_agent, attempts, flag_reason, "
           f"investigation_status, investigation_job_ref, "
           f"investigation_requested_by, "
           f"to_char(created_at, 'YYYY-MM-DD HH24:MI') as raised_at, "
           f"to_char(last_progress_at, 'YYYY-MM-DD HH24:MI') as last_progress "
           f"from {SCHEMA}.agent_board "
           f"where kind = 'issue' and status <> 'done'")
    params: list = []
    if operator:
        sql += " and operator_key = %s"
        params.append(operator)
    sql += " order by attempts desc, id"
    cols = ("id", "operator", "title", "detail", "status", "raised_by",
            "lead", "attempts", "flag", "investigation_status",
            "investigation_job_ref", "investigation_requested_by",
            "raised_at", "last_progress")
    out = []
    bus_ids = []
    for r in pg_rows(sql, tuple(params)):
        d = dict(zip(cols, r))
        d["ask_gate"] = (d["attempts"] or 0) >= 5
        ref = d.get("investigation_job_ref") or ""
        if ref.startswith("bus.events:"):
            try:
                bus_ids.append(int(ref.split(":", 1)[1]))
            except (ValueError, IndexError):
                pass
        out.append(d)
    if bus_ids:
        live = {r[0]: r[1] for r in pg_rows(
            "select id, status from bus.events where id = any(%s)",
            (bus_ids,))}
        for d in out:
            ref = d.get("investigation_job_ref") or ""
            if ref.startswith("bus.events:"):
                try:
                    d["investigation_job_status"] = live.get(
                        int(ref.split(":", 1)[1]))
                except (ValueError, IndexError):
                    d["investigation_job_status"] = None
    return out


def list_board(operator: str | None = None) -> dict:
    """The whole commons at a glance. OPEN FLAGS COME FIRST (Brian,
    capture #1399): reading flags is step one of every heartbeat —
    heartbeat -> read flags -> work. Then every registered agent with
    its presence/current focus and held work, then claimable tasks."""
    sql = (f"select r.agent_key, r.display_name, r.role, r.enabled, "
           f"p.current_focus, p.status_note, "
           f"to_char(p.updated_at, 'YYYY-MM-DD HH24:MI') as presence_at "
           f"from {SCHEMA}.agent_registry r "
           f"left join {SCHEMA}.agent_presence p on p.agent_key = r.agent_key")
    params: list = []
    if operator:
        sql += " where r.operator_key = %s"
        params.append(operator)
    sql += " order by r.agent_key"
    agents = []
    for key, name, role, enabled, focus, note, at in pg_rows(sql, tuple(params)):
        held = pg_rows(
            f"""select id, title, status, attempts, flag_reason
                  from {SCHEMA}.agent_board
                 where claimed_by_agent = %s
                   and status in ('claimed','doing','researching')
                 order by id""",
            (key,))
        agents.append({
            "agent_key": key, "display_name": name, "kind": role,
            "enabled": enabled, "current_focus": focus,
            "status_note": note, "presence_at": at,
            "holding": [{"id": h[0], "title": h[1], "status": h[2],
                         "attempts": h[3], "flag": h[4]} for h in held],
        })
    open_items = list_items(operator=operator, status="open", kind="task")
    return {"operator": operator, "flags": list_flags(operator=operator),
            "agents": agents, "open_items": open_items}


# ------------------------------------------------------------------ selftest

def selftest() -> int:
    """Full lifecycle on disposable rows under operator 'selftest':
    register -> publish -> heartbeat -> post -> claim -> double-claim
    refusal -> progress (+attempt) -> complete; then the FLAG path:
    raise (dry investigation) -> flags-first board read -> team attempts
    by a second agent -> lead claim -> resolve -> flag leaves the board;
    then complete cleanup. Prints SELFTEST PASS only if all proves."""
    op = "selftest"
    a, b = "commons-selftest-a", "commons-selftest-b"
    item_id = None
    steps: list[str] = []

    def cleanup() -> None:
        for key in (a, b):
            pg_exec(f"delete from {SCHEMA}.agent_work_items "
                    f"where created_by_agent = %s or claimed_by_agent = %s",
                    (key, key))
            pg_exec(f"delete from {SCHEMA}.agent_presence where agent_key = %s", (key,))
            pg_exec(f"delete from {SCHEMA}.agent_cycle_state where agent_key = %s", (key,))
            pg_exec(f"delete from {SCHEMA}.agent_registry where agent_key = %s", (key,))

    cleanup()  # clear any residue from an interrupted earlier run
    try:
        r = register(op, a, "Commons Selftest A", kind="selftest")
        assert r["agent_key"] == a, "register A"
        register(op, b, "Commons Selftest B", kind="selftest")
        steps.append("register (idempotent upsert, presence row created)")

        publish_state(a, {"notebook": "selftest", "cycles": 1},
                      current_focus="running the commons selftest")
        got = pg_one(f"select state->>'notebook' from {SCHEMA}.agent_cycle_state "
                     f"where agent_key = %s", (a,))
        assert got == "selftest", "publish_state notebook round-trip"
        steps.append("publish_state (notebook + focus)")

        hb = heartbeat(a, current_focus="claiming a test item")
        assert hb["leases_refreshed"] == 0, "heartbeat before any claim"
        focus = pg_one(f"select current_focus from {SCHEMA}.agent_presence "
                       f"where agent_key = %s", (a,))
        assert focus == "claiming a test item", "heartbeat focus update"
        steps.append("heartbeat (presence + focus)")

        posted = post_item(op, a, "SELFTEST disposable item — delete after proof")
        item_id = posted["item_id"]
        assert posted["status"] == "open", "post_item opens the item"
        steps.append(f"post_item (id {item_id}, open)")

        c1 = claim_item(a, item_id)
        assert c1 and c1["claimed_by_agent"] == a, "first claim succeeds"
        steps.append("claim_item (atomic, leased)")

        c2 = claim_item(b, item_id)
        assert c2 is None, "double-claim by another agent must be refused"
        steps.append("double-claim REFUSED while lease lives")

        p = progress_item(a, item_id, note="first way tried",
                          attempt=True, status="researching")
        assert p and p["attempts"] == 1 and p["status"] == "researching", \
            "progress + attempt"
        steps.append("progress_item (attempt logged, counter=1)")

        done = complete_item(a, item_id, note="way found; closing")
        assert done and done["status"] == "done", "complete_item"
        st = pg_one(f"select status from {SCHEMA}.agent_work_items where id = %s",
                    (item_id,))
        assert st == "done", "item reads done on the board"
        steps.append("complete_item (done — a state that exists; 'failed' does not)")

        # ---- the flag path: team solving + the 150B investigator ----
        fl = raise_flag(op, a, "SELFTEST flag: frobnicate is misaligned",
                        detail="disposable selftest flag",
                        investigate="dry")
        issue_id = fl["item_id"]
        assert fl["kind"] == "issue" and fl["status"] == "researching", \
            "raise_flag opens a researching issue"
        assert fl["investigation_status"] == "requested" \
            and fl["job_ref"].startswith("dry-run") and fl["started"], \
            "investigation requested at raise time (dry — road untouched)"
        assert fl["section"] == "WHAT" and fl["sections_total"] == 4, \
            "section chain starts at WHAT of 4 (B1a sizing law)"
        assert fl["job_ref"] == f"dry-run:item-{issue_id}:what", \
            "dry ref names its section"
        no_bus = pg_one(
            "select count(*) from bus.events where payload->>'commons_item_id' = %s",
            (str(issue_id),))
        assert no_bus == 0, "dry investigation touches no bus event"
        assert missing_investigation_sections(None) == list(INVESTIGATION_SECTIONS), \
            "empty note owes all four sections"
        assert missing_investigation_sections("WHAT: x\n\nEVIDENCE: y") == ["TRIED", "FIXES"], \
            "landed sections drop out of the missing list"
        assert REAP_MAX_TOKENS == 500, "sizing law: 500-token cap"
        assert INVESTIGATION_THINKING is False, \
            "investigation dispatch sends thinking=false (REAP contract)"
        for sec in INVESTIGATION_SECTIONS:
            brief = _section_brief(issue_id, "t", "d", op, a, sec)
            assert f"Write ONLY the {sec} section" in brief, \
                f"section brief asks only for {sec}"
        steps.append("raise_flag (issue + investigation requested, dry)")

        board_b = list_board(operator=op)  # what agent B sees on heartbeat
        f0 = [f for f in board_b["flags"] if f["id"] == issue_id]
        assert len(f0) == 1 and f0[0]["raised_by"] == a \
            and f0[0]["investigation_status"] == "requested", \
            "flag visible FIRST in B's board read, investigation shown"
        steps.append("flags-first board read (B sees A's flag + investigation)")

        att_b = progress_item(b, issue_id,
                              note="B investigates from the shared log",
                              attempt=True)
        assert att_b and att_b["attempts"] == 1, \
            "non-lead team attempt on an issue must be allowed"
        ref_now = pg_one(
            f"select investigation_job_ref from {SCHEMA}.agent_work_items "
            f"where id = %s", (issue_id,))
        assert ref_now == fl["job_ref"], \
            "team notes/attempts never spawn a duplicate investigation"
        steps.append("team attempt by B (no lead claim needed, no dup job)")

        ri = reinvestigate(a, issue_id, dry=True)
        assert ri and ri["job_ref"] == fl["job_ref"] and not ri["started"], \
            "reinvestigate while one is requested starts no duplicate"
        steps.append("reinvestigate dedup (one investigation per issue)")

        # ---- B1b: the collector/advancer ----
        assert _parse_reap_body('{"result": {"text": "WHAT: x"}}') == "WHAT: x", \
            "outbox envelope parses to result text"
        assert _parse_reap_body('{"result": {}}') is None, \
            "envelope without text parses to None"
        assert _parse_reap_body("not json") is None, \
            "bad outbox body parses to None"
        dry_coll = collect_investigation_sections(dry=True)
        assert dry_coll["skipped_dry"] >= 1, \
            "dry rehearsal skips the dry-run investigation, writes nothing"
        ref_still = pg_one(
            f"select investigation_job_ref from {SCHEMA}.agent_work_items "
            f"where id = %s", (issue_id,))
        assert ref_still == fl["job_ref"], \
            "dry collector leaves the dry ref untouched"
        steps.append("collector dry rehearsal (skips dry refs, writes nothing)")

        # Live landing, end-to-end on disposable rows: fabricated bus
        # events + outbox rows (gamma never ran) prove the landing path;
        # no real REAP job is ever queued by this test.
        fl2 = raise_flag(op, a, "SELFTEST flag 2: collector landing",
                         detail="disposable collector proof",
                         investigate="dry")
        issue2 = fl2["item_id"]
        fake_ev = fake_ev2 = None
        try:
            fake_ev = pg_one(
                "insert into bus.events (event_type, source, target, "
                "priority, payload, status) values ('reap_infer', %s, "
                "'gamma', %s, %s, 'done') returning id",
                (a, INVESTIGATION_PRIORITY,
                 Json({"probe_id": INVESTIGATION_PROBE_ID,
                       "commons_item_id": issue2, "section": "EVIDENCE",
                       "thinking": INVESTIGATION_THINKING,
                       "max_tokens": REAP_MAX_TOKENS})))
            pg_exec(
                "insert into successbrian_os.outbox (source_agent, "
                "message_type, subject, body) values ('gamma', "
                "'inference_result', %s, %s)",
                (f"gamma: event {fake_ev} done (reap_infer)",
                 json.dumps({"result": {"text": "EVIDENCE: seen in logs"}})))
            pg_exec(
                f"""update {SCHEMA}.agent_work_items
                       set investigation_status = 'queued',
                           investigation_job_ref = %s,
                           investigation_result_note = %s,
                           updated_at = now()
                     where id = %s""",
                (f"bus.events:{fake_ev}", "WHAT: w", issue2))
            dry2 = collect_investigation_sections(dry=True)
            assert dry2["landed"] >= 1 and dry2["dispatched"] >= 1, \
                "dry rehearsal reports the landable section + next dispatch"
            row2 = pg_rows(
                f"""select investigation_status, investigation_job_ref,
                           investigation_result_note
                      from {SCHEMA}.agent_work_items where id = %s""",
                (issue2,))[0]
            assert row2[0] == "queued" \
                and row2[1] == f"bus.events:{fake_ev}" \
                and row2[2] == "WHAT: w", \
                "dry collector writes nothing to a landable row"
            steps.append("collector dry rehearsal (would land + dispatch, "
                         "row untouched)")

            # Now the live landing at 4/4: 3 sections on the note, a
            # finished FIXES pass lands, investigation completes, and no
            # further bus event is dispatched.
            fake_ev2 = pg_one(
                "insert into bus.events (event_type, source, target, "
                "priority, payload, status) values ('reap_infer', %s, "
                "'gamma', %s, %s, 'done') returning id",
                (a, INVESTIGATION_PRIORITY,
                 Json({"probe_id": INVESTIGATION_PROBE_ID,
                       "commons_item_id": issue2, "section": "FIXES",
                       "thinking": INVESTIGATION_THINKING,
                       "max_tokens": REAP_MAX_TOKENS})))
            pg_exec(
                "insert into successbrian_os.outbox (source_agent, "
                "message_type, subject, body) values ('gamma', "
                "'inference_result', %s, %s)",
                (f"gamma: event {fake_ev2} done (reap_infer)",
                 json.dumps({"result": {"text": "FIXES: do the thing first"}})))
            pg_exec(
                f"""update {SCHEMA}.agent_work_items
                       set investigation_status = 'queued',
                           investigation_job_ref = %s,
                           investigation_result_note = %s,
                           updated_at = now()
                     where id = %s""",
                (f"bus.events:{fake_ev2}",
                 "WHAT: w\n\nEVIDENCE: e\n\nTRIED: t", issue2))
            live_coll = collect_investigation_sections()
            assert live_coll["landed"] >= 1 \
                and live_coll["completed"] >= 1, \
                "collector lands the finished section and completes at 4/4"
            row2 = pg_rows(
                f"""select investigation_status, investigation_job_ref,
                           investigation_result_note
                      from {SCHEMA}.agent_work_items where id = %s""",
                (issue2,))[0]
            assert row2[0] == "done" and row2[1] is None, \
                "4/4 note marks the investigation done, ref cleared"
            assert "FIXES: do the thing first" in (row2[2] or ""), \
                "landed FIXES section is on the note"
            n_ev = pg_one(
                "select count(*) from bus.events where "
                "payload->>'commons_item_id' = %s", (str(issue2),))
            assert n_ev == 2, \
                "completing at 4/4 dispatches no further bus event"
            steps.append("collector live landing (FIXES lands, 4/4 done, "
                         "no further dispatch)")
        finally:
            for ev in (fake_ev, fake_ev2):
                if ev:
                    pg_exec("delete from bus.events where id = %s", (ev,))
                    pg_exec(
                        "delete from successbrian_os.outbox where "
                        "subject = %s",
                        (f"gamma: event {ev} done (reap_infer)",))

        lead = claim_item(a, issue_id)
        assert lead and lead["claimed_by_agent"] == a, "A takes lead"
        att_a = progress_item(a, issue_id, note="lead: second way tried",
                              attempt=True)
        assert att_a and att_a["attempts"] == 2, "attempts count team-wide"
        steps.append("lead claim + second team attempt (counter=2)")

        res = complete_item(a, issue_id, note="solved by the team")
        assert res and res["status"] == "done", "issue resolves to done"
        board_after = list_board(operator=op)
        assert all(f["id"] != issue_id for f in board_after["flags"]), \
            "solved flag leaves the flags section"
        steps.append("resolve (flag closes; team solved it together)")

        board = list_board(operator=op)
        keys = {x["agent_key"] for x in board["agents"]}
        assert {a, b} <= keys, "list_board shows both agents"
        steps.append("list_board (agents + presence + open items)")
    finally:
        cleanup()
    left = pg_one(f"select count(*) from {SCHEMA}.agent_registry "
                  f"where operator_key = %s", (op,))
    assert left == 0, "cleanup left residue"
    for s in steps:
        print(f"  ok: {s}")
    print("SELFTEST PASS")
    return 0


# ------------------------------------------------------------------ CLI

def _print_board(board: dict) -> None:
    print(f"AGENT COMMONS — operator: {board['operator'] or '(all)'}")
    flags = board.get("flags", [])
    print(f"\n⚑ OPEN FLAGS ({len(flags)}) — read on every heartbeat; "
          "the team works these together:")
    for f in flags:
        lead = f["lead"] or "(no lead yet)"
        gate = "  ASK-GATE REACHED (5+ team attempts)" if f["ask_gate"] else ""
        print(f"  ⚑ #{f['id']} {f['title']} "
              f"[raised by {f['raised_by']}, lead: {lead}, "
              f"team attempts: {f['attempts']}]{gate}")
        inv = f.get("investigation_status") or "none"
        if inv != "none":
            job = f.get("investigation_job_status")
            ref = f.get("investigation_job_ref") or ""
            print(f"      150B investigation: {inv}"
                  + (f" (job {job})" if job else "")
                  + (f" [{ref}]" if ref else ""))
        if f["detail"]:
            print(f"      {f['detail']}")
    for ag in board["agents"]:
        focus = ag["current_focus"] or "(no focus published)"
        print(f"\n[{ag['agent_key']}] {ag['display_name']} "
              f"({ag['kind']}{'' if ag['enabled'] else ', disabled'})")
        print(f"  focus: {focus}")
        if ag["status_note"]:
            print(f"  note:  {ag['status_note']}")
        print(f"  presence: {ag['presence_at'] or 'never'}")
        for h in ag["holding"]:
            flag = f"  FLAG: {h['flag']}" if h["flag"] else ""
            print(f"  holding: #{h['id']} {h['title']} "
                  f"[{h['status']}, attempts {h['attempts']}]{flag}")
    print(f"\nOPEN ITEMS ({len(board['open_items'])}):")
    for it in board["open_items"]:
        print(f"  #{it['id']} {it['title']} (posted by {it['created_by']})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agent Commons — shared work board")
    sub = ap.add_subparsers(dest="verb", required=True)

    p = sub.add_parser("register")
    p.add_argument("--operator", required=True)
    p.add_argument("--agent", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--kind", default="ecosystem",
                   help="agent source: muse, grok, dots, google-aqua, ecosystem, ...")
    p.add_argument("--node")
    p.add_argument("--tier", type=int)
    p.add_argument("--cadence")
    p.add_argument("--notes")

    p = sub.add_parser("publish-state")
    p.add_argument("--agent", required=True)
    p.add_argument("--operator")
    p.add_argument("--state-json")
    p.add_argument("--state-file")
    p.add_argument("--focus")
    p.add_argument("--note")

    p = sub.add_parser("heartbeat")
    p.add_argument("--agent", required=True)
    p.add_argument("--operator")
    p.add_argument("--focus")
    p.add_argument("--note")
    p.add_argument("--lease-min", type=int, default=DEFAULT_LEASE_MIN)

    p = sub.add_parser("post")
    p.add_argument("--agent", required=True)
    p.add_argument("--operator", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--detail")
    p.add_argument("--kind", choices=["task", "issue"], default="task")

    p = sub.add_parser("raise-flag")
    p.add_argument("--agent", required=True)
    p.add_argument("--operator", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--detail")
    p.add_argument("--no-investigate", action="store_true",
                   help="do not start the REAP 150B investigation")
    p.add_argument("--dry-investigate", action="store_true",
                   help="record the investigation request without "
                        "touching the road (operations/testing)")

    p = sub.add_parser("reinvestigate")
    p.add_argument("--agent", required=True)
    p.add_argument("--item", type=int, required=True)
    p.add_argument("--dry", action="store_true")

    p = sub.add_parser("claim")
    p.add_argument("--agent", required=True)
    p.add_argument("--item", type=int, required=True)
    p.add_argument("--lease-min", type=int, default=DEFAULT_LEASE_MIN)

    p = sub.add_parser("progress")
    p.add_argument("--agent", required=True)
    p.add_argument("--item", type=int, required=True)
    p.add_argument("--note")
    p.add_argument("--attempt", action="store_true")
    p.add_argument("--status", choices=list(ACTIVE_ITEM_STATUSES))
    p.add_argument("--lease-min", type=int, default=DEFAULT_LEASE_MIN)

    p = sub.add_parser("complete")
    p.add_argument("--agent", required=True)
    p.add_argument("--item", type=int, required=True)
    p.add_argument("--note")

    p = sub.add_parser("release")
    p.add_argument("--agent", required=True)
    p.add_argument("--item", type=int, required=True)

    p = sub.add_parser("board")
    p.add_argument("--operator")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("items")
    p.add_argument("--operator")
    p.add_argument("--status")
    p.add_argument("--agent")
    p.add_argument("--kind", choices=["task", "issue"])
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("collect-investigations")
    p.add_argument("--dry", action="store_true",
                   help="rehearse only: report what would land / "
                        "dispatch / reset, write nothing")

    sub.add_parser("selftest")
    args = ap.parse_args(argv)

    try:
        if args.verb == "register":
            out = register(args.operator, args.agent, args.name, args.kind,
                           node=args.node, tier=args.tier,
                           cadence=args.cadence, notes=args.notes)
        elif args.verb == "publish-state":
            if args.state_json:
                state = json.loads(args.state_json)
            elif args.state_file:
                with open(args.state_file) as f:
                    state = json.load(f)
            else:
                ap.error("publish-state needs --state-json or --state-file")
            out = publish_state(args.agent, state, current_focus=args.focus,
                                status_note=args.note, operator=args.operator)
        elif args.verb == "heartbeat":
            out = heartbeat(args.agent, current_focus=args.focus,
                            status_note=args.note, operator=args.operator,
                            lease_min=args.lease_min)
        elif args.verb == "post":
            out = post_item(args.operator, args.agent, args.title, args.detail,
                            kind=args.kind)
        elif args.verb == "raise-flag":
            investigate = True
            if args.no_investigate:
                investigate = False
            elif args.dry_investigate:
                investigate = "dry"
            out = raise_flag(args.operator, args.agent, args.title,
                             args.detail, investigate=investigate)
        elif args.verb == "reinvestigate":
            out = reinvestigate(args.agent, args.item, dry=args.dry)
            if out is None:
                print(f"REFUSED: item {args.item} is not an issue",
                      file=sys.stderr)
                return 1
        elif args.verb == "claim":
            out = claim_item(args.agent, args.item, lease_min=args.lease_min)
            if out is None:
                print(f"REFUSED: item {args.item} is not claimable "
                      "(missing, done, or held under a live lease)",
                      file=sys.stderr)
                return 1
        elif args.verb == "progress":
            out = progress_item(args.agent, args.item, note=args.note,
                                attempt=args.attempt, status=args.status,
                                lease_min=args.lease_min)
            if out is None:
                print(f"REFUSED: item {args.item} is not held by {args.agent}",
                      file=sys.stderr)
                return 1
        elif args.verb == "complete":
            out = complete_item(args.agent, args.item, note=args.note)
            if out is None:
                print(f"REFUSED: item {args.item} cannot be completed by "
                      f"{args.agent} (missing, done, or held by another)",
                      file=sys.stderr)
                return 1
        elif args.verb == "release":
            out = release_item(args.agent, args.item)
            if out is None:
                print(f"REFUSED: item {args.item} is not held by {args.agent}",
                      file=sys.stderr)
                return 1
        elif args.verb == "board":
            board = list_board(operator=args.operator)
            if args.json:
                print(json.dumps(board, indent=1, default=str))
            else:
                _print_board(board)
            return 0
        elif args.verb == "items":
            items = list_items(operator=args.operator, status=args.status,
                               agent=args.agent, kind=args.kind)
            if args.json:
                print(json.dumps(items, indent=1, default=str))
            else:
                for it in items:
                    flag = f"  FLAG: {it['flag']}" if it["flag"] else ""
                    holder = it["claimed_by"] or "-"
                    print(f"#{it['id']} [{it['kind']}/{it['status']}] "
                          f"{it['title']} "
                          f"(by {it['created_by']}, held by {holder}, "
                          f"attempts {it['attempts']}){flag}")
            return 0
        elif args.verb == "collect-investigations":
            out = collect_investigation_sections(dry=args.dry)
        elif args.verb == "selftest":
            return selftest()
        else:  # pragma: no cover
            ap.error(f"unknown verb {args.verb}")
        print(json.dumps(out, indent=1, default=str))
        return 0
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
