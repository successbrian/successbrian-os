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
