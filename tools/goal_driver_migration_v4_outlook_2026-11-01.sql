-- Goal Driver v4 (Brian, 2026-11-01 16:39 CST): total income is NOT a fixed
-- goal — "this is a number that changes week to week based on the income
-- pipelines and goals we've set." So it is a COMPUTED weekly readout:
-- goal targets x per-conversion value rates. A stream whose value rate is
-- not on the verified record carries NULL and the outlook prints UNKNOWN —
-- it never invents a dollar figure.
BEGIN;
CREATE TABLE IF NOT EXISTS successbrian_os.goal_value_rates (
  goal_key        text PRIMARY KEY REFERENCES successbrian_os.monthly_goals(goal_key),
  value_low_cents  integer,
  value_high_cents integer,
  value_kind       text,           -- recurring_monthly / one_time / ladder
  source           text NOT NULL,
  notes            text
);
INSERT INTO successbrian_os.goal_value_rates (goal_key, value_low_cents, value_high_cents, value_kind, source, notes) VALUES
 ('systeme-50', 1020, 5820, 'recurring_monthly', 'systeme.io affiliate page, verified 2026-11-01',
  '60% lifetime recurring on paid plans: monthly plans pay $10.20-$58.20/mo per customer; annual plans pay more per sale ($282 Webinar / $582 Unlimited one-time-equivalent). Range spans plan mix.'),
 ('gotbackup-40', NULL, NULL, 'ladder', 'brian (income ladder on record)',
  'Value is carried by Brians fixed ladder ($1,250/mo Oct 2027; $2,000 Oct 2028; $2,750 Oct 2029; $3,250 Oct 2030) — a per-enrollment dollar rate is NOT on the verified record, so the outlook shows the ladder, not an invented rate.'),
 ('oliabo-30', NULL, NULL, 'unknown', 'not on record',
  'Oliabo per-customer compensation is not on Brians verified record. UNKNOWN until the comp plan is on record.')
ON CONFLICT (goal_key) DO NOTHING;
COMMIT;
