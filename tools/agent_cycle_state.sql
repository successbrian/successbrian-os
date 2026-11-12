-- agent_cycle_state: per-agent cycle notebook state for the Agent Cycle Protocol.
-- Brian's ruling 2026-11-11: Spencer's cycle state moves from a local file on the
-- Muse VM to alpha, so Altair / the CEO agent / other agents can interact with it.
create table if not exists successbrian_os.agent_cycle_state (
  agent_key text primary key,
  state jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
comment on table successbrian_os.agent_cycle_state is 'Per-agent cycle notebook state (dedup seen-set, trend history, counters) for the Agent Cycle Protocol. Brian ruling 2026-11-11: cycle state lives on alpha so Altair, the CEO agent, and other agents can interact with it.';
