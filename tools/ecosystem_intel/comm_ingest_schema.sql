-- comm_ingest — SuccessBrian OS core communication-ingestion store.
--
-- Brian's order (2026-11-08): ingest ALL Facebook Messenger threads
-- (at least 5 Messenger accounts) and ALL Instagram DM threads (one
-- account, @successbrian) into SuccessBrian OS, written to the CRM by
-- person; originals deletable only after verified-complete; fake/gone
-- accounts handled case by case as intel items.
--
-- Standing frame: Brian's 2026-10-25 common-ingestion ruling — one
-- normalized message envelope in PostgreSQL, person joined on
-- phone/email/handle, raw payload preserved. Design: RECON.md in
-- ~/workspace/builds/messenger-ingest/ (hybrid, export-first route;
-- the Messenger / Instagram-Messages connectors are barred by their
-- own governing docs from bulk mirror use and stay in their
-- narrow-read lane).
--
-- State home (R32): PostgreSQL, database people_unified, schema
-- people, beside the identity tables. NEW tables only — no existing
-- table is altered. Counterparty resolution goes through the identity
-- layer (identity_profiles / identity_people), never beside it.

CREATE SCHEMA IF NOT EXISTS people;

-- Brian's own messaging accounts (each personal profile has its own
-- Messenger inbox; each Page has its own Page inbox — RECON §2c).
CREATE TABLE IF NOT EXISTS people.comm_accounts (
    id                   BIGSERIAL PRIMARY KEY,
    platform             TEXT NOT NULL CHECK (platform IN ('messenger', 'instagram')),
    account_kind         TEXT NOT NULL CHECK (account_kind IN ('profile', 'page')),
    identity_profile_id  BIGINT REFERENCES people.identity_profiles(id)
                         ON DELETE SET NULL,
    label                TEXT NOT NULL UNIQUE,
    account_platform_id  TEXT,
    handle               TEXT,
    owner_display_name   TEXT,
    ingest_state         TEXT NOT NULL DEFAULT 'not_started'
                         CHECK (ingest_state IN ('not_started', 'partial',
                                                 'export_loaded',
                                                 'verified_complete')),
    verified_complete_at TIMESTAMPTZ,
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_comm_accounts_platform_id
    ON people.comm_accounts (platform, account_platform_id)
    WHERE account_platform_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS people.comm_threads (
    id                 BIGSERIAL PRIMARY KEY,
    account_id         BIGINT NOT NULL REFERENCES people.comm_accounts(id)
                       ON DELETE CASCADE,
    platform           TEXT NOT NULL CHECK (platform IN ('messenger', 'instagram')),
    platform_thread_id TEXT NOT NULL,
    thread_type        TEXT NOT NULL DEFAULT 'one_to_one'
                       CHECK (thread_type IN ('one_to_one', 'group',
                                              'marketplace', 'page', 'unknown')),
    title              TEXT,
    is_e2ee            BOOLEAN,
    folder             TEXT,
    first_message_at   TIMESTAMPTZ,
    last_message_at    TIMESTAMPTZ,
    message_count      INT NOT NULL DEFAULT 0,
    ingest_source      TEXT CHECK (ingest_source IN ('dyi_export',
                                                     'secure_storage',
                                                     'connector_read')),
    completeness       TEXT NOT NULL DEFAULT 'partial'
                       CHECK (completeness IN ('partial', 'export_loaded',
                                               'verified')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, platform, platform_thread_id)
);

CREATE INDEX IF NOT EXISTS idx_comm_threads_platform_thread
    ON people.comm_threads (platform, platform_thread_id);
CREATE INDEX IF NOT EXISTS idx_comm_threads_account
    ON people.comm_threads (account_id);

CREATE TABLE IF NOT EXISTS people.comm_thread_participants (
    id                      BIGSERIAL PRIMARY KEY,
    thread_id               BIGINT NOT NULL REFERENCES people.comm_threads(id)
                            ON DELETE CASCADE,
    profile_id              BIGINT REFERENCES people.identity_profiles(id)
                            ON DELETE SET NULL,
    participant_platform_id TEXT,
    participant_key         TEXT NOT NULL,
    display_name_snapshot   TEXT,
    role                    TEXT NOT NULL DEFAULT 'participant'
                            CHECK (role IN ('owner', 'counterparty',
                                            'participant')),
    resolution_state        TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (resolution_state IN ('resolved',
                                                        'candidate',
                                                        'unknown',
                                                        'gone',
                                                        'fake_flagged')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (thread_id, participant_key)
);

CREATE INDEX IF NOT EXISTS idx_comm_participants_profile
    ON people.comm_thread_participants (profile_id);
CREATE INDEX IF NOT EXISTS idx_comm_participants_state
    ON people.comm_thread_participants (resolution_state);

-- The normalized envelope. dedupe_key is the platform message ID when
-- the source carries one; otherwise a content hash of
-- platform_thread_id + timestamp + sender + text (+ first attachment
-- uri), and dedupe_kind says which. Cross-account dedupe (the same
-- thread appearing in two of Brian's own exports) is enforced in code
-- on (platform_thread_id, dedupe_key) across accounts.
CREATE TABLE IF NOT EXISTS people.comm_messages (
    id                  BIGSERIAL PRIMARY KEY,
    thread_id           BIGINT NOT NULL REFERENCES people.comm_threads(id)
                        ON DELETE CASCADE,
    platform_message_id TEXT,
    dedupe_key          TEXT NOT NULL,
    dedupe_kind         TEXT NOT NULL CHECK (dedupe_kind IN ('platform_id',
                                                             'content_hash')),
    sender_profile_id   BIGINT REFERENCES people.identity_profiles(id)
                        ON DELETE SET NULL,
    sender_name_snapshot TEXT,
    direction           TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (direction IN ('in', 'out', 'unknown')),
    sent_at             TIMESTAMPTZ,
    kind                TEXT NOT NULL DEFAULT 'text'
                        CHECK (kind IN ('text', 'photo', 'video', 'audio',
                                        'file', 'call', 'poll', 'share',
                                        'reaction', 'system')),
    text                TEXT,
    raw_payload         JSONB NOT NULL,
    source_file         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (thread_id, dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_comm_messages_thread_time
    ON people.comm_messages (thread_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_comm_messages_sender
    ON people.comm_messages (sender_profile_id);
CREATE INDEX IF NOT EXISTS idx_comm_messages_dedupe
    ON people.comm_messages (dedupe_key);

CREATE TABLE IF NOT EXISTS people.comm_attachments (
    id          BIGSERIAL PRIMARY KEY,
    message_id  BIGINT NOT NULL REFERENCES people.comm_messages(id)
                ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    source_uri  TEXT,
    stored_path TEXT,
    sha256      TEXT,
    bytes       BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_comm_attachments_message
    ON people.comm_attachments (message_id);

CREATE TABLE IF NOT EXISTS people.comm_ingest_runs (
    id                  BIGSERIAL PRIMARY KEY,
    account_id          BIGINT REFERENCES people.comm_accounts(id)
                        ON DELETE SET NULL,
    route               TEXT NOT NULL CHECK (route IN ('dyi_export',
                                                       'secure_storage',
                                                       'connector_read')),
    export_file         TEXT,
    export_sha256       TEXT,
    requested_range     TEXT,
    threads_seen        INT NOT NULL DEFAULT 0,
    messages_seen       INT NOT NULL DEFAULT 0,
    messages_inserted   INT NOT NULL DEFAULT 0,
    messages_duplicated INT NOT NULL DEFAULT 0,
    attachments_seen    INT NOT NULL DEFAULT 0,
    spotcheck           JSONB,
    verified_by         TEXT,
    verified_at         TIMESTAMPTZ,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_comm_runs_account
    ON people.comm_ingest_runs (account_id, created_at DESC);

-- Brian's case-by-case queue. Nothing here auto-resolves; a ruling is
-- recorded and feeds the identity engine's memory (RECON §5).
CREATE TABLE IF NOT EXISTS people.comm_intel_queue (
    id                      BIGSERIAL PRIMARY KEY,
    profile_id              BIGINT REFERENCES people.identity_profiles(id)
                            ON DELETE SET NULL,
    platform                TEXT,
    participant_platform_id TEXT,
    display_name_snapshot   TEXT,
    reason                  TEXT NOT NULL
                            CHECK (reason IN ('gone_account',
                                              'fake_suspect',
                                              'unresolvable',
                                              'duplicate_candidate',
                                              'anonymized_counterparty')),
    evidence                JSONB,
    status                  TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'ruled')),
    brian_ruling            TEXT,
    ruled_at                TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_comm_intel_queue_status
    ON people.comm_intel_queue (status, created_at);
