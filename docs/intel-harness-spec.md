# The Intel Harness — SuccessBrian OS

**Status:** Phase 1 built and selftested, 2026-11-09. Phase 2 designed, not built.
**Ordered by:** Brian Lathe, 2026-11-09 22:30–22:45 CST (Intel Bridge captures #1098–#1104 + the naming/placement ruling filed alongside #1105).
**QA home:** SuccessBrian OS PM project `intel-harness`.

## 1. The order, in Brian's words

> "code my ecosystem; (the clerk) ... so that it (maybe using deepseek 150B reap)... looks at various things finds things it feels it needs to know, first digs into my existing knowledge to know what it knows, then figures out what it needs to know .... creates the research; (clerk stores that new research)... then if there are questions it needs to ask me that it can't resolve, asks me simple questions one by one"
> — Brian, 2026-11-09 22:30/22:33 CST (capture #1098)

> "the questions and planning we just did, I want built into SuccessBrian OS — kind of like an intel harness."
> — Brian, 2026-11-09 22:44 CST

> "in my opinion, 'clerk' is really part of successbrian os ... this whole system works together and must be one solid flow."
> — Brian, 2026-11-09 22:45 CST

## 2. The doctrine: one solid flow

The Intel Harness is **not a module, a desk, or a plugin**. It is the name for the **flow of the whole system**:

**intake → know → gap → research → store → ask**

- The **clerk** is SuccessBrian OS's knowledge-tending *role inside that flow* — not a separate system the harness gets wired onto.
- The **desks** (DealsDesk, CampaignsDesk, …) are **stops in the flow**, not components exchanging handoffs with it.
- There is no inter-component handoff framing and no plugin/bus language in this design, because there are not separate components: there is one system, flowing. Shared code lives in SBOS core because there is one system — not because components share a library.
- Atlas nodes/edges for the harness are **map, not territory**: graph bookkeeping so the system's structure stays visible. They do not make the harness a component.

At every stop, the flow does the same five things:

1. **KNOW** — before researching anything, dig the existing knowledge (Brian's decisions, the second brain, captures, price intel, the companies table — the Agent Knowledge Gateway stores) and establish what the system already knows.
2. **GAP** — state plainly what it still needs to know.
3. **RESEARCH** — create the missing research itself, on the engine ladder (§3, Q2).
4. **STORE** — file the new research in its sanctioned home (R32: documents → AnythingLLM, state → PostgreSQL, automation → n8n, logic → code; **prices are PostgreSQL state only, never facts inside AnythingLLM documents**), stamped with source, hit-signal, and shelf life (§3, Q3).
5. **ASK** — only for what it cannot resolve: simple questions to Brian, one by one, and only past his standing ask gate (§5).

## 3. The six rulings (the spec)

| # | Question | Brian's ruling | Capture |
|---|----------|----------------|---------|
| Q1 | Scope | The loop runs on **everything the clerk touches** — a general capability of the flow. The DealsDesk evaluator is the proof instance (sequencing, not scope). | #1099 |
| Q2 | Muscle | **Ladder**: Sonic (Qwen3.6-35B-A3B) for routine digs, DeepSeek 150B REAP for deep research. | #1100 |
| Q3 | Evidence | **Store the first source immediately, then hunt as many more sources as possible — multiple hits are a higher signal of intel.** Signal level (source-hit count) is carried on the stored research, alongside the shelf-life discipline. | #1101 |
| Q4 | Rulings | **One rulings list that everything reads.** Brian's rulings live as data (substrate: `altair.brian_decisions`); evaluators read rulings/gates as data instead of hardcoding them. | #1102 |
| Q5 | Focus | **"FOCUS on things that are easy to do and make me consistent high profit."** Measurable mapping (Spencer's, labeled as such): *easy* = short time-to-clear, no refurb/project work; *consistent* = steady weekly sold cadence, stable (non-spike, non-melting) price, margin that repeats across many sales. The 20% net-margin cap in `scoring_formulas.py` is a **machinery default, never Brian-ruled** — it stays a buried floor and is never presented as his law. | #1103 |
| Q6 | Marketplaces (DealsDesk instance) | **eBay + the used-server stores** the GPU watch already reads (TechMikeNY, Unix Surplus class). | #1104 |

## 4. Architecture — where things live

**SBOS core (the flow's shared mechanics)** — `~/successbrian-os/tools/intel_harness.py`:

- `what_do_we_know(topic)` — the KNOW step (decisions + captures + price intel today; Phase 2 widens to all gateway stores).
- `decisions_for(item)` / `find_blocking_ruling(item)` — the Q4 rulings reader over `altair.brian_decisions`.
- `time_to_clear(quantity, sold_count_30d, market_share)` — days for a pile to sell, at full market rate and at a labeled single-seller share.
- `agreement_hits(median, peers)` — Q3 hit-signal math (±10% agreement across source families).
- `valid_until(kind)` / `SHELF_LIFE_DAYS` — shelf-life discipline (mirrors `board/scatter_clerk.py`, the source of truth).
- `ask_gate(attempts, ideas_drying)` — Brian's 5-tries ask gate (§5).

**DealsDesk (first stop built; the proof instance)** — `/home/dealsdesk/scripts/`:

- `market_snapshot_writer.py` — populates `public.market_pricing` (current state) + `public.market_pricing_history` (append-only series) per candidate/SKU from eBay Browse sold data (reusing `buy_score_calculator`'s token/comps machinery — imported, not copied) and store asking data (reusing `gpu_watch_daily`'s TechMikeNY/Unix Surplus readers). Every row stamped `source_method` + `detail` (price basis, count basis) + `signal_hits`.
- `candidate_evaluator.py` — the judging stop: rulings-as-data check → `GPU_BANNED` code belt → market read → `calc_flip_score` with real demand/margin inputs (existing `scoring_formulas.py`, shared not copied) → margin cap → holding drag over the real clear horizon → Q5 focus score → verdict with all numbers attached, written to `dealsdesk.candidate_verdicts`.
- Migration of record: `scripts/2026-11-09_market_pricing_intel_harness.sql`.

**Data homes touched:** `public.market_pricing` (+4 columns), `public.market_pricing_history` (new), `dealsdesk.candidate_verdicts` (new), `altair.brian_decisions` (one backfilled ruling, §6).

## 5. The ASK step

Asking Brian is earned, never a first move (Brian's standing law, 2026-10-29): the flow may surface a question only when **(1)** it has logged **5 tries** (five attempts / dead ways) without success, **and (2)** its own outreaches for new ideas are starting to dry up. Then: **simple questions, one by one**, with context — never a bare problem dump. `intel_harness.ask_gate()` encodes the gate; Phase 2 wires it into the sweep so unresolvable gaps accumulate attempts instead of interrupting Brian.

## 6. Phase 1 as built (2026-11-09 night) — results

- **Selftests, all PASS:** `intel_harness.py` (10 checks incl. rulings-reader and ask-gate), `market_snapshot_writer.py --selftest` (schema + write/read roundtrip through the existing `get_market_baseline`), `candidate_evaluator.py --selftest` (8 checks).
- **The worked example reproduces.** Tesla P40 24GB, buy $239, qty 10 → **NO**, with the numbers attached: resale median (sold) $303, net margin **3.78%** (under the 20% machinery floor), flip score 79.9 → margin-capped to 39.95, trend **−11.81%/90d** (melting; tonight's verified −8.8% from the Aug→Nov verified anchors, deepened by the live Browse row at $293), time-to-clear 7.3 market days / 29.3 days at a labeled 0.25 single-seller share, holding drag $36.33, focus 0.585. Verdict stored as `dealsdesk.candidate_verdicts` id 1.
- **Q4's first citizen is real.** The evaluator blocks the P40 from **data**: `find_blocking_ruling()` reads decision `d261025-p40block` in `altair.brian_decisions`. That row is a **transparent backfill** (see §7): Brian's 2026-10-25 ruling was encoded in code and memory but had never been written into the rulings list — the exact failure Q4 exists to end.
- **A synthetic easy+consistent candidate comes out YES** (margin 41.9%, focus 0.94) — the evaluator is not a machine that only says no.
- **Live snapshots written:** P40 via eBay Browse (median sold $293, sampled page of 50); V100 via eBay (median sold $904.98) + TechMikeNY (asking median $899.95 — which scored **signal_hits 2**, agreeing with the eBay family: Q3 working live, across families). Unix Surplus had no V100 readings (its known coverage pattern).
- `market_pricing` went from **0 rows to a living table** (3 current-state rows, 5+ history rows at build time).

## 7. Flags — read before trusting

1. **THE SOLD-DATA CONTRADICTION (unresolved, by design).** `price_historian_sweep.py`'s docstring says sold data is sign-in-walled and buy-it-now asking prices are the market proxy; `buy_score_calculator.py` queries eBay Browse with `soldItems:true` and tonight it returned real-looking sold listings (median $293 vs the verified aggregator median $303). Both cannot be fully right. The writer **stamps every row with its method** (`source_method` + `detail.count_basis`) and code comments do not pick a side — the stored data, accumulating stamped rows, is what settles it. Browse's sold total also has **no documented 30-day window**; rows say so (`count_basis='browse_total_window_unspecified'`), and the evaluator prefers rows whose counts are true period counts.
2. **buy_score total bug (found live).** `_ebay_search` reads `pagination.totalMatched`; the Browse response returns top-level `total`. Its totals have therefore been returning 0 (verified live tonight: items real, totals 0). The writer reads totals from the raw response for its own counts and flags the bug here; the profile file was **not** edited mid-build (it is a live agent dependency).
3. **Profile-copy drift (two instances).** (a) The only home of the sold-comp fetcher is the Hermes profile copy of `buy_score_calculator.py` — per the shared-functions-once law it should graduate to SBOS core / DealsDesk scripts. (b) The same profile dir holds a 9,398-byte **stub** `scoring_formulas.py` (2026-07-25, missing `get_market_baseline` and most of the real module) that shadows the real 293,746-byte module if path order slips; `buy_score` survives only because it force-inserts `/home/dealsdesk/scripts` first. The writer does the same and documents why.
4. **Backfill transparency.** `altair.brian_decisions` row `d261025-p40block` was written during this build. It records Brian's actual ruling (2026-10-25, verbatim quotes; re-ruled 2026-11-09, captures #1091/#1097) and its `context` field states plainly that it is a backfill and why. No other decision rows were created or altered.
5. **deal_signals was the wrong home.** Verdicts were specced for `dealsdesk.deal_signals`, but that table has a CHECK constraint (`signal_type IN ('drop','spike')`) — it is the trend engine's contract and its rows wake builds waiting for drops. Verdicts went to a new `dealsdesk.candidate_verdicts` instead. Altering the constraint to shoehorn verdicts in was rejected as corrupting an existing contract.
6. **market_pricing is current-state, not history** (unique on type+model+marketplace). Trend math therefore reads the new append-only `market_pricing_history`; `get_market_baseline` keeps reading current state, unchanged.
7. **Machinery numbers are labeled, not hidden.** `FLIP_SCORE_MIN=55`, `FOCUS_MIN=0.55`, `MARKET_SHARE_DEFAULT=0.25` (evaluator) and the 20% margin floor (scoring_formulas) are operating defaults. Every verdict prints the floor's provenance: "machinery default, never Brian-ruled". Brian's Q5 law is the focus principle.
8. **signal_hits are stamped at observation time.** A row written before a second family exists keeps hits=1 even after agreement arrives later (the later rows carry the higher count). Recomputing historical hits is Phase 2 polish, not correctness — the freshest row for an item carries the current signal.

## 8. Phase 2 design — the flow, whole (not yet built)

Phase 2 is not "wiring desks onto a harness." It is the rest of the flow's stops learning the same five steps the DealsDesk stop now performs:

1. **Clerk sweep integration.** The hourly clerk sweep (`board/scatter_clerk.py`, watermark-driven) gains the loop at its digestion point: for each capture it cannot classify/file from existing knowledge, it runs KNOW (gateway stores via `what_do_we_know`, widened) → names the GAP explicitly in the capture's record → RESEARCH on the ladder (**Sonic** for routine digs — classification-grade fact-finding, price checks, page reads; **REAP 150B** for deep passes — multi-source synthesis, contradictions, the digs whose shelf life justifies the heavy engine) → STORE via the existing WF3 path with kind + valid-until, **plus** hit-signal accumulation (first source filed at once; the sweep keeps hunting agreeing sources on later passes and raises the signal on the stored filing) → ASK only through the 5-tries gate, queued as simple single questions for chat.
2. **Expired-intel rechecks join the same flow.** WF3 filings whose valid-until passes already resurface as recheck tasks; under the harness a recheck is just the flow running again on a known item (know → gap → research → store), with the new observation appended, never overwritten silently.
3. **Every desk stop consumes rulings as data.** The `find_blocking_ruling` pattern generalizes: before any desk acts on an item, it reads the rulings list for that item. New Brian rulings land in `altair.brian_decisions` once and take effect at every stop — no more dozen-surface cleanups like the P40 removal of 2026-11-09.
4. **Prices stay Postgres state.** Research that produces prices writes `price_intel` / `market_pricing` (stamped, shelf-lived, rechecked on expiry); documents quote dated snapshots only.
5. **The DealsDesk stop deepens.** Snapshot writer on a cadence for watched SKUs (the GPU watch's cards first), so trend series thicken beyond hand-seeded anchors; evaluator verdicts feed the desk's existing reporting; the sold-data contradiction gets settled by the accumulating stamped evidence (or escalated to Brian through the ask gate with the evidence attached).
6. **Question queue.** Unresolvable items accumulate logged attempts in their records; at 5 tries + ideas drying, the flow emits ONE simple question at a time into chat (Spencer/Altair surface), with the attempts and evidence attached. Brian's answer becomes a decision row — which every stop then reads. The flow closes its own loop.

## 9. File index

- Spec: `~/successbrian-os/docs/intel-harness-spec.md` (this file)
- Core: `~/successbrian-os/tools/intel_harness.py` (selftest: `python3 tools/intel_harness.py`)
- Writer: `/home/dealsdesk/scripts/market_snapshot_writer.py` (`--selftest`, `--model/--query/--marketplaces`)
- Evaluator: `/home/dealsdesk/scripts/candidate_evaluator.py` (`--selftest`, `--name/--buy/--qty`)
- Migration: `/home/dealsdesk/scripts/2026-11-09_market_pricing_intel_harness.sql`
- Atlas: node `sys:intel-harness` (bookkeeping — map, not territory, §2)
- Captures: #1098 (order), #1099–#1104 (rulings Q1–Q6), build record (this build's closing capture)

## 10. Management surface — the Spencer Review Toolkit

The flow is managed and guided day by day by the twice-daily Spencer
review passes (captures #1113/#1114/#1130), whose instruments live in
`tools/review/review.py` (window recorder, gauges panel, pass memory
with snapshot/delta, friction ledger, decisions queue, briefing
assembler; state in `successbrian_os.review_*`). Spec:
`docs/spencer-review-toolkit-spec.md`. The toolkit is bookkeeping —
map, not territory: it records and measures the flow; judgment lives
in the passes, rulings with Brian.

**Horizon layer (added 2026-11-09).** The same CLI also carries the
weekly instruments for the Saturday 04:00 weekend horizon check —
`tools/review/horizon.py`: pace (goals vs recorded actuals), trend,
aging, money, health-week (data only), content-chain, the agenda
table the daily passes read as data, build verification (did the
week's builds really improve things — verdicts persisted with their
evidence), and the coherence audit — the Deep Look at whether Atlas
is driving the goals and the system is working its highest
priorities first (goal linkage, Atlas flow, orphan machinery,
handoff stalls, priority discipline; census persisted weekly).
Spec: the horizon-layer section of
`docs/spencer-review-toolkit-spec.md`. The Intel Harness's verdicts
are among the builds build-verify re-checks each week
(BUILD_GAUGE_MAP watches the market-pricing gauge), so harness
improvements are proven on gauges, not asserted.
