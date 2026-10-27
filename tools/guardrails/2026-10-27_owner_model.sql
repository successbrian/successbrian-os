-- Owner-model layer — migration 2026-10-27 (Brian's Tier-2 gap build).
-- Evidence-backed conclusions about the owner. Never silently
-- overwritten: a correction is a new row superseding the old.
-- Starts EMPTY by design; conclusions arrive with evidence over time.
-- Mirrors SCHEMA_SQL in tools/guardrails/owner_model.py (idempotent).
CREATE TABLE IF NOT EXISTS successbrian_os.owner_model (
    id            bigserial PRIMARY KEY,
    conclusion    text NOT NULL,
    domain        text NOT NULL,
    confidence    numeric(3,2) NOT NULL
                  CHECK (confidence >= 0 AND confidence <= 1),
    evidence      jsonb NOT NULL DEFAULT '[]'::jsonb,
    status        text NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','corrected','retired')),
    supersedes_id bigint REFERENCES successbrian_os.owner_model(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
