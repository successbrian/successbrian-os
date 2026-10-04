CREATE TABLE IF NOT EXISTS successbrian_os.aff_programs (
    id              SERIAL PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    terms           TEXT NOT NULL DEFAULT '',
    commission_summary TEXT NOT NULL DEFAULT '',
    cookie_days     INTEGER,
    payout_minimum  NUMERIC,
    status          TEXT NOT NULL DEFAULT 'active',
    my_role         TEXT,
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One revenue lane per program: a distinct way to earn referral income
-- with the same program (review SEO, tutorials, email, bonuses, ...).
CREATE TABLE IF NOT EXISTS successbrian_os.aff_lanes (
    id              SERIAL PRIMARY KEY,
    program_id      INTEGER NOT NULL REFERENCES successbrian_os.aff_programs(id)
                        ON DELETE CASCADE,
    lane_name       TEXT NOT NULL,
    lane_type       TEXT NOT NULL DEFAULT 'other',
    description     TEXT NOT NULL DEFAULT '',
    effort          TEXT NOT NULL DEFAULT 'medium',
    expected_payoff TEXT NOT NULL DEFAULT 'medium',
    why_it_works    TEXT NOT NULL DEFAULT '',
    rule_notes      TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'idea',
    earnings_to_date NUMERIC NOT NULL DEFAULT 0,
    referrals_to_date INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id, lane_name)
);
CREATE INDEX IF NOT EXISTS aff_lanes_program_idx
    ON successbrian_os.aff_lanes (program_id);
CREATE INDEX IF NOT EXISTS aff_lanes_status_idx
    ON successbrian_os.aff_lanes (program_id, status);

-- Reusable content: email sequences, review templates, video scripts,
-- bonus frameworks, lead magnets, checklists.
CREATE TABLE IF NOT EXISTS successbrian_os.aff_playbooks (
    id              SERIAL PRIMARY KEY,
    program_id      INTEGER NOT NULL REFERENCES successbrian_os.aff_programs(id)
                        ON DELETE CASCADE,
    lane_id         INTEGER REFERENCES successbrian_os.aff_lanes(id)
                        ON DELETE SET NULL,
    title           TEXT NOT NULL,
    playbook_type   TEXT NOT NULL DEFAULT 'other',
    body            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Monthly performance per program (lane_id NULL = program total).
CREATE TABLE IF NOT EXISTS successbrian_os.aff_metrics (
    id              SERIAL PRIMARY KEY,
    program_id      INTEGER NOT NULL REFERENCES successbrian_os.aff_programs(id)
                        ON DELETE CASCADE,
    lane_id         INTEGER REFERENCES successbrian_os.aff_lanes(id)
                        ON DELETE SET NULL,
    period_month    TEXT NOT NULL,
    clicks          INTEGER NOT NULL DEFAULT 0,
    conversions     INTEGER NOT NULL DEFAULT 0,
    earnings        NUMERIC NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id, lane_id, period_month)
);

-- Strategy notes and research findings per program.
CREATE TABLE IF NOT EXISTS successbrian_os.aff_notes (
    id              SERIAL PRIMARY KEY,
    program_id      INTEGER NOT NULL REFERENCES successbrian_os.aff_programs(id)
                        ON DELETE CASCADE,
    note            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aff_notes_program_idx
    ON successbrian_os.aff_notes (program_id);
