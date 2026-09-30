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

## 2026-09-29
- pyflakes lint cleanup across all 43 modules — removed 3 unused imports (`Brief` in board/test_dryrun.py, `dataclasses.field` in board/harness/worker.py and tools/crypto-intel/testing/strategies.py), 2 dead locals (`exp` in tools/briefing_table.py, `ms` in tools/marketer_watch.py), 1 placeholder-less f-string (tools/altair_routines/planning.py), and demoted never-read `source` to `_` in 3 tuple unpacks in tools/contact_watcher.py — all verified with py_compile + pyflakes before commit; zero behavior change.
- Survey: no TODO/FIXME/HACK markers, all module docstrings present, nothing else qualified as a 90%+ safe change — left the rest untouched.

## 2026-09-30
- Untracked 7 runtime state/cache files (tools/{automate/state,state,staging}, crypto-intel/.cache, marketer_watch.db) and extended .gitignore — tracked copies were stale snapshots from Sept 27–28 that go stale on every tool run; tools recreate them (verified mkdir/exists guards), same cleanup as the 2026-09-28 __pycache__ removal.
- Fixed stale path in tools/model_tiers.py docstring (tools/automate/state/ → tools/state/); smoke-tested --help after.
- Removed unused `timedelta` import in tools/a2a/checkin_monitor.py (AST-verified single reference).
- README Specs section now lists all 5 specs (was altair-apis only).
- Survey: no TODO/FIXME/HACK markers; `from __future__ import annotations` kept per 2026-09-28 decision.
