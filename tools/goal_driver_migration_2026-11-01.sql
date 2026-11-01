-- Goal Driver machinery (Brian's build order, 2026-11-01): the three clear
-- monthly goals + asset->goal links ONLY where the fit is genuine.
BEGIN;
CREATE SCHEMA IF NOT EXISTS successbrian_os;

CREATE TABLE IF NOT EXISTS successbrian_os.monthly_goals (
  goal_key     text PRIMARY KEY,
  product      text NOT NULL,
  target       integer NOT NULL CHECK (target > 0),
  unit         text NOT NULL,
  source       text NOT NULL,
  ruled_on     date NOT NULL,
  notes        text
);

-- Appropriateness is enforced by shape: a link cannot exist without a
-- written fit reason (fit_note NOT NULL, min length), sourced to who said it.
CREATE TABLE IF NOT EXISTS successbrian_os.goal_asset_links (
  id           bigserial PRIMARY KEY,
  asset_type   text NOT NULL,          -- blog / campaign / roster / partnership / desk / funnel / course / article
  asset_ref    text NOT NULL,          -- slug or stable reference
  goal_key     text NOT NULL REFERENCES successbrian_os.monthly_goals(goal_key),
  fit_note     text NOT NULL CHECK (char_length(fit_note) >= 20),
  status       text NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
  source       text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_type, asset_ref, goal_key)
);

-- Monthly scorecard: counts are ENTERED from the programs' own back offices.
-- Nothing here estimates or invents a count; an unreported month has no row.
CREATE TABLE IF NOT EXISTS successbrian_os.goal_month_scores (
  goal_key     text NOT NULL REFERENCES successbrian_os.monthly_goals(goal_key),
  month        date NOT NULL,          -- first of month
  achieved     integer NOT NULL CHECK (achieved >= 0),
  source       text NOT NULL,          -- where the count came from
  entered_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (goal_key, month)
);

INSERT INTO successbrian_os.monthly_goals (goal_key, product, target, unit, source, ruled_on, notes) VALUES
 ('gotbackup-40','GotBackup',40,'paid enrollments','brian','2026-11-01','Restated 2026-11-01 as one of three clear monthly goals; also tracked goal goal_c4b0016ba891 with the fixed income ladder.'),
 ('oliabo-30','Oliabo',30,'new paid customers','brian','2026-11-01','Tracked goal goal_48ebad23b51f.'),
 ('systeme-50','systeme.io',50,'new paid customers','brian','2026-11-01','Tracked goal goal_cb5c16d6df9d. Pairs with the platform doctrine: Brians CRMs integrate systeme.io so customers never need ClickFunnels/GoHighLevel/Kajabi.')
ON CONFLICT (goal_key) DO NOTHING;

-- Seed links: ONLY fits Brian himself established on the record.
INSERT INTO successbrian_os.goal_asset_links (asset_type, asset_ref, goal_key, fit_note, source) VALUES
 ('blog','ai-builders','gotbackup-40',
  'Brian placed GotBackup on the AI Builders affiliate roster himself (2026-11-01): builders back up 85-391GB model-weight libraries, fleet configs and second-brain data.',
  'brian'),
 ('campaign','influencer-game-plan','oliabo-30',
  'Brian ruled the first game plan for every influencer is to run Oliabo past them (2026-11-01); the campaign exists to produce Oliabo customers.',
  'brian')
ON CONFLICT DO NOTHING;
COMMIT;
