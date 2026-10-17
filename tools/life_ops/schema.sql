-- life_ops: backward planning for hard-date events.
CREATE SCHEMA IF NOT EXISTS life_ops;

ALTER TABLE successbrian_os.life_calendar
    ADD COLUMN IF NOT EXISTS is_hard_date BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS life_ops.event_tasks (
    id SERIAL PRIMARY KEY,
    event_id INT NOT NULL REFERENCES successbrian_os.life_calendar(id)
        ON DELETE CASCADE,
    task TEXT NOT NULL,
    due_date DATE NOT NULL,
    lead_days INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | skipped
    source TEXT NOT NULL DEFAULT 'auto',       -- auto | manual
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_id, task)
);
CREATE INDEX IF NOT EXISTS idx_event_tasks_due
    ON life_ops.event_tasks (due_date) WHERE status = 'pending';
