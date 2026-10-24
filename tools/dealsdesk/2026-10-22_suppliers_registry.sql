-- 2026-10-22 — DealsDesk: suppliers registry + their full offerings.
-- Brian 2026-10-22: "when we find a good Chinese supplier, we want
-- to know everything they offer" (on top of: anything bought from
-- China must be reliable — long-term, honest, will not ditch; the
-- aim is to BUILD those relationships).
--
-- Until now a supplier existed only as a name re-typed on each
-- quote, with reliability re-tagged per row. Relationships belong
-- to SUPPLIERS, not quotes — so they get their own registry:
--   suppliers           one row per supplier: region, reliability
--                       (unrated / repeat-contact / established),
--                       relationship notes, catalog capture state.
--   supplier_offerings  everything we know they offer. When a
--                       supplier proves good, we capture their FULL
--                       catalog here — not just the item we quoted.
-- need_sources gains supplier_id; the verdict gate reads the
-- supplier's record when one is linked (registry wins over the
-- per-quote tags). Additive only; idempotent.

CREATE TABLE IF NOT EXISTS dealsdesk.suppliers (
    id                serial PRIMARY KEY,
    name              text NOT NULL UNIQUE,
    region            text,
    reliability       text NOT NULL DEFAULT 'unrated',
    relationship      text,
    catalog_status    text NOT NULL DEFAULT 'unknown',
    catalog_checked_at timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dealsdesk.supplier_offerings (
    id          serial PRIMARY KEY,
    supplier_id integer NOT NULL
        REFERENCES dealsdesk.suppliers(id) ON DELETE CASCADE,
    category    text,
    item        text NOT NULL,
    detail      text,
    price       numeric,
    observed_at timestamptz NOT NULL DEFAULT now(),
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_offerings_supplier
    ON dealsdesk.supplier_offerings(supplier_id);

ALTER TABLE dealsdesk.need_sources
    ADD COLUMN IF NOT EXISTS supplier_id integer
        REFERENCES dealsdesk.suppliers(id);
