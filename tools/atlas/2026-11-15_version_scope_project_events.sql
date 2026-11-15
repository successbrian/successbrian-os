-- Atlas version-scope: project-level event audit (2026-11-15).
--
-- Brian, 2026-11-15 09:33 CST: "hashrate harbor is a blog" —
-- Hashrate Harbor was registered as a vibe-coded project during the
-- roster pass; it is a blog (a marketing asset, on the blog roster
-- since 2026-10-28), not a project, and Brian ruled it out of the
-- project registry.
--
-- A removal must never be silent. atlas.version_scope_moves is
-- item-level (item_id is a NOT NULL FK into version_scope_items),
-- so project-level events get their own append-only table:
-- atlas_version_scope.py's remove-project writes a
-- 'project_removed' row here — with the ruling source + reason —
-- BEFORE deleting the project row, and refuses any project that
-- still carries scope items or still has part-of children.
--
-- Additive only. Nothing here alters existing tables or rows.

CREATE TABLE IF NOT EXISTS atlas.version_scope_project_events (
    id          SERIAL PRIMARY KEY,
    project_key TEXT NOT NULL,
    event       TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT '',  -- who/when ruled it: Brian quote or record reference
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vs_project_events_key
    ON atlas.version_scope_project_events(project_key);
