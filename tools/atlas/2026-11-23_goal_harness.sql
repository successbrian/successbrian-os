-- 2026-11-23_goal_harness.sql
-- The GOAL HARNESS (Brian's order, 2026-11-23: "build the harness
-- so it can process and understand all this"; spec captures #3108
-- tiered cadence + movement + event-triggered replanning, #3109
-- cross-goal task consolidation).
--
-- goal_harness_state: per-goal harness tier (priority -> look
-- window; gated goals slow), the due-early flag event triggers
-- set, and the last movement measurement time.
-- harness_movements: one row per collected harness look - the
-- measured step-ledger movement Einstein was shown, plus his
-- MOVEMENT verdict parsed back out of the plan.
-- harness_meta: harness watermarks (capture event scan).
-- consolidation_sweeps / consolidation_proposals: Einstein
-- clustering passes over the open goal-linked step pool and the
-- shared-task groups they propose. PROPOSALS ONLY - the harness
-- never merges or deletes steps; a proposal's effect is ordering
-- (priority boost + claim order), recorded in harness_claims.
-- harness_claims: the claim loop's ledger - every claim, hold,
-- boost, note, and outcome, so movement has something true to
-- read and no claim exists without an artifact or an outcome.
-- goal_harness.py also runs this DDL idempotently at startup
-- (ensure_schema), so applying this file by hand is optional.

CREATE TABLE IF NOT EXISTS successbrian_os.goal_harness_state (
    goal_slug        text PRIMARY KEY,
    tier             text NOT NULL,
    window_days      int NOT NULL,
    priority_label   text,
    gated            boolean NOT NULL DEFAULT false,
    due_early        boolean NOT NULL DEFAULT false,
    due_early_reason text,
    due_early_at     timestamptz,
    last_movement_at timestamptz,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS successbrian_os.harness_movements (
    id          serial PRIMARY KEY,
    goal_slug   text NOT NULL,
    pass_id     int,
    look_id     int,
    measured_at timestamptz NOT NULL DEFAULT now(),
    since_at    timestamptz,
    completed   int NOT NULL DEFAULT 0,
    failed      int NOT NULL DEFAULT 0,
    running     int NOT NULL DEFAULT 0,
    queued      int NOT NULL DEFAULT 0,
    stuck       int NOT NULL DEFAULT 0,
    verdict     text,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS successbrian_os.harness_meta (
    key        text PRIMARY KEY,
    value      jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS successbrian_os.consolidation_sweeps (
    id            serial PRIMARY KEY,
    probe_id      text NOT NULL UNIQUE,
    bus_event_id  bigint,
    ran_at        timestamptz NOT NULL DEFAULT now(),
    collected_at  timestamptz,
    steps_scanned int NOT NULL DEFAULT 0,
    pool_ids      jsonb NOT NULL DEFAULT '[]'::jsonb,
    status        text NOT NULL DEFAULT 'dispatched',
    note          text
);

CREATE TABLE IF NOT EXISTS successbrian_os.consolidation_proposals (
    id         serial PRIMARY KEY,
    sweep_id   int NOT NULL,
    group_key  text NOT NULL,
    title      text NOT NULL,
    rationale  text,
    step_ids   jsonb NOT NULL DEFAULT '[]'::jsonb,
    step_keys  jsonb NOT NULL DEFAULT '[]'::jsonb,
    goal_slugs jsonb NOT NULL DEFAULT '[]'::jsonb,
    gate_count int NOT NULL DEFAULT 0,
    status     text NOT NULL DEFAULT 'proposed',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sweep_id, group_key)
);

CREATE TABLE IF NOT EXISTS successbrian_os.harness_claims (
    id            serial PRIMARY KEY,
    step_id       bigint NOT NULL,
    step_key      text NOT NULL,
    goal_slug     text,
    route         text NOT NULL,
    action        text NOT NULL,
    bus_event_id  bigint,
    engine_job_id bigint,
    claimed_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    outcome       text,
    detail        jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS harness_claims_step_idx
    ON successbrian_os.harness_claims (step_id, action);
