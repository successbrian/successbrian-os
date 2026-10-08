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
    sql = ("SELECT id FROM successbrian_os.v4pro_handoffs "
           "WHERE status = 'queued' ORDER BY created_at LIMIT %d;" % limit)
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    ids = [ln.strip() for ln in r.stdout.split("\n") if ln.strip().isdigit()]
    claimed = []
    for hid in ids:
        u = ("UPDATE successbrian_os.v4pro_handoffs SET status = 'working' "
             "WHERE id = %s AND status = 'queued';" % hid)
        ru = subprocess.run(PSQL + ["-c", u], capture_output=True, text=True, timeout=30)
        if ru.returncode == 0:
            claimed.append(int(hid))
    return claimed


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


def mark(hid, status, result="", error=""):
    sql = ("UPDATE successbrian_os.v4pro_handoffs SET status = %s, "
           "v4pro_result = %s, error = %s, completed_at = now() WHERE id = %d;"
           % (pq(status), pq(result[:20000]), pq(error[:1000]), hid))
    subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)


def release(hid):
    sql = ("UPDATE successbrian_os.v4pro_handoffs SET status = 'queued' "
           "WHERE id = %d;" % hid)
    subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)


def main():
    key = get_key()
    if not key:
        print("no DEEPSEEK_API_KEY — worker idle")
        return 0
    claimed = claim_handoffs()
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
            result = call_v4pro(key, build_prompt(h))
            mark(hid, "done", result=result)
            print("#%d: done (%d chars)" % (hid, len(result)))
        except Exception as e:
            mark(hid, "failed", error=str(e))
            print("#%d: failed: %s" % (hid, str(e)[:200]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
