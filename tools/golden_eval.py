#!/usr/bin/env python3
"""
golden_eval — the distillation system's own ruler.

Part of the Distillation System design (2026-11-17): a fixed set
of questions drawn from Brian's REAL rulings, run against
engine_research.dig2. GOOD questions must come back found=True
with the right row in the top 3; UNKNOWN questions (topics Brian
has never ruled on) must come back found=False. Public benchmarks
are not trusted for this (2026 audit: 6.4% of LoCoMo keys wrong) —
this set is small, personal, and honest.

Run on every RETRIEVE change and weekly on the cycle. A score
drop blocks the change that caused it. Grow the set toward 25+
as new rulings land; never edit a question to make a failing
change pass — fix the change or record the failure.

Usage: golden_eval.py [--verbose]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_research import dig2  # noqa: E402

# (kind, question, expected row id in either store or None)
QUESTIONS = [
    ("GOOD", "is the muse matching idea something Brian wants "
             "to move fast on", 538),
    ("GOOD", "should assistants treat their own suggestions as "
             "decided", 535),
    ("GOOD", "what gate number applies to strata models", 123),
    ("GOOD", "can overflow work go to smaller engines", 216),
    ("GOOD", "what replaced the clock class proposal for due "
             "dates", 124),
    ("GOOD", "MUSE MATCHING", 538),
    ("GOOD", "are ES engineering samples ever acceptable", 125),
    ("GOOD", "who is the audience for Brians content", 120),
    ("GOOD", "what happens when a problem keeps recurring",
     {537, 128}),
    ("GOOD", "did Brian rule the integration series", 127),
    ("GOOD", "what is the strata machine direction for cpus", 126),
    ("GOOD", "XRP recommendation", None),
    ("UNKNOWN", "what did Brian decide about quantum computing "
                "stocks", None),
    ("UNKNOWN", "what is Brians ruling on opening a bakery in "
                "Duluth", None),
    ("UNKNOWN", "how does Brian feel about the 2027 Mars mission "
                "timeline", None),
    ("UNKNOWN", "what did Brian rule about submarine purchases",
     None),
    ("UNKNOWN", "what is Brians opinion on sourdough bread", None),
    ("UNKNOWN", "did Brian approve buying a boat", None),
]


def run(verbose=False):
    passed = 0
    failures = []
    for kind, q, want in QUESTIONS:
        r = dig2(q, limit=3)
        ids = [h["id"] for h in r["decisions"]] + \
              [h["id"] for h in r["learnings"]]
        if kind == "GOOD":
            wants = want if isinstance(want, (set, list)) else \
                ({want} if want is not None else None)
            ok = r["found"] and (wants is None or
                                 bool(wants & set(ids)))
        else:
            ok = not r["found"]
        passed += ok
        if verbose or not ok:
            print("%s %s found=%s want=%s got=%s | %s"
                  % (kind, "PASS" if ok else "FAIL", r["found"],
                     want, ids[:3], q[:50]))
        if not ok:
            failures.append((kind, q))
    print("GOLDEN %d/%d" % (passed, len(QUESTIONS)))
    return passed, failures


if __name__ == "__main__":
    p, _f = run(verbose="--verbose" in sys.argv)
    sys.exit(0 if p == len(QUESTIONS) else 1)
