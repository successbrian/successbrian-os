-- AnythingLLM workspace registry (Brian's determination layer).
-- Applied by allm_workspaces.py seed(); kept beside the module as
-- the migration record, per house pattern. Idempotent.
CREATE TABLE IF NOT EXISTS atlas.allm_workspace_registry (
    slug        text PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN
                    ('domain','intake','quarantine')),
    owner       text NOT NULL,
    category    text,
    purpose     text NOT NULL,
    ingest_rule text NOT NULL,
    status      text NOT NULL CHECK (status IN ('live','determined')),
    note        text
);
