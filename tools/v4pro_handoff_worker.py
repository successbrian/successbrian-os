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

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v4pro_router import get_availability, pq  # noqa: E402

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
    workers each get different rows, never the same handoff twice."""
    sql = ("UPDATE successbrian_os.v4pro_handoffs SET status = 'working' "
           "WHERE id IN (SELECT id FROM successbrian_os.v4pro_handoffs "
           "WHERE status = 'queued' ORDER BY created_at LIMIT %d "
           "FOR UPDATE SKIP LOCKED) RETURNING id;" % limit)
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print("claim failed: %s" % (r.stderr or "")[:150])
        return []
    # psql -t still prints the "UPDATE n" command tag — drop it, take ids only
    lines = [ln.strip() for ln in r.stdout.split("\n") if ln.strip()]
    lines = [ln for ln in lines if not ln.upper().startswith("UPDATE")]
    return [int(x) for x in lines if x.isdigit()]


def load_handoff(hid):
    sql = ("SELECT task_kind, task_summary, context, sonic_draft, ask, constraints "
           "FROM successbrian_os.v4pro_handoffs WHERE id = %d;" % hid)
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    parts = (r.stdout.strip().split("\t") + [""] * 6)[:6]
    return dict(zip(["kind", "summary", "context", "draft", "ask", "constraints"], parts))


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
    return r.stdout.strip() or "(no profile yet)"

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

RESEARCH_STAGES = [
    ("UNDERSTAND",
     "Restate the item in your own words. Map its Atlas connections — what "
     "depends on it, what it feeds. State clearly what is actually unknown "
     "vs. what the context already answers."),
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
     "could just do."),
]

def run_research_loop(key, h, hid):
    kind = "atlas-research"
    profile = load_profile(kind)
    learnings = load_learnings(kind)
    base_ctx = ("WORKER PROFILE:\n" + profile +
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
    sql = ("UPDATE successbrian_os.v4pro_handoffs SET status = %s, "
           "v4pro_result = %s, error = %s, completed_at = now() WHERE id = %d;"
           % (pq(status), pq(result[:20000]), pq(error[:1000]), hid))
    subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)


def release(hid):
    sql = ("UPDATE successbrian_os.v4pro_handoffs SET status = 'queued' "
           "WHERE id = %d;" % hid)
    subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)


FLEET_WORKERS = 4  # Brian 2026-10-17: 4 parallel workers
SLOTS_PER_WORKER = 2


def worker_main(slots=SLOTS_PER_WORKER):
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
            if h["kind"] == "atlas-research":
                print("#%d: profile-based research loop" % hid)
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
