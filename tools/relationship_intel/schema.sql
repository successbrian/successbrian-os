-- P5 field capture loop schema (new Vera, relationship intel).
-- Run against people_unified. Idempotent: safe to re-run.
-- NOTE: people.capture_mission_proposals is the BUILD_NOTES table contract
-- owned by P4; P5 creates it here only if P4 hasn't landed yet.

CREATE TABLE IF NOT EXISTS people.capture_mission_proposals (
    proposal_id serial PRIMARY KEY,
    person_id bigint,
    target_name text NOT NULL,
    what_to_capture text NOT NULL,
    reason text,
    proposed_at timestamptz DEFAULT now(),
    status text DEFAULT 'proposed'
);
CREATE INDEX IF NOT EXISTS idx_cmp_status
    ON people.capture_mission_proposals (status);

-- P5 bookkeeping: podcast_questions.id (ecosystem_central) is cross-DB, so no FK.
CREATE TABLE IF NOT EXISTS people.field_capture_missions (
    mission_id integer PRIMARY KEY,
    proposal_id integer REFERENCES people.capture_mission_proposals (proposal_id),
    target_person_id integer,
    target_name text NOT NULL,
    what_to_capture text NOT NULL,
    platform text DEFAULT 'unknown',
    relation_type text DEFAULT 'friend',
    channel text DEFAULT 'podcast_questions',
    status text DEFAULT 'requested',
    created_at timestamptz DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_fcm_status
    ON people.field_capture_missions (status);

-- Processed-file manifest: per-file OCR/edge stats and per-edge confidence
-- summary. people.social_connections has no notes column, so confidence lives
-- here (per-file) and edges carry source='field_capture:<mission_id>'.
CREATE TABLE IF NOT EXISTS people.field_capture_files (
    file_id serial PRIMARY KEY,
    mission_id integer REFERENCES people.field_capture_missions (mission_id),
    filename text NOT NULL,
    sha256 text NOT NULL UNIQUE,
    ocr_chars integer,
    names_found integer,
    handles_found integer,
    edges_created integer,
    penny_fallback boolean DEFAULT false,
    status text DEFAULT 'processed',
    notes text,
    processed_at timestamptz DEFAULT now()
);
