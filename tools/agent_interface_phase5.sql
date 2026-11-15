-- agent_interface_phase5.sql — AGENT INTERFACE v1 (Phase 5): WAKE-UP
-- LITE for OUTSIDE agents in SuccessBrian OS.
--
-- Brian's ruling, 2026-11-15 08:32 CST: "Rule it — and start building
-- v1" (wake-up lite is part of the ruled v1, per the extra-doors dig
-- merged into the plan). Phases 1–4 are tools/agent_interface.sql +
-- _phase2/_phase3/_phase4.sql; this file is purely ADDITIVE on top:
--   1. agent_interface_webhooks — owner-registered wake-up endpoints.
--   2. agent_interface_webhook_deliveries — the delivery queue: one
--      row per (webhook, wake-worthy event), carrying the EXACT
--      data-only payload that gets POSTed, its status, and its
--      attempt trail. A delivery row's id IS the delivery id —
--      retries reuse the same row and the same id, never a new one.
--   3. the audit event vocabulary widens again (same append-only
--      table): changes-feed reads and the webhook lifecycle.
-- The changes-since FEED itself needs no table: it reads the live
-- sources (agent_work_items / agent_interface_requests / the
-- agent_board view) behind a timestamp cursor. The 'events' read
-- scope that gates it is a value in the Phase 3 read_scopes array —
-- part of the vocabulary, granted only by an explicit owner act,
-- never part of the registration default. The Phase 3 CHECK on
-- read_scopes is widened below to admit 'events' (existing grants
-- are untouched: adding a vocabulary value grants it to nobody).
--
-- WHY LITE (the dig, §A): most personal agents are NOT listeners.
-- OpenClaw is the only mainstream host found with a general inbound
-- webhook door; ChatGPT's event triggers fire only from Gmail /
-- Slack / GitHub; MCP notifications reach only a client already
-- holding a stream open. So v1 wake-up is: a changes feed agents
-- POLL on a schedule (recipes in the packet), plus signed outbound
-- webhooks for the receivers that ARE always on (an OpenClaw
-- gateway, a Zapier/n8n-style middleman, the owner's own listener).
-- Full push notifications ride with MCP in v2 (ruled scope).
--
-- PAYLOADS ARE DATA-ONLY — IDS AND A TIMESTAMP, NEVER PROSE. A
-- wake-up payload is untrusted content aimed at an agent: anything
-- prose-shaped in it would be an instruction-injection surface. The
-- payload is exactly {event_id, kind, id, at} — the audit id of the
-- triggering event, the change kind (request / request_decision /
-- flag), the changed record's id, and when it happened. A receiver
-- that wants details fetches them through its own scoped token.
-- tools/agent_interface.py webhook-guard proves on live rows that
-- every queued/delivered payload keeps that shape.
--
-- SIGNING: HMAC-SHA256 over "<timestamp>.<raw body>" (Stripe's
-- pattern), sent as X-SBOS-Signature: t=<ts>,v1=<hex> with the
-- delivery id in X-SBOS-Delivery-Id for dedupe; receivers should
-- allow ~5 minutes of timestamp tolerance. Delivery is
-- at-least-once: receivers must be idempotent on the delivery id.
--
-- *** THE SIGNING SECRET — KNOWN TRADEOFF, STATED PLAINLY ***
-- HMAC signing needs the RAW secret on the server at delivery time;
-- a hash cannot sign. This install has no secrets vault / encrypted
-- secret store for the agent interface, so the secret is stored in
-- the dedicated agent_interface_webhooks table, in the owner's own
-- database, on the owner's own machine — the same trust boundary as
-- the rest of the owner's SBOS data. It is NEVER written to the
-- audit (only a SHA-256 fingerprint is), never shown after
-- registration (listings show the fingerprint), and access rides the
-- database's own access control. This is a deliberate, flagged
-- tradeoff for v1, to be revisited if/when the install gains a real
-- secrets store. Owners should treat the webhook secret like a
-- password and rotate it by revoking + re-registering the webhook.
--
-- NO EXTERNAL CALLS are made by this DDL or by the build: delivery
-- happens only when the owner/operator runs the deliver verb, to
-- endpoints the OWNER registered. The selftest delivers only to a
-- loopback listener on the install machine itself.
--
-- OPERATOR-AGNOSTIC: every row carries operator_key. Agent Commons
-- tables are NOT touched.

create table if not exists successbrian_os.agent_interface_webhooks (
  id                 bigint generated always as identity primary key,
  operator_key       text not null,
  url                text not null,
  secret             text not null,
  secret_fingerprint text not null,
  revoked            boolean not null default false,
  created_at         timestamptz not null default now(),
  revoked_at         timestamptz
);
create index if not exists agent_interface_webhooks_operator_idx
  on successbrian_os.agent_interface_webhooks (operator_key);
comment on table successbrian_os.agent_interface_webhooks is 'Agent Interface v1 Phase 5 (wake-up lite): owner-registered wake-up webhook endpoints. The signing secret is stored RAW in this dedicated table because HMAC signing requires it server-side — a KNOWN, FLAGGED v1 tradeoff (no secrets vault exists in this install); only its SHA-256 fingerprint is ever audited or listed. Brian ruling 2026-11-15.';

create table if not exists successbrian_os.agent_interface_webhook_deliveries (
  id           bigint generated always as identity primary key,
  webhook_id   bigint not null,
  operator_key text not null,
  event_id     bigint not null,
  kind         text not null check (kind in ('request','request_decision','flag')),
  ref_id       bigint not null,
  payload      jsonb not null,
  status       text not null default 'queued'
               check (status in ('queued','delivered')),
  attempts     integer not null default 0,
  last_error   text,
  created_at   timestamptz not null default now(),
  delivered_at timestamptz
);
create index if not exists agent_interface_webhook_deliveries_queue_idx
  on successbrian_os.agent_interface_webhook_deliveries (status, id);
create index if not exists agent_interface_webhook_deliveries_operator_idx
  on successbrian_os.agent_interface_webhook_deliveries (operator_key, id);
comment on table successbrian_os.agent_interface_webhook_deliveries is 'Agent Interface v1 Phase 5: the wake-up delivery queue. One row per (webhook, event); the row id IS the delivery id (retries reuse it — dedupe key for receivers). Payload is data-only {event_id, kind, id, at} — never prose (injection surface). A failing delivery stays queued with its error recorded — visible, never silently dropped.';

alter table successbrian_os.agent_interface_agents
  drop constraint if exists agent_interface_agents_read_scopes_check;
alter table successbrian_os.agent_interface_agents
  add constraint agent_interface_agents_read_scopes_check
  check (read_scopes <@ array['board','requests','goals','people',
                              'calendar','scorecard','events']::text[]);
comment on column successbrian_os.agent_interface_agents.read_scopes is 'Agent Interface v1 Phase 3 + Phase 5: the reading doors the owner granted THIS agent (subset of board/requests/goals/people/calendar/scorecard/events — events gates the Phase 5 changes-since feed). Default is the minimal board+requests; widening is an explicit audited owner act (scopes_changed), never a default. Brian ruling 2026-11-15.';

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
                   'webhook_delivery_failed'));
comment on table successbrian_os.agent_interface_audit is 'APPEND-ONLY audit of Agent Interface events, each row carrying the agent name tag: Phase 1 registration/token/tier events + Phase 2 board writes, dumps, approval decisions + Phase 3 scope grants/changes and scoped reads + Phase 4 email-door events (agent_key email-door) + Phase 5 wake-up lite (changes-feed reads; webhook lifecycle under agent_key wake-up). Brian ruling 2026-11-15 (everything written down, with provenance).';
