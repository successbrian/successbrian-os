-- B12b: dispatch tracking on the goal coverage ledger.
-- planner_rotation.py --dispatch marks each look it has acted on
-- (step created, packet sent, or blocker held) so a look is never
-- dispatched twice and a re-run only picks up undispatched looks.
-- dispatch_ref names what the look became: pm_steps:<key>,
-- bus.reap_infer:<event id>, no-work:blocker-held, or
-- blocked:<reason> when the tier has no live path.
ALTER TABLE successbrian_os.goal_coverage
  ADD COLUMN IF NOT EXISTS dispatched_at timestamptz,
  ADD COLUMN IF NOT EXISTS dispatch_ref text;
