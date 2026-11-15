-- agent_interface.sql — AGENT INTERFACE v1 (Phase 1): registration +
-- permission record for OUTSIDE agents in SuccessBrian OS.
--
-- Brian's ruling, 2026-11-15 08:32 CST: "Rule it — and start building
-- v1" (the v1→v2→v3 agent-interface path: simple door first, remote MCP
-- second, directory listings third; email a full v1 door).
--
-- DESIGN: a NEW table family, not an extension of agent_presence.
-- agent_presence (Agent Commons) is the INTERNAL fleet's board presence
-- — who is here and working on what. This family is the OUTSIDE-agent
-- permission record: who an external agent is, which owner it serves,
-- what tier it holds, and the lifecycle of its scoped token. Different
-- trust boundary, different lifecycle; Commons behavior is untouched
-- (additive only).
--
-- SAFETY MODEL (ruled): the token is stored HASHED ONLY (SHA-256) —
-- plaintext exists once, at issue time, in the issuer's hand. Tokens
-- are scoped to a tier (read < propose < act), expire, and are
-- revocable. There is NO agent-callable send/buy/publish verb anywhere
-- in this design: outward acts go through a durable pending approval
-- the owner approves in SBOS (later phase). The audit table is
-- APPEND-ONLY: code never updates or deletes its rows outside the
-- selftest's disposable cleanup.
--
-- OPERATOR-AGNOSTIC: every row carries operator_key; an owner's agents
-- are data, never schema. Vendor is a name-tag field, never a door.

create table if not exists successbrian_os.agent_interface_agents (
  agent_key       text primary key,
  operator_key    text not null,
  display_name    text not null,
  vendor          text not null default 'other',
  tier            text not null default 'read'
                  check (tier in ('read','propose','act')),
  agent_revoked   boolean not null default false,
  token_hash      text,
  token_issued_at timestamptz,
  token_expires_at timestamptz,
  token_revoked   boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index if not exists agent_interface_agents_operator_idx
  on successbrian_os.agent_interface_agents (operator_key);
comment on table successbrian_os.agent_interface_agents is 'Agent Interface v1: registration + permission record for OUTSIDE agents (any vendor). Tier read/propose/act scopes the doors; token stored SHA-256 hashed only, expiring, revocable. Brian ruling 2026-11-15. Companion: tools/agent_interface.py, docs/agent-interface/.';

create table if not exists successbrian_os.agent_interface_audit (
  id           bigint generated always as identity primary key,
  agent_key    text not null,
  operator_key text,
  event        text not null
               check (event in ('registered','token_issued','token_verified',
                                'token_refused','token_revoked','tier_refused',
                                'agent_revoked')),
  detail       jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now()
);
create index if not exists agent_interface_audit_agent_idx
  on successbrian_os.agent_interface_audit (agent_key, created_at);
comment on table successbrian_os.agent_interface_audit is 'APPEND-ONLY audit of Agent Interface registration/token/tier events, each row carrying the agent name tag. Brian ruling 2026-11-15 (everything written down, with provenance).';
