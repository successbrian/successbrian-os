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

## Commit hygiene (all coders — Brian 2026-10-08, standing)

Every coder in this ecosystem — Spencer, Altair, the Coding Box, any future
agent — follows this contract. (Why it exists: 2026-10-07, a week of
staged-but-uncommitted work including accidental doc deletions piled up behind
two unmerged paths nobody fixed. The repo looked vandalized; nothing was lost,
but it took a full investigation to untangle.)

1. **Never leave staged-but-uncommitted work overnight.** Commit it or unstage
   it before you stop. The index is not a parking lot.
2. **`git add` specific files only.** Never `git add -A` / `git add .` when the
   worktree has unrelated changes — you will sweep up someone else's mess.
3. **Fix a commit blocker the moment you hit it.** Unmerged paths, auth
   failures, whatever stops the commit — resolve it now, don't work around it
   and leave it for later.
4. **Never stage deletions of docs, specs, LICENSE, or .gitignore entries**
   without Brian's explicit go-ahead. Code cleanup never means doc deletion.
5. **`tools/repo_hygiene_checker.py`** (system cron daily 07:00 CDT) probes
   every tracked repo and writes to `successbrian_os.repo_hygiene_history`.
   Healthy = no unmerged paths AND no staged-but-uncommitted changes. If your
   repo goes unhealthy you get a knowledge_bridge alert the same day — fix it
   that day.
