# Spencer Review Toolkit — Spec

**Order:** Brian, 2026-11-09 23:13 CST — "build actual tools and code
INTO successbrian os, that allow you to manage and guide this process
day by day."

**The process:** the twice-daily Spencer ecosystem review passes
(Muse crons `spencer-ecosystem-review-am`, Mon–Fri 08:45 CT, and
`spencer-ecosystem-review-pm`, Mon–Fri 15:45 CT). Charters: Intel
Bridge captures #1113 (pass setup), #1114 (three-lane certainty
authority), #1130 (afternoon pass = the owner-absent window, 05:30–
15:30, judged daily + daily-workflow improvement).

**Doctrine position:** this toolkit is the management surface of the
Intel Harness flow (see `docs/intel-harness-spec.md`). One flow, one
system: the clerk is part of SuccessBrian OS, the desks are stops in
the flow, and this toolkit is the set of instruments the review passes
read and write — recorders, gauges, ledgers, queues, an assembler. The
Atlas node (`sys:spencer-review-toolkit`, part_of `sys:intel-harness`)
is bookkeeping — map, not territory. The toolkit does arithmetic and
layout; **it renders no verdicts**. Judgment lives in the pass agent;
rulings live with Brian.

## Layout

- Code: `tools/review/review.py` (single CLI; imports `sbos_common`
  per the shared-functions-once law). Selftest:
  `python3 tools/review/review.py selftest`
- State (Postgres, `successbrian_os` schema):
  - `review_snapshots` — one row per pass: gauge snapshot (jsonb),
    window summary (jsonb, pm passes), window verdict (text, supplied
    by the pass agent), briefing hash.
  - `review_frictions` — the friction ledger: date found, source,
    description, lane (1 done-in-pass / 2 researched / 3 Brian's),
    state (open / proposed / implemented / ruled / done), optional
    QA-check and capture links.
  - `review_decisions` — the lane-3 queue: item, context, numbers,
    source capture, first-surfaced date, state
    (waiting / ruled / dismissed), ruling. Ruled items never
    resurface: the passes build the waiting list from `state='waiting'`
    only.

## The six instruments

1. **Window recorder** — `review.py window [--date D] [--start HH:MM]
   [--end HH:MM] [--json]`. Default window 05:30–15:30 America/Chicago
   (the Crew 2 stretch). Reconstructs from live stores: cron fires
   (`cron_runs` ⨝ `cron_jobs`/`cron_registry`), captures filed and
   their triaged/ruled transitions in-window (`atlas.scattered_captures`
   timestamps), QA runs by status + failures (`pm_project_qa_runs`),
   desk outputs (candidate verdicts, market-pricing observations,
   authorship runs, WF3 filings, knowledge-index rows), and stalls
   (raw captures aged >24h at window end, stale failing checks).
   **Coverage is a first-class output**: every source is attempted
   inside a guard; an unreadable source is reported as a coverage gap
   with the error, never silently skipped. Known permanent gap:
   board packet production lives in Atlas task nodes, not a
   timestamped result table — covered indirectly via capture
   transition counts, and the gap is printed on every record.
2. **Gauges panel** — `review.py gauges [--json]`. One structured
   snapshot extending the pulse: QA failing checks (id, project,
   check, last run, fail age), clerk watermark + unswept raw backlog
   + oldest raw age, filing guards (AnythingLLM unsorted doc count;
   unindexed embedded docs — stem-normalized join of
   `workspace_documents` against `knowledge_index` catalog rows),
   authorship SLO + reserve + days since publish, AFBN fan-evidence
   count, GitHub stars/forks (live API read, failure → null + gap),
   expired-unrechecked `price_intel` count, `market_pricing`
   last-write age, gamma disk % (SSH df probe via the
   successbrianvps route), issues blocked on Brian
   (`altair.issues status='blocked_brian'` — the raw 'open' count is
   a 568k-row log artifact and is carried only for pulse parity),
   and the review queues' own depths. Standing coverage note:
   Muse-side goal flags (`user_action_required`) are not readable
   from alpha.
3. **Pass memory** — `review.py snapshot [--kind am|pm|manual]
   [--window-verdict TEXT]` stores the gauges (plus today's window
   record for pm) and the rendered briefing's hash. `review.py delta`
   compares the latest snapshot to the previous one — and to ~7 days
   ago when one exists — speaking per gauge in words
   (improved / worsened / unchanged) using a polarity map
   (lower-better: failures, backlogs, unsorted, unindexed, expired
   prices, disk %, blocked-on-Brian; higher-better: stars, fans,
   reserve, watermark). This is what makes "day by day" real.
4. **Friction ledger** — `friction-add / friction-list /
   friction-resolve`. Seeded at build with tonight's verified
   frictions (Hermes-profile stub shadowing, buy_score pagination
   bug, market_pricing writer gap → implemented, unsorted routing
   repair in flight, gamma disk full).
5. **Decisions queue** — `decide-add / decide-list / decide-age /
   decide-rule`. Seeded at build with the two genuinely-open Brian
   items from tonight, each carrying its source capture (idea-engine
   run cadence, #1112; main-line article publish path, #1096).
6. **Briefing assembler** — `review.py briefing --kind am|pm`.
   Renders the skeleton in the passes' exact groups (pm: THE WINDOW /
   DOING WELL / NOT DOING WELL / COULD DO BETTER / DONE THIS PASS,
   then the single DECISION FOR BRIAN; am: the same minus THE
   WINDOW), with numbers filled from the latest snapshot and every
   judgment slot left as a marked `[JUDGMENT: ...]` placeholder.

## How the passes use it (for the cron bodies)

- AM pass: `review.py gauges --json` → work the briefing →
  `review.py snapshot --kind am` when the briefing is delivered.
- PM pass: `review.py window` (today) for THE WINDOW section →
  `review.py snapshot --kind pm --window-verdict "<one line>"`.
- Either pass: `review.py delta` for day-by-day movement;
  `friction-add` for new frictions; `decide-age` for the waiting
  list; `decide-rule` the moment Brian rules.

## Honesty rules baked in

- A source that cannot be read is a printed coverage gap, never a
  silent zero.
- QA "failing" counts include judgment checks that sit at fail by
  design as gap markers (e.g. the R41 gap lines); the panel reports
  the count and the list — interpreting them is the pass's judgment,
  not the tool's.
- The assembler never writes verdict prose; slots stay placeholders
  until a pass agent fills them.

## Horizon layer — the weekly instruments (built 2026-11-09)

Brian's order (2026-11-09 23:29 CST, extended 23:30, 23:37, 23:38):
build the machinery for the Saturday 04:00 WEEKEND HORIZON CHECK into
SuccessBrian OS. The horizon layer is `tools/review/horizon.py`,
exposed on this toolkit's one CLI (`tools/review/review.py`); it
imports the daily layer (`import review as R`) and shares its tables
plus three of its own. State: `successbrian_os.review_agenda`
(the week's ≤3 priorities, set by the Saturday pass, read as data by
the Mon–Fri passes), `successbrian_os.review_build_verdicts` (one row
per build verification, raw evidence kept), and
`successbrian_os.review_coherence` (the weekly Deep Look census, so
coherence movement is computable week over week). Atlas:
`sys:spencer-review-toolkit-horizon` -[part_of]->
`sys:spencer-review-toolkit`. PM: project `spencer-review-toolkit`,
weekly checks horizon-* (one per verb, plus the selftest).

### The ten instrument families

1. **pace** — required pace vs recorded actuals for every goal the
   alpha stores carry machine-readably (sbos_goals success_metrics /
   target dates, public.brian_goals progress, the Mindell deadline
   node). Verdicts: ahead / holding / slipping / no-data, with
   numbers and the method named per goal. A goal whose actuals are
   not machine-readable is a printed GAP line, never an invented
   figure. Known gaps at build: the GotBackup fixed dollar ladder is
   not stored as data anywhere on alpha (goal_month_scores holds 0
   rows); the quick-$1,000 track has no alpha actuals; Claude-side
   tracked goals are not readable from alpha.
   PACE-DATA REPAIR (2026-11-09, capture #1148): the ladder and the
   monthly scorecard are now DATA. Stores: `monthly_goals`
   (Brian-ruled monthly targets: gotbackup-40 / oliabo-30 /
   systeme-50 / captures-3000, plus quick-1000 kind=fast_track —
   the quick-$1,000 track's data home; product pick still OPEN),
   `goal_month_scores` (the actuals home), and `goal_income_ladder`
   (Brian's fixed dollar ladders — GotBackup rungs $1,250/mo by
   2027-10, $2,000 by 2028-10, $2,750 by 2029-10, $3,250 by 2030-10;
   entered by tools/goal_pace_data_migration_2026-11-09.sql from
   Brian's 2026-10-29 ruling; THE LADDER NEVER MOVES — the signup
   pace may be raised if hit, the rungs stay). FEEDING DUTY:
   monthly-goal actuals enter `goal_month_scores` ONLY from program
   back offices, via `tools/goal_driver.py score --goal KEY
   --month YYYY-MM --achieved N --source S` — never estimated,
   never backfilled from prose. An unreported month prints NOT
   REPORTED and the pace verdict for it is no-data; a verdict is
   never computed off a counter that was never updated (the
   sbos_goals current_month_deals counter is one such — pace names
   it not-a-measurement). Until Brian reports a back-office count,
   EVERY monthly goal reads NOT REPORTED (at repair time no month
   had ever been reported); the passes nag for the count via the
   friction ledger. The GotBackup ladder position reads the
   recorded run-rate from income_streams.actual_monthly_usd
   (unset at repair time = NOT REPORTED). Remaining pace gap:
   Claude-side tracked goals are not readable from alpha.
2. **trend** — week-over-week over review_snapshots (history began
   2026-11-09; until a full week exists the report says
   "accumulating" and shows first-vs-latest), recurring QA failures
   from pm_project_qa_runs with streak counts, and the authorship
   reserve/SLO series. Fan-evidence and GitHub stars ride the
   snapshot series (afbn_fans / github_stars gauges).
3. **aging** — the slow-debt report: review_decisions age buckets,
   captures (raw depth + triaged-unruled >14d), altair.issues
   blocked_brian, open PM repair steps bucketed 0–6d / 7–13d / 14d+
   (Brian's flag law: 14 days no progress flags harder), and the
   parked registry — hand-seeded ONLY with a source citation on
   every row (repo Phase 2 items, credential rotations, board
   launcher, gamma disk).
4. **money** — project_budgets + dealsdesk budgets vs the build
   table (builds by status, build items by status, queued totals),
   open ecosystem_needs with per-item caps. A budget whose period
   has lapsed reads "lapsed"; a need without a cap reads "no cap
   set" — never "no limit". Prices are Postgres state only.
5. **health-week** — health_log aggregation, data only: last-7-day
   entries by metric, the full A1C series dated as recorded, dose
   entries by weekday (dated entries only), movement-shaped entry
   counts. The tool emits no targets, no advice, no evaluative
   health language; a banned-phrasing scan runs inside the verb and
   inside the selftest, and the verb aborts rather than print a
   tainted report.
6. **content-chain** — visits → contacts → revenue per blog from
   campaignsdesk.blog_scorecards plus the reach tables
   (reach_daily_activity / reach_snapshots, tracked-link clicks from
   campaignsdesk.outbound_clicks), this week vs last where data
   exists, per-blog ramp stage. Dry tributaries are reported dry
   (at build: scorecard visits/contacts/revenue are dry; no
   scorecard written since 2026-10-29).
7. **agenda-set / agenda-list / agenda-mark** — the week's agenda as
   DATA: week of, 1–3 priorities, each with source + why; state
   set/open/done/moved. Seeded EMPTY by design — the first real
   agenda is set by the first Saturday run; no invented priorities.
8. **week-briefing** (also `briefing --kind weekend` and stored by
   `snapshot --kind weekend`) — the Saturday skeleton in its charter
   groups: THE WEEK ON THE GOALS / MONEY / SYSTEMS / CONTENT /
   HEALTH / THE WEEK'S AGENDA / DEEP LOOK / DONE THIS PASS /
   WAITING ON BRIAN, numbers filled, judgment slots marked.
9. **build-verify** — Brian 23:30 CST: "QA check other
   builds/improvements that happened and make sure they really
   improved things." Enumerates the window's builds (PM projects /
   checks registered, build-word captures, desk git logs) and joins
   (a) the claim, (b) the build's QA checks' current status, (c) the
   mapped gauge before vs after (BUILD_GAUGE_MAP; before = last
   snapshot at/before registration, after = live gauges). Verdicts:
   improved / unchanged / regressed / unverifiable — each with
   evidence lines and an explicit reason when unverifiable.
   `--persist` writes review_build_verdicts; `--add-frictions`
   files regressed builds into the friction ledger (lane 2).
10. **coherence** — the Deep Look (Brian 23:29 + 23:37 + 23:38 CST):
    is Atlas driving the goals, is the system working together on
    them, and is it working the highest priorities first,
    efficiently, week to week and day to day?
    (a) Goal linkage census: per goal, Atlas anchors (seeded from
    live atlas.nodes, cited per goal in GOAL_LINKS) + token-matched
    plan/project nodes, edges, linked tasks open vs done, oldest
    open age. No presence = a named gap class.
    (b) Atlas flow: tasks created / completed / aged >14d in the
    window, by goal where linkable; the board-packet queue
    (atlas_task nodes keyed task:ssb-packet-*) measured live as the
    known boundary stall.
    (c) Orphan machinery census: every system/project node BFS'd
    (undirected, ≤3 hops) to any goal anchor. No path found is
    reported honestly with confidence in words: core substrate
    (SUBSTRATE_KEYS) reads "indirect path plausible"; anything else
    is a CANDIDATE orphan for the pass's judgment, listed with its
    activity (degree, last update, status) so dead weight can be
    told from quiet infrastructure.
    (d) Handoff stalls: one table of cross-system queues (clerk
    raw, board packets, Atlas tasks, v4pro handoffs, PM steps,
    review decisions, blocked issues) with depth + oldest age; an
    unreadable queue is stated, never skipped silently.
    (e) Priority discipline: agenda completion rate from
    review_agenda (not computable until the first Saturday-set week
    completes — stated, not faked); queue-age vs priority inversion
    CANDIDATES (goal-linked items open >14d beside newer unlinked
    items completed — candidates for the pass's judgment, never
    verdicts); the week's motion by goal (completed Atlas work
    mapped vs unmapped = the machinery-for-itself share).
    `--persist` writes the census to review_coherence.

### Honesty rules (horizon layer)

- Every number comes from an alpha store read live at run time, or
  the line is a labeled GAP with the stores searched named.
- Thin history is a reported state ("accumulating"), not a defect
  to hide: snapshot history starts 2026-11-09, so week-over-week
  firms up from 2026-11-16.
- The health instrument's data-only rule is enforced in code
  (banned-phrasing scan), not just in this doc.
- Verdicts the tool cannot support are "unverifiable" with the
  reason attached; inversion candidates are never promoted to
  verdicts by the tool.
