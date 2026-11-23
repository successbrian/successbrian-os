-- 2026-11-23_goal_briefs.sql
-- Goal briefs for the Einstein planner pass (Brian's diagnosis
-- 2026-11-23: "we just need to give Einstein more context. I
-- believe we gave him a very vague paragraph and expected magic").
--
-- goal_briefs is the system of record for the standing brief the
-- einstein_planner brief compiler assembles per goal from the
-- whole ecosystem record: Brian's own words (verbatim, attributed,
-- dated) where they exist, the goal's origin and provenance class
-- (BRIAN-DIRECTED / AGENT-ASSEMBLED / UNKNOWN), connected work,
-- standing constraints and rulings, and the current measured
-- state. The brief is mirrored into the Atlas goal node's
-- readme_md inside GOAL-BRIEF markers, beside the EINSTEIN-PLAN
-- section. newest_source_at is the freshness watermark: a brief
-- older than its goal's coverage window, or with newer source
-- items landed since compilation, is recompiled before the goal's
-- next Einstein look dispatches.
-- einstein_planner.py also runs this DDL idempotently at startup
-- (ensure_schema), so applying this file by hand is optional.

CREATE TABLE IF NOT EXISTS successbrian_os.goal_briefs (
    goal_slug        text PRIMARY KEY,
    brief_md         text NOT NULL,
    compiled_at      timestamptz NOT NULL DEFAULT now(),
    has_brian_words  boolean NOT NULL DEFAULT false,
    origin_class     text NOT NULL DEFAULT 'UNKNOWN',
    newest_source_at timestamptz,
    sources          jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS goal_briefs_compiled_idx
    ON successbrian_os.goal_briefs (compiled_at);
