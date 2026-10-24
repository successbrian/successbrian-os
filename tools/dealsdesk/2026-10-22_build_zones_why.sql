-- 2026-10-22 — DealsDesk: the build, the build zones, and the why.
-- Brian 2026-10-22: "add to dealsdesk (or improve current system)
-- the build and the build zones ... and the why".
--
-- The ZONES are the price->power cluster zones Z1-Z6 defined in
-- docs/architecture/price-power-zones-2026-10-20.md. Until now they
-- existed only as prose in that doc; DealsDesk's scorers and build
-- tracker could not see them. This migration makes them data.
--
-- builds gains:
--   zone_code  which price-power zone the build lives in (FK to the
--              new registry below). Zones overlap on price because
--              they are physics classes, not partitions.
--   why        the build's reason, in Brian's terms. A build without
--              a why is a shopping list; with one, it is a decision.
--   need_id    the ecosystem need this build satisfies (link to the
--              needs system: need -> build -> items).
--
-- build_zones.doctrine carries each zone's sourcing rule from the
-- source doc — the zone's why. Additive only; idempotent.

CREATE TABLE IF NOT EXISTS dealsdesk.build_zones (
    zone_code  text PRIMARY KEY,
    name       text NOT NULL,
    price_min  numeric,
    price_max  numeric,
    doctrine   text,
    source_doc text,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE dealsdesk.builds
    ADD COLUMN IF NOT EXISTS zone_code text
        REFERENCES dealsdesk.build_zones(zone_code);
ALTER TABLE dealsdesk.builds
    ADD COLUMN IF NOT EXISTS why text;
ALTER TABLE dealsdesk.builds
    ADD COLUMN IF NOT EXISTS need_id integer
        REFERENCES dealsdesk.ecosystem_needs(id);

INSERT INTO dealsdesk.build_zones
    (zone_code, name, price_min, price_max, doctrine, source_doc)
VALUES
('Z1', 'The Stream Floor', 100, 450,
 'Sub-3 tok/s per node on big models; clustering/streaming is the '
 'only way in. Buy by the node, win by the count. (The DDR4 fleet '
 '+ REAP program.)',
 'docs/architecture/price-power-zones-2026-10-20.md'),
('Z2', 'The Interactive Shelf', 900, 2200,
 '10-65 tok/s on MoE daily models; 70B mostly need not apply. '
 'Daily drivers.',
 'docs/architecture/price-power-zones-2026-10-20.md'),
('Z3', 'The GPU Tower Belt', 450, 3200,
 'Fastest $/tok/s INSIDE the VRAM wall (24-48GB); the wall is the '
 'law. (Tower doctrine: V100/P40/3090-class, ~150W caps.)',
 'docs/architecture/price-power-zones-2026-10-20.md'),
('Z4', 'The Unified Heavy Zone', 3400, 7100,
 'Everything fits (128-192GB); MoE flies, dense 70B crawls (~5). '
 'A capacity play, not a speed play.',
 'docs/architecture/price-power-zones-2026-10-20.md'),
('Z5', 'The Cluster Shelf', 6600, 14000,
 'Pairs pool 256-384GB; 235B+ resident; RPC pays a latency tax; '
 'a 10GbE fabric leg suits expert-streaming (Colibri-style).',
 'docs/architecture/price-power-zones-2026-10-20.md'),
('Z6', 'The Rental Sky', NULL, NULL,
 'No capex — rented API frontier (DeepSeek V4 Pro class): $/token, '
 'someone else''s hardware. The rental balance ran dry 2026-09-27; '
 'the fleet exists because of it.',
 'docs/architecture/price-power-zones-2026-10-20.md')
ON CONFLICT (zone_code) DO NOTHING;
