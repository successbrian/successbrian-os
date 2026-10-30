-- 2026-10-27 collectors migration (Tier 2 collectors build)
-- Dedupe state for bridge_poller.py: every external item filed to the
-- Intel Bridge is recorded here first-seen; an item is never filed twice.
CREATE TABLE IF NOT EXISTS successbrian_os.collector_seen (
    source       text NOT NULL,          -- miniflux | changedetection | changedetection-test
    external_id  text NOT NULL,          -- entry id / watch_uuid:snapshot_ts / hash
    content_hash text,
    capture_id   integer,                -- atlas.scattered_captures id, NULL when baselined silently
    note         text,
    first_seen   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, external_id)
);
COMMENT ON TABLE successbrian_os.collector_seen IS
 'Tier2 collectors dedupe state (2026-10-27). Written by tools/collectors/bridge_poller.py only.';
