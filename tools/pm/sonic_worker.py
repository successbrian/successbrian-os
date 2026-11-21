#!/usr/bin/env python3
"""Sonic judgment worker — the sonic judgment claimant (B12c).

B12b dispatch could not serve sonic-tier judgment: morpheus-worker
claimed EVERY judgment step, and serving sonic work on Morpheus would
be DOWNWARD overflow (forbidden), so sonic-tier looks filed a named
blocker instead. This worker is the missing claimant. It claims ONLY
judgment steps whose payload names engine_tier='sonic' (via the
tier filter in pm_core.claim, B12c) and serves each one as ONE small,
constrained Sonic call — the same house contract as morpheus_worker:

  payload = {"instruction": "...", "context": "...",
             "output_keys": ["verdict", "evidence"], "max_tokens": 800,
             "engine_tier": "sonic"}

Rules enforced in code, not in prompts (mirrored from morpheus_worker):
  * PACKET SIZE: instruction + context over MAX_PACKET_CHARS is refused
    ('packet too large — needs breakdown'). Oversized work goes back to
    be split, never stuffed into the model.
  * OUTPUT CONTRACT: the reply must contain a JSON object holding every
    named output key, with verdict dialects normalized onto the house
    contract {verdict, evidence} (shared _normalize_verdict — see
    morpheus_worker; a judge that rendered a verdict must not fail
    for dialect). Unparseable or verdict-less output FAILS the step —
    the worker never guesses or patches.
  * QUIET WINDOW: no model calls 02:00-05:00 (board window doctrine).
  * CONNECTION DISCIPLINE: no database connection is ever held open
    across a model call. Fetch, close, call, then finish on a fresh
    connection.
  * NEVER CLAIMS NON-SONIC WORK: the claim carries tier='sonic', so
    morpheus-tier and untiered (legacy) judgment steps stay with the
    morpheus-worker. A sonic-tier step is served on Sonic or not at
    all — never handed down.

Sonic endpoint: SONIC_URL (default http://127.0.0.1:11439/v1/chat/
completions, from sbos_common). Model: SONIC_MODEL, default qwen-a3b
— the model actually serving on 11439 per /v1/models 2026-11-13
(sbos_common.SONIC_MODEL default corrected to qwen-a3b,
improvement_log row 37, 2026-11-20.)

A finished judgment step stores {parsed, raw_tail} as its result.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402
import pm_core  # noqa: E402
import morpheus_worker as mw  # noqa: E402

ENDPOINT = os.environ.get("SONIC_URL", sbos_common.SONIC_URL)
MODEL = os.environ.get("SONIC_MODEL", "qwen-a3b")
MAX_PACKET_CHARS = 24000  # ~6k tokens: one question, one small packet
ACTOR = "sonic-worker"


def call_sonic(instruction, context, max_tokens):
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


def _finish(key, status, result):
    """Finish a step on a FRESH connection (see connection discipline)."""
    c = pm_core.conn()
    cur = c.cursor()
    pm_core.finish(cur, key, status, result)
    c.commit()
    c.close()


def run_step(row):
    _sid, key, _title, _kind, _pri, _origin = row
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute("SELECT payload FROM successbrian_os.pm_steps WHERE step_key=%s",
                (key,))
    payload = cur.fetchone()[0] or {}
    c.close()
    instruction = payload.get("instruction", "")
    context = payload.get("context", "")
    keys = payload.get("output_keys") or []
    max_tokens = int(payload.get("max_tokens", 800))
    if not instruction or not keys:
        _finish(key, "failed",
                {"why": "judgment step needs payload.instruction and "
                        "payload.output_keys"})
        return f"{key}: FAILED (bad payload)"
    if len(instruction) + len(context) > MAX_PACKET_CHARS:
        _finish(key, "failed",
                {"why": "packet too large — needs breakdown",
                 "chars": len(instruction) + len(context)})
        return f"{key}: FAILED (packet too large — needs breakdown)"
    try:
        raw = call_sonic(instruction, context, max_tokens)
    except Exception as e:
        _finish(key, "failed",
                {"why": f"sonic call: {type(e).__name__}: {e}"})
        return f"{key}: FAILED (call error)"
    parsed = mw.extract_json(raw)
    if parsed is None:
        _finish(key, "failed",
                {"why": "no JSON object in reply", "raw_tail": raw[-1000:]})
        return f"{key}: FAILED (no JSON)"
    normalized = mw._normalize_verdict(parsed)
    if normalized is not None:
        omitted = [k for k in keys if k not in normalized]
        if omitted:
            normalized["missing_keys"] = omitted
        _finish(key, "done", {"parsed": normalized,
                              "raw_tail": raw[-500:]})
        return (f"{key}: DONE (verdict {normalized['verdict']}, "
                f"dialect-normalized)")
    missing = [k for k in keys if k not in parsed]
    if missing:
        _finish(key, "failed",
                {"why": f"missing output keys: {missing}",
                 "raw_tail": raw[-1000:]})
        return f"{key}: FAILED (missing keys {missing})"
    _finish(key, "done", {"parsed": parsed, "raw_tail": raw[-500:]})
    return f"{key}: DONE {json.dumps(parsed)[:160]}"


def run_once(limit=1):
    if mw.in_quiet_window():
        print("quiet window (02:00-05:00) — no model calls")
        return []
    c = pm_core.conn()
    cur = c.cursor()
    # tier='sonic': ONLY sonic-tier judgment steps. Morpheus-tier and
    # untiered steps are the morpheus-worker's; claiming them here
    # would be upward routing of work that belongs below.
    rows = pm_core.claim(cur, ACTOR, limit=limit, kinds=["judgment"],
                         tier="sonic")
    c.commit()
    c.close()
    if not rows:
        print("no sonic judgment steps ready")
        return []
    lines = [run_step(r) for r in rows]
    for line in lines:
        print(line)
    return lines


def dialect_test():
    """Pure dialect probes (no model call, no DB): the shared verdict
    normalizer's cases, so the gamma-clerk persistence check can run
    this cheaply on every run-due without spending model calls."""
    return mw.dialect_test()


def selftest():
    dialect_test()
    # Routing probe (transactional, rolled back): tier='sonic' claims
    # ONLY the sonic-tier step; exclude_tier='sonic' (the morpheus
    # worker's filter) claims the morpheus-tier + untiered steps and
    # never the sonic one. The two filters are disjoint by
    # construction — a step has exactly one claimant.
    tag = f"sonic-selftest-{int(time.time())}"
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute("BEGIN")
    pm_core.add_step(
        cur, f"{tag}-sonic", "sonic routing probe", kind="judgment",
        priority=90,
        payload={"instruction": "probe", "context": "probe",
                 "output_keys": ["verdict"], "engine_tier": "sonic"})
    pm_core.add_step(
        cur, f"{tag}-morpheus", "morpheus routing probe",
        kind="judgment", priority=95,
        payload={"instruction": "probe", "context": "probe",
                 "output_keys": ["verdict"], "engine_tier": "morpheus"})
    pm_core.add_step(
        cur, f"{tag}-untiered", "untiered routing probe",
        kind="judgment", priority=80,
        payload={"instruction": "probe", "context": "probe",
                 "output_keys": ["verdict"]})
    sonic_rows = pm_core.claim(cur, "selftest-sonic", limit=10,
                               kinds=["judgment"], tier="sonic")
    assert [r[1] for r in sonic_rows] == [f"{tag}-sonic"], sonic_rows
    print("PASS sonic claim takes only the sonic-tier step")
    other_rows = pm_core.claim(cur, "selftest-morpheus", limit=10,
                               kinds=["judgment"], exclude_tier="sonic")
    assert sorted(r[1] for r in other_rows) == sorted(
        [f"{tag}-morpheus", f"{tag}-untiered"]), other_rows
    print("PASS morpheus exclusion takes morpheus + untiered, never sonic")
    cur.execute("ROLLBACK")
    c.close()
    # Live serving probe: one real Sonic call on a disposable
    # sonic-tier judgment step, plus the oversize refusal.
    c = pm_core.conn()
    cur = c.cursor()
    pm_core.add_step(
        cur, tag, "sonic worker selftest", kind="judgment", priority=96,
        payload={"instruction": "Read the context and report the color named in it.",
                 "context": "Field note: the test flag planted on the hill is blue.",
                 "output_keys": ["color"], "max_tokens": 300,
                 "engine_tier": "sonic"})
    pm_core.add_step(
        cur, f"{tag}-big", "oversize packet selftest", kind="judgment",
        priority=95,
        payload={"instruction": "Summarize.",
                 "context": "x" * (MAX_PACKET_CHARS + 1),
                 "output_keys": ["summary"], "max_tokens": 100,
                 "engine_tier": "sonic"})
    c.commit()
    c.close()
    lines = run_once(limit=2)
    joined = "\n".join(lines)
    assert f"{tag}: DONE" in joined and '"blue"' in joined, lines
    print("PASS Sonic judgment executed, JSON contract validated")
    assert "packet too large" in joined, lines
    print("PASS oversize packet refused — breakdown rule enforced")
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute("DELETE FROM successbrian_os.pm_steps WHERE step_key LIKE %s",
                (tag + "%",))
    c.commit()
    c.close()
    print("PASS cleanup — sonic worker selftest green")
    print("SONIC_WORKER_OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sonic judgment worker")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dialect-test", action="store_true",
                    help="pure verdict-dialect probes only (no model, "
                         "no DB) - the cheap QA persistence check")
    args = ap.parse_args(argv)
    if args.dialect_test:
        return dialect_test()
    if args.selftest:
        return selftest()
    if args.once:
        run_once(limit=args.limit)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
