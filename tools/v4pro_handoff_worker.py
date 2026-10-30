#!/usr/bin/env python3
"""
v4pro_handoff_worker.py — Process queued V4 Pro handoffs.

PURPOSE: Pick up handoffs Sonic queued, run them on DeepSeek V4 Pro when
         credits allow, write results back. Completes the tradeoff loop:
         Sonic drafts fast in chat, V4 Pro sharpens deep in the background.
WHY: Brian 2026-10-07 tradeoff system — deep work shouldn't block chat,
     and V4 Pro credits shouldn't burn on things Sonic can do.
CALLED BY: system cron `v4pro-handoff-worker` every 15 min (successbrian).
NOTES:
  - Re-checks availability from v4pro_balance_history before EVERY API call.
    Never spends when the latest row is stale or shows $0. Queued items wait;
    they are never failed for lack of credits.
  - Key: DEEPSEEK_API_KEY from /home/successbrian/.hermes/.env (the
    InstantlyClaw rental — never Brian's). Never printed, logged, or written.
  - At most 3 handoffs per run (spend bound). API timeout 300s (deep
    reasoning takes minutes).
  - On API error the handoff is marked failed with the error text (truncated);
    Sonic/Brian can re-queue. Nothing retries silently.
"""

import re
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v4pro_router import get_availability, pq  # noqa: E402
import sbos_common  # SBOS common routines — Batch C migration (2026-10-27)

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t"]

ENV_FILE = Path("/home/successbrian/.hermes/.env")
CHAT_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-pro"
MAX_PER_RUN = 3
API_TIMEOUT = 300


def get_key():
    try:
        for line in ENV_FILE.read_text().splitlines():
            s = line.strip()
            if s.startswith("DEEPSEEK_API_KEY="):
                v = s.split("=", 1)[1].strip().strip("'\"")
                if v and v != "none":
                    return v
    except Exception:
        pass
    return ""


def claim_handoffs(limit=MAX_PER_RUN):
    """Atomic claim: one statement, FOR UPDATE SKIP LOCKED — parallel
    workers each get different rows, never the same handoff twice.
    Batch C migration (2026-10-27): delegates to sbos_common.handoff_claim."""
    try:
        return sbos_common.handoff_claim(limit)
    except Exception as e:
        print("claim failed: %s" % str(e)[:150])
        return []


def load_handoff(hid):
    # Batch C migration (2026-10-27): delegates to sbos_common.handoff_get
    # (true column values instead of tab-split text — strictly cleaner
    # for fields containing tabs/newlines; same dict shape).
    return sbos_common.handoff_get(hid)


def build_prompt(h):
    return (
        "You are DeepSeek V4 Pro, the deep-reasoning tier of Brian's agent fleet.\n"
        "Sonic (the fast local model, Brian's chat face) has done the quick pass below.\n"
        "Your job: sharpen it — go deeper, catch what he missed, decide where he's torn.\n"
        "Don't repeat his draft back; deliver the deeper cut.\n\n"
        "TASK: %s\n"
        "YOUR ASSIGNMENT: %s\n\n"
        "CONTEXT:\n%s\n\n"
        "SONIC'S DRAFT (sharpen, don't start cold):\n%s\n\n"
        "CONSTRAINTS:\n%s\n"
        % (h["summary"], h["ask"], h["context"] or "(none)",
           h["draft"] or "(no draft — work it fresh)", h["constraints"] or "(none)")
    )


def call_v4pro(key, prompt):
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system",
             "content": "You are the deep-reasoning tier. Be thorough, decisive, and concrete."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        CHAT_URL, data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]




# ---- Profile-based research loop (Brian 2026-10-17) ----
# Each run: load profile + recent learnings -> work stages -> write new
# learnings -> die. Fresh context every run; learnings compound.

def load_profile(kind):
    r = subprocess.run(PSQL + ["-c",
        "SELECT profile_md FROM successbrian_os.worker_profiles "
        "WHERE worker_kind = %s;" % pq(kind)],
        capture_output=True, text=True, timeout=30)
    profile = r.stdout.strip() or "(no profile yet)"
    # Relevant ecosystem SOPs, pulled LIVE from business_core.rules via the
    # worker_profile_sops mapping — never hardcoded, never stale.
    rs = subprocess.run(PSQL + ["-c",
        "SELECT r.category || ': ' || r.rule "
        "FROM successbrian_os.worker_profile_sops m "
        "JOIN business_core.rules r ON r.id = m.rule_id "
        "WHERE m.worker_kind = %s AND r.tenant_id = 'brian' "
        "ORDER BY r.id;" % pq(kind)],
        capture_output=True, text=True, timeout=30)
    sops = [ln.strip() for ln in rs.stdout.split("\n") if ln.strip()]
    if sops:
        profile += ("\n\n## RELEVANT ECOSYSTEM SOPS "
                    "(live from business_core.rules — these are standing law)\n" +
                    "\n".join("- " + x[:600] for x in sops))
    return profile

def load_learnings(kind, limit=12):
    r = subprocess.run(PSQL + ["-c",
        "SELECT learning FROM successbrian_os.v4pro_worker_learnings "
        "WHERE worker_kind = %s ORDER BY created_at DESC LIMIT %d;"
        % (pq(kind), limit)],
        capture_output=True, text=True, timeout=30)
    rows = [ln.strip() for ln in r.stdout.split("\n") if ln.strip()]
    if not rows:
        return "(no learnings yet — you are the first run)"
    return "\n".join("- " + x for x in rows)

def write_learning(kind, text, handoff_id):
    subprocess.run(PSQL + ["-c",
        "INSERT INTO successbrian_os.v4pro_worker_learnings "
        "(worker_kind, learning, handoff_id) VALUES (%s, %s, %d);"
        % (pq(kind), pq(text[:2000]), handoff_id)],
        capture_output=True, text=True, timeout=30)


def save_learnings_from_text(kind, text, hid):
    """Parse LEARNING: lines and write each one."""
    n = 0
    for ln in (text or "").split("\n"):
        t = ln.strip()
        if t.upper().startswith("LEARNING:"):
            write_learning(kind, t[len("LEARNING:"):].strip(), hid)
            n += 1
    if n:
        print("#%d: wrote %d learning(s)" % (hid, n))
    return n

RESEARCH_STAGES = [
    ("UNDERSTAND",
     "Restate the item in your own words. Map its Atlas connections — what "
     "depends on it, what it feeds. State clearly what is actually unknown "
     "vs. what the context already answers. Flag decisions you cannot make: "
     "ALTAIR DECISION: <q> for ecosystem-ops calls, MEGHAN DECISION: <q> for "
     "CEO-level calls, PENDING BRIAN CALL: <q> for Brian's calls."),
    ("ANALYZE",
     "Work the substance. Tradeoffs, free-first cost reality, fit with the "
     "ecosystem (self-hosted, his hardware, zero-chat-operation). Which "
     "Atlas dependencies help or block it?"),
    ("CHALLENGE",
     "Steelman the case AGAINST. Find holes, hidden assumptions, ways this "
     "fails in Brian's real world (two jobs, scrap hardware, no budget for "
     "SaaS). Be brutal — a surviving idea is a better idea."),
    ("PROPOSE",
     "Concrete plan proposals, each one line of title plus one line of "
     "rationale. Mark which ones need Brian's call vs. which the system "
     "could just do. For every flagged decision also write: GOAL: <one-line "
     "goal> and TRIED: <what was already tried, short> and ACCEPT_IF: "
     "<how to judge an acceptable answer — write the check before asking>."),
]



# ---- Lyra escalation chain (Brian 2026-10-17) ----
# Worker runs as Lyra (ecosystem manager). Decision points escalate:
# ecosystem-ops -> Altair, CEO-level -> Meghan, Brian-level -> inbox w/
# priority. Board reviews at the checkpoint; Altair then Meghan review
# the board's findings. Brian's answers trigger a re-think.

BOARD_CONFIG = "/home/successbrian/successbrian-os/board/config/brian.yaml"

def load_board_seats():
    """Full live board roster from Postgres (successbrian_os.board_seats).
    Seats are data, not config — Brian edits rows, never files."""
    try:
        r = subprocess.run(
            PSQL + ["-c",
                    "SELECT title, mandate FROM successbrian_os.board_seats "
                    "WHERE active ORDER BY wave, title;"],
            capture_output=True, text=True, timeout=30)
        rows = [ln.split("\t") for ln in r.stdout.split("\n") if "\t" in ln]
        if rows:
            return [(t.strip(), m.strip()) for t, m in rows]
    except Exception as e:
        print("board seats PG read failed (%s) — trying YAML" % str(e)[:80])
    try:
        sys.path.insert(0, "/home/successbrian/successbrian-os/board/harness")
        from seats import load_seats
        return [(st.title, st.mandate) for st in load_seats(BOARD_CONFIG)]
    except Exception as e:
        print("board seat load failed (%s) — session runs without seat roster"
              % str(e)[:100])
        return []

def parse_escalations(text):
    """Find ALTAIR DECISION: / MEGHAN DECISION: / PENDING BRIAN CALL: lines."""
    out = []
    for ln in (text or "").split("\n"):
        t = ln.strip()
        u = t.upper()
        for prefix, tier in (("ALTAIR DECISION:", "altair"),
                             ("MEGHAN DECISION:", "meghan"),
                             ("PENDING BRIAN CALL:", "brian")):
            if u.startswith(prefix):
                q = t[len(prefix):].strip()
                if q:
                    out.append((tier, q))
                break
    return out

def parse_brian_priority(text, question):
    """MEGHAN REVIEW assigns BRIAN PRIORITY: <1-3> near the question."""
    best = 2
    ql = question[:60].lower()
    for ln in (text or "").split("\n"):
        if "BRIAN PRIORITY" in ln.upper() and ql in ln.lower():
            m = re.search(r"([1-3])", ln)
            if m:
                return int(m.group(1))
    m = re.search(r"BRIAN PRIORITY:\s*([1-3])", text or "", re.I)
    if m:
        best = int(m.group(1))
    return best

def file_escalation(hid, kind, tier, question, context, priority=2, packet=None):
    """Record escalation (packet v2); route to the real agent / Brian's inbox."""
    packet = packet or {}
    r = subprocess.run(PSQL + ["-c",
        "INSERT INTO successbrian_os.worker_escalations "
        "(handoff_id, worker_kind, tier, question, context, priority, "
        " goal, reason, tried, accept_if) "
        "VALUES (%d, %s, %s, %s, %s, %d, %s, %s, %s, %s) RETURNING id;"
        % (hid, pq(kind), pq(tier), pq(question[:2000]),
           pq((context or "")[:2000]), priority,
           pq(packet.get("goal", "")[:300]), pq(packet.get("reason", "")[:500]),
           pq(packet.get("tried", "")[:500]), pq(packet.get("accept_if", "")[:500]))],
        capture_output=True, text=True, timeout=30)
    eid = int(r.stdout.strip().split("\n")[0]) if r.returncode == 0 else None
    pq_id = None
    if tier in ("altair", "meghan"):
        # Real agent sees it on their heartbeat via knowledge_bridge.
        subprocess.run(PSQL + ["-c",
            "INSERT INTO public.knowledge_bridge "
            "(source_agent, target_agent, subject, message, urgency) "
            "VALUES ('lyra', %s, %s, %s, 'high');"
            % (pq(tier), pq("Lyra worker escalation (handoff #%d)" % hid),
               pq(question[:2000] + "\n\nContext: " + (context or "")[:1500]))],
            capture_output=True, text=True, timeout=30)
        print("#%d: escalated to %s via bridge (esc #%s)" % (hid, tier, eid))
    elif tier == "brian":
        rq = subprocess.run(PSQL + ["-c",
            "INSERT INTO successbrian_os.pending_questions "
            "(asked_by, question, context, priority) VALUES ('lyra', %s, %s, %d) "
            "RETURNING id;"
            % (pq(question[:2000]),
               pq("From Lyra worker handoff #%d (%s)" % (hid, (context or "")[:500])),
               priority)],
            capture_output=True, text=True, timeout=30)
        if rq.returncode == 0:
            pq_id = int(rq.stdout.strip().split("\n")[0])
            subprocess.run(PSQL + ["-c",
                "UPDATE successbrian_os.worker_escalations SET pq_id = %d "
                "WHERE id = %d;" % (pq_id, eid)],
                capture_output=True, text=True, timeout=30)
        print("#%d: filed for Brian (priority %d, pq #%s)" % (hid, priority, pq_id))
    return eid



# ---- v2: packet, guards, trajectories, kill-switch ----

def chain_halted():
    r = subprocess.run(PSQL + ["-c",
        "SELECT value FROM successbrian_os.chain_controls "
        "WHERE key = 'lyra_chain_halted';"],
        capture_output=True, text=True, timeout=30)
    return r.stdout.strip().lower() == "true"

def chain_control(key):
    r = subprocess.run(PSQL + ["-c",
        "SELECT value FROM successbrian_os.chain_controls WHERE key = %s;"
        % pq(key)], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()

def record_worker_error():
    """Auto-stop on error burst (v2 kill-switch): N failures in an hour halts."""
    subprocess.run(PSQL + ["-c",
        "INSERT INTO successbrian_os.chain_controls (key, value) "
        "VALUES ('lyra_err_' || to_char(now(),'YYYYMMDDHH24MI'), '1') "
        "ON CONFLICT (key) DO NOTHING;"],
        capture_output=True, text=True, timeout=30)
    r = subprocess.run(PSQL + ["-c",
        "SELECT count(*) FROM successbrian_os.chain_controls "
        "WHERE key LIKE 'lyra_err_%' AND updated_at > now() - interval '1 hour';"],
        capture_output=True, text=True, timeout=30)
    try:
        thresh = int(chain_control("lyra_auto_stop_on_errors") or "5")
    except ValueError:
        thresh = 5
    if r.stdout.strip().isdigit() and int(r.stdout.strip()) >= thresh:
        subprocess.run(PSQL + ["-c",
            "UPDATE successbrian_os.chain_controls SET value = 'true', "
            "updated_at = now() WHERE key = 'lyra_chain_halted';"],
            capture_output=True, text=True, timeout=30)
        print("KILL-SWITCH: error burst (%s/hr) — chain halted, Brian must restart"
              % r.stdout.strip())
        return True
    return False

def parse_packet(text, question):
    """Pull ACCEPT_IF / TRIED / GOAL lines associated with a flagged question."""
    pkt = {"accept_if": "", "tried": "", "goal": ""}
    ql = question[:50].lower()
    lines = (text or "").split("\n")
    for i, ln in enumerate(lines):
        u = ln.strip().upper()
        if u.startswith("ACCEPT_IF:") and ql in "\n".join(lines[max(0,i-6):i]).lower():
            pkt["accept_if"] = ln.strip()[len("ACCEPT_IF:"):].strip()[:500]
        elif u.startswith("TRIED:") and ql in "\n".join(lines[max(0,i-6):i]).lower():
            pkt["tried"] = ln.strip()[len("TRIED:"):].strip()[:500]
        elif u.startswith("GOAL:") and ql in "\n".join(lines[max(0,i-6):i]).lower():
            pkt["goal"] = ln.strip()[len("GOAL:"):].strip()[:300]
    return pkt

def load_trajectories(kind, limit=2):
    """ExpeL's second memory: recent successful runs as few-shot examples."""
    r = subprocess.run(PSQL + ["-c",
        "SELECT left(v4pro_result, 1500) FROM successbrian_os.v4pro_handoffs "
        "WHERE task_kind = %s AND status = 'done' AND v4pro_result IS NOT NULL "
        "ORDER BY completed_at DESC LIMIT %d;" % (pq(kind), limit)],
        capture_output=True, text=True, timeout=30)
    rows = [ln.strip() for ln in r.stdout.split("\n") if ln.strip()]
    if not rows:
        return ""
    return ("\n\nPAST SUCCESSFUL RUNS (same kind — learn the shape of good output):\n" +
            "\n---\n".join(rows))

def tier_brief():
    """Tiers as config, injected into review prompts."""
    r = subprocess.run(PSQL + ["-c",
        "SELECT tier || ': ' || label || ' | decides: ' || decision_classes "
        "FROM successbrian_os.worker_tiers ORDER BY tier;"],
        capture_output=True, text=True, timeout=30)
    return r.stdout.strip() or "(tier config unavailable)"


def board_session_prompt(base_ctx, notes_text):
    live = load_board_seats()
    seats = "\n".join("- %s: %s" % st for st in live) or "(roster unavailable)"
    return (base_ctx +
        "\n\n=== BOARD SESSION ===\n"
        "You are Brian's board of directors in session — the FULL board, "
        "%d seats, advisory only (input via recommendations, never orders). "
        "The seats:\n" % len(live) + seats +
        "\n\nReview the research state below. Each seat speaks briefly FROM ITS "
        "MANDATE — only seats with something real to say speak. Then output:\n\n"
        "BOARD FINDINGS:\n1. <finding>\n\nDISAGREEMENTS:\n- <where seats split>\n\n"
        "QUESTIONS FOR BRIAN:\n- <question>\n\n"
        "Research state:\n" + notes_text[:12000])

def review_prompt(base_ctx, board_text, reviewer, reviewer_role, decision_tier):
    flag_note = (" If a decision here is important and valuable enough to "
                 "warrant the FULL 14-seat board (irreversible, big money, "
                 "real tradeoffs across mandates), emit: FULL BOARD RECOMMENDED: "
                 "<why>." if decision_tier == "ceo" else "")
    return (base_ctx + flag_note +
        "\n\n=== %s REVIEW ===\nYou are %s — %s. "
        "CONFORMITY GUARD: evaluate the RAW findings below INDEPENDENTLY. "
        "Do NOT defer to the board's verdict or any prior tier's take — "
        "they can be wrong, and nodding along is the failure mode. Where you "
        "disagree with the board, say so plainly and why. "
        "For each open %s-level decision: "
        "either RESOLVE it with your reasoning (RESOLVED: <decision> — <why>), "
        "or confirm it needs escalation (%s DECISION: <question>). "
        "For anything needing Brian, use PENDING BRIAN CALL: <question> and add "
        "a line BRIAN PRIORITY: <1-3> (3 = blocks progress, 2 = matters, 1 = FYI)."
        "\n\nBoard findings:\n%s"
        % (reviewer.upper(), reviewer, reviewer_role, decision_tier,
           decision_tier.upper(), board_text[:8000]))



def has_profile(kind):
    r = subprocess.run(PSQL + ["-c",
        "SELECT 1 FROM successbrian_os.worker_profiles WHERE worker_kind = %s;"
        % pq(kind)], capture_output=True, text=True, timeout=30)
    return "1" in r.stdout.split()





SONIC_CAPABLE = {"ecosystem-health"}  # kinds Sonic can run light
SONIC_URL = "http://127.0.0.1:11439/v1/chat/completions"


def lyra_mode():
    r = subprocess.run(PSQL + ["-c",
        "SELECT value FROM successbrian_os.chain_controls "
        "WHERE key = 'lyra_mode';"],
        capture_output=True, text=True, timeout=30)
    return r.stdout.strip() or "v4"


def call_sonic(prompt, max_tokens=2000):
    import json, urllib.request
    req = urllib.request.Request(
        SONIC_URL,
        data=json.dumps({
            "model": "qwen3.6",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0.3}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"]


def run_sonic_light(h, hid):
    """Single-pass Sonic run for sonic-capable work. Emits HEALTH_FIX lines
    for the deterministic applier, plus findings. The machine keeps working
    while V4 is dry."""
    prompt = (
        "You are a Lyra health worker (light mode — V4 Pro is dry, you are "
        "Sonic, the local model). Be mechanical and careful.\n\n"
        "ASSIGNMENT: %s\n\nCONTEXT:\n%s\n\n"
        "Output:\n"
        "1. HEALTH_FIX lines for safe reversible fixes ONLY, one per line:\n"
        "   HEALTH_FIX: DROP_DEAD_EDGE | from,to,type\n"
        "   HEALTH_FIX: SUPERSEDE_LEARNING | drop_id,keep_id\n"
        "   HEALTH_FIX: SET_NODE_STATUS | node_key,new_status\n"
        "   HEALTH_FIX: WIRE_ORPHAN | from,to,type\n"
        "   (Only emit a fix when you are certain. When unsure, skip it.)\n"
        "2. FINDINGS: numbered list of what you found.\n"
        "3. PROPOSED PLANS: anything needing Brian or deeper work."
        % (h["summary"], (h.get("context") or "")[:4000]))
    try:
        out = call_sonic(prompt)
    except Exception as e:
        return "SONIC LIGHT-PASS FAILED: %s" % str(e)[:200]
    print("#%d: sonic light-pass done (%d chars)" % (hid, len(out)))
    # Learnings stay cheap too
    try:
        learn_out = call_sonic(
            "One line starting with LEARNING: — what did this health sweep "
            "teach about keeping the ecosystem clean? Skip filler.", 300)
        save_learnings_from_text(h["kind"], learn_out, hid)
    except Exception:
        pass
    return out


def run_full_board(key, h, hid):
    """Full 14-seat board deliberation. One independent V4 call per seat,
    then a synthesis that preserves disagreements."""
    seats = load_board_seats()
    if not seats:
        return "FULL BOARD ABORTED: no seats loaded"
    question = h["ask"] or h["summary"]
    context = h.get("context") or "(none)"
    constraints = h.get("constraints") or "(none)"

    takes = []
    for title, mandate in seats:
        # Pull this seat's full row for domain/constraints
        row = subprocess.run(
            PSQL + ["-c",
                    "SELECT domain, coalesce(constraints,'') "
                    "FROM successbrian_os.board_seats WHERE title = %s;"
                    % pq(title)],
            capture_output=True, text=True, timeout=30)
        domain, con = "", ""
        if "\t" in row.stdout:
            parts = row.stdout.strip().split("\t")
            domain = parts[0] if len(parts) > 0 else ""
            con = parts[1] if len(parts) > 1 else ""
        prompt = (
            "You are the %s on Brian's board of directors — advisory only, "
            "you recommend, Brian decides.\n"
            "Your domain: %s\nYour mandate: %s\n"
            "%s\n\n"
            "THE QUESTION BEFORE THE BOARD:\n%s\n\nCONTEXT:\n%s\n\n"
            "CONSTRAINTS:\n%s\n\n"
            "Give YOUR seat's independent take: your recommendation, your "
            "reasoning from YOUR mandate, what worries you, and what you'd "
            "need to know to be surer. Speak only for your seat — you have "
            "not heard any other seat. End with: SEAT CALL: <your one-line call>."
            % (title, domain, mandate,
               ("Your hard constraints: " + con + "\n") if con else "",
               question, context[:4000], constraints[:1000]))
        try:
            out = call_v4pro(key, prompt)
        except Exception as e:
            out = "SEAT SILENT (%s): %s" % (title, str(e)[:100])
        takes.append((title, out))
        print("#%d: board seat %s done (%d chars)" % (hid, title, len(out)))

    takes_text = "\n\n".join(
        "=== %s ===\n%s" % (t, o[:2500]) for t, o in takes)
    synth = call_v4pro(
        key,
        "You are synthesizing a full board session — 14 directors each gave "
        "an independent take on the question below. Merge them into a board "
        "deliberation record. Do NOT smooth over disagreements — surface them.\n\n"
        "QUESTION: %s\n\nTHE 14 TAKES:\n%s\n\n"
        "Output EXACTLY:\n\nBOARD CONSENSUS:\n<where the seats agree>\n\n"
        "BOARD DISAGREEMENTS:\n- <seat> vs <seat>: <what they split on and why>\n\n"
        "SEAT CALLS:\n- <seat>: <their one-line call>\n\n"
        "BOARD RECOMMENDATION:\n<the board's collective recommendation to Brian>\n\n"
        "PENDING BRIAN CALL: <the decision Brian himself must make, if any>."
        % (question, takes_text[:14000]))
    print("#%d: board synthesis done (%d chars)" % (hid, len(synth)))

    # File any Brian-call flags from the synthesis
    seen = set()
    for tier, q in parse_escalations(synth):
        if q[:80] in seen:
            continue
        seen.add(q[:80])
        prio = parse_brian_priority(synth, q) if tier == "brian" else 2
        pkt = parse_packet(synth, q)
        pkt["reason"] = "full-board synthesis flagged during board deliberation"
        file_escalation(hid, "full-board", tier, q,
                        "%s | full board" % h["summary"], prio, pkt)

    # Learnings
    learn_out = call_v4pro(
        key, "You just ran a full 14-seat board deliberation. Output 1-3 "
        "learnings about the deliberation itself (not the topic) as lines "
        "starting with LEARNING: — e.g. which seats clashed, what the "
        "synthesis missed. Skip generic filler.")
    save_learnings_from_text("full-board", learn_out, hid)
    return synth


def run_research_loop(key, h, hid):
    kind = "atlas-research"
    profile = load_profile(kind)
    learnings = load_learnings(kind)
    trajectories = load_trajectories(kind)
    base_ctx = ("You are a Lyra worker — Lyra is the ecosystem manager, "
                "a customized Hermes agent stripped down to run the ecosystem. "
                "You research, you escalate, you never decide for Brian.\n\n"
                "ESCALATION TIERS (configured):\n" + tier_brief() +
                "\n\nWORKER PROFILE:\n" + profile + trajectories +
                "\n\nLEARNINGS FROM PREVIOUS RUNS (apply them):\n" + learnings +
                "\n\nATLAS ITEM: %s\nASSIGNMENT: %s\n\nITEM CONTEXT:\n%s\n\nCONSTRAINTS:\n%s"
                % (h["summary"], h["ask"], h["context"] or "(none)",
                   h["constraints"] or "(none)"))
    notes = []
    for stage_name, stage_ask in RESEARCH_STAGES:
        prior = ""
        for n, o in notes:
            prior += "\n--- %s (previous stage output) ---\n%s\n" % (n, o[:3000])
        prompt = (base_ctx +
                  "\n\nYou are in stage: %s. %s\n%s\n\n"
                  "Output this stage's work only — thorough but tight."
                  % (stage_name, stage_ask, prior))
        out = call_v4pro(key, prompt)
        notes.append((stage_name, out))
        print("#%d: stage %s done (%d chars)" % (hid, stage_name, len(out)))
    all_notes = "\n".join("--- %s ---\n%s" % (n, o) for n, o in notes)
    # BOARD SESSION at the checkpoint (Brian 2026-10-17)
    board_out = call_v4pro(key, board_session_prompt(base_ctx, all_notes))
    notes.append(("BOARD", board_out))
    print("#%d: board session done (%d chars)" % (hid, len(board_out)))
    # ALTAIR reviews the board's findings (ecosystem ops lens)
    altair_out = call_v4pro(key, review_prompt(
        base_ctx, board_out, "Altair", "Sr. VP, ecosystem operations — "
        "owns the lab, the fleet, and day-to-day execution",
        "ecosystem-ops"))
    notes.append(("ALTAIR REVIEW", altair_out))
    print("#%d: altair review done (%d chars)" % (hid, len(altair_out)))
    # MEGHAN reviews (CEO lens), assigns Brian priorities
    meghan_out = call_v4pro(key, review_prompt(
        base_ctx, board_out + "\n\nAltair's review:\n" + altair_out[:4000],
        "Meghan", "CEO — capital, strategy, and what Brian himself must decide",
        "ceo"))
    notes.append(("MEGHAN REVIEW", meghan_out))
    print("#%d: meghan review done (%d chars)" % (hid, len(meghan_out)))
    all_notes = "\n".join("--- %s ---\n%s" % (n, o) for n, o in notes)
    # File every flagged decision to its tier
    seen = set()
    for stage_name, stage_out in notes:
        for tier, q in parse_escalations(stage_out):
            if q[:80] in seen:
                continue
            seen.add(q[:80])
            prio = parse_brian_priority(meghan_out, q) if tier == "brian" else 2
            pkt = parse_packet(stage_out, q)
            pkt["reason"] = "%s flagged during %s" % (tier, stage_name)
            file_escalation(hid, kind, tier, q,
                            "%s | %s" % (h["summary"], stage_name), prio, pkt)
    final = call_v4pro(key, base_ctx +
        "\n\nAll research stages complete. Their output:\n" + all_notes[:12000] +
        "\n\nNow write the FINAL synthesis in EXACTLY this format:\n\n"
        "FINDINGS:\n1. <finding>\n\nPROPOSED PLANS:\n1. <title> | <rationale>\n\n"
        "DATA GAPS:\n- <what would sharpen this>\n\n"
        "Flag anything needing Brian's call as: PENDING BRIAN CALL: <question>.")
    learn_out = call_v4pro(key,
        "You just researched: %s\n\nWrite 1-3 DURABLE learnings for FUTURE "
        "research runs — things about HOW to research well in Brian's "
        "ecosystem (methods, pitfalls, useful context, traps to avoid), NOT "
        "facts about this item. One per line, each starting exactly with "
        "'LEARNING: '. If nothing is worth keeping, output NONE."
        % h["summary"])
    n_learn = 0
    for ln in learn_out.split("\n"):
        t = ln.strip()
        if t.upper().startswith("LEARNING:"):
            write_learning(kind, t[len("LEARNING:"):].strip(), hid)
            n_learn += 1
    print("#%d: wrote %d learning(s)" % (hid, n_learn))
    return final


def mark(hid, status, result="", error=""):
    # Batch C migration (2026-10-27): delegates to sbos_common.handoff_mark
    # (parameterized; same 20000/1000 truncation caps).
    sbos_common.handoff_mark(hid, status, result, error)


def release(hid):
    # Batch C migration (2026-10-27): delegates to sbos_common.handoff_release.
    sbos_common.handoff_release(hid)


FLEET_WORKERS = 4  # Brian 2026-10-17: 4 parallel workers
SLOTS_PER_WORKER = 2


def worker_main(slots=SLOTS_PER_WORKER):
    if chain_halted():
        print("chain halted by kill-switch — worker idle (Brian must restart)")
        return 0
    key = get_key()
    if not key:
        print("no DEEPSEEK_API_KEY — worker idle")
        return 0
    claimed = claim_handoffs(slots)
    if not claimed:
        print("queue empty — nothing to do")
        return 0
    for hid in claimed:
        avail = get_availability()
        if not avail["usable"]:
            print("#%d: V4 Pro not usable (%s) — released back to queue" % (hid, avail["reason"]))
            release(hid)
            continue
        h = load_handoff(hid)
        print("#%d: sending to V4 Pro (%s, balance $%.2f)…"
              % (hid, h["summary"][:50], avail["usd"]))
        try:
            if h["kind"] == "full-board":
                print("#%d: FULL BOARD deliberation (14 seats)" % hid)
                result = run_full_board(key, h, hid)
            elif lyra_mode() == "sonic" and h["kind"] in SONIC_CAPABLE:
                print("#%d: V4 dry — Sonic light-pass (%s)" % (hid, h["kind"]))
                result = run_sonic_light(h, hid)
            elif has_profile(h["kind"]):
                print("#%d: Lyra profile loop (%s)" % (hid, h["kind"]))
                result = run_research_loop(key, h, hid)
            else:
                result = call_v4pro(key, build_prompt(h))
            mark(hid, "done", result=result)
            print("#%d: done (%d chars)" % (hid, len(result)))
        except Exception as e:
            if "429" in str(e):
                release(hid)
                print("#%d: rate-limited (429) — released back to queue" % hid)
            else:
                mark(hid, "failed", error=str(e))
                print("#%d: failed: %s" % (hid, str(e)[:200]))
                if record_worker_error():
                    return 0
    return 0


def main():
    """Fleet mode: spawn FLEET_WORKERS parallel workers, each claiming
    different handoffs via the atomic claim. --worker runs one worker."""
    if "--worker" in sys.argv:
        slots = SLOTS_PER_WORKER
        if "--slots" in sys.argv:
            try:
                slots = int(sys.argv[sys.argv.index("--slots") + 1])
            except (ValueError, IndexError):
                pass
        return worker_main(slots)
    procs = []
    for w in range(FLEET_WORKERS):
        p = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__),
             "--worker", "--slots", str(SLOTS_PER_WORKER)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        procs.append(p)
    for i, p in enumerate(procs):
        out, _ = p.communicate(timeout=2400)
        tag = "[worker %d] " % i
        print(tag + out.replace("\n", "\n" + tag).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
