-- 2026-10-22 — DealsDesk: target buy prices + kept sources per need.
-- Brian 2026-10-22: "with dealsdesk, we should track a target buy price
-- and start keeping potential sources" / "yes build improve".
-- Additive only. Idempotent (IF NOT EXISTS throughout). No existing
-- column, row, or reader is changed in meaning.
--
-- ecosystem_needs gains:
--   target_buy_price  Brian's per-unit buy trigger for this need
--                     (a source at or under it is actionable).
--   hard_terms        Structured gates a listing/source must satisfy
--                     (e.g. {"board": "MZ32-AR0", "rev": "1.x"}), so
--                     validity terms stop living only in prose.
--   qty_needed        Integer fill target (legacy `magnitude` is text).
--   qty_filled        Units bought against the need (write-back).
--
-- need_sources: sources kept PER NEED — human-supplied (origin=manual)
-- alongside anything a worker files (origin=worker). A source is a
-- lead, not a commitment: it ages (stale after 7 days un-refreshed,
-- mirroring build_price_alerts STALE_DAYS), can be marked dead, and
-- is_anti marks a do-not-buy source (e.g. a marked-up listing).
--
-- need_purchases: the write-back log. Recording a purchase increments
-- qty_filled; when qty_filled >= qty_needed the need is satisfied and
-- stops surfacing.

ALTER TABLE dealsdesk.ecosystem_needs
    ADD COLUMN IF NOT EXISTS target_buy_price numeric;
ALTER TABLE dealsdesk.ecosystem_needs
    ADD COLUMN IF NOT EXISTS hard_terms jsonb;
ALTER TABLE dealsdesk.ecosystem_needs
    ADD COLUMN IF NOT EXISTS qty_needed integer;
ALTER TABLE dealsdesk.ecosystem_needs
    ADD COLUMN IF NOT EXISTS qty_filled integer NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS dealsdesk.need_sources (
    id              serial PRIMARY KEY,
    need_id         integer NOT NULL REFERENCES dealsdesk.ecosystem_needs(id),
    origin          text NOT NULL DEFAULT 'manual'
                    CHECK (origin IN ('manual', 'worker', 'seed')),
    seller          text,
    platform        text,
    url             text,
    price           numeric,
    shipping        numeric,
    terms           jsonb,
    note            text,
    is_anti         boolean NOT NULL DEFAULT false,
    status          text NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'stale', 'dead', 'bought')),
    observed_at     timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_need_sources_need
    ON dealsdesk.need_sources(need_id);

CREATE TABLE IF NOT EXISTS dealsdesk.need_purchases (
    id           serial PRIMARY KEY,
    need_id      integer NOT NULL REFERENCES dealsdesk.ecosystem_needs(id),
    source_id    integer REFERENCES dealsdesk.need_sources(id),
    qty          integer NOT NULL,
    unit_price   numeric,
    purchased_on date NOT NULL DEFAULT CURRENT_DATE,
    note         text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_need_purchases_need
    ON dealsdesk.need_purchases(need_id);
