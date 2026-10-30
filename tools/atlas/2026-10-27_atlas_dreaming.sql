-- Atlas dreaming / consolidation (Brian 2026-10-27). Idempotent.
-- Applied also by dreaming.py ensure_schema(); kept beside the module
-- as the migration record, per house pattern.
CREATE TABLE IF NOT EXISTS atlas.dream_config (
    id int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    mode text NOT NULL DEFAULT 'dry_run' CHECK (mode IN ('dry_run','live')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    note text
);
INSERT INTO atlas.dream_config (id, mode, note)
VALUES (1, 'dry_run', 'Set 2026-10-27 by Brian order via dreaming build; dry_run is the shipped default')
ON CONFLICT (id) DO NOTHING;
CREATE TABLE IF NOT EXISTS atlas.dream_runs (
    id serial PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    mode text NOT NULL,
    counts jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS atlas.dream_review (
    id serial PRIMARY KEY,
    run_id int REFERENCES atlas.dream_runs(id),
    kind text NOT NULL,
    subject_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','dismissed')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atlas.dream_actions (
    id serial PRIMARY KEY,
    run_id int REFERENCES atlas.dream_runs(id),
    action text NOT NULL,
    subject text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    ts timestamptz NOT NULL DEFAULT now()
);
