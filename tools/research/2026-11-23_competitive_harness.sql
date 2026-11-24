-- 2026-11-23_competitive_harness.sql
-- COMPETITIVE RESEARCH HARNESS (Brian's order, 2026-11-23 18:51 CST:
-- "we need a 'competitive research' harness -- and the things we
-- learned today need to be part of that research -- which can lead
-- to tasks, blog articles and anything relevant").
--
-- The queue + routing ledger. Studies themselves live in their
-- sanctioned homes (AnythingLLM docs, altair.second_brain, Intel
-- Bridge captures); these tables hold the question, its state, the
-- links to its study, and every output the study routed to - so a
-- finding can always be traced back to the question that raised it
-- and forward to the work it created.

CREATE TABLE IF NOT EXISTS successbrian_os.research_questions (
    id            serial PRIMARY KEY,
    question      text NOT NULL,
    subject       text NOT NULL UNIQUE,
    origin        text,
    feeds         text,
    article_ref   text,
    fetch_urls    jsonb NOT NULL DEFAULT '[]'::jsonb,
    status        text NOT NULL DEFAULT 'queued',
    priority      int  NOT NULL DEFAULT 50,
    bus_event_id  bigint,
    probe_id      text,
    evidence      jsonb,
    study_text    text,
    allm_pointer  text,
    second_brain_id bigint,
    capture_id    bigint,
    created_at    timestamptz NOT NULL DEFAULT now(),
    dispatched_at timestamptz,
    collected_at  timestamptz,
    routed_at     timestamptz
);

CREATE TABLE IF NOT EXISTS successbrian_os.research_routes (
    id          serial PRIMARY KEY,
    question_id int NOT NULL
        REFERENCES successbrian_os.research_questions(id),
    route_kind  text NOT NULL,
    ref         text NOT NULL,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (question_id, route_kind, ref)
);

CREATE INDEX IF NOT EXISTS research_questions_status_idx
    ON successbrian_os.research_questions (status, priority DESC, id);
