"""
Board of Directors harness — generic C-level morning session runner.

WHY:
    Brian's Sep 2026 advisory-board-system proved a board can run daily and
    still produce nothing (83% empty summaries, 440/441 tasks pending). This
    harness is the productized answer: a GENERIC session runner any
    entrepreneur configures with their own C-level seats (YAML), while Brian's
    9-seat instance is just one bent config. Generic-at-first, bends-per-user.

CALLED BY:
    - board/test_dryrun.py (manual verification)
    - The 3:30 AM board-of-directors-daily cron worker (production sessions)
    - Future entrepreneurs' own schedulers, via board/config/*.yaml

NOTES:
    Harness = the loop machinery (seats, worker, gate, sinks, session).
    System  = a bent config (seats, briefs, sink). Never hardcode one
    entrepreneur's domains into the harness modules.
"""
