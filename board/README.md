# Board of Directors Harness

A generic morning board session any entrepreneur can run with their own
C-level seats — using Brian's harness + system.

## The idea in one paragraph

Every morning, ephemeral directors wearing C-level title hats meet for one
session: they read a brief of yesterday's state, make 2–3 big-picture calls
each, then dissolve. A chair applies the **90% gate** (board proposes, chair
disposes), binding decisions are **recorded**, the recording is **verified**
by querying back, and minutes are written. The harness is generic; the seats,
briefs, and sink are the bent config.

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
    brief.py          # BriefBuilder + pluggable state pullers (NOT INSTRUMENTED rule)
    gate.py           # The 90% gate (deterministic heuristic scoring)
    sinks.py          # DecisionSink interface; SecondBrainSink + JsonlSink
    session.py        # BoardSession orchestration + minutes
  config/
    brian.yaml        # BENT — Brian's 9-seat instance (Morpheus via kssh, second_brain sink)
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

- 9 seats: MLM, Affiliate Marketing, Marketing (systeme.io), People
  Enrichment (leads), Blog Content (Shakespeare's direction, video, hiro.fm),
  Trading Desk (strategy only, never signals), Hardware Flipping (public
  pricing only), Ecosystem Build, and the CFO as wave-2 closer consolidating
  the money picture.
- Model: Morpheus (14B) at `127.0.0.1:11437` on k11-alpha, reached via kssh.
- Sink: PostgreSQL `second_brain`; the 4:40 AM 150B context bundle refresh
  picks the decisions up, feeding the 5:25 AM bus briefing.
- Session: 3:30 AM cron → 4:30 hard wrap.
