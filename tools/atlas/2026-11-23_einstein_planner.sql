-- 2026-11-23_einstein_planner.sql
-- Einstein deep-look planner pass (Brian order 2026-11-23: planning
-- gets Einstein looking at the goals and writing plans back,
-- including what needs to be researched).
--
-- einstein_passes is the dispatch/collect ledger for Einstein looks:
-- one row per dispatched feeder packet, its bus event, and the look
-- its plan was written back as. The PLAN itself does not live here -
-- it lives in successbrian_os.goal_coverage (the look) and in the
-- Atlas goal node's readme_md, the stores the planner already owns.
-- einstein_planner.py also runs this DDL idempotently at startup
-- (ensure_schema), so applying this file by hand is optional.

CREATE TABLE IF NOT EXISTS successbrian_os.einstein_passes (
    id            serial PRIMARY KEY,
    goal_slug     text NOT NULL,
    probe_id      text NOT NULL UNIQUE,
    bus_event_id  bigint,
    status        text NOT NULL DEFAULT 'dispatched',
    dispatched_at timestamptz NOT NULL DEFAULT now(),
    collected_at  timestamptz,
    look_id       integer,
    plan_text     text,
    note          text
);

CREATE INDEX IF NOT EXISTS einstein_passes_status_idx
    ON successbrian_os.einstein_passes (status, id);
