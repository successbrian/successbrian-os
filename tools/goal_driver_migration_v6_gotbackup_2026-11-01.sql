-- Goal Driver v6 (2026-11-01): GotBackup comp WAS in the ecosystem record
-- (successbrian_os.income_streams, valued 2026-10-29 from public comp
-- summaries; back office is the authority). Fill the layers from it.
BEGIN;
ALTER TABLE successbrian_os.goal_value_rates ADD COLUMN IF NOT EXISTS initial_cents integer;
UPDATE successbrian_os.goal_income_layers
SET rate_note = '200% first-month commission = $19.94 per $9.97 sale (annual plan: 50% of $99.97). At 40/mo pace a cohort pays $797.60 in its first month.',
    source = 'ecosystem record: successbrian_os.income_streams GotBackup row (public comp summaries checked 2026-10-29; back office is the authority)'
WHERE goal_key='gotbackup-40' AND layer='initial';
UPDATE successbrian_os.goal_income_layers
SET rate_note = '25% matching checks on direct referrals'' earnings + binary cycle bonuses (variable). Grows as the downline produces.',
    source = 'ecosystem record: successbrian_os.income_streams GotBackup row (2026-10-29)'
WHERE goal_key='gotbackup-40' AND layer='downline';
INSERT INTO successbrian_os.goal_income_layers (goal_key, layer, grows, rate_note, source) VALUES
 ('gotbackup-40','recurring', true,
  '25% recurring = $2.49/member/mo. At 40/mo pace each cohort adds $99.60/mo residual; month-12 run-rate modeled $1,893 (direct only, no churn, excl. matching/binary). Churn is the swing factor and is unmeasured.',
  'ecosystem record: successbrian_os.income_streams GotBackup row (2026-10-29)')
ON CONFLICT (goal_key, layer) DO UPDATE SET rate_note=EXCLUDED.rate_note, source=EXCLUDED.source;
UPDATE successbrian_os.goal_value_rates
SET value_low_cents = 249, value_high_cents = 249, initial_cents = 1994, value_kind = 'initial_plus_recurring',
    source = 'ecosystem record: income_streams GotBackup row (2026-10-29)',
    notes = 'Per enrollment: $19.94 initial (first month) + $2.49/mo recurring that stacks per cohort. Value columns carry the RECURRING $2.49 only; the outlook text states the initial separately. Ladder cross-check: Brians fixed ladder $1,250/$2,000/$2,750/$3,250 sits under the no-churn model line (rungs price in ~3%/mo churn).'
WHERE goal_key='gotbackup-40';
COMMIT;
