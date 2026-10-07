# The Checker Pattern (ecosystem standard, per Brian 2026-10-07)

Every recurring system check — daily, hourly, every 30 minutes, any cadence — works the same way:

## The three parts

1. **Checker** — deterministic code in this repo (`tools/<thing>_checker.py`), run by cron.
   Probes ONE thing. Writes RAW values only: no thresholds, no floors, no interpretation,
   no pinning. On failure it writes nothing (a stale value beats a false one) and exits non-zero.

2. **Table** — `successbrian_os.<thing>_history` in PostgreSQL (`ecosystem_central` on k11-alpha).
   Every check is a row: `checked_at timestamptz`, the raw value columns, `source text`.
   Index on `checked_at DESC`. History is kept — never delete rows to "save space."

3. **Readers** — Altair, other agents, and processes read the table. The standard read:
   ```sql
   SELECT * FROM successbrian_os.<thing>_history ORDER BY checked_at DESC LIMIT 1;
   ```
   Nobody hardcodes the value, a threshold, or an assumption from a previous run.
   If the latest row is older than 2x the check interval, treat the value as stale.

## Naming

- Cron job: `<thing>-checker` (kind=cron, no_agent script job)
- Code: `tools/<thing>_checker.py` in successbrian-os, committed + pushed, deployed from the repo
- Table: `successbrian_os.<thing>_history`

## What is NOT a checker

Workers that DO things (build content, send messages, run pipelines) are not checkers —
they don't get history tables. Only recurring probes of system state follow this pattern.

## Reference implementation

`tools/v4pro_state_checker.py` + `successbrian_os.v4pro_balance_history` (2026-10-07).
