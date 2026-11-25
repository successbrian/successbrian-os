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
  * CONNECTION DISCIPLINE: no database connection is ever held open
    across a model call. This fleet's PG connections die when held
    idle across long calls ('SSL connection has been closed
    unexpectedly' — learned live twice on 2026-10-24). Fetch, close,
    call, then finish on a fresh connection.

A finished judgment step stores {parsed, raw_tail} as its result.
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


_PASS_WORDS = ("pass", "passed", "ok", "true", "yes")


def _normalize_verdict(parsed):
    """Map a judge reply in a known dialect onto the house contract
    {verdict, evidence}. Returns the normalized dict, or None when the
    reply carries no recognizable verdict. Dialects seen in the wild:
    {verdict: ...} (house), {status: PASS/FAIL, reasons: [...]},
    {result: PASS/FAIL, ...} and {pass: true/false, reason: ...}.
    {conditions_held: [...], conditions_not_held: [...]} (a checklist
    verdict: pass iff nothing is not held), and a verdict object nested
    one level down under a wrapper key (e.g. {"report": {"result":
    "PASS", ...}} — the wrapper itself carries no verdict key).
    Extended 2026-11-25 (review pass, check 637): the two shapes that
    failed as 'missing output keys' on pm_steps 11960/12095.
    A judge that rendered a verdict must not be executed for dialect:
    until 2026-11-13 the worker failed those steps as 'missing output
    keys' and 29 QA checks recorded machinery failures instead of the
    real verdicts their judges had already given. Extended 2026-11-13
    (cycle #172, check 637): three more failures the same morning
    carried {result: PASS/FAIL} and one carried {pass: false} - same
    verdict, different key. A reply with no verdict-bearing key at
    all (e.g. a free-form improvement text) still fails as before:
    no verdict was rendered, so there is nothing to normalize."""
    if not isinstance(parsed, dict):
        return None
    verdict = None
    conditions_evidence = None
    if "verdict" in parsed:
        v = parsed["verdict"]
        verdict = ("pass" if (v is True or str(v).strip().lower()
                              in _PASS_WORDS) else "fail")
    elif "status" in parsed:
        s = str(parsed["status"]).strip().lower()
        if s:
            verdict = "pass" if s in _PASS_WORDS else "fail"
    elif "result" in parsed:
        r = parsed["result"]
        if isinstance(r, bool):
            verdict = "pass" if r else "fail"
        else:
            s = str(r).strip().lower()
            if s:
                verdict = "pass" if s in _PASS_WORDS else "fail"
    elif "pass" in parsed:
        p = parsed["pass"]
        if isinstance(p, bool):
            verdict = "pass" if p else "fail"
        else:
            s = str(p).strip().lower()
            if s:
                verdict = "pass" if s in _PASS_WORDS else "fail"
    elif "conditions_held" in parsed or "conditions_not_held" in parsed:
        held = parsed.get("conditions_held")
        not_held = parsed.get("conditions_not_held")
        if isinstance(held, list) and isinstance(not_held, list):
            verdict = "pass" if not not_held else "fail"
            conditions_evidence = (
                "held: " + ", ".join(str(x) for x in held)
                + "; not held: " + ", ".join(str(x) for x in not_held))
    if verdict is None:
        # One level down: the verdict object nested under a wrapper key.
        # Only the unambiguous keys ("verdict"/"result") count here —
        # "status"/"pass" are too generic to trust nested (a queue
        # snapshot's {"status": "pending"} is not a verdict). Exactly
        # one nested verdict-bearing object must exist; otherwise the
        # reply stays unrecognized rather than guessed.
        nested = [v for v in parsed.values()
                  if isinstance(v, dict)
                  and ("verdict" in v or "result" in v)]
        if len(nested) == 1:
            inner = _normalize_verdict(nested[0])
            if inner is not None:
                out = dict(parsed)
                out["verdict"] = inner["verdict"]
                if "evidence" not in out:
                    out["evidence"] = inner.get("evidence", "")
                return out
        return None
    out = dict(parsed)
    out["verdict"] = verdict
    if "evidence" not in out:
        ev = (conditions_evidence or out.get("reasons")
              or out.get("reason"))
        if ev is None:
            det = out.get("details")
            if isinstance(det, str):
                ev = det
            elif det is not None:
                ev = json.dumps(det)[:500]
        out["evidence"] = ev or ""
    return out


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
        raw = call_morpheus(instruction, context, max_tokens)
    except Exception as e:
        _finish(key, "failed",
                {"why": f"morpheus call: {type(e).__name__}: {e}"})
        return f"{key}: FAILED (call error)"
    parsed = extract_json(raw)
    if parsed is None:
        _finish(key, "failed",
                {"why": "no JSON object in reply", "raw_tail": raw[-1000:]})
        return f"{key}: FAILED (no JSON)"
    normalized = _normalize_verdict(parsed)
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
    if in_quiet_window():
        print("quiet window (02:00-05:00) — no model calls")
        return []
    c = pm_core.conn()
    cur = c.cursor()
    # B12c: Morpheus NEVER claims sonic-tier judgment steps. Serving
    # sonic work on Morpheus would be downward overflow (forbidden);
    # the sonic-worker owns those (tier='sonic' in the payload).
    rows = pm_core.claim(cur, ACTOR, limit=limit, kinds=["judgment"],
                         exclude_tier="sonic")
    c.commit()
    c.close()
    if not rows:
        print("no judgment steps ready")
        return []
    lines = [run_step(r) for r in rows]
    for line in lines:
        print(line)
    return lines


def dialect_test():
    """Pure dialect probes (no model call, no DB): the exact shapes
    that failed as 'missing output keys' on 2026-11-13 (check 637).
    Prints DIALECT_OK so the gamma-clerk persistence check can run
    it cheaply on every run-due without spending model calls."""
    dialect_cases = [
        ({"result": "PASS", "details": {"workspace_id": 149}}, "pass"),
        ({"result": "FAIL", "reason": "no install report exists"},
         "fail"),
        ({"result": "FAIL"}, "fail"),
        ({"pass": False, "reason": "Lack of evidence"}, "fail"),
        ({"status": "FAIL", "stage": "factcheck",
          "details": "factcheck output does not exist"}, "fail"),
        ({"verdict": "pass", "evidence": "on record"}, "pass"),
        # 2026-11-25 (review pass, check 637): the conditions checklist
        # shape from pm_steps 11960, and a verdict nested one level
        # down under a wrapper key (pm_steps 12095).
        ({"conditions_held": ["body_text_serif"],
          "conditions_not_held": []}, "pass"),
        ({"conditions_held": ["body_text_serif"],
          "conditions_not_held": ["comfortable_reading_size",
                                  "clear_blank_space_between_paragraphs"]},
         "fail"),
        ({"report": {"result": "PASS", "confidence": 0.9}}, "pass"),
        ({"report": {"result": "FAIL", "reason": "queue stuck"}},
         "fail"),
    ]
    for raw_in, want in dialect_cases:
        got = _normalize_verdict(raw_in)
        assert got is not None and got["verdict"] == want, (raw_in, got)
    ev = _normalize_verdict({"status": "FAIL", "stage": "factcheck",
                             "details": "factcheck output missing"})
    assert ev["evidence"] == "factcheck output missing", ev
    assert _normalize_verdict(
        {"improvement": "Introduce a quiet-pain detector"}) is None
    # Ambiguous or verdict-free nested shapes stay unrecognized.
    assert _normalize_verdict(
        {"a": {"result": "PASS"}, "b": {"result": "FAIL"}}) is None
    assert _normalize_verdict(
        {"snapshot": {"status_counts": {"pending": 1}}}) is None
    ev2 = _normalize_verdict(
        {"conditions_held": ["a"], "conditions_not_held": ["b"]})
    assert ev2["evidence"] == "held: a; not held: b", ev2
    print(f"DIALECT_OK ({len(dialect_cases)} cases; no-verdict reply "
          "still unrecognized)")
    return 0


def selftest():
    dialect_test()
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
    c.commit()
    c.close()
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
    c.commit()
    c.close()
    print("PASS cleanup — morpheus worker selftest green")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Morpheus judgment worker")
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
        selftest()
        return 0
    if args.once:
        run_once(limit=args.limit)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
