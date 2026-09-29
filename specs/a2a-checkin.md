# A2A Check-in Protocol: Altair → Spencer twice-daily standup

Per Brian: "you and Altair need to talk a lot." This is the async standup —
Altair reports to Spencer twice daily, in his own voice, over the A2A
knowledge_bridge. Lyra watches the pipeline. Spencer's receivers surface
only what Brian needs.

## The chain

```
Altair's cron (weekdays 9:30 AM / 2:30 PM CDT, --no-agent)
  → tools/a2a/spencer_checkin.py
    → gathers live context (goal queue, <72h notes, today's A2A inbox)
    → Morpheus (127.0.0.1:11437) composes the check-in in Altair's voice
    → INSERT altair.knowledge_bridge (sender='altair', target='spencer')
  → Spencer's receiver crons (9:45 AM / 2:45 PM CDT)
    → records in dated memory; silent unless blockers/news/3+ days quiet
  → Lyra's monitor crons (weekdays 10:15 AM / 3:15 PM CDT)
    → tools/a2a/checkin_monitor.py verifies the row landed; alerts if not
```

## Why --no-agent (not an agent turn)

Hermes cron agent turns proved unreliable for this (2026-09-29):

1. `delegate_task` subagents stalled: the non-streaming SDK timeout (1800s
   default) outlived the 600s cron inactivity watchdog, so the whole job
   died as "idle" instead of raising a retryable timeout.
   → Fixed in hermes-agent `direct_api_call`: SDK timeout now capped at
   (HERMES_CRON_TIMEOUT − 60s). Commit in successbrian/altair-senior-vp-agent.
2. `hermes chat -q` printed "Ready." without processing the query.
3. `hermes -z` oneshot hung.
4. Cron agent turns need `approvals.cron_mode: allow` on the profile.

The script calls Morpheus directly and writes the DB row itself — ~15–36s,
deterministic, no agent machinery. If Hermes agent turns become reliable,
the producer can move back to an agent turn; the DB contract is unchanged.

## Urgency semantics

Urgency = **whether Brian must act**, not how dramatic the work sounds.

- `routine` (default): work in progress, investigating, nothing needed.
- `important`: Brian must decide, approve, or provide something.
- `critical`: Brian must act today.

Repeat-topic suppression: if a check-in escalates the same topic as the
previous escalated check-in, urgency steps down one level
(critical→important→routine) and the subject is prefixed `[continuing]`.
State: `~/.hermes/scripts/spencer_checkin_state.json`.

## Recency weighting

Fresh signals outrank memory, always:

1. Current goal queue (what Altair is actively tasked with NOW)
2. Memory notes modified in the last 72h (explicitly dated)
3. Today's A2A inbox messages
4. Long-term memory tail — labeled BACKGROUND, may be dated, never
   reported as current news unless confirmed by fresher signals.

## Files

| File | Role |
|---|---|
| `tools/a2a/spencer_checkin.py` | Producer (canonical; deployed to `~/.hermes/scripts/`) |
| `tools/a2a/checkin_monitor.py` | Lyra's pipeline health check (canonical) |
| `specs/a2a-checkin.md` | This protocol |

## Database

Transport: `ecosystem_central.altair.knowledge_bridge`
(sender, target, subject, body, urgency, created_at).

- Check-ins: `sender='altair'`, `target='spencer'`
- Pipeline alerts: `sender='lyra'`, `target='spencer'`, `urgency='important'`

## Deployment

Edit the canonical files in this repo, commit, push, then redeploy:

```bash
cp tools/a2a/spencer_checkin.py /home/successbrian/.hermes/scripts/spencer_checkin.py
cp tools/a2a/checkin_monitor.py  /home/successbrian/.hermes/profiles/lyra/scripts/checkin_monitor.py
```

Never edit the deployed copies in place — they are build artifacts.
