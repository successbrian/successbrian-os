-- cron_registry: every scheduled job, what it does, what it feeds.
CREATE SCHEMA IF NOT EXISTS successbrian_os;
CREATE TABLE IF NOT EXISTS successbrian_os.cron_registry (
    id SERIAL PRIMARY KEY,
    job_name TEXT NOT NULL UNIQUE,          -- script or label, e.g. derive_needs.py
    schedule TEXT NOT NULL,                 -- cron expression (min hr dom mon dow)
    command TEXT,                           -- full cron command (for matching)
    purpose TEXT,                           -- one line: what it does
    weight TEXT NOT NULL DEFAULT 'unknown', -- light | heavy | unknown
    upstream TEXT[] DEFAULT '{}',           -- job_names that must run first
    downstream TEXT[] DEFAULT '{}',          -- job_names that consume output
    min_gap_minutes INT DEFAULT 10,         -- min stagger after upstream
    area TEXT,                              -- signals | deals | pm | intel | ...
    enriched BOOLEAN NOT NULL DEFAULT FALSE,-- hand-verified deps/weight
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
