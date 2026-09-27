# Daily Improvements

Every day, this repo gets a little better. Each entry: what changed and why.

## 2026-09-27
- Added `docs/CODE-STANDARDS.md` — module docstring format (PURPOSE / WHY / CALLED BY / NOTES) so future agents know the why, not just the what.
- Documented every module in `tools/` and `tools/automate/` with the new format — the WHY is now explicit everywhere.
- Added `tools/automate/` — the 90% rule as code (rules engine, live watchers, 6 production rules).
- Added `tools/model_tiers.py` — model routing with V4 Pro credit flag.
- Added `tools/second_brain.py` — second-brain write path for learnings.
