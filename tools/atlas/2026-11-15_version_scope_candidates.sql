-- Project vetting engine (Phase B) — Brian, 2026-11-15 09:50 CST,
-- verbatim: "just like we have a blog vetting system, we need a vibe
-- code project vetting system". The Phase A definition sheet is the
-- MARK; this is the ENGINE that crunches candidates against it — a
-- deliberate mirror of the blog candidate engine
-- (campaignsdesk.blog_candidates / blog_candidate_crunches):
-- candidates enter here, NEVER straight into the roster; crunches
-- append, never duplicate; a GRADE reads the mark live from
-- atlas.version_scope_definition_items; the engine NEVER registers a
-- candidate and NEVER sets a disposition — disposition is recorded
-- only from a Brian ruling, with his words as the source.
-- Additive only.

CREATE TABLE IF NOT EXISTS atlas.version_scope_project_candidates (
    candidate_key      TEXT PRIMARY KEY,
    display_name       TEXT NOT NULL,
    state              TEXT NOT NULL DEFAULT 'candidate'
        CHECK (state IN ('candidate', 'crunched', 'graded')),
    priority           TEXT NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('normal', 'high', 'super_high')),
    goal_ref           TEXT NOT NULL DEFAULT '',
    seed_evidence      JSONB NOT NULL DEFAULT '{}'::jsonb,
    disposition        TEXT
        CHECK (disposition IN ('registered', 'parked', 'merged',
                               'dropped')),
    disposition_source TEXT NOT NULL DEFAULT '',
    last_grade         JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_worked_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS
    atlas.version_scope_project_candidate_crunches (
    id            SERIAL PRIMARY KEY,
    candidate_key TEXT NOT NULL
        REFERENCES atlas.version_scope_project_candidates(
            candidate_key) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stages        JSONB NOT NULL DEFAULT '{}'::jsonb,
    items         JSONB NOT NULL DEFAULT '{}'::jsonb,
    unsupported_mentions JSONB NOT NULL DEFAULT '[]'::jsonb,
    balance       JSONB NOT NULL DEFAULT '{}'::jsonb
);
