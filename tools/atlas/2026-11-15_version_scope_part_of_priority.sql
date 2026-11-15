-- Atlas version-scope: part-of + priority (2026-11-15 correction pass).
--
-- Brian, 2026-11-15 09:21 CST: "road chat is part of successbrian os
-- (not separate)" — RoadChat is a component (optional plugin) of
-- SuccessBrian OS, not a standalone project. version_scope_projects
-- gains part_of so a component's row points at its parent project;
-- the row is KEPT (history matters — the registration happened; the
-- correction re-homes it, never erases it), and scope-gaps excludes
-- part-of projects: their undefined scope is the parent's business.
--
-- Brian, 2026-11-15 09:22 CST: "traffic streemz is a marketing skin
-- and it's super high priority" — projects gain a priority
-- (normal | high | super_high); scope-gaps surfaces super_high first,
-- clearly flagged. Priority is ruled separately from scope and never
-- implies scope items.
--
-- Additive only. Nothing here alters existing rows' meaning.

ALTER TABLE atlas.version_scope_projects
    ADD COLUMN IF NOT EXISTS part_of TEXT
    REFERENCES atlas.version_scope_projects(project_key);

ALTER TABLE atlas.version_scope_projects
    ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'normal';

DO $$
BEGIN
    ALTER TABLE atlas.version_scope_projects
        ADD CONSTRAINT version_scope_projects_priority_check
        CHECK (priority IN ('normal', 'high', 'super_high'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
