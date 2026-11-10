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
