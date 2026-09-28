# Daily Improvements

Every day, this repo gets a little better. Each entry: what changed and why.

## 2026-09-27
- Added `docs/CODE-STANDARDS.md` — module docstring format (PURPOSE / WHY / CALLED BY / NOTES) so future agents know the why, not just the what.
- Documented every module in `tools/` and `tools/automate/` with the new format — the WHY is now explicit everywhere.
- Added `tools/automate/` — the 90% rule as code (rules engine, live watchers, 6 production rules).
- Added `tools/model_tiers.py` — model routing with V4 Pro credit flag.
- Added `tools/second_brain.py` — second-brain write path for learnings.

## 2026-09-28
- Removed 7 unused imports (`socket` in tools/model_tiers.py, `json` in tools/automate/watchers.py and tools/marketer_watch.py, `time` in tools/crypto-intel/intel/news.py, `timezone` in tools/briefing_table.py, `load_seats` in board/harness/session.py, `sq` in tools/altair_routines/decisions.py) — AST-verified as single-occurrence (import line only), recompiled + smoke-tested after.
- Stopped tracking `__pycache__`/`.pyc` in git (deleted ~20 stale bytecode files, added rules to `.gitignore`) — bytecode is regenerated on demand and the tracked copies were silently going stale on every edit.
- Skipped: `refine_intake.py` docstring uses WHAT/HOW section headers instead of WHY/NOTES; the content covers both, so renaming was churn, not improvement. `from __future__ import annotations` kept as-is (intentional compat import).
