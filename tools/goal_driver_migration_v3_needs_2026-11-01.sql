-- Goal Driver v3 (Brian, 2026-11-01 16:29 CST): "i want the ecosystem knowing
-- what it needs to build for me... how much content, how much ai inference
-- machines, etc." Goals now DERIVE build requirements. Every planning rate is
-- a stored, labeled assumption (source says whose figure it is) — derived
-- numbers are plans, never measurements, and the needs report shows its math.
BEGIN;
CREATE TABLE IF NOT EXISTS successbrian_os.planning_rates (
  rate_key   text PRIMARY KEY,
  value      numeric NOT NULL,
  unit       text NOT NULL,
  source     text NOT NULL,        -- whose figure this is
  notes      text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO successbrian_os.planning_rates (rate_key, value, unit, source, notes) VALUES
 ('article_views_per_month', 300, 'views per live article per month at maturity',
  'claude-planning-assumption',
  'Planning figure only, to be replaced by measured blog data as posts age. Young articles draw less.'),
 ('reader_capture_rate', 0.05, 'share of article readers who capture (name + channel)',
  'claude-planning-assumption',
  'Planning figure for a working capture door (PDF edition + Hiro door) on a targeted article.'),
 ('article_output_tokens', 6000, 'generated tokens per finished article (draft + revision + audio script)',
  'claude-planning-assumption',
  'Rough generation load per content piece, incl. the Hiro audio script version.'),
 ('node_tokens_per_day', 500000, 'usable generated tokens per inference node per day',
  'claude-planning-assumption',
  'Deliberately conservative: a 10-25 tok/s node run part-time on content work, shared with other duties.')
ON CONFLICT (rate_key) DO NOTHING;
COMMIT;
