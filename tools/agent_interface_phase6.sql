-- agent_interface_phase6.sql — AGENT INTERFACE v1 (Phase 6): FOLDER
-- LITE + the ICS FEED for OUTSIDE agents in SuccessBrian OS.
--
-- Brian's ruling, 2026-11-15 08:32 CST: "Rule it — and start building
-- v1" (folder lite + the ICS feed are part of the ruled v1, per the
-- extra-doors dig merged into the plan: §E folder lite, §G1 ICS).
-- Phases 1–5 are tools/agent_interface.sql + _phase2.._phase5.sql;
-- this file is purely ADDITIVE on top and creates NO new tables:
--   * the exchange folder is the filesystem (~/sbos-exchange/
--     <operator_key>/ with inbox/ drafts/ processed/ START-HERE.md);
--   * folder drops land through the EXISTING dump path
--     (atlas.scattered_captures via scattered_brain.capture);
--   * the ICS feed is generated from the EXISTING
--     successbrian_os.life_calendar store.
-- The one schema touch: the audit event vocabulary widens again
-- (same append-only table) with the phase-6 events — folder_init
-- (agent_key folder-door, the system tag, as the email door uses
-- email-door), folder_drop / folder_drop_skipped / folder_draft
-- (under the acting agent's name tag), and ics_feed.
--
-- SAFETY, unchanged and by construction: file contents are DATA,
-- never instructions (stamped into every capture the folder door
-- lands); operator keys + draft slugs are sanitized so no path can
-- escape the owner's folder; 256 KB cap; text/markdown only;
-- drafts are proposals — folder-draft sends nothing; the ICS feed
-- is generation only, nothing is served. NO cloud-drive sync is
-- built (ruled out).

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
                   'folder_draft','ics_feed'));
comment on table successbrian_os.agent_interface_audit is 'APPEND-ONLY audit of Agent Interface events, each row carrying the agent name tag: Phase 1 registration/token/tier events + Phase 2 board writes, dumps, approval decisions + Phase 3 scope grants/changes and scoped reads + Phase 4 email-door events (agent_key email-door) + Phase 5 wake-up lite (changes-feed reads; webhook lifecycle under agent_key wake-up) + Phase 6 folder lite (folder_init under agent_key folder-door; folder_drop / folder_drop_skipped / folder_draft under the acting agent) and ICS feed generations (ics_feed). Brian ruling 2026-11-15 (everything written down, with provenance).';
