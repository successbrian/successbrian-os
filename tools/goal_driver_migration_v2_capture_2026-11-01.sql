-- Goal Driver v2 (Brian, 2026-11-01 16:27 CST): add the capture goal.
-- The three paid-conversion goals stay exactly as ruled; the capture goal is
-- a different KIND (supply / leading indicator) and is recorded as such.
BEGIN;
ALTER TABLE successbrian_os.monthly_goals
  ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'paid_conversion';
INSERT INTO successbrian_os.monthly_goals (goal_key, product, target, unit, source, ruled_on, notes, kind) VALUES
 ('captures-3000','Captured contacts',3000,'new captured contacts','brian','2026-11-01',
  'Supply goal behind the three paid goals: 120 conversions/mo worked backward at a 3-5% warm-lead planning conversion. Ramp ruled same sitting: 500/mo while capture doors come online, then 1,500, landing on 3,000 as the standing target. Tracked goal goal_f1f98e1a4e49.',
  'capture')
ON CONFLICT (goal_key) DO NOTHING;
COMMIT;
