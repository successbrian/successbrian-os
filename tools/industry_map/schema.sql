-- Industry-map module schema (successbrian-os).
--
-- One "industry map" per income stream (or income-stream family): the layout
-- an entrepreneur develops to understand an industry the way Brian mapped the
-- MLM industry in Oct 2026 -- companies, how they relate, intel over time,
-- and the sources worth watching.
--
-- Generic schema: no entrepreneur-specific data lives here. Brian's own
-- MLM map is seeded as the first row set, not as schema.

CREATE TABLE IF NOT EXISTS successbrian_os.industry_maps (
    id           SERIAL PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    income_stream TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- COMPANIES ARE NOT CREATED HERE. Since Brian's one-companies-table
-- ruling (2026-10-27), companies live in people_unified.people.companies
-- (kind = business kind; a map is a collection on the company row).
-- industry_map.py add-company writes there. The old
-- successbrian_os.industry_companies table was merged and DROPPED
-- 2026-10-27; do not recreate it.

CREATE TABLE IF NOT EXISTS successbrian_os.industry_company_links (
    id           SERIAL PRIMARY KEY,
    map_id       INTEGER NOT NULL REFERENCES successbrian_os.industry_maps(id)
                     ON DELETE CASCADE,
    from_node    TEXT NOT NULL,
    to_company   TEXT NOT NULL,
    relationship TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS industry_company_links_map_idx
    ON successbrian_os.industry_company_links (map_id);

CREATE TABLE IF NOT EXISTS successbrian_os.industry_intel (
    id           SERIAL PRIMARY KEY,
    map_id       INTEGER NOT NULL REFERENCES successbrian_os.industry_maps(id)
                     ON DELETE CASCADE,
    company_name TEXT,
    intel_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    category     TEXT NOT NULL DEFAULT 'company_update',
    finding      TEXT NOT NULL,
    source_url   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS industry_intel_map_idx
    ON successbrian_os.industry_intel (map_id, intel_date DESC);

-- map_id NULL = source is useful across industries (e.g. a regulator).
CREATE TABLE IF NOT EXISTS successbrian_os.industry_intel_sources (
    id           SERIAL PRIMARY KEY,
    map_id       INTEGER REFERENCES successbrian_os.industry_maps(id)
                     ON DELETE CASCADE,
    name         TEXT NOT NULL,
    url          TEXT,
    source_type  TEXT NOT NULL,
    focus        TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
