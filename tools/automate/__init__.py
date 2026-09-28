"""successbrian-os automation package.

PURPOSE:
    The 90% rule as code: rules declare check -> confidence -> action,
    the engine acts at >=90% (reversible), queues the rest for approval
    or research.

WHY:
    Puts Brian's standing autonomy bar into executable form so every
    automated decision carries its confidence and a log.

CALLED BY:
    - tools/automate/run.py (CLI entry point)

NOTES:
    Intentionally minimal — the full docstrings live in engine.py,
    rules.py, watchers.py, and run.py.
"""
