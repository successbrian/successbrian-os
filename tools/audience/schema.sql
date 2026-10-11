-- SuccessBrian OS: audience builder schema.
-- The entrepreneur picks which channels to focus on, logs weekly numbers,
-- and gets a deterministic growth report. The report PROPOSES; the
-- entrepreneur DECIDES. All state lives here, never in markdown files.

CREATE TABLE IF NOT EXISTS successbrian_os.audience_channels (
    id          SERIAL PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'other'
                CHECK (kind IN ('newsletter','blog','video','short_video',
                               'social','email','podcast','community','other')),
    url         TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    is_focus    BOOLEAN NOT NULL DEFAULT FALSE,
    focus_rank  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS successbrian_os.audience_snapshots (
    id              SERIAL PRIMARY KEY,
    channel_id      INTEGER NOT NULL
                      REFERENCES successbrian_os.audience_channels(id)
                      ON DELETE CASCADE,
    week_start      DATE NOT NULL,
    audience_size   INTEGER NOT NULL CHECK (audience_size >= 0),
    posts_published INTEGER NOT NULL DEFAULT 0 CHECK (posts_published >= 0),
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, week_start)
);
CREATE INDEX IF NOT EXISTS audience_snapshots_week_idx
    ON successbrian_os.audience_snapshots (week_start);

-- Week-over-week growth per channel. A row appears only when a channel has
-- two consecutive logged weeks, so the first logged week is a baseline.
CREATE OR REPLACE VIEW successbrian_os.audience_weekly_growth AS
WITH ranked AS (
    SELECT s.channel_id, s.week_start, s.audience_size, s.posts_published,
           LAG(s.audience_size) OVER w AS prev_size,
           LAG(s.week_start) OVER w AS prev_week
    FROM successbrian_os.audience_snapshots s
    WINDOW w AS (PARTITION BY s.channel_id ORDER BY s.week_start)
)
SELECT c.slug, c.name, c.kind, c.is_focus, c.focus_rank,
       r.week_start, r.audience_size, r.posts_published,
       r.prev_week, r.prev_size,
       (r.audience_size - r.prev_size) AS delta,
       CASE WHEN r.prev_size > 0
            THEN ROUND(100.0 * (r.audience_size - r.prev_size)
                       / r.prev_size, 1)
       END AS pct_change
FROM ranked r
JOIN successbrian_os.audience_channels c ON c.id = r.channel_id
WHERE r.prev_size IS NOT NULL;

-- Multi-audience upgrade (2026-10-11): one user, many crowds.
-- Additive and idempotent: re-running init_db on an existing deployment
-- only creates what is missing. Existing channels/snapshots/views untouched.
--
-- Shape: audiences (who they are + what axis they measure on) ->
-- campaigns (one audience, one goal) -> campaign_assets (the creative:
-- images, memes, posts tailored to that crowd). Channels link to
-- audiences many-to-many: one channel can serve several crowds.

CREATE TABLE IF NOT EXISTS successbrian_os.audiences (
    id           SERIAL PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    who_they_are TEXT NOT NULL DEFAULT '',
    axis         TEXT NOT NULL DEFAULT '',
    notes        TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS successbrian_os.campaigns (
    id          SERIAL PRIMARY KEY,
    audience_id INTEGER NOT NULL
                REFERENCES successbrian_os.audiences(id) ON DELETE CASCADE,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    goal        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','paused','done')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (audience_id, slug)
);

CREATE TABLE IF NOT EXISTS successbrian_os.channel_audiences (
    channel_id  INTEGER NOT NULL
                REFERENCES successbrian_os.audience_channels(id)
                ON DELETE CASCADE,
    audience_id INTEGER NOT NULL
                REFERENCES successbrian_os.audiences(id)
                ON DELETE CASCADE,
    PRIMARY KEY (channel_id, audience_id)
);

CREATE TABLE IF NOT EXISTS successbrian_os.campaign_assets (
    id          SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL
                REFERENCES successbrian_os.campaigns(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'other'
                CHECK (kind IN ('image','meme','post','video','other')),
    brief       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'idea'
                CHECK (status IN ('idea','making','ready','posted')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS campaign_assets_campaign_idx
    ON successbrian_os.campaign_assets (campaign_id);
