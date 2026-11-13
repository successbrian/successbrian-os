-- B12: planner rotation coverage ledger (2026-11-13).
-- Design: ~/workspace/builds/atlas-planner-goal-loop/design-2026-11-12.md
-- (Brian, 2026-11-12 20:36 CST: the main planner loops through ALL goals,
-- priority-ordered, least-recently-looked breaking the tail, over several
-- days; each look is unique and filed against the goal.)
--
-- successbrian_os.goal_coverage is the coverage ledger: one row per unique
-- goal look. The look is ALSO mirrored onto the goal node's details
-- (last_looked_at / look_count / blocker / planner_seat, B10 keys) by
-- planner_rotation.py, so atlas.goal_nodes keeps answering "when was this
-- goal last actually looked at" without a join. The ledger is the audit
-- trail; the node is the current state. Neither table is ever deleted
-- from by the rotation (ledger rows append; node details only advance).
--
-- Applied as successbrian (successbrian_os is its writable schema).
-- Idempotent: CREATE TABLE IF NOT EXISTS + IF NOT EXISTS index.

CREATE TABLE IF NOT EXISTS successbrian_os.goal_coverage (
  id SERIAL PRIMARY KEY,
  goal_slug TEXT NOT NULL,
  looked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  planner_seat TEXT NOT NULL DEFAULT 'planner',
  findings TEXT NOT NULL,
  work_spawned TEXT NOT NULL DEFAULT '',
  engine_tier TEXT NOT NULL DEFAULT 'planner'
    CHECK (engine_tier IN ('planner', 'morpheus', 'sonic', 'reap')),
  blocker TEXT,
  created_by TEXT NOT NULL DEFAULT 'spencer-cycle'
);

CREATE INDEX IF NOT EXISTS goal_coverage_slug_idx
  ON successbrian_os.goal_coverage (goal_slug, looked_at DESC);

COMMENT ON TABLE successbrian_os.goal_coverage IS
  'Planner rotation coverage ledger (B12): one row per unique goal look. engine_tier is the tier the look''s spawned work belongs to (planner shaping / morpheus routine synthesis / sonic-reap hard judgment); v1 records the tier decision, actual engine dispatch is the B12b follow-up.';
