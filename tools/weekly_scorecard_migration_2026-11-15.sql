-- weekly_scorecard_migration_2026-11-15.sql — the SuccessBrian OS
-- WEEKLY SCORECARD store (tools/weekly_scorecard.py).
--
-- Brian's order, 2026-11-15: build the weekly scorecard into the
-- product. Design: ~/workspace/builds/sbos-scorecard/
-- DESIGN-2026-11-15.md (one card, two readers — the owner reads five
-- numbers once a week; the OS reads the same numbers as signals).
--
-- The agent interface's scorecard door (tools/agent_interface.py,
-- Phase 3) has waited for this store since it was built: it answered
-- honestly "no weekly-scorecard data store exists here". This file
-- is the only schema the store needs, purely ADDITIVE — five small
-- tables in successbrian_os, per-owner by operator_key, like
-- everything else in SBOS:
--   weekly_scorecard_settings — the owner's standing numbers: the
--     monthly "enough" number and the weekly hours cap.
--   weekly_scorecard_metrics  — the five numbers, as ROLES the owner
--     names in their own words, with floor / target / stretch and a
--     linked goal (a goal that moves no number is a wish).
--   weekly_scorecard_weeks    — one row per owner per week (Monday):
--     open until reviewed; a missed week stays open and carries
--     forward, never counted as handled (the calendar law). Holds
--     the two system checks (shoulder taps, hours vs cap), the one
--     fix, the one promise, and whether last week's promise was kept.
--   weekly_scorecard_entries  — per week, per number: the owner's
--     value (NULL = not entered — never invented), a desk-suggested
--     value kept strictly separate, the floor/target/stretch snapshot
--     the week was judged against, the green/yellow/red status, and
--     the owner's one-sentence plan.
--   weekly_scorecard_taps     — shoulder-tap log by kind: every time
--     the business needed the owner personally, logged with its kind,
--     so a recurring tap can be named and fixed.

create table if not exists successbrian_os.weekly_scorecard_settings (
  operator_key   text primary key,
  enough_monthly numeric,
  hours_cap      numeric,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
comment on table successbrian_os.weekly_scorecard_settings is 'Weekly scorecard (2026-11-15): per-owner standing numbers — the monthly "enough" number (what the business must bring in to be worth it) and the weekly cap on hours on the business. NULL = never set; unknown stays unknown, never invented.';

create table if not exists successbrian_os.weekly_scorecard_metrics (
  id             bigserial primary key,
  operator_key   text not null,
  slot           int  not null check (slot between 1 and 5),
  role           text not null check (role in ('in','talks','delivered','shipped','cash')),
  name           text not null,
  what_it_counts text,
  floor_value    numeric,
  target_value   numeric,
  stretch_value  numeric,
  goal_slug      text,
  active         boolean not null default true,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (operator_key, slot)
);
comment on table successbrian_os.weekly_scorecard_metrics is 'Weekly scorecard (2026-11-15): the five numbers as roles (1 In / 2 Talks / 3 Delivered / 4 Shipped / 5 Cash), named by the owner in their own words, with floor/target/stretch and a linked goal slug (successbrian_os.sbos_goals). Five slots, hard cap — short lists survive, long lists die.';

create table if not exists successbrian_os.weekly_scorecard_weeks (
  id                bigserial primary key,
  operator_key      text not null,
  week_start        date not null,
  status            text not null default 'open'
                    check (status in ('open','reviewed')),
  shoulder_taps     int,
  hours_on_business numeric,
  hours_cap         numeric,
  one_fix           text,
  one_promise       text,
  prev_promise_kept boolean,
  reviewed_at       timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (operator_key, week_start)
);
comment on table successbrian_os.weekly_scorecard_weeks is 'Weekly scorecard (2026-11-15): one row per owner per week (week_start = Monday). status open until the owner reviews it; a missed week stays open and carries forward (the calendar law) — it is never counted as handled. Carries the two system checks (shoulder_taps, hours_on_business vs hours_cap), the review''s one_fix and one_promise, and prev_promise_kept — whether the promise made the week before was kept, recorded at this review.';

create table if not exists successbrian_os.weekly_scorecard_entries (
  id              bigserial primary key,
  week_id         bigint not null references successbrian_os.weekly_scorecard_weeks(id) on delete cascade,
  metric_id       bigint not null references successbrian_os.weekly_scorecard_metrics(id),
  value           numeric,
  suggested_value numeric,
  floor_value     numeric,
  target_value    numeric,
  stretch_value   numeric,
  status          text check (status in ('green','yellow','red')),
  plan            text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (week_id, metric_id)
);
comment on table successbrian_os.weekly_scorecard_entries is 'Weekly scorecard (2026-11-15): one owner-entered number. value is the OWNER''s number only — NULL means not entered, and nothing anywhere fills it in. suggested_value is a desk pre-collection shown to the owner as a suggestion at review; it never becomes the value silently. floor/target/stretch are the snapshot the week was judged against. status follows the Deiss rule: green on target, yellow behind with a plan, red behind with no plan; NULL until a value exists and a target is set.';

create table if not exists successbrian_os.weekly_scorecard_taps (
  id           bigserial primary key,
  operator_key text not null,
  tapped_on    date not null default current_date,
  kind         text not null,
  note         text,
  created_at   timestamptz not null default now()
);
create index if not exists weekly_scorecard_taps_owner_date
  on successbrian_os.weekly_scorecard_taps (operator_key, tapped_on);
comment on table successbrian_os.weekly_scorecard_taps is 'Weekly scorecard (2026-11-15): the shoulder-tap log — every time the business needed the owner personally, logged by kind. A recurring kind is a system defect with a name; falling taps are the proof the system is working.';
