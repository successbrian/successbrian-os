# Rulings Census

Brian's standing rulings, each with a liveness check — built 2026-11-17
after the A2000 ruling died silently for a month: the old price sweep
that carried it stopped in October, the rebuilt desk never inherited
it, and nothing compared the ruled set against the live set, so there
was nothing for the loss to be noticed against.

## How it works

- **Registry**: `successbrian_os.ruling_census` (alpha). One row per
  standing ruling: the ruling in one sentence, Brian's verbatim quote
  where the record holds one (provenance column: verbatim / restated /
  system-state, per the ruling-provenance standard), category
  (tracking / never / recurring / behavior), what it binds, and the
  QA check that proves it is still alive.
- **Probes**: rows point at `successbrian_os.pm_project_checks`
  entries (project `rulings-census` for census-born probes; older
  rows reuse the checks built with their own machinery — 567, 570,
  621, 622, 627, 629, 636, 718, 723, 725–728). A probe measures the
  machinery, not the intention: sightings flowing, watch running,
  ban holding, gate still set.
- **Exception sweep**: Muse cron `rulings-census-daily` (~09:59 CST,
  registered in the SBOS timekeeper as muse-cron) joins census to
  checks and reports ONLY exceptions to Brian's chat: a failing
  probe, a probe that has not run in 48h, and — Mondays only — the
  rows marked `gap`. Silent when all green.
- **Honest statuses**: `live` (probe passing), `gap` (a known hole,
  recorded as a first-class row instead of hidden — e.g. the
  do-not-track ban not yet wired into the PicClick/Craigslist
  pipelines; the MZ32-AR0 rev 1.x buy rule with no live need),
  `manual` (behavior laws with no automated probe — checked by
  review, labeled as such, never faked green).

## Growing it

When Brian rules something with ongoing effect, the ruling is not
done until it has a census row and, where a machine signal exists, a
probe. When machinery is rebuilt or replaced, the census is the
cargo list: every row bound to the old machinery must land on the
new machinery or be marked `gap` out loud.

Seed/rebuild SQL: `tools/pm/ruling_census_seed.sql` (idempotent
table + the 2026-11-17 seed of 20 rows + the QA spec writes for
checks 729–732; the check rows themselves are created with
project_qa.py under project `rulings-census`).
