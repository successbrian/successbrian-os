#!/usr/bin/env python3
"""
Thin dispatcher: one call shape for the 14B.

PURPOSE:
    `routine.py <briefing|decisions|planning> <command> [args]` runs the
    matching module and prints its JSON. The 14B learns ONE invocation
    pattern instead of three scripts; `--help` documents every command's
    say/expect contract for the system prompt.

WHY:
    Brian's directive (2026-09-27): the 14B must do only two things —
    paraphrase `say` into 2-3 sentences and classify Brian's reply into the
    `expect` schema. A single dispatcher keeps the tool surface minimal so
    the small model can't fumble module names or argument shapes. All flow
    stays in Python; the model never sees internals.

CALLED BY:
    Altair's chat loop (Morpheus 14B) on k11-alpha.

NOTES:
    Always prints exactly one JSON object on stdout, even on errors, so the
    14B's parse never breaks. Subprocess calls use the same interpreter.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = {
    "briefing": "briefing.py",
    "decisions": "decisions.py",
    "planning": "planning.py",
}

HELP = """Altair routines — one call shape: routine.py <area> <command> [args]

Every command prints ONE JSON object. Your job per reply:
  1. Paraphrase the `say` text into 2-3 sentences for Brian (leisure-mode tone).
  2. Classify Brian's reply into the `expect` schema, then call the next command.

CONTRACT FIELDS:
  say      - text phrased for Brian. Paraphrase, don't read verbatim.
  expect   - what Brian's reply should be:
               feedback -> free text; pass as --feedback to the next step
               choice   -> he picks from `options`; pass the picked text
               text     -> free text; no routine call needed unless he asks
  options  - the allowed choices when expect=choice. Never invent others.
  done     - true means this routine is finished; chat freely after.
  error    - something broke; `say` has the fallback line. Use it.

BRIEFING (walk Brian through a briefing file, topic by topic):
  routine.py briefing start --date YYYY-MM-DD --slot sunday
      -> first topic {say, expect: feedback|choice, session, topic, total}
  routine.py briefing next --session ID --feedback "his words"
      -> stores feedback, advances; {done: true} with a closing line at the end
  routine.py briefing status --session ID
      -> {covered, total, remaining[]} progress check

DECISIONS (get Brian's call on open decisions, record them durably):
  routine.py decisions pending
      -> [{id, title, options[], source}] open decisions, or done if none
  routine.py decisions ask --id <id>
      -> one decision {say, expect: choice|feedback, options[]}
  routine.py decisions record --id <id> --choice approve|reject|park [--note "x"]
      -> marks decided everywhere, logs to second brain. Closes the loop.

PLANNING (turn a goal into a saved plan, one question at a time):
  routine.py planning start --goal "text"
      -> {say: first question, expect: text, plan: ID}
  routine.py planning answer --plan ID --text "his answer"
      -> next question; after the 5th, a summary with expect: choice [save it|not yet]
  routine.py planning save --plan ID
      -> writes the plan file + second brain, {done: true}
  routine.py planning list
      -> recent plans [{id, goal, status}]

RULES:
  - Never show Brian raw JSON, ids, or file paths.
  - Never skip ahead: one topic / one decision / one question per turn.
  - If a briefing file is missing, the routine says so plainly — never invent topics.
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h", "help"):
        print(HELP)
        return
    area, rest = sys.argv[1], sys.argv[2:]
    if area not in MODULES:
        print(json.dumps({
            "error": f"unknown area '{area}'",
            "say": "Something glitched on my end — let's pick that back up "
                   "in a moment.",
            "expect": "text", "done": True}))
        sys.exit(1)
    if not rest:
        print(json.dumps({
            "error": "no command given",
            "say": "Something glitched on my end — let's pick that back up "
                   "in a moment.",
            "expect": "text", "done": True}))
        sys.exit(1)
    mod = os.path.join(HERE, MODULES[area])
    try:
        r = subprocess.run([sys.executable, mod] + rest,
                           capture_output=True, text=True, timeout=120)
        out = r.stdout.strip()
        if out:
            print(out)
        else:
            print(json.dumps({
                "error": r.stderr.strip()[:300] or "empty output",
                "say": "Something glitched on my end — let's pick that back "
                       "up in a moment.",
                "expect": "text", "done": True}))
            sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "error": str(e)[:300],
            "say": "Something glitched on my end — let's pick that back up "
                   "in a moment.",
            "expect": "text", "done": True}))
        sys.exit(1)


if __name__ == "__main__":
    main()
