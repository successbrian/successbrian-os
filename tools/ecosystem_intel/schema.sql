-- ecosystem_intel: the shared memory that stops agents re-deriving the world.
--
-- Brian's law: no agent should spend precious time figuring out the same
-- thing over and over. Facts, procedures, and traps learned once get
-- recorded here and served cheaply to every agent after.
--
-- Multi-tenant like business_core: same schema + code for all users,
-- data isolated per tenant_id.
--
-- Three kinds of intel:
--   facts   — stable truths (IPs, API shapes, credentials locations)
--   howtos  — procedures that worked (deploy a bridge, push a repo)
--   gotchas — traps with the fix (things that bit someone before)

CREATE SCHEMA IF NOT EXISTS ecosystem_intel;

CREATE TABLE IF NOT EXISTS ecosystem_intel.facts (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    confidence  TEXT NOT NULL DEFAULT 'verified',
    source      TEXT,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, key)
);

CREATE TABLE IF NOT EXISTS ecosystem_intel.howtos (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    topic       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    steps       TEXT NOT NULL,
    related     TEXT,
    UNIQUE (tenant_id, topic)
);

CREATE TABLE IF NOT EXISTS ecosystem_intel.gotchas (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    trap        TEXT NOT NULL,
    why         TEXT NOT NULL,
    fix         TEXT NOT NULL,
    UNIQUE (tenant_id, trap)
);

CREATE INDEX IF NOT EXISTS idx_ei_facts_tenant_cat
    ON ecosystem_intel.facts (tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_ei_howtos_tenant
    ON ecosystem_intel.howtos (tenant_id);
