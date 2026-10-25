-- Anchor columns for market-flowing references (see ram_deals.py docstring).
ALTER TABLE dealsdesk.ram_market_reference
    ADD COLUMN IF NOT EXISTS seed_ref_usd_per_gb NUMERIC(10,3);
ALTER TABLE dealsdesk.ram_market_reference
    ADD COLUMN IF NOT EXISTS baseline_median NUMERIC(10,3);
UPDATE dealsdesk.ram_market_reference
    SET seed_ref_usd_per_gb = ref_usd_per_gb
    WHERE seed_ref_usd_per_gb IS NULL;
-- Note: the 2026-10-25 first scans overwrote ref with raw ask medians before
-- anchoring existed; restore Brian's verified seed refs explicitly.
UPDATE dealsdesk.ram_market_reference SET seed_ref_usd_per_gb = 17.00, ref_usd_per_gb = 17.00, cap_usd_per_gb = 11.900 WHERE ram_class = 'ddr5_udimm';
UPDATE dealsdesk.ram_market_reference SET seed_ref_usd_per_gb = 15.50, ref_usd_per_gb = 15.50, cap_usd_per_gb = 10.850 WHERE ram_class = 'ddr5_sodimm';
UPDATE dealsdesk.ram_market_reference SET seed_ref_usd_per_gb = 1.90,  ref_usd_per_gb = 1.90,  cap_usd_per_gb = 1.425  WHERE ram_class = 'ddr4_rdimm';
UPDATE dealsdesk.ram_market_reference SET seed_ref_usd_per_gb = 5.70,  ref_usd_per_gb = 5.70,  cap_usd_per_gb = 4.275  WHERE ram_class = 'ddr4_consumer';
