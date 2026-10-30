# Board of Directors Harness

A generic morning board session any entrepreneur can run with their own
C-level seats — using Brian's harness + system.

## The idea in one paragraph

Every morning, ephemeral directors wearing C-level title hats meet for one
session: they read a brief of yesterday's state, then **loop through the
entire agenda queue** — every queued item gets exactly one call from its
routed seat — then dissolve. (Brian switched the board off the old
each-seat-picks-2–3-calls shape on 2026-10-21: anything that didn't make a
seat's top 2–3 was silently unruled.) A chair applies the **90% gate**
(board proposes, chair disposes), binding decisions are **recorded**, the
recording is **verified** by querying back, and minutes are written — with
the queue's carry-over count stated, never hidden. The harness is generic;
the seats, briefs, agenda source, and sink are the bent config.

## Why this exists (the failure it answers)

Brian's September 2026 board ran 5x daily and *completed* — while 83% of
sessions produced empty summaries, 440/441 tasks sat pending, and zero
followups resolved. **Board active ≠ board producing.** The decision pipeline
was decorative: schema with no execution engine. This harness's non-negotiable
guards:

1. **Empty output is a flagged failure**, never silent acceptance.
2. **Record is always followed by verify** (query the sink back, count; a
   mismatch is a pipeline failure, said out loud).
3. **The gate holds** anything below 90% as a recommendation for the human —
   never auto-executed, never dropped.

## Layout

```
board/
  harness/            # GENERIC — never hardcode one entrepreneur's domains here
    seats.py          # Seat dataclass + YAML loading (title/domain/mandate/wave/...)
    worker.py         # Stateless model worker (OpenAI-compatible endpoint, retry-once, fluff detection)
    agenda.py         # The agenda queue (source + routing + processed ledger)
    brief.py          # BriefBuilder + pluggable state pullers (NOT INSTRUMENTED rule)
    gate.py           # The 90% gate (deterministic heuristic scoring)
    sinks.py          # DecisionSink interface; SecondBrainSink + JsonlSink
    session.py        # BoardSession orchestration + minutes
  config/
    brian.yaml        # BENT — Brian's 14-seat instance (Morpheus via kssh, second_brain sink)
    seats.example.yaml# TEMPLATE — copy and bend for a new entrepreneur
  specs/board-harness.md
  test_dryrun.py      # Real 2-seat dry-run against the model (no mocks)
```

## Quick start (new entrepreneur)

1. Copy `config/seats.example.yaml` → `config/<you>.yaml`; follow the TODOs.
2. Wire brief pullers in `harness/brief.py` (or leave NOT INSTRUMENTED — the
   board flags the gap instead of deliberating on fiction).
3. `python3 board/test_dryrun.py --config board/config/<you>.yaml`
4. Schedule one early-morning cron with a hard deadline before whatever
   consumes the decisions.

## Brian's instance

- 14 seats (source of truth: the `successbrian_os.board_seats` table in
  PostgreSQL — this list mirrors it as of 2026-10-25): MLM, Affiliate
  Marketing, Marketing (systeme.io), People Enrichment (leads), Blog Content
  (Shakespeare's direction, video, hiro.fm), Trading Desk (strategy only,
  never signals), Hardware Flipping (public pricing only), Ecosystem Build,
  Audience (social/discovery, not email or funnels), Campaign (time-boxed
  pushes only), Compliance (offer rulebooks, MLM gates, health-claim
  guardrails), Knowledge (second brain, intake, competitive intel),
  Relationship (relationship health, key people — not leads), and the CFO
  as wave-2 closer consolidating the money picture.
- Model: Morpheus (14B) at `127.0.0.1:11437` on k11-alpha, reached via kssh.
- Agenda: **Atlas open gates + tasks** (atlas.nodes: pending gates, then
  open/queued atlas_tasks, oldest first). An item leaves the queue only
  when the board has ruled on it (ledger in the minutes dir); at the
  deadline, unprocessed items carry over and lead the next session.
- Sink: PostgreSQL `second_brain`; the 04:42 150B context bundle refresh
  picks the decisions up, feeding the 5:30 AM bus briefing (Mon/Tue).
- Session: 02:30 Mon–Fri (AGENT_CONTRACT rule 14 quiet window: last AI
  work starts 02:00, complete by 02:30; the board sits alone) → agenda
  deadline 04:30 (two-hour cap), ahead of the 04:42 context-bundle refresh.
- After the board: 04:30-05:00 decision processing - the 04:42 bundle
  refresh carries the session's decisions into the ecosystem's working
  context; the full AI cadence resumes at 05:00.
