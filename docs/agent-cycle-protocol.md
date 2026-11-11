# Agent Cycle Protocol — SuccessBrian OS feature spec v2

Brian's rulings behind this build:
- 2026-11-11 03:22 CST — build functionality inside SBOS so Spencer runs a
  20-minute self-check routine and becomes a 24/7 automated agentic system
  that continuously improves the ecosystem. (v1 shipped same morning:
  tools/spencer_cycle.py + Muse cron spencer-20min-cycle + PM project
  spencer-20min-cycle, QA 574/575.)
- 2026-11-11 03:28 CST — generalize: the system must work with ALL personal
  agents similar to Muse; a new SuccessBrian OS feature; fully integrated
  with PostgreSQL, the second brain, all ecosystem nodes (including remote
  nodes like gamma); compatible with Wix blogging, systeme.io, FlexiFunnels.
  Ideas filed as Intel Bridge capture #1264.
- 2026-11-11 03:29 CST — confirmed: the system needs to fully integrate with
  Altair and the system's NAMEABLE CEO agent (the CEO seat's name is an
  operator setting; Brian's CEO agent is named Meghan).

## 1. The protocol (one loop, every agent)

sense → deduplicate → file → act within authority tier → report by exception

- SENSE: run the checks in the agent's manifest (PostgreSQL) using the
  shared check library. No agent hand-rolls its own copy of a check.
- DEDUPLICATE: every finding carries a dedup key; the findings table holds
  one open row per key. A condition that persists is ONE finding, not 72
  messages a day.
- FILE: new findings go to the findings table AND to the Intel Bridge
  (atlas.scattered_captures) so the clerk sorts them into the second
  brain — what one agent's cycle learns, every agent can later read.
- ACT: only inside the agent's authority tier (below). Acting means the
  safe internal work: re-check, prepare, park, file, feed a ruled queue.
- REPORT: silence is the default. The operator hears about a cycle only
  when a finding needs his decision, a threshold breaks, or prepared work
  awaits his review. Digests roll into the ecosystem review passes.

## 2. PostgreSQL schema (successbrian_os, built v2)

- agent_registry — agent_key, operator_key, role (operator_agent /
  orchestrator / ceo / remote_ceo / worker), display_name (NAMEABLE:
  the CEO seat's display_name is operator data — Brian's is "Meghan";
  another operator names theirs), node, cadence, authority_tier,
  enabled, notes.
- agent_cycle_manifests — agent_key, check_key, enabled, params jsonb.
- agent_cycle_runs — agent_key, started_at, finished_at, checks_run,
  findings_new, findings_active, summary jsonb.
- agent_findings — dedup_key UNIQUE, agent_key, check_key, title,
  detail, status (open/acked/resolved), first_seen, last_seen, times_seen.

## 3. Authority tiers (stored per agent, enforced in code)

- Tier 0 — sense only (new agents start here).
- Tier 1 — internal reversible work: re-checks, dedup filing, queue
  feeding under already-ruled lanes, state bookkeeping.
- Tier 2 — prepare-for-operator: drafts, fix proposals, plans parked for
  the operator's review. Nothing outward.
- Tier 3 — ruled standing lanes only: an agent may execute ONLY lanes
  the operator has explicitly ruled as standing (e.g. an existing
  enrichment lane). Tier 3 never widens itself.

Hard floor for every tier: no sends, no purchases, no publishes, no
contacting people — those always need the operator's own go, per his
standing approval-scope law.

## 4. Altair integration

Altair is the orchestrator on alpha (heartbeat wakes :05/:35, wake_lib.py
packets, heartbeat_claim.py PM-step claiming at 17/47). His cycle is the
SAME protocol pointed at operations state:
- Manifest (seeded v2): qa_failing, raw_backlog, gamma_liveness,
  price_expired, issues_open.
- Cadence: his cycle runs on alpha at :07/:37 (two minutes after his
  wake), flock-guarded, via tools/agent_cycle.py --agent altair.
- His findings land in the same findings table + bridge, so Spencer's
  20-minute cycle and the review passes see one shared picture.
- NEXT STEP (not in v2): wake_lib packet gains an "AGENT CYCLE" section
  (his open findings + last run) so his Sonic judgment works the findings
  the deterministic cycle collected — the same pattern as Meghan's
  Rolodex packet section. Until then the cycle is deterministic-only.

## 5. The nameable CEO agent integration

The CEO seat is a ROLE in the registry; its display name is operator
data (registry.display_name), never hardcoded in cycle code, checks, or
reports. Brian's CEO agent (Meghan, alpha, heartbeat :00/:30, wake
:20/:50) gets:
- Manifest (seeded v2): qa_failing, raw_backlog, price_expired,
  gamma_liveness — the executive layer watches health + shelf life +
  backlog, not operations detail.
- Cadence: alpha cron at :22/:52 via tools/agent_cycle.py --agent ceo.
- HONESTY RULE (carried from heartbeat_claim): while the CEO agent's own
  thinking engine is offline/unproven, her cycle is deterministic
  sensing + filing only — mechanics, never fake thinking. The cycle
  makes her seat's WATCH continuous even while her wake is broken; it
  does not pretend she deliberated.
- Her Rolodex heartbeat loop (wake_lib section, 2026-11-09) stays as is;
  the cycle complements it, it does not replace it.

## 6. Remote nodes (gamma pattern)

A remote agent (e.g. the gamma CEO seat) runs agent_cycle.py locally on
its node against its local manifest cache and syncs findings/runs up
through the transport that already exists (bus events / outbox rows to
alpha). Alpha's registry holds the remote row so the operator's digest
covers every node. Building the gamma-side runner is v3 work; the v2
registry row reserves the seat.

## 7. Marketing adapters (v4, per Brian's 03:28 list)

Adapters are sensor+hand pairs registered as checks/actions:
- Wix blogging: sensors = publish/review queue state, comment events
  (Brian's ruled webhook → n8n pattern, 2026-10-25); hands = prepare
  publish packages in CampaignsDesk's pipeline only.
- systeme.io: sensors = funnel lead flow + campaign stats; hands =
  prepare follow-ups. No sends from a cycle.
- FlexiFunnels: sensors = lead events via the existing n8n →
  ContactFlowCRM plumbing; hands = none in v4 (sense + file only).
The governing analogy, stated in capture #1264: leads waiting while
nobody works them is the same defect as captures waiting while gamma
idles. Adapters ship one at a time, Wix first.

## 8. Multi-operator law

Same code for every operator (Brian, 2026-10-29): protocol, checks, and
tables are core SBOS code; agents, names, manifests, tiers, and goals
are per-operator DATA rows (operator_key on every table).

## 9. What v2 ships today vs later

SHIPPED v2: this spec; the four PostgreSQL tables seeded for spencer /
altair / ceo / gamma-ceo seats; the shared runner tools/agent_cycle.py
(check library: raw_backlog, qa_failing, gamma_liveness, price_expired,
issues_open) with PG run/finding logging + bridge filing; alpha cadence
crons for altair (:07/:37) and ceo (:22/:52); spencer_cycle.py now also
logs its runs/findings into the shared tables; PM project
agent-cycle-protocol with QA.
LATER: v3 gamma-side runner + wake_lib AGENT CYCLE sections for Altair
and the CEO seat; v4 marketing adapters (Wix → systeme.io →
FlexiFunnels); operator digest page.
