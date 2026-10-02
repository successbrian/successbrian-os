-- Jive schema. Idempotent: safe to re-run.
-- Tables jive reads: successbrian_os.conversation_captures (written by
-- tools/jive/capture.py), successbrian_os.tasks (completed work).

CREATE TABLE IF NOT EXISTS successbrian_os.conversation_captures (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id         text,
    platform           text NOT NULL DEFAULT 'cli',
    source_agent       text NOT NULL DEFAULT 'unknown',
    user_message       text,
    assistant_response text,
    model              text,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conv_agent   ON successbrian_os.conversation_captures (source_agent);
CREATE INDEX IF NOT EXISTS idx_conv_created ON successbrian_os.conversation_captures (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_session ON successbrian_os.conversation_captures (session_id);

CREATE TABLE IF NOT EXISTS successbrian_os.jive_flags (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    flag_type  text NOT NULL,
    severity   text NOT NULL DEFAULT 'info',
    message    text NOT NULL,
    source_ref text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS successbrian_os.jive_links (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type text NOT NULL,
    source_id   bigint NOT NULL,
    target_type text NOT NULL,
    target_id   bigint NOT NULL,
    relation    text NOT NULL,
    score       real,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS successbrian_os.jive_summary (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    window_start timestamptz NOT NULL,
    window_end   timestamptz NOT NULL,
    summary_text text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Watermark: jive processes each capture exactly once and runs only
-- when there is new input.
CREATE TABLE IF NOT EXISTS successbrian_os.jive_state (
    key        text PRIMARY KEY,
    value      text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO successbrian_os.jive_state (key, value) VALUES
    ('last_capture_id', '0'),
    ('last_run_at', '2000-01-01 00:00:00+00')
ON CONFLICT (key) DO NOTHING;
