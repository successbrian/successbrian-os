-- business_core schema: the business brain as data, not just docs.
--
-- Design:
--   * Every table carries tenant_id. The schema + code are shared by all
--     users of successbrian-os; the DATA is unique per tenant.
--   * Brian's tenant id is 'brian'. Other tenants get their own rows.
--   * The markdown BUSINESS_CORE doc is a RENDERED VIEW of this data
--     (see core.py render_markdown) — never a separate source of truth.
--   * Agents orient via: SELECT * FROM business_core.<table>
--     WHERE tenant_id = '<theirs>'  — or core.py's get_brief().

CREATE SCHEMA IF NOT EXISTS business_core;

-- Each user's isolated business identity.
CREATE TABLE IF NOT EXISTS business_core.tenants (
    id            TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    tagline       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Products across the layers: crm-core | skin-core | skin | os | channel
CREATE TABLE IF NOT EXISTS business_core.products (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES business_core.tenants(id),
    name        TEXT NOT NULL,
    layer       TEXT NOT NULL,
    one_liner   TEXT,
    repo        TEXT,
    status      TEXT NOT NULL DEFAULT 'planned',
    pricing     TEXT,
    UNIQUE (tenant_id, name)
);

-- How the products fit together.
CREATE TABLE IF NOT EXISTS business_core.product_links (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES business_core.tenants(id),
    from_product TEXT NOT NULL,
    rel         TEXT NOT NULL,
    to_product  TEXT NOT NULL,
    note        TEXT
);

-- Money sleeves.
CREATE TABLE IF NOT EXISTS business_core.income_streams (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES business_core.tenants(id),
    name        TEXT NOT NULL,
    kind        TEXT,
    status      TEXT,
    note        TEXT,
    UNIQUE (tenant_id, name)
);

-- Directed capital flows between sleeves.
CREATE TABLE IF NOT EXISTS business_core.capital_flows (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES business_core.tenants(id),
    from_stream TEXT NOT NULL,
    to_stream   TEXT NOT NULL,
    rule        TEXT NOT NULL
);

-- Inviolable rules every agent must respect.
CREATE TABLE IF NOT EXISTS business_core.rules (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES business_core.tenants(id),
    category    TEXT NOT NULL,
    rule        TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'hard'
);

-- The tool stack.
CREATE TABLE IF NOT EXISTS business_core.tool_stack (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES business_core.tenants(id),
    tool        TEXT NOT NULL,
    role        TEXT NOT NULL,
    cost_basis  TEXT,
    note        TEXT,
    UNIQUE (tenant_id, tool)
);

-- Key humans and agents.
CREATE TABLE IF NOT EXISTS business_core.people (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES business_core.tenants(id),
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    role        TEXT NOT NULL,
    note        TEXT,
    UNIQUE (tenant_id, name)
);

-- Where the business is going.
CREATE TABLE IF NOT EXISTS business_core.roadmap (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES business_core.tenants(id),
    item        TEXT NOT NULL,
    horizon     TEXT NOT NULL DEFAULT 'future',
    status      TEXT NOT NULL DEFAULT 'open'
);

-- Helpful indexes for the brief query path.
CREATE INDEX IF NOT EXISTS idx_bc_products_tenant
    ON business_core.products (tenant_id);
CREATE INDEX IF NOT EXISTS idx_bc_rules_tenant
    ON business_core.rules (tenant_id);
CREATE INDEX IF NOT EXISTS idx_bc_streams_tenant
    ON business_core.income_streams (tenant_id);
