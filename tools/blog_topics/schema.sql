-- Blog topic finder: scores candidate niches for Brian's 100-blog network.
CREATE TABLE IF NOT EXISTS successbrian_os.blog_topics (
    id              SERIAL PRIMARY KEY,
    topic           TEXT NOT NULL UNIQUE,
    niche           TEXT NOT NULL DEFAULT '',
    -- Brian's triage criteria (2026-10-08): hit hard/fast, easy to get into, not gated
    demand          TEXT NOT NULL DEFAULT 'medium',  -- high | medium | low (search demand)
    speed           TEXT NOT NULL DEFAULT 'medium',  -- fast | medium | slow (time to traffic)
    brian_ease      TEXT NOT NULL DEFAULT 'medium',  -- high | medium | low (his knowledge/passion)
    -- MLM linkage: which MLM product this topic funnels toward (NULL = none)
    mlm_product     TEXT,
    mlm_company     TEXT,
    -- Proposed affiliate monetization lane (checked vs competition graph)
    affiliate_lane  TEXT,
    -- Computed by topic_finder.py score command
    score           NUMERIC,
    status          TEXT NOT NULL DEFAULT 'candidate', -- candidate | active | gated | rejected
    gated_reason    TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
