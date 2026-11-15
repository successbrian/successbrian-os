-- Atlas version-scope store (Phase 1, 2026-11-15).
-- Brian's ruling, 2026-11-15 08:43 CST: "as we define what V1 of
-- succesbrian os is, we need to start scoping things into V2 and V3 ...
-- and this needs to happen for all my vibe coded projects -- build tools
-- into atlas to help us manage this for vibe coding (including
-- successbrian os itself)".
--
-- Design: DEDICATED tables in the atlas schema, linked to the project's
-- Atlas node (atlas.nodes node_key), rather than scope items as Atlas
-- nodes/edges. Why: version scope is a versioned ledger -- items carry
-- status + ruling source, and MOVES between versions must keep an
-- append-only history. Nodes/edges carry neither a per-item status
-- ledger nor move history without contorting the graph; the graph keeps
-- what it is good at (the project node + structure + pointers), the
-- ledger lives here. Atlas holds structure + pointers, not long-form
-- records: summaries stay one line, sources are pointers/quotes.
--
-- Additive only. Nothing here alters atlas.nodes / atlas.edges behavior.

CREATE TABLE IF NOT EXISTS atlas.version_scope_projects (
    project_key       TEXT PRIMARY KEY,
    display_name      TEXT NOT NULL,
    atlas_node_key    TEXT REFERENCES atlas.nodes(node_key),
    scope_note        TEXT NOT NULL DEFAULT '',
    registered_source TEXT NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS atlas.version_scope_items (
    id            SERIAL PRIMARY KEY,
    project_key   TEXT NOT NULL REFERENCES atlas.version_scope_projects(project_key) ON DELETE CASCADE,
    version_label TEXT NOT NULL,  -- 'v1' | 'v2' | 'v3' | later | 'none' (ruled out, no version home)
    item_key      TEXT NOT NULL,
    name          TEXT NOT NULL,
    summary       TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'in_scope'
                  CHECK (status IN ('in_scope','parked','moved','done','ruled_out')),
    source        TEXT NOT NULL DEFAULT '',  -- who/when ruled it: Brian quote or record reference
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_key, item_key)
);
CREATE INDEX IF NOT EXISTS idx_vs_items_project ON atlas.version_scope_items(project_key, version_label);

-- Append-only move history: an item moved v2->v1 shows the move here;
-- the item row's version_label changes, history is never rewritten.
CREATE TABLE IF NOT EXISTS atlas.version_scope_moves (
    id           SERIAL PRIMARY KEY,
    item_id      INTEGER NOT NULL REFERENCES atlas.version_scope_items(id) ON DELETE CASCADE,
    project_key  TEXT NOT NULL,
    item_key     TEXT NOT NULL,
    from_version TEXT NOT NULL,
    to_version   TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT '',
    moved_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vs_moves_item ON atlas.version_scope_moves(item_id);
