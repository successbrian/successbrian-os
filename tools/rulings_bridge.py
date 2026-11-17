#!/usr/bin/env python3
"""
rulings_bridge — promote ruling captures into Brian's curated stores.

Brian's order (2026-11-17 01:43 CST: "do everything you are 100%
confident in"), fixing the diagnosis of the same night: intel intake
(atlas.scattered_captures) is healthy, but altair.brian_decisions
froze 2026-10-31 and altair.brian_learnings froze 2026-11-02 because
nothing distilled captures into them.

This bridge is the DETERMINISTIC leg of that distillation — no model
in the loop, so nothing here can hallucinate a ruling:

  SELECT captures carrying the ruling-audit format
         (a CLAIM line + a BRIAN'S QUOTED WORDS line)
  PARSE  claim + verbatim quote out of the capture text
  VERIFY the quote is present and non-trivial, the claim non-empty
  WRITE  one altair.brian_decisions row (answer = claim + quote,
         context names the source capture) and one
         altair.brian_learnings row per capture
  SKIP   any capture already bridged (idempotent by source marker)

Captures without a verbatim quote are NOT promoted — under the
ruling-provenance standard they are interpretations, and promoting
them is model work (the research.verify packet's job), not this
bridge's. The bridge reports how many it skipped and why.

Usage: rulings_bridge.py [--dry-run] [--limit N]
"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_research import _rows, _one, _exec  # noqa: E402

CLAIM_RE = re.compile(r"^CLAIM:\s*(.+)$", re.M)
QUOTE_RE = re.compile(r"^BRIAN'S QUOTED WORDS:\s*(.+)$", re.M)
ATTR_RE = re.compile(r"\s*\(Brian,.*$", re.S)


def parse_capture(raw):
    cm = CLAIM_RE.search(raw or "")
    qm = QUOTE_RE.search(raw or "")
    if not cm or not qm:
        return None
    claim = ATTR_RE.sub("", cm.group(1)).strip()
    quote = qm.group(1).strip().strip('"')
    if len(claim) < 8 or len(quote) < 10:
        return None
    return claim, quote


def already_bridged(capture_id):
    marker = "rulings_bridge:capture-%d" % capture_id
    d = _one("SELECT id FROM altair.brian_decisions WHERE context "
             "LIKE %s", ("%" + marker + "%",))
    l = _one("SELECT id FROM altair.brian_learnings WHERE source = %s",
             (marker,))
    return bool(d), bool(l), marker


def bridge(limit=None, dry_run=False):
    rows = _rows("SELECT id, title, raw_text, created_at FROM "
                 "atlas.scattered_captures WHERE raw_text LIKE %s "
                 "ORDER BY created_at",
                 ("%BRIAN'S QUOTED WORDS:%",))
    if limit:
        rows = rows[:limit]
    stats = {"seen": len(rows), "parsed": 0, "skipped_parse": 0,
             "already": 0, "decisions": 0, "learnings": 0}
    for r in rows:
        parsed = parse_capture(r["raw_text"])
        if not parsed:
            stats["skipped_parse"] += 1
            continue
        stats["parsed"] += 1
        claim, quote = parsed
        has_d, has_l, marker = already_bridged(r["id"])
        if has_d and has_l:
            stats["already"] += 1
            continue
        if dry_run:
            stats["decisions"] += 0 if has_d else 1
            stats["learnings"] += 0 if has_l else 1
            continue
        if not has_d:
            _exec("INSERT INTO altair.brian_decisions (decision_id, "
                  "question, context, answer, answered_at, asked_at) "
                  "VALUES (%s, %s, %s, %s, %s, %s)",
                  ("bridge-cap-%d" % r["id"], claim[:300],
                   "Intel Bridge capture #%d via %s; %s"
                   % (r["id"], marker, (r["title"] or "")[:160]),
                   claim + '\nBrian: "' + quote + '"',
                   r["created_at"], r["created_at"]))
            stats["decisions"] += 1
        if not has_l:
            _exec("INSERT INTO altair.brian_learnings (content, "
                  "source, importance, status) VALUES (%s, %s, "
                  "'normal', 'unshared')",
                  (claim + '\nBrian: "' + quote + '"', marker))
            stats["learnings"] += 1
    return stats


def selftest():
    sample = ("RULING-AUDIT FLAG [log-x] memory/x.md:1\n"
              "CLAIM: TEST CLAIM HERE (Brian, 2026-01-01: \"words\")\n"
              "BRIAN'S QUOTED WORDS: some verbatim words here\n")
    p = parse_capture(sample)
    ok = p and p[0] == "TEST CLAIM HERE" and \
        p[1] == "some verbatim words here"
    print(("PASS " if ok else "FAIL ") + "parse ruling-audit format")
    bad = parse_capture("no format here")
    print(("PASS " if bad is None else "FAIL ")
          + "unformatted capture not promoted")
    print("SELFTEST " + ("OK" if ok and bad is None else "FAILED"))
    return 0 if ok and bad is None else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "selftest":
        sys.exit(selftest())
    dry = "--dry-run" in args
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    print(bridge(limit=limit, dry_run=dry))
