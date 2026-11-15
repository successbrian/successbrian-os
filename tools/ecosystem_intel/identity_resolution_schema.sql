-- identity_resolution — SuccessBrian OS core identity layer.
--
-- Brian's order (2026-11-08): build the ecosystem-fit identity ideas
-- into SuccessBrian OS, with lookalike/clone detection. Clean-room
-- implementation; new tables only. Existing tables are never altered.
-- State home (R32): PostgreSQL, database people_unified, schema people.

CREATE SCHEMA IF NOT EXISTS people;

CREATE TABLE IF NOT EXISTS people.identity_people (
    id               BIGSERIAL PRIMARY KEY,
    display_name     TEXT NOT NULL,
    name_norm        TEXT NOT NULL,
    people_person_id BIGINT,
    brian_confirmed  BOOLEAN NOT NULL DEFAULT FALSE,
    pinned_fields    JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes            TEXT,
    profile_count    INT NOT NULL DEFAULT 0,
    platform_count   INT NOT NULL DEFAULT 0,
    surface_count    INT NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Breadth columns for installs created before the 2026-11-08 breadth
-- ruling (this module's own new table only; nothing existing altered).
ALTER TABLE people.identity_people
    ADD COLUMN IF NOT EXISTS profile_count INT NOT NULL DEFAULT 0;
ALTER TABLE people.identity_people
    ADD COLUMN IF NOT EXISTS platform_count INT NOT NULL DEFAULT 0;
ALTER TABLE people.identity_people
    ADD COLUMN IF NOT EXISTS surface_count INT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_identity_people_name_norm
    ON people.identity_people (name_norm);
CREATE INDEX IF NOT EXISTS idx_identity_people_people_person
    ON people.identity_people (people_person_id);

CREATE TABLE IF NOT EXISTS people.identity_profiles (
    id           BIGSERIAL PRIMARY KEY,
    person_id    BIGINT REFERENCES people.identity_people(id)
                 ON DELETE SET NULL,
    platform     TEXT NOT NULL CHECK (platform IN (
                     'facebook', 'instagram', 'threads', 'messenger',
                     'whatsapp', 'telegram', 'linkedin', 'x', 'tiktok',
                     'youtube', 'email', 'other')),
    platform_id  TEXT,
    handle       TEXT,
    handle_norm  TEXT,
    display_name TEXT,
    profile_url  TEXT,
    followers    BIGINT,
    following    BIGINT,
    bio_current  TEXT,
    source       TEXT,
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_profiles_platform_id
    ON people.identity_profiles (platform, platform_id)
    WHERE platform_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_profiles_platform_handle_noid
    ON people.identity_profiles (platform, handle_norm)
    WHERE platform_id IS NULL AND handle_norm IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_identity_profiles_handle_norm
    ON people.identity_profiles (handle_norm);
CREATE INDEX IF NOT EXISTS idx_identity_profiles_handle_root
    ON people.identity_profiles ((regexp_replace(handle_norm, '[0-9]+$', '')))
    WHERE handle_norm IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_identity_profiles_person
    ON people.identity_profiles (person_id);
CREATE INDEX IF NOT EXISTS idx_identity_profiles_platform
    ON people.identity_profiles (platform);

-- Profile-URL provenance (Brian, 2026-11-08: "store the profile
-- url's for me to look up"): url_source='source' means the URL
-- arrived with the data; 'composed' means
-- --backfill-profile-urls built it from a canonical pattern.
-- This module's own table only; the breadth-column ALTER above
-- is the precedent followed.
ALTER TABLE people.identity_profiles
    ADD COLUMN IF NOT EXISTS url_source TEXT;

-- Evidence-signal storage (Brian, 2026-11-15: self-link pages and
-- identical photos as logged, accumulating evidence). declared_links
-- holds every outbound link a profile declares (website + bio
-- links, as captured); photo_url / photo_hash hold the profile
-- photo and the sha256 of the image bytes when a capture lane
-- fetched it — an identical-image check only, never face data.
-- This module's own table only; additive, same precedent.
ALTER TABLE people.identity_profiles
    ADD COLUMN IF NOT EXISTS declared_links JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE people.identity_profiles
    ADD COLUMN IF NOT EXISTS photo_url TEXT;
ALTER TABLE people.identity_profiles
    ADD COLUMN IF NOT EXISTS photo_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_identity_profiles_photo_hash
    ON people.identity_profiles (photo_hash)
    WHERE photo_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS people.identity_matches (
    id           BIGSERIAL PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('same_person', 'lookalike_risk')),
    profile_a_id BIGINT NOT NULL REFERENCES people.identity_profiles(id),
    profile_b_id BIGINT NOT NULL REFERENCES people.identity_profiles(id),
    score        NUMERIC(6, 4),
    grade        TEXT CHECK (grade IN (
                     'CONFIRMED', 'STRONG', 'POSSIBLE', 'REJECTED', 'EXCLUDED')),
    signals      JSONB NOT NULL DEFAULT '{}'::jsonb,
    method       TEXT NOT NULL DEFAULT 'engine'
                 CHECK (method IN ('engine', 'agent', 'brian')),
    status       TEXT NOT NULL DEFAULT 'auto'
                 CHECK (status IN ('auto', 'pending_review', 'ruled_same',
                                   'ruled_different')),
    resolved_by  TEXT,
    resolved_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (profile_a_id < profile_b_id),
    UNIQUE (kind, profile_a_id, profile_b_id)
);

CREATE INDEX IF NOT EXISTS idx_identity_matches_status
    ON people.identity_matches (kind, status, grade);
CREATE INDEX IF NOT EXISTS idx_identity_matches_a
    ON people.identity_matches (profile_a_id);
CREATE INDEX IF NOT EXISTS idx_identity_matches_b
    ON people.identity_matches (profile_b_id);

CREATE TABLE IF NOT EXISTS people.identity_bio_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    profile_id  BIGINT NOT NULL REFERENCES people.identity_profiles(id),
    bio         TEXT,
    bio_hash    TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      TEXT
);

CREATE INDEX IF NOT EXISTS idx_identity_bio_snapshots_profile_time
    ON people.identity_bio_snapshots (profile_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS people.identity_life_events (
    id          BIGSERIAL PRIMARY KEY,
    profile_id  BIGINT NOT NULL REFERENCES people.identity_profiles(id),
    event_type  TEXT NOT NULL CHECK (event_type IN (
                    'job_change', 'company_change', 'product_launch',
                    'promotion', 'relocation', 'new_offer', 'milestone',
                    'other')),
    confidence  NUMERIC(4, 3),
    summary     TEXT,
    old_bio     TEXT,
    new_bio     TEXT,
    method      TEXT NOT NULL DEFAULT 'rules-v1',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_identity_life_events_profile_time
    ON people.identity_life_events (profile_id, detected_at DESC);
