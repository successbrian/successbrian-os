-- Secrets closure — migration 2026-10-27 (Tier 1 security).
-- Inventory of secret-scan findings. NO secret values are EVER stored:
-- only repo/file/line, credential TYPE, verified-live flag, first-seen.
-- NOTE: a generic secret_findings table already existed (0 rows,
-- source default 'secret-scan-daily'); this migration EXTENDS it with
-- the inventory columns the closure requires. Idempotent.
CREATE TABLE IF NOT EXISTS successbrian_os.secret_findings (
    id serial PRIMARY KEY,
    found_at timestamptz NOT NULL DEFAULT now(),
    file_path text NOT NULL DEFAULT '',
    finding_type text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'new',
    source text NOT NULL DEFAULT 'secret-scan-daily',
    notes text
);
ALTER TABLE successbrian_os.secret_findings
  ADD COLUMN IF NOT EXISTS scan_run TEXT,
  ADD COLUMN IF NOT EXISTS source_kind TEXT,
  ADD COLUMN IF NOT EXISTS repo TEXT,
  ADD COLUMN IF NOT EXISTS line_no INT,
  ADD COLUMN IF NOT EXISTS commit_hash TEXT,
  ADD COLUMN IF NOT EXISTS credential_type TEXT,
  ADD COLUMN IF NOT EXISTS verified_live BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS hash_prefix TEXT,
  ADD COLUMN IF NOT EXISTS first_seen TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS secret_findings_dedupe_idx
  ON successbrian_os.secret_findings (COALESCE(repo,''), file_path, COALESCE(line_no,0), COALESCE(credential_type,''), COALESCE(commit_hash,''));
CREATE INDEX IF NOT EXISTS secret_findings_verified_idx
  ON successbrian_os.secret_findings (verified_live) WHERE verified_live;
COMMENT ON TABLE successbrian_os.secret_findings IS 'Secret-scan inventory 2026-10-27. Types/locations only — never values.';
