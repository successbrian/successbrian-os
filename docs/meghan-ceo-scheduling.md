# Meghan CEO - scheduling + identity (2026-10-14)

CEO agent identity standard: meghan-ceo. Persona name stays "Meghan Alpha"
in display text; every machine identifier (sender / source_agent / asked_by /
read filter / unit + file names) uses meghan-ceo. Legacy meghan-alpha is
accepted in READ filters only, during transition.

## What runs Meghan (three separate triggers - do not merge)

- CEO wake (judgment): OpenClaw gateway cron, schedule 7,37 * * * * America/Chicago.
  Gateway job name meghan-ceo-heartbeat, id 2de41e27-cf05-49af-9122-affcf506f840,
  in /home/successbrian/.openclaw/cron/jobs.json.migrated.
- Script heartbeat (deterministic snapshot): USER systemd timer ceo-heartbeat.timer,
  every 30 min at :00/:30. Activates ceo-heartbeat.service, which runs
  /home/dealsdesk/scripts/ceo_heartbeat.py (canonical copy:
  successbrian-os/tools/dealsdesk/ceo_heartbeat.py).
- Daily Pipeline Report: SYSTEM systemd timer daily-pipeline-report.timer,
  daily 11:30 CDT. Activates daily-pipeline-report.service, which runs
  /home/unified_people_pipeline/scripts/daily_pipeline_report.py --channel knowledge_bridge.

## The timer that "did not exist"

ceo-heartbeat.timer exists as a USER timer (systemctl --user), not a system
timer. The earlier "missing timer" finding only checked system systemd.
NO system timer was added - one would double-fire with the user timer.
Verify with: systemctl --user list-timers | grep ceo-heartbeat

## Reader fix (2026-10-14)

Daily Pipeline Report rows on altair.knowledge_bridge (sender meghan-alpha,
target brian,lyra,mavity, 11:30:01 daily) all sat unread (read_at NULL).
Writer is the systemd-triggered script above, NOT process_ai_task_queue.py -
that file only CONSUMES the rows. The writer now dual-writes: the KB row is
unchanged, plus a successbrian_os.outbox row (source_agent meghan-ceo,
message_type broadcast, target_agent all, same subject/body) - outbox /
dashboard inbox is where Brian looks.

## Zombie stopped + renamed (2026-10-14)

The 60s idle loop was a separate Alpha-node Python orchestrator, NOT the CEO.
meghan-alpha.service: stopped + disabled + renamed to alpha-orchestrator.service.
Script /root/meghan_alpha.py renamed to /root/alpha-orchestrator.py.
Override dir renamed with it. Old files kept for rollback - nothing deleted.
Rollback: mv the three paths back, systemctl daemon-reload,
systemctl enable --now meghan-alpha.service.
Old unit name no longer resolves; gateway untouched (still running).

## Known stale bits - NOT fixed here

- Gateway KiloCode failover: gateway log shows repeated
  FailoverError Unknown model kilocode/kilo/auto (66 lines since 2026-10-14
  00:00). Reported only - gateway is shared; do not touch without Brian.
- "70B" claim: no live docstring claims 70B. The 70B reference is a
  historical plan (upgrade the old orchestrator from qwen2.5:7b to 70B) that was
  never executed. Reality: wake runs on the gateway default model; the Meghan
  agent models.json lists available providers (qwen3.6:35b, qwen2.5:7b,
  Groq llama-3.3-70b, Kilo laguna placeholder). Nothing edited.
- Credentials: plaintext credentials exist in the renamed orchestrator
  script + its unit/override. They were NOT read, copied, or moved as values
  (files renamed whole). ROTATION IS A BRIAN ACTION via the secure vault
  flow - left explicitly UNDONE.
- daily-pipeline-report.timer description still says "6:30am" but fires
  11:30 - cosmetic, left alone (editing the live timer risked the 11:30 run).
- dealsdesk still broadcasts outbox rows addressed to target meghan-alpha
  (280 rows). The wake read filter accepts legacy meghan-alpha for now;
  the dealsdesk sender should switch to meghan-ceo in its own change.


## Verification pass 2 (2026-10-14 ~05:05 CDT, second worker)

Re-verified every claim above independently (bak diffs, unit states, DB reads).
All "done" claims held, plus two completions this pass:

- STRAY .tmp QUARANTINED (not deleted): /etc/systemd/system/alpha-orchestrator-kilocode.service.tmp
  (Jul 28, no unit, systemd never loads .tmp) moved to
  /root/alpha-orchestrator-kilocode.service.tmp.quarantined-20261014 (952 bytes).
  Rollback: sudo mv it back. This also removes the stale
  "Meghan Alpha CEO orchestrator (Kilo Code Gateway, 60s heartbeat)" Description.
- DOCSTRING FIXED: /root/alpha-orchestrator.py header (lines 3,7) now says
  qwen2.5:7b per unit env + NOT the CEO agent (was: 70B claim).
  Backup: /root/alpha-orchestrator.py.bak-20261014-meghan-ceo (21598 bytes, original).
  17x '70B' remain in the code body (query_70b fn names, log strings, prompt builder)
  - left: docstring-only scope, file is disabled legacy, never runs.
- alpha-orchestrator.service re-confirmed: inactive/dead, disabled, no reverse deps,
  WantedBy empty. meghan-processor.service: inactive/dead, disabled, pre-existing
  (May 28, Tier-1 ingestion, ExecStart /root/meghan_processor.py) - LEFT untouched.
- No system ceo-heartbeat timer/unit exists (user timer only - no double-fire).
  Deployed /home/dealsdesk/scripts/ceo_heartbeat.py differs from repo canonical
  by 3 docstring lines only (functional code identical).
- WAKE-GAP OBSERVATION (not fixed, gateway untouched): last successbrian_os.ceo_heartbeats
  source='wake' row 2026-10-14 02:57; gateway restarted 04:13; no wake rows since.
  Wake cadence was already irregular pre-edit (00:41 -> 02:57 gap). Needs a
  gateway-side look; do NOT touch gateway without Brian.
- BRIDGE DORMANT (left alone): scripts/meghan_intel_bridge.py reads
  public.intel_buffer WHERE source_agent='meghan-alpha' - that stream is the KILLED
  zombie's Cycle Output spam (last row Oct 13 22:49), NOT the wake. Bridge log last
  ran Sep 18; no cron/timer/schedule found. If wake decisions should reach SBOS
  action_items, the bridge needs re-pointing to successbrian_os.intel_buffer +
  meghan-ceo as a SEPARATE change. successbrian_os.intel_buffer has only 13 rows
  (last Oct 12) vs public.intel_buffer 30,616 rows - the two tables are NOT the
  same stream. Do not conflate.
- A2A hub scripts still use agentId 'meghan-alpha' (dozens of scripts/) - a
  separate addressing domain from the wake; left untouched.
- CREDENTIALS: rotation still UNDONE - Brian action via secure vault flow.
