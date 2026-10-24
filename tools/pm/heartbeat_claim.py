#!/usr/bin/env python3
"""Heartbeat pitch-in — Brian's ruling (2026-10-24): Altair, Meghan, and
Lyra pitch in through their heartbeats, as appropriate to their layer,
so the PM queue keeps moving 24/7 instead of waiting for a chat session.

Each agent's pass claims work shaped for its layer:

  LYRA (worker/research layer, every 10 min) — deterministic prep:
    * the bus digest: unread critical/high knowledge-bridge messages
      are read, digested into the intake step's result, and marked
      read. The bus finally has a consumer.
    * desk packets: CampaignsDesk signal steps get their positioning
      outcome from the desk's own gate (article_ideas.position);
      positioned signals file a Morpheus judgment follow-up for the
      angle work; held signals close with the gate's reason.

  ALTAIR (operations decider, :05/:35 cadence) — judgment:
    claims the top remaining agent step and makes ONE Sonic call
    (only when a slot is free; never in the 02:00-05:00 board window).
    The reply is a JSON contract: {assessment, action, certainty}.
    Altair may only COMPLETE review-kind steps (assessment work);
    for execution steps a 'complete' verdict becomes a plan attached
    to the step plus a Morpheus-sized judgment follow-up — Altair
    breaking work down, per the council ruling. Under 90% certainty
    or an escalate verdict parks the step in held_brian with the
    assessment attached, ready for Brian in chat.

  MEGHAN (executive layer, :00/:30 cadence) — mechanics only for now:
    her engine (Prometheus/Gemma) is not served yet, so her pass does
    executive queue mechanics — aging high-priority steps gain
    priority — and says so plainly. No fake thinking.

Decisions Altair makes by judgment are written origin 'ecosystem'
(the ops decider acting under standing doctrine, no Brian involved).
Mechanical actions write origin 'system'.
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402
from morpheus_worker import extract_json  # noqa: E402

SONIC = "http://127.0.0.1:11439"
DESK_CODE = os.path.expanduser("~/campaignsdesk/code")


def dict_cur():
    import psycopg2.extras
    c = pm_core.psycopg2.connect(
        dbname="ecosystem_central", host="localhost",
        cursor_factory=psycopg2.extras.RealDictCursor)
    return c, c.cursor()


def release(cur, key, extra_payload=None):
    if extra_payload:
        cur.execute(
            """UPDATE successbrian_os.pm_steps
                  SET status='queued', actor=NULL, started_at=NULL,
                      payload = payload || %s::jsonb, updated_at=now()
                WHERE step_key=%s""", (json.dumps(extra_payload), key))
    else:
        cur.execute(
            """UPDATE successbrian_os.pm_steps
                  SET status='queued', actor=NULL, started_at=NULL,
                      updated_at=now()
                WHERE step_key=%s""", (key,))


# ---------------------------------------------------------------- LYRA
def lyra_bus_digest(cur, step):
    cur.execute(
        """SELECT id, sender, target, subject, body, urgency, created_at
             FROM altair.knowledge_bridge
            WHERE read_at IS NULL AND urgency IN ('critical','high')
            ORDER BY created_at""")
    msgs = cur.fetchall()
    digest = []
    for m in msgs:
        digest.append({
            "from": m["sender"], "to": m["target"],
            "urgency": m["urgency"], "subject": m["subject"],
            "at": m["created_at"].isoformat(),
            "body": (m["body"] or "")[:300]})
        cur.execute("UPDATE altair.knowledge_bridge SET read_at=now() "
                    "WHERE id=%s", (m["id"],))
    pm_core.finish(cur, step["step_key"], "done",
                   {"digested": len(digest), "messages": digest})
    pm_core.decide(cur, "lyra",
                   f"Lyra heartbeat digested {len(digest)} unread "
                   f"critical/high bus messages and marked them read",
                   step_key=step["step_key"], origin="system")
    return f"lyra: digested {len(digest)} bus criticals -> step done"


def lyra_desk_step(cur, step):
    payload = step_payload(cur, step["step_key"])
    sid = payload.get("signal_id")
    if not sid:
        release(cur, step["step_key"])
        return f"lyra: desk step {step['step_key']} has no signal_id — released"
    cur.execute("SELECT id, kind, title, body FROM campaignsdesk.signals "
                "WHERE id=%s", (sid,))
    sig = cur.fetchone()
    if not sig:
        pm_core.finish(cur, step["step_key"], "failed",
                       {"why": f"signal {sid} not found"})
        return f"lyra: desk step {step['step_key']} signal missing — failed"
    packet = {"signal_id": sid, "kind": sig["kind"], "title": sig["title"],
              "body": (sig["body"] or "")[:1500]}
    outcome = None
    try:
        sys.path.insert(0, DESK_CODE)
        from article_ideas import position
        outcome = position({"title": sig["title"], "body": sig["body"],
                            "kind": sig["kind"]})
    except Exception as e:
        outcome = {"_error": f"{type(e).__name__}: {e}"}
    if isinstance(outcome, dict) and "_error" not in outcome:
        status = str(outcome.get("status") or outcome.get("positioning")
                     or "").lower()
        if "hold" in status or "held" in status:
            pm_core.finish(cur, step["step_key"], "done",
                           {"packet": packet, "position": outcome,
                            "gate": "held"})
            return f"lyra: desk signal {sid} held by the gate — step done"
        if status:
            pm_core.finish(cur, step["step_key"], "done",
                           {"packet": packet, "position": outcome,
                            "gate": "positioned"})
            pm_core.add_step(
                cur, f"desk-idea-{sid}",
                f"Angle/brief judgment for positioned signal {sid}: "
                f"{sig['title']}"[:300],
                kind="judgment", origin="system", priority=40,
                payload={"instruction":
                         "Given this positioned CampaignsDesk signal, "
                         "propose the article angle and a one-paragraph "
                         "brief. Return JSON only.",
                         "context": json.dumps(
                             {"signal": packet, "position": outcome})[:6000],
                         "output_keys": ["angle", "brief", "confidence"]})
            return (f"lyra: desk signal {sid} positioned ({status}) — "
                    f"step done, Morpheus follow-up filed")
    release(cur, step["step_key"], {"packet": packet,
                                    "prepared_by": "lyra"})
    return (f"lyra: desk signal {sid} packet assembled — left queued "
            f"for judgment")


def step_payload(cur, key):
    cur.execute("SELECT payload FROM successbrian_os.pm_steps "
                "WHERE step_key=%s", (key,))
    row = cur.fetchone()
    return (row["payload"] if row else None) or {}


def lyra_pass(limit=3):
    c, cur = dict_cur()
    rows = pm_core.claim(cur, "lyra-heartbeat", limit=limit,
                         kinds=["review", "desk"])
    c.commit()
    lines = []
    for row in rows:
        step = {"id": row["id"] if isinstance(row, dict) else row[0],
                "step_key": row["step_key"] if isinstance(row, dict)
                else row[1]}
        kind = row["kind"] if isinstance(row, dict) else row[3]
        if kind == "review" and step["step_key"] == "intake-bridge-criticals":
            lines.append(lyra_bus_digest(cur, step))
        elif kind == "desk":
            lines.append(lyra_desk_step(cur, step))
        else:
            release(cur, step["step_key"])
            lines.append(f"lyra: released {step['step_key']} "
                         f"(not Lyra-shaped in v1)")
    c.commit()
    c.close()
    for line in lines:
        print(line)
    if not lines:
        print("lyra: nothing to claim")
    return lines


# ---------------------------------------------------------------- ALTAIR
def sonic_free_slot():
    try:
        with urllib.request.urlopen(f"{SONIC}/slots", timeout=3) as r:
            slots = json.loads(r.read().decode())
        return any(not s.get("is_processing") for s in slots)
    except Exception:
        return False


def sonic_judge(step, payload):
    context = json.dumps(payload)[:3000] if payload else ""
    prompt = (
        "You are Altair, operations decider for SuccessBrian OS. Assess "
        "this PM step and decide its disposition.\n"
        f"STEP: {step['title']}\nKIND: {step['kind']}\n"
        f"CONTEXT: {context}\n\n"
        "Reply with a single JSON object only: "
        '{"assessment": "one paragraph", "action": "complete" | '
        '"escalate_brian" | "needs_more_work", "certainty": 0.0-1.0, '
        '"followup": "a small follow-up task if any, else empty"}. '
        "Use complete ONLY if the step is assessment/review work that "
        "your assessment itself finishes. Execution work is never "
        "complete by assessment — give it needs_more_work with the plan "
        "in assessment and a Morpheus-sized followup.")
    body = json.dumps({
        "model": "qwen-a3b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": 900}).encode()
    req = urllib.request.Request(f"{SONIC}/v1/chat/completions",
                                 data=body,
                                 headers={"Content-Type":
                                          "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"]


def altair_pass():
    if 2 <= datetime.now().hour < 5:
        print("altair: board window (02:00-05:00) — no pitch-in calls")
        return []
    if not sonic_free_slot():
        print("altair: Sonic fully busy — chat keeps priority, skipping")
        return []
    c, cur = dict_cur()
    rows = pm_core.claim(cur, "altair-heartbeat", limit=1,
                         kinds=["repair", "build", "review", "desk"])
    c.commit()
    if not rows:
        c.close()
        print("altair: nothing to claim")
        return []
    row = rows[0]
    step = {"step_key": row["step_key"] if isinstance(row, dict) else row[1],
            "title": row["title"] if isinstance(row, dict) else row[2],
            "kind": row["kind"] if isinstance(row, dict) else row[3]}
    payload = step_payload(cur, step["step_key"])
    c.close()  # NEVER hold a DB connection across a model call (fleet law)
    try:
        raw = sonic_judge(step, payload)
        verdict = extract_json(raw)
    except Exception as e:
        verdict = None
        raw = f"{type(e).__name__}: {e}"
    c, cur = dict_cur()  # fresh connection to apply the outcome
    if not verdict or "action" not in verdict:
        release(cur, step["step_key"])
        c.commit()
        c.close()
        print(f"altair: no valid verdict for {step['step_key']} — released")
        return []
    action = verdict.get("action")
    certainty = float(verdict.get("certainty") or 0)
    lines = []
    if action == "complete" and certainty >= 0.90 \
            and step["kind"] == "review":
        pm_core.finish(cur, step["step_key"], "done",
                       {"altair_verdict": verdict})
        pm_core.decide(cur, "altair",
                       f"Altair decided: {step['title']} — "
                       f"{verdict.get('assessment', '')[:200]}",
                       step_key=step["step_key"], certainty=certainty,
                       origin="ecosystem")
        lines.append(f"altair: COMPLETED {step['step_key']} "
                     f"(certainty {certainty})")
    elif action == "complete" or action == "needs_more_work":
        followup = (verdict.get("followup") or "").strip()
        extra = {"altair_plan": verdict.get("assessment", "")}
        if followup:
            pm_core.add_step(
                cur, f"altair-followup-{step['step_key']}",
                f"Altair follow-up for {step['step_key']}: "
                f"{followup}"[:300],
                kind="judgment", origin="system", priority=50,
                payload={"instruction": followup,
                         "context": json.dumps(payload)[:4000],
                         "output_keys": ["result", "confidence"]})
            extra["followup_step"] = f"altair-followup-{step['step_key']}"
        release(cur, step["step_key"], extra)
        lines.append(f"altair: planned {step['step_key']} — plan attached"
                     + (", judgment follow-up filed" if followup else ""))
    else:
        cur.execute(
            """UPDATE successbrian_os.pm_steps
                  SET status='held_brian', result=%s::jsonb,
                      updated_at=now()
                WHERE step_key=%s""",
            (json.dumps({"altair_verdict": verdict}), step["step_key"]))
        pm_core.decide(cur, "altair",
                       f"Altair escalated to Brian: {step['title']} "
                       f"(certainty {certainty})",
                       step_key=step["step_key"], origin="system")
        lines.append(f"altair: ESCALATED {step['step_key']} to Brian "
                     f"(certainty {certainty})")
    c.commit()
    c.close()
    for line in lines:
        print(line)
    return lines


# ---------------------------------------------------------------- MEGHAN
def meghan_pass():
    c, cur = dict_cur()
    cur.execute(
        """SELECT step_key, priority FROM successbrian_os.pm_steps
            WHERE status='queued' AND priority >= 60
              AND created_at < now() - interval '24 hours'""")
    aged = cur.fetchall()
    lines = ["meghan: engine offline (Prometheus not served) — "
             "executive mechanics only"]
    for r in aged:
        key = r["step_key"] if isinstance(r, dict) else r[0]
        cur.execute(
            """UPDATE successbrian_os.pm_steps
                  SET priority = LEAST(95, priority + 5), updated_at=now()
                WHERE step_key=%s""", (key,))
        pm_core.decide(cur, "meghan",
                       f"Meghan pass (mechanics): aged step {key} "
                       f"priority raised", step_key=key, origin="system")
        lines.append(f"meghan: aged step {key} priority +5")
    c.commit()
    c.close()
    for line in lines:
        print(line)
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description="Heartbeat pitch-in")
    ap.add_argument("--agent", required=True,
                    choices=["lyra", "altair", "meghan"])
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args(argv)
    if args.agent == "lyra":
        lyra_pass(limit=args.limit)
    elif args.agent == "altair":
        altair_pass()
    else:
        meghan_pass()
    return 0


if __name__ == "__main__":
    sys.exit(main())
