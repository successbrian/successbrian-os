-- 2026-10-25_ram_deals.sql — DealsDesk RAM $/GB market-flowing deal caps.
-- Brian's rule (2026-10-25): RAM buys need $/GB maximums that FLOW WITH THE
-- MARKET; the point is deal-hunting, not market-price buying. Factors chosen
-- by Muse at Brian's delegation ("you tell me what is best"): DDR5 0.70,
-- DDR4 0.75 of the market reference $/GB.

CREATE TABLE IF NOT EXISTS dealsdesk.ram_market_reference (
    ram_class        TEXT PRIMARY KEY,
    factor           NUMERIC(4,3) NOT NULL,
    ref_usd_per_gb   NUMERIC(10,3) NOT NULL,
    cap_usd_per_gb   NUMERIC(10,3) NOT NULL,
    obs_count        INTEGER NOT NULL DEFAULT 0,
    basis            TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dealsdesk.ram_sightings (
    id           BIGSERIAL PRIMARY KEY,
    ram_class    TEXT NOT NULL,
    title        TEXT NOT NULL,
    total_gb     INTEGER NOT NULL,
    price        NUMERIC(10,2) NOT NULL,
    usd_per_gb   NUMERIC(10,3) NOT NULL,
    source       TEXT NOT NULL,
    url          TEXT,
    seller       TEXT,
    seen_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ram_sightings_class_seen
    ON dealsdesk.ram_sightings (ram_class, seen_at DESC);

CREATE TABLE IF NOT EXISTS dealsdesk.ram_deal_alerts (
    id             BIGSERIAL PRIMARY KEY,
    ram_class      TEXT NOT NULL,
    title          TEXT NOT NULL,
    total_gb       INTEGER NOT NULL,
    price          NUMERIC(10,2) NOT NULL,
    usd_per_gb     NUMERIC(10,3) NOT NULL,
    market_ref     NUMERIC(10,3) NOT NULL,
    cap_usd_per_gb NUMERIC(10,3) NOT NULL,
    pct_of_market  NUMERIC(5,1) NOT NULL,
    source         TEXT NOT NULL,
    url            TEXT,
    seller         TEXT,
    stock_note     TEXT,
    alerted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    chat_reported_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ram_deal_alerts_open
    ON dealsdesk.ram_deal_alerts (chat_reported_at, alerted_at);
