-- SuccessBrian OS: ingestion engine schema.
-- Content flows in from many sources (second brain, AnythingLLM, markdown
-- files, agent chat sessions). Candidate income streams, audiences,
-- campaigns, and ideas flow out. The pipeline PROPOSES; the entrepreneur
-- DECIDES what becomes real. Nothing here writes to ventures, audiences,
-- or campaigns until the entrepreneur accepts a candidate.

CREATE TABLE IF NOT EXISTS successbrian_os.ingest_sources (
    id               SERIAL PRIMARY KEY,
    kind             TEXT NOT NULL
                     CHECK (kind IN ('second_brain', 'anythingllm',
                                     'markdown', 'chat')),
    ref              TEXT NOT NULL,
    last_ingested_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kind, ref)
);

CREATE TABLE IF NOT EXISTS successbrian_os.ingest_candidates (
    id          SERIAL PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_ref  TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL
                CHECK (kind IN ('income_stream', 'audience',
                                'campaign', 'idea')),
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    evidence    TEXT NOT NULL DEFAULT '',
    score       INTEGER NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100),
    status      TEXT NOT NULL DEFAULT 'proposed'
                CHECK (status IN ('proposed', 'accepted', 'rejected')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ingest_candidates_status_idx
    ON successbrian_os.ingest_candidates (status);
