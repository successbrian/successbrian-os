-- agent_interface_phase3.sql — AGENT INTERFACE v1 (Phase 3): per-agent
-- READ SCOPES + the scoped reading doors for OUTSIDE agents in
-- SuccessBrian OS.
--
-- Brian's ruling, 2026-11-15 08:32 CST: "Rule it — and start building
-- v1". Phase 1 (registration + permission record) is
-- tools/agent_interface.sql; Phase 2 (board / dump / pending-approval)
-- is tools/agent_interface_phase2.sql; this file is purely ADDITIVE on
-- top of both:
--   1. agent_interface_agents gains read_scopes — the set of reading
--      doors the OWNER granted this one agent. Existing agents default
--      to the minimal set ('board','requests') — nobody's access is
--      widened by this migration, ever. Widening is an explicit,
--      audited owner act (set-scopes), never a default.
--   2. the audit event vocabulary widens again (same append-only
--      table): scope grants/changes and every scoped read + refusal
--      are audited with the agent's name tag.
--
-- SCOPE VOCABULARY (fitted to what exists on this install — see
-- tools/agent_interface.py PHASE 3 for the per-scope source map):
--   board     — the Agent Commons board (agent_board view)
--   requests  — the agent's OWN pending-approval requests only
--   goals     — successbrian_os.sbos_goals (Atlas plans on top of it)
--   people    — people_unified.people.people (bounded slice; contact
--               details are NOT served through this door)
--   calendar  — successbrian_os.life_calendar (open items; past-due
--               open items are carried forward, never dropped)
--   scorecard — NO data store exists in this install yet (the weekly
--               scorecard is a template/article, not data). The door
--               exists and answers honestly "not available yet" —
--               it never fabricates numbers.
--
-- READS NEVER MUTATE OWNER DATA: the reading doors run SELECTs only.
-- The only writes the interface makes on a read are its own audit
-- rows. Agent Commons tables are not touched by this file.

alter table successbrian_os.agent_interface_agents
  add column if not exists read_scopes text[]
    not null default array['board','requests']::text[];
alter table successbrian_os.agent_interface_agents
  drop constraint if exists agent_interface_agents_read_scopes_check;
alter table successbrian_os.agent_interface_agents
  add constraint agent_interface_agents_read_scopes_check
  check (read_scopes <@ array['board','requests','goals','people',
                              'calendar','scorecard']::text[]);
comment on column successbrian_os.agent_interface_agents.read_scopes is 'Agent Interface v1 Phase 3: the reading doors the owner granted THIS agent (subset of board/requests/goals/people/calendar/scorecard). Default is the minimal board+requests; widening is an explicit audited owner act (scopes_changed), never a default. Brian ruling 2026-11-15.';

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
                   'action_requested','action_approved','action_denied',
                   'scopes_changed','read','scope_refused'));
comment on table successbrian_os.agent_interface_audit is 'APPEND-ONLY audit of Agent Interface events, each row carrying the agent name tag: Phase 1 registration/token/tier events + Phase 2 board writes, dumps, approval decisions + Phase 3 scope grants/changes and every scoped read + scope refusal. Brian ruling 2026-11-15 (everything written down, with provenance).';
