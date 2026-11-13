-- 2026-11-13_goal_nodes.sql — BUILD_QUEUE B10 (Phase 3, Atlas goal machinery)
-- Goal-node schema for atlas.nodes, per
--   ~/workspace/builds/atlas-planner-goal-loop/design-2026-11-12.md
--
-- The confirmed gap (2026-11-12): atlas.nodes holds no goal-type nodes
-- and no goal->task conversion code exists. This migration is the schema
-- half: the contract a node_type='goal' row must satisfy, enforced in
-- the database, plus the read view the planner rotation (B12) queries.
--
-- Contract (mirrored in Python by tools/atlas/goal_nodes.py; the two
-- must agree — goal_nodes.py --selftest checks them against each other):
--   node_key   'goal:<goal_slug>'            (goal_slug = sbos_goals.goal_slug)
--   node_type  'goal'
--   name       sbos_goals.goal_name
--   status     sbos_goals.status mapped: active/in_progress -> active,
--              planning -> planned, blocked -> blocked,
--              cancelled -> cancelled, completed -> done, else planned
--   ref_kind   'sbos_goal', ref_id = sbos_goals.id as text
--   details    jsonb, required keys:
--     goal_slug            text, non-empty
--     priority             int 0-100 (sbos_goals.priority mapped:
--                         critical 90, high 75, medium 50, low 25,
--                         anything else 50 — B10 default, Brian-correctable)
--     coverage_window_days int 1-30, default 4 (design's 3-5 day working
--                         assumption: every goal looked at over ~4 days)
--   details optional keys (only these; unknown keys are rejected):
--     category, target_date (YYYY-MM-DD, real calendar date),
--     last_looked_at (ISO timestamptz), look_count (int >= 0),
--     planner_seat (text), blocker (text or null),
--     parent_goal_slug (text or null)
--   Edge types reserved for B11/B12 (not created here):
--     goal --spawns--> atlas_task, atlas_task --serves--> goal,
--     goal --parent_of--> goal (sbos_goals.parent_goal_id)
--
-- Safety: additive only. No existing row is node_type='goal' (0 rows on
-- 2026-11-13), so the CHECK cannot fail on live data. Idempotent:
-- re-running is a no-op (OR REPLACE / IF NOT EXISTS guards).

-- Calendar-date guard: YYYY-MM-DD that exists (leap-year aware).
CREATE OR REPLACE FUNCTION atlas._goal_date_valid(s text)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT s ~ '^\d{4}-\d{2}-\d{2}$'
    AND (substring(s, 6, 2))::int BETWEEN 1 AND 12
    AND (substring(s, 9, 2))::int BETWEEN 1 AND
      CASE (substring(s, 6, 2))::int
        WHEN 2 THEN CASE
          WHEN (substring(s, 1, 4))::int % 4 = 0
           AND ((substring(s, 1, 4))::int % 100 <> 0
             OR (substring(s, 1, 4))::int % 400 = 0)
          THEN 29 ELSE 28 END
        WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30
        ELSE 31 END
$$;

-- Timestamp guard: a real calendar date + optional HH:MM[:SS[.frac]][Z|±HH:?MM].
CREATE OR REPLACE FUNCTION atlas._goal_ts_valid(s text)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT s ~ '^\d{4}-\d{2}-\d{2}([T ]([01]\d|2[0-3]):[0-5]\d(:[0-5]\d(\.\d+)?)?(Z|[+-]([01]\d|2[0-3]):?[0-5]\d)?)?$'
    AND atlas._goal_date_valid(substring(s, 1, 10))
$$;

-- The contract itself: pure jsonb checks, IMMUTABLE so a CHECK may call it.
CREATE OR REPLACE FUNCTION atlas.goal_node_details_valid(d jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_typeof(d) = 'object'
    AND d ? 'goal_slug'
    AND jsonb_typeof(d -> 'goal_slug') = 'string'
    AND length(d ->> 'goal_slug') > 0
    AND d ? 'priority'
    AND jsonb_typeof(d -> 'priority') = 'number'
    AND (d ->> 'priority') ~ '^-?[0-9]+$'
    AND (d ->> 'priority')::int BETWEEN 0 AND 100
    AND d ? 'coverage_window_days'
    AND jsonb_typeof(d -> 'coverage_window_days') = 'number'
    AND (d ->> 'coverage_window_days') ~ '^-?[0-9]+$'
    AND (d ->> 'coverage_window_days')::int BETWEEN 1 AND 30
    AND (NOT (d ? 'category') OR jsonb_typeof(d -> 'category') = 'string')
    AND (NOT (d ? 'target_date')
         OR (jsonb_typeof(d -> 'target_date') = 'string'
             AND atlas._goal_date_valid(d ->> 'target_date')))
    AND (NOT (d ? 'last_looked_at')
         OR (jsonb_typeof(d -> 'last_looked_at') = 'string'
             AND atlas._goal_ts_valid(d ->> 'last_looked_at')))
    AND (NOT (d ? 'look_count')
         OR (jsonb_typeof(d -> 'look_count') = 'number'
             AND (d ->> 'look_count') ~ '^-?[0-9]+$'
             AND (d ->> 'look_count')::int >= 0))
    AND (NOT (d ? 'planner_seat')
         OR jsonb_typeof(d -> 'planner_seat') = 'string')
    AND (NOT (d ? 'blocker')
         OR jsonb_typeof(d -> 'blocker') IN ('string', 'null'))
    AND (NOT (d ? 'parent_goal_slug')
         OR jsonb_typeof(d -> 'parent_goal_slug') IN ('string', 'null'))
    AND NOT EXISTS (
      SELECT 1 FROM jsonb_object_keys(d) k
      WHERE k NOT IN ('goal_slug', 'priority', 'coverage_window_days',
                      'category', 'target_date', 'last_looked_at',
                      'look_count', 'planner_seat', 'blocker',
                      'parent_goal_slug'))
$$;

COMMENT ON FUNCTION atlas.goal_node_details_valid(jsonb) IS
  'B10: details contract for atlas.nodes node_type=''goal''. '
  'Required: goal_slug, priority 0-100, coverage_window_days 1-30. '
  'Optional keys only as listed in 2026-11-13_goal_nodes.sql; '
  'adding a key means extending this function (and goal_nodes.py).';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'nodes_goal_details_ck'
      AND conrelid = 'atlas.nodes'::regclass) THEN
    ALTER TABLE atlas.nodes ADD CONSTRAINT nodes_goal_details_ck
      CHECK (node_type <> 'goal'
             OR atlas.goal_node_details_valid(details));
  END IF;
END $$;

-- Read view for the planner rotation (B12): one row per goal node with
-- the coverage math already done. look_overdue is true for a goal never
-- looked at, or looked at longer ago than its coverage window.
CREATE OR REPLACE VIEW atlas.goal_nodes AS
SELECT n.id,
       n.node_key,
       n.name,
       n.status,
       n.details ->> 'goal_slug' AS goal_slug,
       (n.details ->> 'priority')::int AS priority,
       n.details ->> 'category' AS category,
       (n.details ->> 'target_date')::date AS target_date,
       (n.details ->> 'last_looked_at')::timestamptz AS last_looked_at,
       coalesce((n.details ->> 'look_count')::int, 0) AS look_count,
       (n.details ->> 'coverage_window_days')::int AS coverage_window_days,
       n.details ->> 'planner_seat' AS planner_seat,
       n.details ->> 'blocker' AS blocker,
       n.details ->> 'parent_goal_slug' AS parent_goal_slug,
       n.ref_id AS sbos_goal_id,
       n.created_at AS node_created_at,
       n.updated_at AS node_updated_at,
       CASE WHEN n.details ->> 'last_looked_at' IS NULL THEN NULL
            ELSE extract(epoch FROM
              (now() - (n.details ->> 'last_looked_at')::timestamptz)) / 86400
       END AS days_since_look,
       CASE WHEN n.details ->> 'last_looked_at' IS NULL THEN true
            ELSE (now() - (n.details ->> 'last_looked_at')::timestamptz)
                 > make_interval(days =>
                     (n.details ->> 'coverage_window_days')::int)
       END AS look_overdue
FROM atlas.nodes n
WHERE n.node_type = 'goal';

COMMENT ON VIEW atlas.goal_nodes IS
  'B10: goal-type Atlas nodes with coverage math (days_since_look, '
  'look_overdue). Source of truth for the planner rotation (B12); '
  'populated by the B11 goal->task sync from successbrian_os.sbos_goals.';
