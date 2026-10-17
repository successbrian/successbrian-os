-- PURPOSE: ecosystem signal feed — the raw observations that the needs-derivation
--   runner evaluates. Signals are facts (cpu temp, follower counts, blog hits);
--   thresholds turn them into screams (needs) in sbos_need_requests.
-- WHY: Brian 2026-10-17 — "successbrian-os needs to be improved to better detect
--   the ecosystem needs... and it feeds the screams."
-- CALLED BY: tools/signals/collect_*.py writers; tools/signals/derive_needs.py reader.

CREATE TABLE IF NOT EXISTS successbrian_os.ecosystem_signals (
    id          SERIAL PRIMARY KEY,
    signal_key  TEXT NOT NULL UNIQUE,
    signal_class TEXT NOT NULL,  -- infra | pipeline | audience | blog | email | funnel | seo
    source      TEXT NOT NULL DEFAULT 'spencer',
    value_num   DOUBLE PRECISION,
    value_text  TEXT,
    meta        JSONB NOT NULL DEFAULT '{}',
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signals_class ON successbrian_os.ecosystem_signals(signal_class);
CREATE INDEX IF NOT EXISTS idx_signals_observed ON successbrian_os.ecosystem_signals(observed_at);

-- Thresholds: the rules that turn a signal breach into a scream.
-- condition 'gt': scream when latest value_num > threshold_num
-- condition 'lt': scream when latest value_num < threshold_num
CREATE TABLE IF NOT EXISTS successbrian_os.signal_thresholds (
    id             SERIAL PRIMARY KEY,
    signal_key     TEXT NOT NULL,
    signal_class   TEXT NOT NULL,
    condition      TEXT NOT NULL CHECK (condition IN ('gt', 'lt')),
    threshold_num  DOUBLE PRECISION NOT NULL,
    need_item      TEXT NOT NULL,
    need_specs     TEXT NOT NULL DEFAULT '',
    need_class     TEXT NOT NULL DEFAULT 'general',
    qty            INTEGER NOT NULL DEFAULT 1,
    max_cost       NUMERIC,
    priority       INTEGER NOT NULL DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    cooldown_hours INTEGER NOT NULL DEFAULT 24,
    enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    notes          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_thresholds_key ON successbrian_os.signal_thresholds(signal_key);

-- Seed thresholds from the 2026-10-17 infra sweep (verified on k11-alpha).
INSERT INTO successbrian_os.signal_thresholds
    (signal_key, signal_class, condition, threshold_num, need_item, need_specs,
     need_class, qty, max_cost, priority, cooldown_hours, enabled, notes)
VALUES
    ('k11.cpu_temp_c', 'infra', 'gt', 90,
     'inference thermal headroom',
     'CLASS=inference-hardware | EVIDENCE=k11 CPU temp sustained above 90C (AMD max ~95C); thermal boost throttling silently cuts throughput | TREND=sustained',
     'inference-hardware', 1, NULL, 8, 24, TRUE,
     'Seeded 2026-10-17 from live sweep: Tctl steady 93.2C'),
    ('k11.mem_available_gb', 'infra', 'lt', 12,
     'memory headroom for agent workloads',
     'CLASS=inference-hardware | EVIDENCE=k11 mem_available below 12GB; box carries 44GB swap | TREND=worsening',
     'inference-hardware', 1, NULL, 7, 24, TRUE,
     'Seeded 2026-10-17: 90GB box, 74GB used, 3.9GB free'),
    ('k11.swap_used_gb', 'infra', 'gt', 30,
     'memory headroom for agent workloads',
     'CLASS=inference-hardware | EVIDENCE=k11 swap above 30GB; heavy swap thrash slows everything | TREND=sustained',
     'inference-hardware', 1, NULL, 7, 24, TRUE,
     'Seeded 2026-10-17: 44GB swap in use'),
    ('k11.disk_used_pct', 'infra', 'gt', 88,
     'bulk storage headroom',
     'CLASS=storage | EVIDENCE=k11 root disk above 88% | TREND=sustained',
     'storage', 1, NULL, 6, 48, TRUE,
     'Seeded 2026-10-17: disk at 75%, headroom still fine'),
    ('db.longest_query_min', 'infra', 'gt', 25,
     'database runaway-query review',
     'CLASS=ops | EVIDENCE=a single query ran longer than 25min; statement_timeout guard (30min) will kill it — verify no legit workload was cut | TREND=event',
     'ops', 1, NULL, 6, 24, TRUE,
     'Seeded 2026-10-17: 4-day cartesian incident led to the 30min guard')
ON CONFLICT DO NOTHING;
