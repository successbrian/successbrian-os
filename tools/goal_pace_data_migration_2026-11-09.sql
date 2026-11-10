-- goal_pace_data_migration_2026-11-09.sql
-- Work order capture #1148 (Brian, 2026-11-09 23:52 CST: "do all these
-- improvements"): repair the goal-pace data the horizon toolkit's pace
-- verb reads (capture #1147 demo gaps).
--
-- 1. successbrian_os.goal_income_ladder — Brian's fixed dollar ladders
--    as DATA (amounts are Brian's data, never hardcoded in code).
--    GotBackup rungs: Brian 2026-10-29 (income_streams id 18 notes;
--    AGENTS.md BIGGIES): $1,250/mo by Oct 2027, $2,000 by Oct 2028,
--    $2,750 by Oct 2029, $3,250 by Oct 2030. THE LADDER NEVER MOVES:
--    the 40/mo signup pace may be raised if hit (Brian's rule), the
--    dollar rungs stay.
-- 2. monthly_goals gains the quick-$1,000 track's data home
--    (kind='fast_track', so goal_driver's exactly-3 paid_conversion
--    invariant is untouched). Product pick is still OPEN; NO score
--    rows are seeded — goal_month_scores stays evidence-only
--    (back-office counts, entered via goal_driver.py score).

CREATE TABLE IF NOT EXISTS successbrian_os.goal_income_ladder (
    id serial PRIMARY KEY,
    goal_key text NOT NULL,
    rung_month date NOT NULL,
    target_monthly_usd numeric NOT NULL,
    source text NOT NULL,
    ruled_on date,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (goal_key, rung_month)
);

INSERT INTO successbrian_os.goal_income_ladder
    (goal_key, rung_month, target_monthly_usd, source, ruled_on, notes)
VALUES
    ('gotbackup-40', DATE '2027-10-01', 1250,
     'Brian 2026-10-29 (income_streams id 18 TARGET LADDER; AGENTS.md BIGGIES)',
     DATE '2026-10-29',
     'Fixed ladder — the ladder never moves. If the 40/mo pace is being hit, the PACE may be raised; the dollar rungs stay (Brian 2026-10-29).'),
    ('gotbackup-40', DATE '2028-10-01', 2000,
     'Brian 2026-10-29 (income_streams id 18 TARGET LADDER; AGENTS.md BIGGIES)',
     DATE '2026-10-29',
     'Fixed ladder — the ladder never moves.'),
    ('gotbackup-40', DATE '2029-10-01', 2750,
     'Brian 2026-10-29 (income_streams id 18 TARGET LADDER; AGENTS.md BIGGIES)',
     DATE '2026-10-29',
     'Fixed ladder — the ladder never moves.'),
    ('gotbackup-40', DATE '2030-10-01', 3250,
     'Brian 2026-10-29 (income_streams id 18 TARGET LADDER; AGENTS.md BIGGIES)',
     DATE '2026-10-29',
     'Fixed ladder — the ladder never moves.')
ON CONFLICT (goal_key, rung_month) DO NOTHING;

INSERT INTO successbrian_os.monthly_goals
    (goal_key, product, target, unit, source, ruled_on, notes, kind)
VALUES
    ('quick-1000',
     'Quick-$1,000 track (vendor product TBD)',
     1000,
     'USD commissions in ~30 days (~$300/sale)',
     'brian',
     DATE '2026-10-29',
     'Fast track: roughly $1,000 in ~30 days from strangers, through ~$300-per-sale commissions on a real, already-built vendor product sold via lead generation. Product pick still OPEN (Brian). Actuals home: goal_month_scores under this key, entered from evidence only — no sales recorded at seed time (0 evidenced sales; nothing fabricated). Data home added 2026-11-09 (capture #1148).',
     'fast_track')
ON CONFLICT DO NOTHING;
