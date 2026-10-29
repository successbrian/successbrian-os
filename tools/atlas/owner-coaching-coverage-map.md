# Owner-Coaching — Common-Core Coverage Map

Registered 2026-10-28 on Brian's directives (19:03 CDT: "successbrian os needs
to handle most of what the majority of these agree with in common"; 19:05 CDT:
the monetization layer). Capability: Atlas `sys:owner-coaching` — Brian's life
pillars: **Family, Faith, Friends, Fitness, Finance**. QA wrapper: PM project
`brian-health-tracking` (name kept — renaming is costly across runner state;
the project now QA-wraps the whole capability's coverage, not only Fitness).

Owner-coaching has **no AnythingLLM workspace of its own** (verified
2026-10-28: no owner-coaching slug in the workspace registry; the
ai-strategies-* workspaces are audience-facing coaching material per R9 — a
different thing). This doc therefore lives in the **SuccessBrian OS**
workspace. Registration/mapping only: no new coaching behavior was built, no
pillar added or renamed.

## The six common-core domains (what most life coaches agree on)

| # | Domain | SBOS home | State |
|---|--------|-----------|-------|
| 1 | Career / business | business-goals workspace (`allm:business-goals`) + SBOS goals machinery (goal side) | **Partial — domain placement is a GAP (open question A)** |
| 2 | Health & wellness | `pillar:fitness` (health five nested) + `successbrian_os.health_log` | Covered-by-pillar (data flow partial — PM checks 303–307) |
| 3 | Relationships | `pillar:family` + `pillar:friends` | Covered-by-pillar (both named-undefined shape) |
| 4 | Money / finances | `pillar:finance` | Covered-by-pillar (named-undefined shape) |
| 5 | Mindset / personal growth | `stress_mindset` sub-domain of `pillar:fitness`; material in the second brain (`sys:altair-second-brain`) | **Partial — placement is open question B** |
| 6 | Faith / spiritual | `pillar:faith` | Covered-by-pillar (named-undefined shape) |

## Cross-cutting mechanics

| Mechanic | SBOS home | State |
|----------|-----------|-------|
| Goal-setting | business-goals workspace + goals machinery (goals kept in view — core of the 2026-10-24 owner-coaching ruling) | Covered-by-existing-system |
| Accountability / commitment checks | Built-in owner coaching in the daily chat + PM project_qa commitment checks | Covered-by-existing-system |
| Habits / routines | The one calendar (`proj:calendar-carry-forward` — missed items reschedule, never vanish) | Partial (machinery ruled; pillar routines only beginning to live in it) |
| Balance | The one calendar + day-by-day best-time tracking (issue window 16:00–20:00; Friday 16:00–19:00 sleep block closed) | Partial |
| Time management | The one calendar with carry-forward + chat briefs | Partial |

## Monetization layer (Brian, 2026-10-28 19:05 CDT)

Each line is coaching → tool → affiliate line. **Standing disciplines on every
line:** (1) mechanical disclosure of the affiliate interest at the point of
recommendation, every time; (2) the selection rule — a product is recommended
only if Brian would recommend it with **no** commission; commission is never
the reason.

| Line | Path | Enrollment state |
|------|------|------------------|
| systeme.io | Career/Business + Finance coaching → systeme.io, the platform Brian sells | **ON RECORD** — Brian sells systeme.io; terms 60% lifetime (checked 2026-10-26); coaching owners to buy it ruled 2026-10-24 (PM decisions 121–124) |
| AI machines | Career/Business coaching → which AI machines to buy to upgrade the owner's local infrastructure (DealsDesk scorecard/buy-rule practice) | Line model **ON RECORD** (2026-10-24); per-vendor program enrollments not separately verified in this pass |
| Garmin watches | Fitness coaching → Garmin fitness-tracking hardware | **UNKNOWN** — enrollment not on record (general enrollment unknown since 2026-10-25); never state enrolled. Brian's ownership of a Garmin is **NOT on record** |
| Pixel phones | Fitness coaching → Pixel phone as the phone/health hub (Health Connect is the data door) | **UNKNOWN** — enrollment not on record; never state enrolled. Brian's own paired device **is** a Pixel 10 Pro — he uses what he would recommend |

## Open questions for Brian (NOT decided — PM judgment checks carry them)

- **A — Career/business placement:** is career/business a sixth domain of the
  owner-coaching capability, does it live inside Finance, or is it already
  covered by the business-goals machinery?
- **B — Mindset placement:** is mindset/personal growth a cross-cutting layer
  across all pillars, or does it stay as the `stress_mindset` sub-domain of
  Fitness?

Atlas: `coverage:*` (6), `coverage-mechanic:*` (5), `monetization:*` (4) child
nodes under `sys:owner-coaching`, with `maps-to`/`feeds` edges to their homes.
