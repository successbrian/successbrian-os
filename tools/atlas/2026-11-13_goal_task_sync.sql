-- 2026-11-13_goal_task_sync.sql — BUILD_QUEUE B11 (Phase 3, Atlas goal machinery)
-- Goal→task conversion v1: the sync half of the B10 schema.
--
-- B10 built the goal-node contract and left population to B11
-- ("--list read-back 0 goal nodes (population is B11's sync)").
-- This migration is the task-node contract: the validator + CHECK a
-- node_type='task' row must satisfy when it is a goal's task, plus the
-- read view the planner rotation (B12) queries for a goal's tasks.
--
-- Contract (mirrored in Python by tools/atlas/goal_task_sync.py; the two
-- must agree — goal_task_sync.py --selftest checks them against each
-- other):
--   node_key   'task:<goal_slug>:<task_id>'   (task_id = successbrian_os.tasks.id)
--   node_type  'task'
--   name       tasks.title
--   status     tasks.status mapped: pending/open/active/in_progress -> active,
--              blocked -> blocked, completed/done -> done,
--              cancelled -> cancelled, archived -> archived, else planned
--   ref_kind   'sbos_task', ref_id = tasks.id as text
--   details    jsonb, required keys:
--     task_id              int >= 1
--     goal_slug            text, non-empty
--     priority             text, non-empty (tasks.priority, lowercased)
--     status               text, the mapped node status (single source of
--                          truth — node status column carries the same value)
--   details optional keys (only these; unknown keys are rejected):
--     progress_pct         int 0-100
--     target_date          YYYY-MM-DD, real calendar date
--     assigned_to          text or null
--     stale_flag           text or null
--     completed_at         ISO timestamp or null
--     source_updated_at    ISO timestamp or null
--   Edge: goal:<goal_slug> --contains--> task:<goal_slug>:<task_id>
--
-- CHECK scope — the three pre-existing hand-made task nodes
-- (task:verified-backups, task:reverse-engineering-queue,
-- task:re-llama-server-alpha) carry free-form details with ref_kind
-- NULL and predate any contract. The CHECK therefore binds ONLY rows
-- with ref_kind = 'sbos_task': the sync's rows must conform, the
-- hand-made rows are untouched and their details stay exactly as
-- their authors wrote them. (B10 could bind all goal rows because 0
-- goal rows existed; task rows already exist, so the scope guard is
-- the honest equivalent.)
--
-- Sync scope (decided from live data 2026-11-13, recorded in
-- goal_task_sync.py): goals WITH a goal_slug (57 rows, 56 unique
-- slugs — infra-provisioning-worker-20260913 is duplicated, ids 96
-- cancelled / 167 planning; the sync takes the non-cancelled row).
-- The other 3,030 sbos_goals rows have no slug, so they have no
-- stable node_key; the sync counts them as skipped, never invents a
-- slug. Tasks synced are the OPEN ones under slugged goals (6 on
-- 2026-11-13, all DealsDesk/Mantis work); completed/cancelled tasks
-- stay in successbrian_os.tasks and are never imported as dead
-- history — a task that leaves open status gets its node reconciled
-- to its terminal status instead. 173 open tasks belong to unslugged
-- goals and stay unlinked; the sync reports the count, it does not
-- hide it.
--
-- Safety: additive only. Idempotent: re-running is a no-op
-- (OR REPLACE / IF NOT EXISTS guards). Apply as postgres — the Atlas
-- DDL path is psql -h localhost -U postgres (successbrian has no
-- CREATE on the atlas schema; B10 precedent).

-- Reuse B10's date/timestamp guards (atlas._goal_date_valid,
-- atlas._goal_ts_valid) — do not redefine them here.

-- The contract itself: pure jsonb checks, IMMUTABLE so a CHECK may call it.
-- NULL details is rejected outright (jsonb_typeof(NULL) is NULL, which a
-- CHECK would otherwise treat as a pass).
CREATE OR REPLACE FUNCTION atlas.task_node_details_valid(d jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT d IS NOT NULL
    AND jsonb_typeof(d) = 'object'
    AND d ? 'task_id'
    AND jsonb_typeof(d -> 'task_id') = 'number'
    AND (d ->> 'task_id') ~ '^-?[0-9]+$'
    AND (d ->> 'task_id')::int >= 1
    AND d ? 'goal_slug'
    AND jsonb_typeof(d -> 'goal_slug') = 'string'
    AND length(d ->> 'goal_slug') > 0
    AND d ? 'priority'
    AND jsonb_typeof(d -> 'priority') = 'string'
    AND length(d ->> 'priority') > 0
    AND d ? 'status'
    AND jsonb_typeof(d -> 'status') = 'string'
    AND length(d ->> 'status') > 0
    AND (NOT (d ? 'progress_pct')
         OR (jsonb_typeof(d -> 'progress_pct') = 'number'
             AND (d ->> 'progress_pct') ~ '^-?[0-9]+$'
             AND (d ->> 'progress_pct')::int BETWEEN 0 AND 100))
    AND (NOT (d ? 'target_date')
         OR (jsonb_typeof(d -> 'target_date') = 'string'
             AND atlas._goal_date_valid(d ->> 'target_date')))
    AND (NOT (d ? 'assigned_to')
         OR jsonb_typeof(d -> 'assigned_to') IN ('string', 'null'))
    AND (NOT (d ? 'stale_flag')
         OR jsonb_typeof(d -> 'stale_flag') IN ('string', 'null'))
    AND (NOT (d ? 'completed_at')
         OR (jsonb_typeof(d -> 'completed_at') IN ('string', 'null')
             AND (d ->> 'completed_at' IS NULL
                  OR atlas._goal_ts_valid(d ->> 'completed_at'))))
    AND (NOT (d ? 'source_updated_at')
         OR (jsonb_typeof(d -> 'source_updated_at') IN ('string', 'null')
             AND (d ->> 'source_updated_at' IS NULL
                  OR atlas._goal_ts_valid(d ->> 'source_updated_at'))))
    AND NOT EXISTS (
      SELECT 1 FROM jsonb_object_keys(d) k
      WHERE k NOT IN ('task_id', 'goal_slug', 'priority', 'status',
                      'progress_pct', 'target_date', 'assigned_to',
                      'stale_flag', 'completed_at', 'source_updated_at')
    )
$$;

-- Bind the contract to sync-created task rows only (see scope note above).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'nodes_task_details_ck'
      AND conrelid = 'atlas.nodes'::regclass) THEN
    ALTER TABLE atlas.nodes ADD CONSTRAINT nodes_task_details_ck
      CHECK ((node_type <> 'task')
             OR (ref_kind IS DISTINCT FROM 'sbos_task')
             OR atlas.task_node_details_valid(details));
  END IF;
END $$;

-- Read view: a goal's tasks, for the planner rotation (B12) and --status.
CREATE OR REPLACE VIEW atlas.goal_tasks AS
SELECT n.node_key,
       n.name,
       n.status,
       n.details ->> 'goal_slug' AS goal_slug,
       (n.details ->> 'task_id')::int AS task_id,
       n.details ->> 'priority' AS priority,
       (n.details ->> 'progress_pct')::int AS progress_pct,
       n.details ->> 'target_date' AS target_date,
       n.details ->> 'assigned_to' AS assigned_to,
       n.ref_id AS source_task_id
FROM atlas.nodes n
WHERE n.node_type = 'task' AND n.ref_kind = 'sbos_task';
