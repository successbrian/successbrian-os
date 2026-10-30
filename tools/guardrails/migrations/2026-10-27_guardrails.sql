-- SBOS guardrails — migration 2026-10-27 (WS-CAP, Brian 2026-10-27).
-- State home for capacity sensing, DealsDesk capacity needs, and the
-- advisory earned-autonomy ladder. Mirrors SCHEMA_SQL in
-- tools/guardrails/guardrails_common.py (idempotent).
-- NO dollar/budget tables: scarcity here is LOCAL horsepower only.
CREATE TABLE IF NOT EXISTS successbrian_os.capacity_nodes (
    name TEXT PRIMARY KEY,
    host TEXT,
    endpoint TEXT,
    kind TEXT NOT NULL DEFAULT 'llama_cpp',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.capacity_snapshots (
    id BIGSERIAL PRIMARY KEY,
    node_name TEXT NOT NULL REFERENCES successbrian_os.capacity_nodes(name),
    taken_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reachable BOOLEAN NOT NULL DEFAULT false,
    latency_ms INT,
    slots_total INT,
    slots_busy INT,
    load1 NUMERIC,
    cpu_count INT,
    mem_total_mb INT,
    mem_available_mb INT,
    mem_pressure_pct NUMERIC,
    saturated BOOLEAN NOT NULL DEFAULT false,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS capacity_snapshots_node_time_idx
    ON successbrian_os.capacity_snapshots (node_name, taken_at DESC);
CREATE TABLE IF NOT EXISTS successbrian_os.capacity_needs (
    id BIGSERIAL PRIMARY KEY,
    dedupe_key TEXT UNIQUE NOT NULL,
    node_name TEXT NOT NULL,
    item TEXT NOT NULL,
    sbos_need_request_id INT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','cleared')),
    first_filed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    cleared_at TIMESTAMPTZ,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS successbrian_os.autonomy_action_types (
    action_type TEXT PRIMARY KEY,
    display_name TEXT,
    current_level INT NOT NULL DEFAULT 0 CHECK (current_level BETWEEN 0 AND 3),
    streak INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.autonomy_events (
    id BIGSERIAL PRIMARY KEY,
    action_type TEXT NOT NULL REFERENCES successbrian_os.autonomy_action_types(action_type),
    outcome TEXT NOT NULL CHECK (outcome IN ('approved_clean','approved_edited','rejected')),
    actor TEXT,
    note TEXT,
    level_before INT,
    level_after INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.guardrails_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO successbrian_os.guardrails_config (key, value)
VALUES ('autonomy_promote_n','5')
ON CONFLICT (key) DO NOTHING;

-- Seed: only endpoints verified on k11-alpha on 2026-10-27 from
-- tools/pm/repair_ladder.py WORKERS (llama.cpp servers, local host).
-- K11 bravo/gamma and node-zero are NOT seeded: no inference endpoint
-- for them was verified in fleet code/config on alpha.
INSERT INTO successbrian_os.capacity_nodes (name, host, endpoint, kind) VALUES
  ('sonic','127.0.0.1','http://127.0.0.1:11439','llama_cpp'),
  ('morpheus','127.0.0.1','http://127.0.0.1:11437','llama_cpp'),
  ('penny','127.0.0.1','http://127.0.0.1:11438','llama_cpp'),
  ('k11-alpha-local','127.0.0.1',NULL,'host')
ON CONFLICT (name) DO NOTHING;
