-- agent_interface_phase2.sql — AGENT INTERFACE v1 (Phase 2): the board
-- door, the dump door, and the PENDING-APPROVAL machinery for OUTSIDE
-- agents in SuccessBrian OS.
--
-- Brian's ruling, 2026-11-15 08:32 CST: "Rule it — and start building
-- v1" (the v1→v2→v3 agent-interface path). Phase 1 (registration +
-- permission record) is tools/agent_interface.sql; this file is purely
-- ADDITIVE on top of it:
--   1. the audit event vocabulary widens (same table, more event kinds —
--      board writes, dumps, and approval decisions are audited too);
--   2. one NEW table: agent_interface_requests, the durable
--      pending-approval record for outward acts.
--
-- THE OUTWARD-ACT GATE (ruled safety model — do not weaken): an outside
-- agent NEVER executes an outward act. It files a request here
-- (kind send/contact/buy/publish/post + payload + reason) and the
-- request sits 'pending' until the OWNER approves or denies it.
-- Approval moves the record to 'approved' ONLY — it executes NOTHING.
-- There is deliberately no 'executed' status in this table and no code
-- path anywhere in the agent interface that sends, buys, publishes, or
-- contacts anyone; an owner-facing execution surface is a later phase
-- and does not exist yet.
--
-- Agent Commons tables (agent_presence / agent_work_items /
-- agent_work_progress) are NOT touched by this file: the board door
-- writes through tools/agent_board.py exactly as internal agents do,
-- so Commons behavior is unchanged.
--
-- OPERATOR-AGNOSTIC: every row carries operator_key; vendor stays a
-- name-tag field on the Phase 1 registration record, never a door.

alter table successbrian_os.agent_interface_audit
  drop constraint if exists agent_interface_audit_event_check;
alter table successbrian_os.agent_interface_audit
  add constraint agent_interface_audit_event_check
  check (event in ('registered','token_issued','token_verified',
                   'token_refused','token_revoked','tier_refused',
                   'agent_revoked',
                   'board_focus','board_post','board_claim',
                   'board_claim_refused','board_progress','board_complete',
                   'dump',
                   'action_requested','action_approved','action_denied'));
comment on table successbrian_os.agent_interface_audit is 'APPEND-ONLY audit of Agent Interface events, each row carrying the agent name tag: Phase 1 registration/token/tier events + Phase 2 board writes, dumps, and approval decisions. Brian ruling 2026-11-15 (everything written down, with provenance).';

create table if not exists successbrian_os.agent_interface_requests (
  id           bigint generated always as identity primary key,
  agent_key    text not null,
  operator_key text not null,
  kind         text not null
               check (kind in ('send','contact','buy','publish','post')),
  payload      jsonb not null default '{}'::jsonb,
  reason       text,
  status       text not null default 'pending'
               check (status in ('pending','approved','denied')),
  requested_at timestamptz not null default now(),
  decided_at   timestamptz,
  decided_by   text
);
create index if not exists agent_interface_requests_operator_idx
  on successbrian_os.agent_interface_requests (operator_key, status);
comment on table successbrian_os.agent_interface_requests is 'Agent Interface v1 Phase 2: durable PENDING-APPROVAL record for outward acts requested by outside agents. Status is pending/approved/denied ONLY — approval records the owner''s go and executes NOTHING (no executed state exists by design; no send/buy/publish/contact code path exists in the agent interface). Brian ruling 2026-11-15.';
