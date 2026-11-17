#!/usr/bin/env python3
"""
distill — the model leg of the Distillation System (design
2026-11-17, Part 2). The deterministic leg (rulings_bridge)
promotes captures carrying Brian's verbatim words. This leg
handles the rest of the triaged intake: durable learnings hiding
in ordinary captures.

Pipeline per capture, on the fleet's 30-minute cycle:
  DRAFT   Morpheus proposes candidate learnings, each with the
          EXACT source span it came from. No span, no candidate.
  CHECK   Deterministic: the span must be a verbatim substring of
          the capture text. Code decides, not the model.
  VERIFY  Sonic judges whether the span actually supports the
          claim (SUPPORTS / NO). The drafter never grades itself.
  FILE    engine_research.file_finding writes the learning
          ADD-only, evidence attached, conflict gate active.
          This leg NEVER writes decisions — decisions come only
          from Brian's verbatim words (bridge) or Brian himself.

Every processed capture is logged in altair.distill_log, so the
cycle is idempotent and resumable: kill it mid-run and the next
cycle picks up where it stopped, nothing double-filed.

Usage: distill.py [--limit N] [--dry-run] | selftest
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_research import _rows, _exec, file_finding  # noqa: E402
from sbos_common import llm_chat, MORPHEUS_URL, MORPHEUS_MODEL  # noqa: E402
from sbos_common import SONIC_URL, SONIC_MODEL  # noqa: E402

DRAFT_PROMPT = """You extract durable learnings from one intel capture
for a personal knowledge system. A learning is a fact, preference,
state, or decision-relevant detail that will still matter in a
month. News noise, prices, and one-off chatter are NOT learnings.

Capture title: {title}
Capture text:
{text}

Output ONLY a JSON array (no prose) of up to 3 objects:
[{{"claim": "<one-sentence learning>", "span": "<exact verbatim
substring of the capture text that proves the claim>"}}]
The span MUST be copied character-for-character from the text
above. If there is nothing durable, output []."""

VERIFY_PROMPT = """You verify one extracted learning. Answer with
exactly one word: SUPPORTS if the source span fully supports the
claim, or NO if it does not, only partly does, or adds anything
beyond the span.

Claim: {claim}
Source span: {span}"""


def parse_drafts(out):
    """Pull the JSON array out of a model reply; [] on any doubt."""
    m = re.search(r"\[.*\]", out or "", re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    cands = []
    for it in arr if isinstance(arr, list) else []:
        if isinstance(it, dict) and it.get("claim") and \
                it.get("span"):
            cands.append({"claim": str(it["claim"]).strip(),
                          "span": str(it["span"]).strip()})
    return cands[:3]


def span_ok(span, text):
    """The deterministic gate: verbatim substring or rejected."""
    return bool(span) and len(span) >= 25 and span in (text or "")


def distill_capture(cap, dry_run=False):
    # Sizing measured 2026-11-17: Morpheus generation on the
    # loaded box runs ~1 tok/s-class for long outputs — a 6,000
    # char prefill + 700-token draft blew a 240s timeout. The
    # durable content of a capture is front-loaded; 3,000 chars
    # and a 450-token draft fit the leg's real speed.
    text = (cap.get("raw_text") or "")[:3000]
    title = cap.get("title") or "capture"
    out, _u = llm_chat(prompt=DRAFT_PROMPT.format(
        title=title, text=text), url=MORPHEUS_URL,
        model=MORPHEUS_MODEL, max_tokens=450, timeout=600)
    cands = parse_drafts(out)
    stats = {"drafted": len(cands), "span_rejected": 0,
             "verify_rejected": 0, "filed": 0, "parked": 0}
    for c in cands:
        if not span_ok(c["span"], text):
            stats["span_rejected"] += 1
            continue
        vout, _u2 = llm_chat(prompt=VERIFY_PROMPT.format(
            claim=c["claim"], span=c["span"]), url=SONIC_URL,
            model=SONIC_MODEL, max_tokens=10, timeout=120)
        if not (vout or "").strip().upper().startswith("SUPPORTS"):
            stats["verify_rejected"] += 1
            continue
        if dry_run:
            stats["filed"] += 1
            continue
        res = file_finding(
            {"topic": title[:120], "claim": c["claim"],
             "evidence": ["capture #%d span: %s"
                          % (cap["id"], c["span"])],
             "provenance": {"type": "source",
                            "source": "distill:capture-%d"
                                      % cap["id"]},
             "workspace_slug": cap.get("workspace_slug")},
            homes=("learning",))
        if res.get("learning") == "inserted":
            stats["filed"] += 1
        elif "PARKED" in str(res.get("learning", "")):
            stats["parked"] += 1
    return stats


def run(limit=8, dry_run=False):
    # Error outcomes are RETRYABLE (a slow night must not
    # permanently skip a capture): only non-error log rows count
    # as processed.
    caps = _rows(
        "SELECT c.id, c.title, c.raw_text, c.workspace_slug FROM "
        "atlas.scattered_captures c WHERE c.status = 'triaged' "
        "AND length(c.raw_text) > 200 AND c.title NOT LIKE "
        "'Ruling-audit flag%%' AND c.title NOT LIKE 'FRESHNESS "
        "ALARM%%' AND NOT EXISTS (SELECT 1 FROM altair.distill_log "
        "d WHERE d.capture_id = c.id AND d.outcome NOT LIKE "
        "'error%%') ORDER BY c.created_at LIMIT %s",
        (limit,))
    totals = {"captures": 0, "drafted": 0, "span_rejected": 0,
              "verify_rejected": 0, "filed": 0, "parked": 0,
              "errors": 0}
    for cap in caps:
        totals["captures"] += 1
        try:
            s = distill_capture(cap, dry_run=dry_run)
            for k in s:
                totals[k] += s[k]
            outcome = "filed:%d parked:%d" % (s["filed"], s["parked"])
            detail = json.dumps(s)
        except Exception as e:
            totals["errors"] += 1
            outcome, detail = "error", str(e)[:200]
        if not dry_run:
            _exec("INSERT INTO altair.distill_log (capture_id, "
                  "outcome, detail) VALUES (%s, %s, %s) ON CONFLICT "
                  "(capture_id) DO UPDATE SET outcome = "
                  "EXCLUDED.outcome, detail = EXCLUDED.detail, "
                  "created_at = now()",
                  (cap["id"], outcome, detail))
        print("capture %d: %s %s" % (cap["id"], outcome, detail),
              flush=True)
    print(totals)
    return totals


def selftest():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(("PASS " if cond else "FAIL ") + name)

    check("parse clean JSON array",
          parse_drafts('[{"claim": "a fact here", "span": "some '
                       'span text"}]') ==
          [{"claim": "a fact here", "span": "some span text"}])
    check("parse prose-wrapped JSON",
          len(parse_drafts('Sure: [{"claim": "x", "span": "y"}] '
                           'done')) == 1)
    check("parse garbage -> []", parse_drafts("no json") == [])
    check("span verbatim accepted",
          span_ok("the quick brown fox jumps",
                  "xx the quick brown fox jumps yy"))
    check("span paraphrase rejected",
          not span_ok("the quick brown fox leaps",
                      "xx the quick brown fox jumps yy"))
    check("span too short rejected",
          not span_ok("short", "a short text"))
    failed = [n for n, ok in checks if not ok]
    print("SELFTEST " + ("OK" if not failed else
                         "FAILED: " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "selftest":
        sys.exit(selftest())
    dry = "--dry-run" in args
    limit = 8
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    run(limit=limit, dry_run=dry)
