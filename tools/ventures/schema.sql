-- SuccessBrian OS: venture toolkit schema.
-- Ideas get fleshed out, scored, and drafted into goals - all in the DB,
-- never in markdown files (per Brian's rule).

CREATE TABLE IF NOT EXISTS successbrian_os.ventures (
    id            SERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    raw_pitch     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'raw'
                  CHECK (status IN ('raw','fleshed','scored','drafted','active','shelved','sample')),
    profile       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- profile keys: problem, customer, offer, revenue_model, price_point,
    --   startup_cost_usd, weekly_hours, stream_fit[], risks[], first_steps[], notes
    score         JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- score keys: total, band, breakdown{}
    income_streams TEXT[] NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ventures_status_idx
    ON successbrian_os.ventures (status);

CREATE TABLE IF NOT EXISTS successbrian_os.goal_drafts (
    id          SERIAL PRIMARY KEY,
    venture_id  INTEGER NOT NULL REFERENCES successbrian_os.ventures(id),
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    milestones  JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- milestones: [{title, detail}]
    status      TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','approved','created','dropped')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS goal_drafts_venture_idx
    ON successbrian_os.goal_drafts (venture_id);
