-- 2026-10-27_backups.sql — verified-backup state (Tier 1, Brian 2026-10-27)
-- Applied to ecosystem_central. Idempotent; sbos_backup.py also ensures
-- the same schema at runtime. State home: PostgreSQL (R32).
CREATE TABLE IF NOT EXISTS successbrian_os.backup_runs (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('pg','files','check')),
    repo TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running','ok','fail')),
    snapshot_id TEXT,
    bytes BIGINT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS successbrian_os.backup_drills (
    id BIGSERIAL PRIMARY KEY,
    drilled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pg_backup_at TIMESTAMPTZ,
    file_snapshot_id TEXT,
    checks JSONB NOT NULL DEFAULT '{}'::jsonb,
    verdict TEXT NOT NULL CHECK (verdict IN ('PASS','FAIL')),
    notes TEXT
);

-- SBOS tools connect as successbrian (pm_core); tables must be writable by it.
GRANT ALL ON successbrian_os.backup_runs, successbrian_os.backup_drills TO successbrian;
GRANT ALL ON ALL SEQUENCES IN SCHEMA successbrian_os TO successbrian;
