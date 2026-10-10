# Daily Improvements

Every day, this repo gets a little better. Each entry: what changed and why.

## 2026-10-10
- Removed dead helpers: `star()` in tools/audience/political_meme.py (a five-point-star drawing primitive, never called since the file was created — the political_backdrop draws its stars inline with its own gradient logic; only `render_political_meme` is imported externally) and `now_iso()` in tools/a2a_hub_v2.py (hub handlers use `time.time()` for presence timestamps, so the helper had zero callers) — the `from datetime import datetime, timezone` import it alone justified went with it. Verified zero references repo-wide via AST + grep, py_compile clean. Why it matters: uncalled code is a lie about the codebase — removing it keeps the next reader's map honest.
- Survey: py_compile clean on all 108 modules, no TODO/FIXME/HACK markers, zero missing module docstrings, no removable unused imports (only `from __future__ import annotations` directives, intentional). Reviewed-but-kept (uncertain intent / possible k11-external callers): `guard_write()` in tools/dealsdesk/seller_blocklist.py (documented public API for writers), `load_seats()` in board/harness/seats.py (board library, Altair's harness may call it), `db_delete()` in tools/audience/meme_idea_box.py, `effective_price()` in tools/dealsdesk/capacity_solver.py, `enabled_names()` in tools/ventures/streams.py, `trending()`/`global_data()` in tools/crypto-intel/intel/coingecko.py, `verdict_row()` in tools/affiliate_program_check.py, and the `icon_robot_futuristic()` robot-bust asset in tools/audience/political_meme.py (crafted art, dead today but a judgment call for Brian). README/docs current — nothing else qualified.

## 2026-10-08
- Removed stale root `knowledge_hygiene.py` — a broken duplicate (IndentationError at line 134, botched `if a.expire:` block) of the older pre-`--dry-run` variant; the canonical, improved version lives in its own repo (`successbrian/second-brain-for-agents`) and nothing in this repo imports or references the duplicate. Kept the repo py_compile-clean.
- Survey: py_compile clean on all 104 remaining modules, no TODO/FIXME/HACK markers, zero missing module docstrings, no removable unused imports, `/home/successbrian` paths are intentional k11-alpha deployment targets (left alone), README/docs current — nothing else qualified.

## 2026-10-07
- Docstring compliance pass (CODE-STANDARDS rubric): added WHY: + CALLED BY: + NOTES: to tools/audience/health_template.py (health desk's lived-experience lane, Oliabo emblem rule, deployment-checkout sys.path note), WHY: + CALLED BY: to tools/audience/political_meme.py (Navy identity non-negotiable, #MAGAUSNavyVet, self-retiring election_inset rail), WHY: + CALLED BY: to tools/audience/war_on_oil.py (reference render proving the political chrome), CALLED BY: to tools/audience/meme_template.py (4 importing siblings), and CALLED BY: to tools/ventures/goals.py + scoring.py (both imported by ideas.py's flesh step). Docstring-only, 54 insertions, zero behavior change, py_compile clean, committed+pushed.
- Survey: py_compile clean on all 93 modules, no TODO/FIXME/HACK markers, no removable unused imports (only `__future__` directives, intentional), the /home/hatch/workspace/successbrian-os sys.path inserts in tools/audience/ remain the second checkout's deployment convention (left alone per 2026-10-06), the two empty crypto-intel __init__.py files stay intentionally minimal, /home/successbrian paths are intentional k11-alpha deployment targets, README/docs current — nothing else qualified.

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

## 2026-10-01
- Nothing qualified for a safe improvement: `py_compile` clean, no TODO/FIXME/HACK markers, all module docstrings present (including the freshly-pulled ventures `scoring.py`, whose docstring already follows the rubric), README/docs current, no dead code or brittle paths found. Left the repo untouched rather than manufacture churn.
## 2026-10-02
- Removed 4 unused imports across 3 tools (`timedelta` in tools/a2a/checkin_monitor.py, `glob` + `timedelta` in tools/daywatch/morpheus_watch.py, `sys` in tools/ventures/prospect.py) — AST + grep verified zero other references, py_compile clean, prospect --help smoke-tested. Runtime --help failures of checkin_monitor/morpheus_watch verified pre-existing (missing psycopg2/psql on this VM, tools run on k11-alpha) — not caused by the cleanup.
- Survey: py_compile clean across all 53 modules, no real TODO/FIXME/HACK markers, all module docstrings present, hard-coded /home/successbrian paths are intentional k11-alpha deployment targets — left untouched.

## 2026-10-03
- Removed 6 unused imports across 4 tools — `datetime`+`sys` (tools/audience/audience.py), `sys` (tools/industry_map/industry_map.py), `datetime` (tools/jive/jive.py), `os`+`sys` (tools/people_migrate/migrate_oliabo_leads.py). AST walk + grep verified zero references anywhere including cross-module attribute access; `py_compile` clean on all 58 modules.
- Survey: `py_compile` clean, no real TODO/FIXME/HACK markers, all module docstrings present (new jive/industry_map/people_migrate files follow the PURPOSE/WHY/CALLED BY/NOTES rubric), README/docs current — nothing else qualified, left the rest untouched.

## 2026-10-04
- Docstring compliance pass (CODE-STANDARDS WHY-mandatory section): added WHY: to tools/refine_intake.py (grounded in Brian's quoted 2026-09-27 "refine it not reduce it" directive), tools/ventures/goals.py (draft-as-handoff-shape reasoning from its own docstring), tools/ventures/scoring.py (deterministic-rubric reasoning from the no-chat-model-decides rule); renamed "WHY this exists" to "WHY:" in tools/briefing_table.py for header consistency. Docstring-only, zero behavior change, py_compile clean. Left the two empty crypto-intel __init__.py files alone (adding WHY to "intentionally minimal" package inits would be churn).
- Survey: py_compile clean across all modules, no TODO/FIXME/HACK markers, runtime .db files properly gitignored, hard-coded /home/successbrian paths are intentional k11-alpha deployment targets — nothing else qualified.

## 2026-10-05
- Added the mandatory WHY: section to tools/audience/meme_template.py module docstring (grounded in Brian's 2026-10-04/05 standing design rules: light-background readability first, gradient+3D headline as the curiosity hook, plain-worded comparative cards, always-1080x1080 square). Docstring-only, zero behavior change, py_compile clean. Left the two empty crypto-intel __init__.py files alone (intentionally minimal — adding WHY would be churn).
- Survey: py_compile clean on all modules, no TODO/FIXME/HACK markers, no unused imports in the two newly-pulled modules (affiliate_monetization.py, qlora_dataset_builder.py), the /home/successbrian path in qlora_dataset_builder.py is an intentional documented k11-alpha deployment target (RUNS-ON-NODES NOTE), README/docs current — nothing else qualified.

## 2026-10-06
- Removed unused imports: `background`, `footer`, `BRAND` + `ImageFont` from tools/audience/health_template.py; `icon`, `grad_rounded` from tools/audience/political_meme.py; `GRAY`, `W` from tools/audience/war_on_oil.py; `import sys` from tools/employment/extract_entities.py and tools/employment/scan_mailbox.py; `import copy` from tools/focus/intel.py. Verified each name has zero references outside its import line, py_compile + import smoke test clean.
- Survey: py_compile clean on all modules, no TODO/FIXME/HACK markers, module docstrings complete per CODE-STANDARDS (WHY present everywhere), the /home/hatch/workspace/successbrian-os sys.path inserts in tools/audience/ are a second checkout's deployment convention — changing them could break deployed crons, so left alone as noted-unsafe. README/docs current — nothing else qualified.

## 2026-10-09
- Removed unused imports: `datetime` in tools/repo_hygiene_checker.py, `shutil` in tools/v4pro_status.py — dead weight, verified no references anywhere in either file before removal; both modules still py_compile clean. Why it matters: lint-clean imports keep the 07:00 repo-hygiene checker and the V4 Pro status reader (Altair's code paths) tidy for the next agent who reads them cold.
