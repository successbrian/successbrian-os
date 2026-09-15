-- second_brain: a knowledge store that doesn't rot.
-- Every fact carries confidence, expiry, and verification so stale or
-- unverified knowledge can't silently poison the system.

CREATE TABLE IF NOT EXISTS second_brain (
    id            BIGSERIAL PRIMARY KEY,
    topic         TEXT NOT NULL,                  -- what this fact is about (dups allowed; hygiene tool reconciles)
    category      TEXT NOT NULL,                  -- fact | rule | research | ...
    content       TEXT NOT NULL,                  -- the fact itself
    confidence    TEXT NOT NULL DEFAULT 'medium', -- low | medium | high | expired
    source        TEXT,                           -- where it came from
    verification  TEXT,                           -- how it was verified
    expires_at    TIMESTAMPTZ,                    -- NULL = never; >90d = ask first
    tags          TEXT[],                         -- for indexing
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Operational noise (system_state, quick-scan, pipeline_state) does NOT go here.
-- Give it a separate state log, and keep the brain for durable facts.

CREATE INDEX IF NOT EXISTS idx_second_brain_topic  ON second_brain (topic);
CREATE INDEX IF NOT EXISTS idx_second_brain_tags   ON second_brain USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_second_brain_expiry ON second_brain (expires_at);
CREATE INDEX IF NOT EXISTS idx_second_brain_cat    ON second_brain (category, confidence);
