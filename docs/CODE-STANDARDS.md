# Code Standards — SuccessBrian OS

Every module in this repo documents itself for future agents. A future agent
reading cold should understand what a file does, why it exists, and who calls
it — from the docstring alone.

## Module docstring format

```
"""
<One-line purpose.>

WHY:
    Why this exists. What problem it solves, what decision it encodes,
    what breaks if it's removed. Link the reasoning, not just the behavior.

CALLED BY:
    Who/what invokes this — cron job ids, other modules, humans.

NOTES:
    Gotchas, known limitations, things a future agent must not assume.
"""
```

- PURPOSE first, one line. Then WHY, CALLED BY, NOTES as sections.
- WHY is mandatory. "What" without "why" rots — the next agent can't tell
  whether a behavior is load-bearing or accidental.
- Never document a guess as a fact. Mark estimates, stubs, and unverified
  assumptions explicitly.

## Move policy (per Brian 2026-09-27)

Prototype code found outside repos gets moved into the right repo. The
original may be DELETED only after:
1. The move is complete (file lives in the repo, committed, pushed), AND
2. The move is TESTED from the new location (imports cleanly / runs /
   produces the same output as the original).

Move → test → delete. If the test fails, the original stays and the failure
is logged. Quarantine-never-delete still applies to everything else.

## Daily improvements

`daily-repo-improvements` (3:00 AM daily) makes small, safe improvements to
each tracked repo and documents them in `docs/IMPROVEMENTS.md` (date + what +
why). 90% rule applies: only autonomous-safe changes get committed; anything
uncertain is noted, not committed.
