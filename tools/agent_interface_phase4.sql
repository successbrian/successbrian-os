-- agent_interface_phase4.sql — AGENT INTERFACE v1 (Phase 4): the
-- EMAIL DOOR machinery for OUTSIDE agents / owners in SuccessBrian OS.
--
-- Brian's ruling, 2026-11-15 08:32 CST: "Rule it — and start building
-- v1" (email a full v1 door, per the extra-doors dig merged into the
-- plan). Phase 1 (registration + permission record) is
-- tools/agent_interface.sql; Phase 2 (board / dump / pending-approval)
-- is tools/agent_interface_phase2.sql; Phase 3 (read scopes) is
-- tools/agent_interface_phase3.sql; this file is purely ADDITIVE on
-- top of all three:
--   1. agent_interface_email_addresses — per-owner SECRET capability
--      addresses (the Things/Asana/Todoist pattern from the dig). The
--      address token is stored SHA-256 HASHED ONLY, exactly like the
--      agent tokens: the plain address is shown once, at creation.
--      The domain is a CONFIG PLACEHOLDER (default
--      sbos-owner-domain.example) — NOT a real configured domain.
--   2. agent_interface_email_log — every inbound message the door
--      processed: accepted or rejected, with the reason, the capture
--      it landed as (if any), and any approval decision it carried.
--      This is the owner's inspection record for the door.
--   3. agent_interface_outbox — outbound digests / approval prompts
--      are COMPOSED here and sit at status 'queued'. The status CHECK
--      admits 'queued' ONLY: a 'sent' status is unrepresentable in
--      this table, because NOTHING in Phase 4 sends email. Sending
--      belongs to the live hookup (see below).
--   4. the audit event vocabulary widens again (same append-only
--      table): email address lifecycle, accept/reject, decisions,
--      and outbox composition are audited. Email-door events carry
--      agent_key 'email-door' (the door's own system tag — email is
--      an owner door, not an agent door) + the owner key.
--
-- SCOPE BOUNDARY (ruled for this phase): Phase 4 builds the email-door
-- MACHINERY inside SBOS only. It does NOT sign up for any email
-- provider, does NOT change any DNS, does NOT send any real email,
-- and does NOT open any public endpoint. The LIVE HOOKUP is a
-- separate named step that needs the owner's own go: choosing an
-- email provider, configuring the real domain (DNS: MX / SPF / DKIM /
-- DMARC), and pointing the provider's inbound webhook at the install.
-- Until then, inbound processing runs on payload files handed to
-- tools/agent_interface.py email-process, and outbound digests sit in
-- the outbox as 'queued', unsent.
--
-- AUTH MODEL (the dig's mandatory trio): (1) the capability address
-- itself is a credential — possession of the unguessable address is
-- required before anything is read; (2) aligned authentication — a
-- message is accepted as the owner's only if the payload's
-- provider-reported results show DMARC pass AND (aligned SPF pass OR
-- aligned DKIM pass); missing/failed auth fails CLOSED (rejected +
-- audited), and the From header alone is never trusted; (3) contents
-- are DATA, never instructions — accepted mail lands through the dump
-- door's own capture path with that rule stamped into its provenance.
--
-- INBOUND PAYLOAD SHAPE: modelled on Postmark's inbound webhook JSON
-- (From / To / Subject / TextBody / HtmlBody / MailboxHash are
-- Postmark's documented fields, per the 2026-11-15 extra-doors dig).
-- Postmark reports authentication through SpamAssassin result headers
-- rather than a structured object, so the payload's
-- "AuthenticationResults" object ({SPF, SPFAligned, DKIM, DKIMAligned,
-- DMARC}) is SBOS's OWN normalized field: at live hookup, the trusted
-- webhook receiver populates it from the provider's reported results.
-- The processor reads ONLY that field for auth — never any header
-- inside the message itself.
--
-- OPERATOR-AGNOSTIC: every row carries operator_key; an owner's email
-- door is data, never schema. Agent Commons tables are NOT touched.

create table if not exists successbrian_os.agent_interface_email_addresses (
  id            bigint generated always as identity primary key,
  operator_key  text not null,
  token_hash    text not null unique,
  domain        text not null,
  revoked       boolean not null default false,
  created_at    timestamptz not null default now(),
  revoked_at    timestamptz
);
create index if not exists agent_interface_email_addr_operator_idx
  on successbrian_os.agent_interface_email_addresses (operator_key);
comment on table successbrian_os.agent_interface_email_addresses is 'Agent Interface v1 Phase 4: per-owner SECRET email capability addresses. Token stored SHA-256 hashed only (plain address shown once at creation); domain is a config placeholder, NOT a real configured domain — the live hookup (provider + DNS) is a separate step needing the owner''s go. Brian ruling 2026-11-15.';

create table if not exists successbrian_os.agent_interface_email_log (
  id            bigint generated always as identity primary key,
  operator_key  text,
  address_id    bigint,
  to_address    text,
  sender        text,
  subject       text,
  outcome       text not null check (outcome in ('accepted','rejected')),
  reason        text,
  decision      text check (decision in ('approved','denied','attempted')),
  request_id    bigint,
  capture_id    bigint,
  created_at    timestamptz not null default now()
);
create index if not exists agent_interface_email_log_operator_idx
  on successbrian_os.agent_interface_email_log (operator_key, created_at desc);
comment on table successbrian_os.agent_interface_email_log is 'Agent Interface v1 Phase 4: the email door''s inspection record — every inbound message processed, accepted or rejected with its reason, the capture it landed as, and any approval decision it carried. Contents of messages are never stored here (they land as captures); this is metadata only.';

create table if not exists successbrian_os.agent_interface_outbox (
  id            bigint generated always as identity primary key,
  operator_key  text not null,
  to_address    text not null,
  subject       text not null,
  body          text not null,
  kind          text not null default 'digest'
                check (kind in ('digest','approve_request')),
  request_id    bigint,
  status        text not null default 'queued' check (status in ('queued')),
  created_at    timestamptz not null default now()
);
create index if not exists agent_interface_outbox_operator_idx
  on successbrian_os.agent_interface_outbox (operator_key, created_at desc);
comment on table successbrian_os.agent_interface_outbox is 'Agent Interface v1 Phase 4: composed outbound email (digests / approval prompts) sitting UNSENT at status queued — the CHECK admits queued only, so a sent status is unrepresentable. NOTHING sends from this table in Phase 4; sending belongs to the live hookup, a separate step needing the owner''s go.';

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
                   'outbox_queued'));
comment on table successbrian_os.agent_interface_audit is 'APPEND-ONLY audit of Agent Interface events, each row carrying the agent name tag: Phase 1 registration/token/tier events + Phase 2 board writes, dumps, approval decisions + Phase 3 scope grants/changes and scoped reads + Phase 4 email-door events (agent_key email-door: address lifecycle, accept/reject, decisions, outbox composition). Brian ruling 2026-11-15 (everything written down, with provenance).';
