#!/usr/bin/env python3
"""Morpheus judgment worker — the decomposition ruling, built.

Brian (2026-10-24): Altair, Meghan, and Lyra break work down so that
Morpheus can run a lot of things. This worker is the executing half of
that ruling. It claims PM steps of kind 'judgment' and runs each one as
ONE small, constrained Morpheus call:

  payload = {"instruction": "...", "context": "...",
             "output_keys": ["angle", "confidence"], "max_tokens": 800}

Rules enforced in code, not in prompts:
  * PACKET SIZE: instruction + context over MAX_PACKET_CHARS is refused
    ('packet too large — needs breakdown'). Oversized work goes back to
    the council to be split, never stuffed into the model.
  * OUTPUT CONTRACT: the reply must contain a JSON object holding every
    named output key. Unparseable or incomplete output FAILS the step —
    the worker never guesses or patches.
  * QUIET WINDOW: no model calls 02:00-05:00 (board window doctrine).

A finished judgment step stores {parsed, raw_tail} as its result. What
the judgment MEANS is the claiming layer's business; this worker only
guarantees small-in, contract-checked-out.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

ENDPOINT = "http://127.0.0.1:11437/v1/chat/completions"
MODEL = "morpheus"
MAX_PACKET_CHARS = 24000  # ~6k tokens: one question, one small packet
ACTOR = "morpheus-worker"


def in_quiet_window(now=None):
    h = (now or datetime.now()).hour
    return 2 <= h < 5


def call_morpheus(instruction, context, max_tokens):
    prompt = (
        f"{instruction}\n\nCONTEXT:\n{context}\n\n"
        "Reply with a single JSON object only — no prose, no markdown fences.")
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"]


def extract_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def run_step(row):
    _sid, key, _title, _kind, _pri, _origin = row
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute("SELECT payload FROM successbrian_os.pm_steps WHERE step_key=%s",
                (key,))
    payload = cur.fetchone()[0] or {}
    instruction = payload.get("instruction", "")
    context = payload.get("context", "")
    keys = payload.get("output_keys") or []
    max_tokens = int(payload.get("max_tokens", 800))
    if not instruction or not keys:
        pm_core.finish(cur, key, "failed",
                       {"why": "judgment step needs payload.instruction and payload.output_keys"})
        c.commit(); c.close()
        return f"{key}: FAILED (bad payload)"
    if len(instruction) + len(context) > MAX_PACKET_CHARS:
        pm_core.finish(cur, key, "failed",
                       {"why": "packet too large — needs breakdown",
                        "chars": len(instruction) + len(context)})
        c.commit(); c.close()
        return f"{key}: FAILED (packet too large — needs breakdown)"
    try:
        raw = call_morpheus(instruction, context, max_tokens)
    except Exception as e:
        pm_core.finish(cur, key, "failed", {"why": f"morpheus call: {type(e).__name__}: {e}"})
        c.commit(); c.close()
        return f"{key}: FAILED (call error)"
    parsed = extract_json(raw)
    if parsed is None:
        pm_core.finish(cur, key, "failed",
                       {"why": "no JSON object in reply", "raw_tail": raw[-1000:]})
        c.commit(); c.close()
        return f"{key}: FAILED (no JSON)"
    missing = [k for k in keys if k not in parsed]
    if missing:
        pm_core.finish(cur, key, "failed",
                       {"why": f"missing output keys: {missing}", "raw_tail": raw[-1000:]})
        c.commit(); c.close()
        return f"{key}: FAILED (missing keys {missing})"
    pm_core.finish(cur, key, "done", {"parsed": parsed, "raw_tail": raw[-500:]})
    c.commit(); c.close()
    return f"{key}: DONE {json.dumps(parsed)[:160]}"


def run_once(limit=1):
    if in_quiet_window():
        print("quiet window (02:00-05:00) — no model calls")
        return []
    c = pm_core.conn()
    cur = c.cursor()
    rows = pm_core.claim(cur, ACTOR, limit=limit, kinds=["judgment"])
    c.commit(); c.close()
    if not rows:
        print("no judgment steps ready")
        return []
    lines = [run_step(r) for r in rows]
    for line in lines:
        print(line)
    return lines


def selftest():
    tag = f"morpheus-selftest-{int(time.time())}"
    c = pm_core.conn()
    cur = c.cursor()
    pm_core.add_step(
        cur, tag, "morpheus worker selftest", kind="judgment", priority=96,
        payload={"instruction": "Read the context and report the color named in it.",
                 "context": "Field note: the test flag planted on the hill is blue.",
                 "output_keys": ["color"], "max_tokens": 300})
    pm_core.add_step(
        cur, f"{tag}-big", "oversize packet selftest", kind="judgment",
        priority=95,
        payload={"instruction": "Summarize.",
                 "context": "x" * (MAX_PACKET_CHARS + 1),
                 "output_keys": ["summary"], "max_tokens": 100})
    c.commit(); c.close()
    lines = run_once(limit=2)
    joined = "\n".join(lines)
    assert f"{tag}: DONE" in joined and '"blue"' in joined, lines
    print("PASS Morpheus judgment executed, JSON contract validated")
    assert "packet too large" in joined, lines
    print("PASS oversize packet refused — breakdown rule enforced")
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute("DELETE FROM successbrian_os.pm_steps WHERE step_key LIKE %s",
                (tag + "%",))
    c.commit(); c.close()
    print("PASS cleanup — morpheus worker selftest green")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Morpheus judgment worker")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if args.once:
        run_once(limit=args.limit)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
