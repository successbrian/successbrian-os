# Solid Runners Counting — Spec

**Status:** SPEC ONLY (Brian's rulings, 2026-11-18 11:07–11:13 CST; staged into the PM
queue the same day on his order: "Stage it into SuccessBrian OS now"). Nothing in this
document is built yet. The build proceeds through the chained PM steps listed at the end.
**Home when built:** `successbrian-os/tools/runners/` on alpha.
**Goal of record:** Muse tracked goal `goal_6197405015e8` ("30 solid runners who run
with Brian"). This spec is the ecosystem home of that goal's machinery — per Brian's
standing ruling, builds live in SuccessBrian OS; Muse-side records are interim only.

## The goal

Find **30 solid runners** who run with Brian consistently.

This goal is **separate** from sponsoring 30 people a month into Oliabo (tracked goal
`goal_48ebad23b51f`), which continues unchanged. The two numbers are never conflated:

- **30/month is flow** — the monthly sponsored cohorts.
- **30 runners is the accumulated core** — the runners emerge from those cohorts over
  time, plus referral and influencer channels. A runner is not a second recruiting
  target; a runner is what a sponsored/referred person *becomes* by producing,
  sustained.

First hunting ground: the January Prima / Mindell campaign's 20–30 outstanding people
(health professionals, >$100k earners) — candidate slate at
`~/workspace/builds/outreach-readiness/PRIMA-CANDIDATE-SLATE.md` (Muse-side, interim).
Candidacy never counts toward the 30; only the bar below counts.

## The definition (Brian, 2026-11-18 11:08 CST)

> "solid runners are personnally referred people or influencers who get 5+ a month,
> month after month"

A solid runner is:

1. a **personally referred** person, **or** an **influencer**, who
2. **gets 5+ a month** — brings in 5+ new people per month — and
3. does it **month after month** — sustained, not a one-month spike.

Brian did not state a number of months for "month after month." The streak length is
**not assumed anywhere in this build**: step s2 proposes a streak rule and files it for
Brian's ruling; until he rules, no name is certified "solid" on a streak basis.

## Identification is the system's job (Brian, 2026-11-18 11:10 CST)

> "You (or my ecosystem) will be the one that tells me who the solid runners are by
> counting actual downline progress. it won't be me telling you this..."

The ecosystem counts and **reports the roster to Brian**. Brian never reports names
into this system. If the count cannot be produced for a month, the system says so —
silence is never dressed up as a zero.

## The counting spec (Brian, 2026-11-18 11:12 CST)

> "enrollments the system should be able to count or predict based on flow of stuff"

- **Counted quantity: ENROLLMENTS**, attributed per person, per month.
- **COUNT mode:** enrollments the system can actually see moving through Brian's own
  machinery — capture → nurture → enrollment — are counted directly from records.
- **PREDICT mode:** where a direct count is not visible, the system predicts from the
  **flow** — referrals arriving, invites converting, event flow, campaign responses,
  influencer activity — and forecasts who is producing enrollments at the 5+/month pace.
- **GUARD (Brian's do-not-guess law, applied):** a prediction is always **labeled** a
  prediction, never reported as a count. The roster keeps counted and predicted names
  in **separate sections** until actual enrollments confirm a prediction; only then
  does a name move to the counted section.

## The roster (output)

Monthly, delivered to Brian through the ecosystem's normal reporting path:

- **Counted runners** — name, enrollments this month, monthly history, streak length,
  running total toward 30.
- **Predicted runners** — name, predicted pace, the flow signals behind the prediction,
  clearly labeled PREDICTED.
- The month's count inputs stated (what was counted, what was predicted, what was
  unknown) — an honest month, every month.

## Open question — where the data lives (step s1's job)

Where live enrollment and downline data sits **today is UNKNOWN**. Candidates to check
in s1: `people_unified` sponsorship/referral edges; `lead_scraper` and email-tracking
tables; any Oliabo back-office records present on alpha. The deliverable is a findings
note in this folder stating what is countable today, what is predictable-only, and what
is unknown — no source is assumed before it is read.

## Staging (PM queue, 2026-11-18)

Umbrella step `solid-runners-counting` (marked done: spec filed + staging complete),
then a dependency chain, pri 50, origin brian, each unlocking only when the previous
completes:

1. `solid-runners-counting-s1-data-sources` — locate the enrollment/downline data;
   findings note in the repo.
2. `solid-runners-counting-s2-count-design` — attribution rules, counted-vs-predicted
   labeling, and a PROPOSED streak rule filed for Brian's ruling (never assumed).
3. `solid-runners-counting-s3-counter-v1` — build the counting tool in `tools/runners/`
   reading the s1 sources; produces the roster.
4. `solid-runners-counting-s4-roster-report` — monthly roster delivery to Brian;
   counted and predicted in separate sections.
5. `solid-runners-counting-s5-qa` — QA checks: counter runs clean, roster fresh,
   no predicted name in the counted section.

## What this build is not

- Not a recruiting or outreach tool: it sends nothing, contacts nobody, changes no
  campaign. Registration and counting only.
- Not the sponsoring goal: it never touches the 30/month flow goal's records.
- Not a verdict machine: it reports counts and labeled predictions to Brian; who he
  works with stays his call.
