-- 2026-11-23_dashboard.sql
-- SBOS Dashboard generator (Brian order 2026-11-23): an exception-first
-- status page rendered from the live stores for the review passes and
-- the Wednesday sitting. dashboard.py also runs this DDL idempotently
-- at generate time (ensure_schema), so applying this file by hand is
-- optional.
--
-- dashboard_snapshots keeps the latest render plus history: the JSON
-- the page was built from (so the QA check can recount its headline
-- numbers live) and the rendered HTML itself.

CREATE TABLE IF NOT EXISTS successbrian_os.dashboard_snapshots (
    id serial PRIMARY KEY,
    generated_at timestamptz NOT NULL DEFAULT now(),
    data jsonb NOT NULL,
    html text NOT NULL
);

CREATE INDEX IF NOT EXISTS dashboard_snapshots_generated_idx
    ON successbrian_os.dashboard_snapshots (generated_at DESC);
