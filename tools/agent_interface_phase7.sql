-- agent_interface_phase7.sql — AGENT INTERFACE v1 (Phase 7): the
-- G-PACKAGE POLISH for OUTSIDE agents in SuccessBrian OS.
--
-- Brian's ruling, 2026-11-15 08:32 CST: "Rule it — and start building
-- v1". The readiness test (capture #1892) PASSED all six steps and
-- named eight polish gaps, G1–G8; the plan's own rule says a step
-- that needs hand-holding is the next build. This file is the only
-- schema touch the G-package needs, purely ADDITIVE:
--   * successbrian_os.agent_interface_owners — the owner's Section 1
--     profile (G2): the facts render-packet fills the arrival packet
--     from (owner name, business, business summary, timezone,
--     approval channel, install name), recorded owner-side via
--     set-owner-profile. A field never recorded stays NULL —
--     unknown stays unknown, never invented.
--   * the audit event vocabulary widens (same append-only table)
--     with the phase-7 events: owner_profile_set + packet_rendered
--     (under the system tag owner-profile) and session_resumed
--     (the G5 where-was-i read, under the resuming agent's tag).
-- Everything else in the G-package is code + packet text: G1 the
-- CLI appendix (data in the module, asserted against --help by
-- selftest7), G3 packet scope wording, G4 receipt enrichment,
-- G5 where-was-i, G6 the JSON dump receipt, G7 the request-action
-- payload schema (enforced for NEW requests only — stored payloads
-- are data), G8 board-read claim_lease_until + the caller's own
-- progress notes. No existing table, column, or behavior changes.

create table if not exists successbrian_os.agent_interface_owners (
  operator_key     text primary key,
  owner_name       text,
  business         text,
  business_summary text,
  timezone         text,
  approval_channel text,
  install_name     text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
comment on table successbrian_os.agent_interface_owners is 'G2 (Phase 7): per-owner Section 1 profile for the agent interface — the facts render-packet fills the arrival packet from. Recorded owner-side via set-owner-profile; unrecorded fields stay NULL (unknown is recorded as unknown, never filled in). Brian ruling 2026-11-15; readiness gap G2, capture #1892.';

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
                   'scopes_changed','read','scope_refused',
                   'email_address_created','email_address_revoked',
                   'email_accepted','email_rejected','email_decision',
                   'outbox_queued',
                   'changes_read',
                   'webhook_registered','webhook_revoked',
                   'webhook_queued','webhook_delivered',
                   'webhook_delivery_failed',
                   'folder_init','folder_drop','folder_drop_skipped',
                   'folder_draft','ics_feed',
                   'owner_profile_set','packet_rendered',
                   'session_resumed'));
comment on table successbrian_os.agent_interface_audit is 'APPEND-ONLY audit of Agent Interface events, each row carrying the agent name tag: Phase 1 registration/token/tier events + Phase 2 board writes, dumps, approval decisions + Phase 3 scope grants/changes and scoped reads + Phase 4 email-door events (agent_key email-door) + Phase 5 wake-up lite (changes-feed reads; webhook lifecycle under agent_key wake-up) + Phase 6 folder lite (folder_init under agent_key folder-door; folder_drop / folder_drop_skipped / folder_draft under the acting agent) and ICS feed generations (ics_feed) + Phase 7 G-package (owner_profile_set / packet_rendered under agent_key owner-profile; session_resumed under the resuming agent). Brian ruling 2026-11-15 (everything written down, with provenance).';
