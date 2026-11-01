-- Goal Driver v5 (Brian, 2026-11-01 16:40 CST): income is calculated in
-- LAYERS — "initial commissions, downline commissions that grow, etc."
-- Each goal's income model is now a set of layers; a layer with no verified
-- rate stays NULL and prints UNKNOWN. Downline layers are marked as GROWING
-- (they compound with the downline's own production, unlike a flat rate).
BEGIN;
CREATE TABLE IF NOT EXISTS successbrian_os.goal_income_layers (
  goal_key   text NOT NULL REFERENCES successbrian_os.monthly_goals(goal_key),
  layer      text NOT NULL CHECK (layer IN ('initial','downline','recurring','bonus','other')),
  grows      boolean NOT NULL DEFAULT false,   -- true = compounds as downline/team grows
  rate_note  text,                              -- the rate in words, when on record
  source     text NOT NULL,
  PRIMARY KEY (goal_key, layer)
);
INSERT INTO successbrian_os.goal_income_layers (goal_key, layer, grows, rate_note, source) VALUES
 ('systeme-50','recurring', true,
  '60% lifetime recurring per paid customer; the layer grows because every month''s new customers stack onto all previous months.',
  'systeme.io affiliate page, verified 2026-11-01'),
 ('gotbackup-40','initial', false,
  NULL, 'not on record — GotBackup comp plan rates not yet in the verified record'),
 ('gotbackup-40','downline', true,
  NULL, 'not on record — downline/override structure exists in the model shape (Brian: downline commissions that grow) but rates are not on the verified record'),
 ('oliabo-30','initial', false,
  NULL, 'not on record — Oliabo comp plan rates not yet in the verified record'),
 ('oliabo-30','downline', true,
  NULL, 'not on record — Oliabo downline structure to be filled from the comp plan when it is on record')
ON CONFLICT (goal_key, layer) DO NOTHING;
COMMIT;
