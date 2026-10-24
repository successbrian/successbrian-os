-- SBOS main PM core — migration 2026-10-24 (slice 1 of the coded-loop upgrade).
-- State home for the control plane: step rows + dependency edges + the ONE
-- decision stream. Mirrors SCHEMA_SQL in tools/pm/pm_core.py (idempotent).
CREATE TABLE IF NOT EXISTS successbrian_os.pm_steps (
    id          bigserial PRIMARY KEY,
    step_key    text UNIQUE NOT NULL,
    title       text NOT NULL,
    kind        text NOT NULL DEFAULT 'task',
    source      text,
    origin      text NOT NULL DEFAULT 'ecosystem'
                CHECK (origin IN ('ecosystem','brian','system')),
    status      text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','blocked','held_brian',
                                  'done','failed','cancelled')),
    priority    integer NOT NULL DEFAULT 50,
    certainty   numeric(4,3),
    actor       text,
    location    text,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    result      jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz,
    heartbeat_at timestamptz
);
CREATE TABLE IF NOT EXISTS successbrian_os.pm_step_deps (
    step_id       bigint NOT NULL REFERENCES successbrian_os.pm_steps(id) ON DELETE CASCADE,
    depends_on_id bigint NOT NULL REFERENCES successbrian_os.pm_steps(id) ON DELETE CASCADE,
    PRIMARY KEY (step_id, depends_on_id)
);
CREATE TABLE IF NOT EXISTS successbrian_os.pm_decisions (
    id         bigserial PRIMARY KEY,
    step_id    bigint REFERENCES successbrian_os.pm_steps(id) ON DELETE SET NULL,
    decided_by text NOT NULL,
    decision   text NOT NULL,
    rationale  text,
    certainty  numeric(4,3),
    origin     text NOT NULL DEFAULT 'ecosystem'
               CHECK (origin IN ('ecosystem','brian','system')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pm_decisions_created_idx
    ON successbrian_os.pm_decisions (created_at DESC);
CREATE INDEX IF NOT EXISTS pm_steps_ready_idx
    ON successbrian_os.pm_steps (status, priority DESC, created_at);
