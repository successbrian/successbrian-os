-- agent_commons.sql — AGENT COMMONS: the shared work board + presence surface
-- of SuccessBrian OS (companion to the Agent Cycle Protocol family:
-- agent_registry / agent_cycle_runs / agent_findings / agent_cycle_state).
--
-- Brian's order, 2026-11-11 (Intel Bridge capture #1398): "build this as an
-- official successbrian os feature — where the user can tie in their own
-- agent (such as a muse agent, grok bot, dots, google aqua or even other
-- ecosystem agents) and these agents all share what they are currently
-- working on... like a common 'to do' list..."
--
-- OPERATOR-AGNOSTIC BY DESIGN (Brian's SBOS generalization ruling,
-- 2026-10-29): every row carries operator_key. The feature is core code;
-- an operator's agents are data rows. Brian's four seats
-- (spencer / altair / ceo / gamma-ceo) are instance data, not schema.
--
-- LIFECYCLE LAW (Brian, 2026-10-29): item statuses are
-- open / claimed / doing / researching / done — NEVER 'failed'. An item
-- that resists sits in 'researching' while ways are tried; every try is
-- a logged progress row. FLAGS, not verdicts: attempts >= 5 or 14 days
-- without progress flag the item up (see the agent_board view).
--
-- Written once, driven through tools/agent_board.py — the vendor-neutral
-- tie-in interface. An outside agent (Muse, Grok, Dots, Google Aqua, or
-- any other) only needs shell/SSH or SQL access to the operator's store.

create table if not exists successbrian_os.agent_presence (
  agent_key     text primary key,
  operator_key  text not null,
  current_focus text,
  status_note   text,
  updated_at    timestamptz not null default now()
);
create index if not exists agent_presence_operator_idx
  on successbrian_os.agent_presence (operator_key);
comment on table successbrian_os.agent_presence is 'Agent Commons presence: one row per registered agent — what it is currently working on (current_focus) and a free status note, refreshed by heartbeat. Brian order 2026-11-11, capture #1398.';

create table if not exists successbrian_os.agent_work_items (
  id                bigint generated always as identity primary key,
  operator_key      text not null,
  title             text not null,
  detail            text,
  status            text not null default 'open'
                    check (status in ('open','claimed','doing','researching','done')),
  created_by_agent  text not null,
  claimed_by_agent  text,
  claimed_at        timestamptz,
  claim_lease_until timestamptz,
  attempts          integer not null default 0,
  last_progress_at  timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index if not exists agent_work_items_operator_status_idx
  on successbrian_os.agent_work_items (operator_key, status);
create index if not exists agent_work_items_claimed_by_idx
  on successbrian_os.agent_work_items (claimed_by_agent);
-- kind: 'task' = a to-do item; 'issue' = a FLAG raised by an agent (Brian's
-- refinement, capture #1399): board-visible to every agent on its next
-- heartbeat, worked by the whole team from one shared attempt log.
alter table successbrian_os.agent_work_items
  add column if not exists kind text not null default 'task'
  check (kind in ('task','issue'));
create index if not exists agent_work_items_kind_idx
  on successbrian_os.agent_work_items (kind, status);
comment on table successbrian_os.agent_work_items is 'Agent Commons common work board (the shared to-do list). kind=task: a to-do, claimed atomically under a lease (a claimed task cannot be double-claimed while its lease lives; heartbeat/progress refresh the lease). kind=issue: a FLAG — any agent may post notes/attempts to its shared log while one agent holds the lead claim. Statuses follow the can-do lifecycle — no failed state exists. Brian order 2026-11-11, captures #1398 + #1399.';

-- THE 150B INVESTIGATOR (Brian's refinement 2, capture #1400): raising a
-- flag automatically starts a DeepSeek REAP 150B deep-investigation. The
-- board-side half lives here: the issue carries its investigation state.
-- The live enqueue is one row in bus.events (event_type 'reap_infer',
-- target 'gamma', priority 5 — the road's standard class; the
-- investigation JOINS the reap queue and never preempts paying work).
-- investigation_job_ref points at that row ('bus.events:<id>'); its live
-- status is read from bus.events at board-read time. The worker-side
-- report post-back (gamma writing its report onto the issue as a team
-- note) is follow-on wiring; investigation_result_note is its slot.
alter table successbrian_os.agent_work_items
  add column if not exists investigation_status text not null default 'none'
  check (investigation_status in ('none','requested','queued','running','done'));
alter table successbrian_os.agent_work_items
  add column if not exists investigation_requested_at timestamptz;
alter table successbrian_os.agent_work_items
  add column if not exists investigation_requested_by text;
alter table successbrian_os.agent_work_items
  add column if not exists investigation_job_ref text;
alter table successbrian_os.agent_work_items
  add column if not exists investigation_result_note text;

create table if not exists successbrian_os.agent_work_progress (
  id         bigint generated always as identity primary key,
  item_id    bigint not null references successbrian_os.agent_work_items (id) on delete cascade,
  agent_key  text not null,
  note       text,
  is_attempt boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists agent_work_progress_item_idx
  on successbrian_os.agent_work_progress (item_id, created_at);
comment on table successbrian_os.agent_work_progress is 'Agent Commons progress log: every progress note and every logged attempt on a work item (an attempt = one way tried; five attempts or 14 days without progress raises the flag — a dead way is data, never a verdict).';

-- (drop + create, not create-or-replace: adding the kind column changed
-- the view's column order, which CREATE OR REPLACE VIEW refuses.)
drop view if exists successbrian_os.agent_board;
create view successbrian_os.agent_board as
select
  i.*,
  (i.status <> 'done' and i.attempts >= 5) as flag_attempts,
  (i.status <> 'done'
   and coalesce(i.last_progress_at, i.created_at) < now() - interval '14 days') as flag_stale,
  case
    when i.status <> 'done' and i.attempts >= 5
         and coalesce(i.last_progress_at, i.created_at) < now() - interval '14 days'
      then 'attempts>=5 and no progress in 14 days'
    when i.status <> 'done' and i.attempts >= 5
      then 'attempts>=5'
    when i.status <> 'done'
         and coalesce(i.last_progress_at, i.created_at) < now() - interval '14 days'
      then 'no progress in 14 days'
    else null
  end as flag_reason
from successbrian_os.agent_work_items i;
comment on view successbrian_os.agent_board is 'Agent Commons board read surface: work items plus lifecycle flags (attempts>=5 / 14 days no progress). A flag is visibility for the operator, never a terminal state.';
