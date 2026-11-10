#!/usr/bin/env python3
"""Heartbeat wake packets — the SBOS cron wakes the agent.

Brian, 2026-11-08: the Altair/Meghan heartbeats are SBOS crons
(not agent crons). They wake the actual agent profile EVERY
heartbeat to analyze and do work (hermes -p <profile> -z), and
they can also fire plain workers when only a worker is needed
(the engine queues + engine_runner are that worker lane).

This module assembles the tick's packet from the decider
record — what is waiting, what is owed, what changed — so the
agent wakes to facts, not a blank prompt. The agent's own
output is the heartbeat's business: it comes back on stdout
and is logged by the caller.
"""
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
import sbos_common  # noqa: E402

WAKE_INSTRUCTION = """You are being woken by your SBOS heartbeat cron. This is your regular half-hour turn to analyze and work — not a chat with Brian.

YOUR STATE OF PLAY:
{packet}

DO THIS TURN:
1. Analyze what is in front of you. The decider packages are your joint work with the other decider: either of you may break down a queued package, and a finished package needs BOTH of your independent reviews and votes — decided only when both agree at 98% certainty or more.
2. Do the work that is yours this turn using your tools: the decider machinery is /home/successbrian/successbrian-os/tools/decider_lib.py (tables successbrian_os.decider_packages and decider_reviews in ecosystem_central). Record breakdowns, task results you commission, reviews (VERDICT / CERTAINTY / DECISION / MISSING, in the decider_reviews shape) and decisions in the record — work that lives only in this conversation is lost.
3. If a piece of work only needs a worker, fire a worker instead of doing it yourself: enqueue a 'chat' job for the right engine (reap/sonic/morpheus/penny queues via sbos_common.engine_job_enqueue) — the engine runner executes it.
4. End with a short written summary of what you analyzed, what you did, and what you are leaving for the next heartbeat. No messages to Brian from this wake — anything he must see goes into the record (a capture in atlas.scattered_captures) for the clerk to surface."""

ROLODEX_INSTRUCTION = """ROLODEX — YOUR STANDING PASS EVERY HEARTBEAT (Brian, 2026-11-09):
Brian has given you the Rolodex. It is an Atlas project (proj:rolodex) in Altair's second brain, with its own AnythingLLM workspace ('rolodex'). Every heartbeat, alongside your decider work, do a Rolodex pass IN DEPTH:
READ FIRST, from the second brain, never from memory alone: the ROLODEX section in your packet (live Atlas project state, newest Rolodex captures, Brian's newest Rolodex decisions, the QA check's last verdict), the rolodex AnythingLLM workspace (rolodex-charter.md and rolodex-heartbeat-latest.md — your last pass), and, when you need more, the Agent Knowledge Gateway: ~/successbrian-os/tools/ecosystem_intel/agent_knowledge.py --briefing "Rolodex".
THINK with the engines Brian named: Sonic, DeepSeek 150B (REAP), and Morpheus. Fire engine jobs for the heavy reading and deep passes (sbos_common.engine_job_enqueue on the sonic / reap / morpheus queues) and consume their results when they land — this turn or a later heartbeat — building pass over pass on two aims: better integration of the Rolodex into SuccessBrian OS, and making the Rolodex itself better and better. If a named engine is unavailable in a pass, say so in your write-back; never fake a pass.
WRITE BACK every pass, all three: (1) file your findings as a capture (~/successbrian-os/tools/atlas/scattered_brain.py capture) so the clerk surfaces them and the ecosystem sees them; (2) replace rolodex-heartbeat-latest.md in the rolodex AnythingLLM workspace with this pass (~/successbrian-os/tools/atlas/allm_embed.py rolodex rolodex-heartbeat-latest.md <your file>); (3) whenever the pass changes the project's state or design, update the Atlas proj:rolodex summary/details to match.
Hold the Rolodex the way Brian holds it: it is a graph, loosely — his contacts (he brought them all in; you can find them, they stay his), multiple promotions running at once, the wider sorting and sifting of everybody from real sources only, unknown stays unknown, and no single company or promotion defines a person. This standing pass is thinking, designing, and filing only: never send anything to a contact and never buy anything on it."""


def rolodex_packet():
    """The read-from half: live Rolodex state from the second
    brain, assembled fresh each wake. Every source degrades to a
    plain line on failure — a broken source must never break the
    wake."""
    lines = ["ROLODEX — live from the second brain (proj:rolodex):"]
    try:
        rows = sbos_common.pg_rows(
            "SELECT status, left(summary, 400) FROM atlas.nodes "
            "WHERE node_key = 'proj:rolodex'")
        if rows:
            lines.append("  Atlas project: %s — %s" % (rows[0][0], rows[0][1]))
        else:
            lines.append("  Atlas project: proj:rolodex NOT FOUND")
    except Exception as e:
        lines.append("  Atlas project: unavailable (%s)" % e)
    try:
        rows = sbos_common.pg_rows(
            "SELECT last_status, last_run_at FROM "
            "successbrian_os.pm_project_checks "
            "WHERE project_key = 'rolodex-meghan-heartbeat'")
        if rows:
            lines.append("  QA check (fresh Rolodex-thinking output): "
                         "last=%s at %s" % (rows[0][0], rows[0][1]))
    except Exception as e:
        lines.append("  QA check: unavailable (%s)" % e)
    try:
        rows = sbos_common.pg_rows(
            "SELECT id, left(title, 95), status FROM "
            "atlas.scattered_captures WHERE title ILIKE '%rolodex%' "
            "OR context ILIKE '%rolodex%' ORDER BY id DESC LIMIT 5")
        if rows:
            lines.append("  Newest Rolodex captures:")
            for cid, title, st in rows:
                lines.append("    #%s [%s] %s" % (cid, st, title))
    except Exception as e:
        lines.append("  Rolodex captures: unavailable (%s)" % e)
    try:
        rows = sbos_common.pg_rows(
            "SELECT decision_id, left(question, 95) FROM "
            "altair.brian_decisions WHERE question ILIKE '%rolodex%' "
            "OR context ILIKE '%rolodex%' OR answer ILIKE '%rolodex%' "
            "ORDER BY id DESC LIMIT 3")
        if rows:
            lines.append("  Brian's newest Rolodex decisions:")
            for did, q in rows:
                lines.append("    %s: %s" % (did, q))
    except Exception as e:
        lines.append("  Rolodex decisions: unavailable (%s)" % e)
    return "\n".join(lines)




def build_packet(seat):
    other = "meghan" if seat == "altair" else "altair"
    lines = []
    counts = sbos_common.pg_rows(
        "SELECT status, count(*) FROM "
        "successbrian_os.decider_packages GROUP BY 1 ORDER BY 1")
    lines.append("Decider packages by status: "
                 + (", ".join("%s=%s" % (a, b) for a, b in counts)
                    or "none"))
    queued = sbos_common.pg_rows(
        "SELECT id, left(title, 90), round FROM "
        "successbrian_os.decider_packages WHERE status = 'queued' "
        "ORDER BY id LIMIT 5")
    if queued:
        lines.append("Waiting to be broken down (oldest first):")
        for pid, title, rnd in queued:
            lines.append("  pkg #%s (round %s): %s" % (pid, rnd, title))
    ready = sbos_common.pg_rows(
        "SELECT p.id, left(p.title, 90), p.round, "
        "(SELECT count(*) FROM successbrian_os.decider_reviews r "
        "WHERE r.package_id = p.id AND r.round = p.round) "
        "FROM successbrian_os.decider_packages p "
        "WHERE p.status = 'ready_for_review' ORDER BY p.id LIMIT 5")
    if ready:
        lines.append("Finished packages awaiting reviews:")
        for pid, title, rnd, votes in ready:
            lines.append("  pkg #%s (round %s, %s/2 votes in): %s"
                         % (pid, rnd, votes, title))
    inflight = sbos_common.pg_rows(
        "SELECT id, left(title, 90) FROM "
        "successbrian_os.decider_packages "
        "WHERE status IN ('breaking_down','in_progress') "
        "ORDER BY id LIMIT 5")
    if inflight:
        lines.append("Packages with engine tasks in flight: "
                     + ", ".join("#%s %s" % (a, b) for a, b in inflight))
    decided = sbos_common.pg_rows(
        "SELECT id, left(title, 80) FROM "
        "successbrian_os.decider_packages WHERE status = 'decided' "
        "AND decided_at > now() - interval '2 hours' ORDER BY id")
    if decided:
        lines.append("Decided in the last 2 hours: "
                     + ", ".join("#%s %s" % (a, b) for a, b in decided))
    lines.append("You are %s. The other decider is %s. Your "
                 "heartbeat partner's work is in the same tables — "
                 "read before you duplicate." % (seat, other))
    if seat == "meghan":
        lines.append(rolodex_packet())
    return "\n".join(lines)


def wake_prompt(seat):
    prompt = WAKE_INSTRUCTION.format(packet=build_packet(seat))
    if seat == "meghan":
        prompt = prompt + "\n\n" + ROLODEX_INSTRUCTION
    return prompt


if __name__ == "__main__":
    seat = sys.argv[1] if len(sys.argv) > 1 else "altair"
    print(wake_prompt(seat))
