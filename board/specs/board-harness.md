# Spec: Board of Directors Harness

## What it is

A **harness** (reusable loop machinery) + **system** (one entrepreneur's bent
config) for running a daily morning board of directors with ephemeral C-level
seats. Any entrepreneur gets the functionality by bending the config; nobody
forks the harness.

## Generic vs bent

| Generic (harness/, never per-user) | Bent (config + pullers, per entrepreneur) |
|---|---|
| Seat schema + YAML loading | The actual seat roster and mandates |
| Stateless model worker, retry-once, fluff detection | Model endpoint + credentials |
| 90% gate scoring | Threshold (default 0.90) |
| DecisionSink interface + JsonlSink | SecondBrainSink (Brian's PG) or custom sink |
| BriefBuilder + NOT INSTRUMENTED rule | The actual state pullers |
| Session choreography + minutes | Schedule, deadlines, minutes dir |

## Session choreography

0. **Evening needs-pass** (prior evening, ~20:00): each seat analyzes its
   own domain and names what would sharpen tomorrow's calls — two kinds:
   `REPORT:` (a NEW type of report it wants built) and `DETAIL:` (news,
   trends, or topics it wants to know more about), up to 5 per seat. First
   it REVIEWS its previous requests: `SATISFIED:` closes out answers/reports
   that met its goal; misses get honed with refined follow-ups.
   DETAILs go into the overnight research queue; REPORTs become the
   instrumentation backlog (new pullers/reports to build — the board's
   standing "recommend instrumenting it" rule, now with a paper trail).
   The morning brief's shared context carries answered DETAILs plus the
   open REPORT backlog. The needs-pass waits on the model API like the
   session does.
1. **Brief** (≤15 min): BriefBuilder runs the pullers named in the seats'
   `brief_keys` plus shared context (night-shift report, recent decisions,
   overnight research answers). Missing state → explicit `NOT INSTRUMENTED`,
   never fiction.
2. **Wave 1**: each seat gets one stateless call (system = role prompt from
   title/domain/mandate/constraints; user = brief). Sequential with a hard
   barrier — a seat FULLY completes before the next starts. Transport errors
   and thin outputs are retried with exponential backoff (30s → 300s cap),
   unbounded: if we're waiting on the model API, we WAIT (2026-10-08). A new
   session never starts while the previous one is still running (lockfile).
3. **Wave 2**: seats with `depends_on` receive formatted wave-1 outputs as
   extra context (e.g. CFO consolidates money after the revenue chiefs).
4. **Gate**: chair scores every call (base 0.95; penalties for external
   actions, irreversible moves, unverified data claims, vagueness). ≥
   threshold → **binding**; below → **recommendation** (held for the human).
5. **Record**: binding decisions go to the sink with the session tag.
6. **Verify**: query the sink back, count. `verified < recorded` = pipeline
   failure. Zero usable calls across all seats = failed session. Both are
   written into the minutes — never silent.
7. **Minutes**: markdown file with decisions, recommendations, per-seat
   outputs, latencies, and health notes.

## Failure-mode guards (from the Sep 2026 post-mortem)

- **BOARD ACTIVE ≠ BOARD PRODUCING**: guarded by fluff detection (worker),
  zero-call session failure (session), and verify counts (sink).
- **Decorative pipeline**: guarded by record→verify with a real query-back,
  not a rowcount assumption.
- **Board trusts bad labels**: guarded by the NOT INSTRUMENTED rule — no
  state, no deliberation on that domain; the board recommends instrumenting
  it instead.
- **First answer mediocrity**: accepted by design (board = breadth); the
  gate + the human's feedback loop is where quality compounds. The loop is
  the product, not the first answer.

## Doctrines (non-negotiable)

- **BOARD PROPOSES, CHAIR DISPOSES.** The board never auto-executes.
- **Seats are title spots, not worker jobs.** Ephemeral: spawned per
  session, dissolved after. No persistent opinions.
- **Quarantine-never-delete, dry-run by default** for anything the board's
  decisions touch downstream.

## Open questions

- Meghan-as-chair integration (v1: the session worker chairs).
- Whether wave-1 seats should see each other's outputs (currently only
  wave-2 closers do).
- Onboarding interview that generates a bent config from plain language
  (the advisory-board-system's Altair-as-translator tier).
