# Morpheus Day-Watch

Morpheus looks at fleet health throughout the day and triages. The
correlation + judgment layer on top of Lyra's deterministic 15-min
threshold checks. All local on k11-alpha, zero AI credits.

## Why

Brian 2026-09-30: "morpheus needs to be looking and doing what it can
all throughout the day ... reliably run right off of k11 alpha without
needing any ai credits." Deterministic checks catch threshold breaches;
a local model adds "these 5 workers went quiet together - common cause?"
for free.

## Components

- Canonical: `tools/daywatch/morpheus_watch.py`
- Deployed: `/home/successbrian/.hermes/profiles/lyra/scripts/morpheus_watch.py`
  (Lyra owns health monitoring; edit the repo, redeploy.)
- Cron: `morpheus-daywatch` on Lyra's profile, `--no-agent`,
  `*/30 7-18 * * *` (every 30 min, 7 AM - 7 PM daily). Nights are covered
  by the deterministic 15-min check; the 7 AM pass reads its log tail.
- State: `/home/successbrian/.hermes/profiles/lyra/state/morpheus_watch_state.json`
  (last_run heartbeat, last reported findings, last_error).

## Inputs (deterministic snapshot, no model)

1. Tail of Lyra's 15-min health log (last ~2h): load/mem/disk + auto-fix actions.
2. Failed systemd units right now.
3. Restart counts on watched services (crash loops hide here).
4. Current disk/mem pressure.
5. Urgent knowledge_bridge rows from the last 2h (what the fleet already flagged).

## Output contract

- Morpheus replies VERDICT: ALL_CLEAR | FINDINGS, URGENCY: routine|important,
  plus one-line findings (what + why it matters + suggested next step).
- ALL_CLEAR: heartbeat only, no bridge row. Silence is health.
- New findings: one bridge row, sender='lyra', target='spencer',
  subject '[daywatch] <first finding>'. Urgency per the check-in rubric;
  the prompt biases conservative (investigating / no change = ALL_CLEAR).
- Dedup: an ongoing incident reports once. Repeat findings are suppressed
  via stem overlap against the state file; a finding explicitly marked
  WORSENED by the model still reports.
- Morpheus unreachable: records last_error in state, exits 1 (cron shows
  the failure; no silent death).

## Boundaries (Brian's rules)

- Morpheus LOOKS and TRIAGES. No service restarts, no kills, no config
  changes, no deletions. The "doing" is: correlating incidents,
  prioritizing the broken-things list, handing Altair/Spencer concrete
  next diagnostic steps.
- Remediation stays with the deterministic auto-fix or humans.
- Findings reach Brian only through the normal receiver/surfacing rules.
