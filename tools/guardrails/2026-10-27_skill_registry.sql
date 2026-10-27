-- 2026-10-27_skill_registry.sql
-- Skill/MCP supply-chain gate — Brian's order, 2026-10-27.
-- One row per adopted skill or MCP server: what it is, where it lives,
-- and the sha256 it was pinned at on adoption. Weekly drift-scan
-- (skill_gate.py scan) re-hashes each location and updates
-- scan_verdict: clean (matches pin) / drift (differs) / missing (gone).
-- Idempotent: safe to apply any number of times. The module also
-- ensures this schema on every run; this file is the dated record.
-- No secret values ever belong in this table: MCP rows carry the
-- server NAME and file path only.

CREATE TABLE IF NOT EXISTS successbrian_os.skill_registry (
    id              serial PRIMARY KEY,
    name            text NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('skill', 'mcp')),
    source_url      text,
    pinned_ref      text,
    content_hash    text,
    location_path   text NOT NULL,
    adopted_at      timestamptz NOT NULL DEFAULT now(),
    last_scanned_at timestamptz,
    scan_verdict    text NOT NULL DEFAULT 'registered'
                    CHECK (scan_verdict IN
                        ('registered', 'clean', 'drift', 'missing')),
    notes           text,
    UNIQUE (kind, name, location_path)
);
