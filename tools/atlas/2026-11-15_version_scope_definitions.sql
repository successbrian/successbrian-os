-- Atlas version-scope: project definition sheet (2026-11-15).
--
-- Brian, 2026-11-15 09:39 CST: "income projects defined. audiences
-- defined. ideas on how we'll market it definied... etc etc ... all
-- the steps needed to vet and sort them".
--
-- Version scope alone does not make a vibe-coded project "defined".
-- Every registered project now carries a standard DEFINITION SHEET —
-- the project-level counterpart of the blog fleet's 12-part planning
-- package (blog_fleet.py STANDARD_ITEMS discipline): a FIXED standard
-- set of 10 items (the set lives as DEFINITION_ITEMS in
-- atlas_version_scope.py), seeded to every registered project, each
-- item UNKNOWN until Brian's record actually settles it. A cell is
-- DEFINED only with a detail + a citable source on the cell itself;
-- the tool refuses an uncited fill. version_scope is derived from
-- the scope tables, never hand-set; sort_verdict is Brian's ruling
-- only and seeds UNKNOWN everywhere.
--
-- Dedicated tables in the atlas schema, same ledger pattern as the
-- scope store: the items table carries state + detail + source, and
-- _definition_moves is the append-only change history (a cell's
-- history is never silently rewritten).
--
-- Additive only. Nothing here alters existing tables or rows.

CREATE TABLE IF NOT EXISTS atlas.version_scope_definition_items (
    project_key TEXT NOT NULL
        REFERENCES atlas.version_scope_projects(project_key)
        ON DELETE CASCADE,
    item_key    TEXT NOT NULL,  -- one of the 10 DEFINITION_ITEMS keys
    state       TEXT NOT NULL DEFAULT 'unknown'
                CHECK (state IN ('defined', 'unknown')),
    detail      TEXT NOT NULL DEFAULT '',  -- what the record settles, one short paragraph
    source      TEXT NOT NULL DEFAULT '',  -- citation: Brian quote / ruling date / record home
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_key, item_key)
);
CREATE INDEX IF NOT EXISTS idx_vs_def_items_project
    ON atlas.version_scope_definition_items(project_key, state);

-- Append-only definition change history: every set (including the
-- derived version_scope refresh) lands here when anything changed.
CREATE TABLE IF NOT EXISTS atlas.version_scope_definition_moves (
    id          SERIAL PRIMARY KEY,
    project_key TEXT NOT NULL,
    item_key    TEXT NOT NULL,
    from_state  TEXT NOT NULL DEFAULT '',
    to_state    TEXT NOT NULL DEFAULT '',
    detail      TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT '',
    moved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vs_def_moves_project
    ON atlas.version_scope_definition_moves(project_key, item_key);
