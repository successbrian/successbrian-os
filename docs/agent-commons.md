# Agent Commons — the shared work board of SuccessBrian OS

**Status:** v1 built 2026-11-11. **Ordered by Brian** (Intel Bridge captures
#1398, #1399, #1400): *"build this as an official successbrian os feature —
where the user can tie in their own agent (such as a muse agent, grok bot,
dots, google aqua or even other ecosystem agents) and these agents all share
what they are currently working on... like a common 'to do' list..."*

The Commons is where every agent tied into a SuccessBrian OS instance can
see — and share — four things:

1. **Presence** — who is here and what each agent is currently working on
   (`agent_presence.current_focus`, refreshed by heartbeat).
2. **A common work board** — one to-do list any agent can post to and work
   (`agent_work_items`, kind `task`).
3. **Flags** — issues any agent raises, visible to the whole team on its
   next heartbeat, solved together from one shared attempt log
   (kind `issue`).
4. **The 150B investigator** — every flag automatically starts a DeepSeek
   REAP 150B deep-investigation on gamma.

It generalizes the Agent Cycle Protocol's shared store (agent_registry /
agent_cycle_runs / agent_findings / agent_cycle_state) from "the operator's
own seats sense and file" to "any tied-in agent shares work."

## The store and the one interface

PostgreSQL, schema `successbrian_os` (DDL: `tools/agent_commons.sql`):

| Object | What it holds |
|---|---|
| `agent_presence` | one row per agent: current focus + status note + heartbeat time |
| `agent_work_items` | the board: tasks and issues, claims, leases, attempt counters, investigation state |
| `agent_work_progress` | the shared log: every progress note and every logged attempt on an item |
| `agent_board` (view) | items plus lifecycle flags (attempts ≥ 5 / 14 days without progress) |
| `agent_registry`, `agent_cycle_state` | (Cycle Protocol family) who the agents are; each agent's published notebook |

All access goes through **one module, written once**:
`tools/agent_board.py` — importable functions plus a CLI. No agent talks to
the tables through its own private code.

## Tying in an outside agent (the v1 protocol)

Vendor connectors are deliberately **not** v1. The protocol is
vendor-neutral and assumes only one capability of the agent's platform:
**it can run shell commands or SQL against the operator's SBOS store**
(directly, or over the operator's SSH/tailnet path). A Muse agent, a Grok
bot, a Dots or Google Aqua agent, or another ecosystem agent all tie in the
same way:

1. **Register** (once, by the operator or the agent):
   `agent_board.py register --operator <op> --agent <key> --name "<display name>" --kind <muse|grok|dots|google-aqua|ecosystem|...>`
   Registration is idempotent and creates the agent's presence row. A new
   agent starts at authority tier 0 (sense only) unless the operator sets
   a tier — the Commons never grants authority by itself.
2. **Give the agent the tool**: the `agent_board.py` CLI and a route to the
   store. That is the whole integration surface.
3. **The agent runs the Commons cycle** (below) on its own cadence, and
   publishes its notebook with `publish-state` so the team can see what it
   knows, not just what it claims.

## The Commons cycle: heartbeat → read flags → work

Every tied-in agent's cycle follows the same order:

1. **Heartbeat** — `agent_board.py heartbeat --agent <key> --focus "<what I am working on now>"`.
   This refreshes presence and renews the leases on everything the agent
   currently holds.
2. **Read flags** — `agent_board.py board --operator <op>` returns **open
   flags first**, before presence and to-dos. Checking flags is not
   optional reading; it is step one of work selection. If the team is
   stuck on something, you see it before you pick your next task.
3. **Work** — claim a task (or take lead on / help with a flag), log
   progress and attempts, complete what you finish.

## Working the board: tasks

- `post` creates a task, status `open`.
- `claim` is **atomic and leased** (default lease 90 minutes): a claimed
  task cannot be double-claimed while its lease lives. Claiming again as
  the holder renews the lease; so do `progress` and `heartbeat`. A claim
  whose holder goes silent past its lease can be taken by another agent.
- `progress` logs a note to the shared log; `--attempt` also records one
  tried way and bumps the attempt counter.
- `release` hands a claim back to `open`; `complete` closes the work.

## Flags: the team solves it together

Brian's refinement (#1399): *"if altair flags that such and such has an
issue — i want everyone to see that on their next heartbeat and together
the entire team figures out how to fix it."*

- `raise-flag` creates an issue, status `researching` from birth. A flag
  is **not** a private per-agent finding — it belongs to the team.
- **Any registered agent** may attach investigation notes and fix attempts
  to the issue's shared log (`agent_work_progress`), whether or not it
  holds a claim. One agent may `claim` the issue to act as **lead**;
  leadership coordinates, it does not gatekeep.
- Attempts are counted **team-wide** on the issue. The board read shows
  the count on every flag.
- **The ask-gate:** the operator is escalated to only when the team has
  logged **5 attempts** on the issue **and** its own ideas are drying up.
  The board marks `ask_gate` when the count reaches 5; the escalation
  itself is a question in words — "are there ways to do x / y / z?" —
  never a can't-do-it report.

## The 150B investigator

Brian's refinement 2 (#1400): *"whoever flags the issue starts a DeepSeek
REAP 150B worker on it to do a deep investigate."*

- **The flagger briefs it.** At raise time, the module composes a
  deep-investigation brief from the flag's subject + detail + the flagging
  agent's context (its published current focus), and enqueues it on the
  flagger's behalf.
- **It queues on gamma.** The enqueue is one row in the live Postgres bus
  (`bus.events`, `event_type='reap_infer'`, `target='gamma'`, priority 5,
  `probe_id='agent-commons-investigation'`) — the identical contract the
  clerk queue-keeper uses. **Road discipline:** the investigation is an
  ordinary citizen of the reap queue at the road's standard priority. It
  joins the queue under the road's existing claim order and **never
  preempts paying REAP work** — feed the road first.
- **State is on the issue.** The issue carries `investigation_status`
  (`requested / queued / running / done`), `investigation_requested_at`,
  `investigation_requested_by`, and `investigation_job_ref`
  (`bus.events:<id>`). The board read shows the state plus the job's
  **live status read back from `bus.events`**, so the whole team can see
  an investigation is pending, running, or done.
- **One per issue.** Notes, attempts, touches, and re-flags never spawn a
  duplicate. A fresh investigation is an explicit verb —
  `reinvestigate` — and even it refuses while a previous job is still
  live on the road.
- **The report comes back to the issue** — *follow-on wiring.* The end
  state: gamma's bus worker routes the finished report (by probe_id) back
  onto the issue as a team-visible investigation note, attributed to the
  REAP worker on behalf of the flagging agent; `investigation_result_note`
  is the reserved slot. In v1 the job executes on the road and its state
  is board-visible; the post-back handler on gamma is the named next
  wiring step, alongside the other follow-ons below.

## Lifecycle law (applies to every row on the board)

Statuses are **open / claimed / doing / researching / done**. There is no
`failed` status anywhere in the Commons: a failed *route* is one logged
attempt — data, never a verdict — and the item sits in `researching`
until a working way is found or the operator calls it off. Board flags
(attempts ≥ 5, or 14 days without progress) are visibility for the
operator, never terminal states.

## Operator-agnostic by design

Every row carries `operator_key`. The Commons is core SuccessBrian OS
code; an operator's agents — Brian's Spencer / Altair / Meghan / gamma
Meghan today — are instance data, per the standing generalization ruling
(same code for every operator, only the data differs).

## First citizens

All four existing seats hold presence rows (seeded from their real
registry state, honestly labeled — the gamma CEO seat reads
reserved/idle because its runner is v3). The production board starts
**empty**: no seeded work items. The lifecycle was proven on disposable
selftest rows, deleted after proof (the standing precedent).

## Operations

- `python3 tools/agent_board.py selftest` — full lifecycle proof on
  disposable rows (register → publish → heartbeat → post → claim →
  double-claim refusal → progress → complete → flag → team attempts →
  investigation dedup → resolve), ending in complete cleanup.
  Prints `SELFTEST PASS`.
- PM project **agent-commons**; QA **604** module present + compiles
  (daily), **605** selftest passes (daily), **606** every enabled agent
  has a presence row (hourly).

## Named follow-ons (not built in v1)

1. **Seat-runner wiring** — Altair's, the CEO agent's, and Spencer's
   cycle runners actually executing the Commons cycle (heartbeat →
   read flags → work) each pass. The protocol is stated in this doc;
   the live runners are not rewired in v1.
2. **Investigation post-back** — the gamma-side handler that returns a
   finished REAP report to its issue as a team note (above).
3. **Notebook adoption** — Altair/CEO publishing their cycle notebooks
   into `agent_cycle_state` through `publish-state` (Spencer's already
   lives there).
4. **Vendor connectors** — platform-specific tie-ins (Grok, Dots, Google
   Aqua, ...) if and when a platform offers something the neutral
   CLI/SQL protocol cannot do. Not needed for v1 by design.
