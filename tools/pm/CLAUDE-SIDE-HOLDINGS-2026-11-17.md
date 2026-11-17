# Muse-Side Holdings — Inventory & Move Plan

Brian's ruling (2026-11-17): standing machinery and work products
live in the ecosystem (SuccessBrian OS), not in Muse; Muse-side is
interim-only, and labeled. Census row 22 carries the ruling. This is
the inventory he ordered the same night: everything still living on
the Muse side, classified, with a move plan for each.

Method: full Muse scheduler list (incl. disabled) + hooks list
(none exist) + operative state files, cross-checked against the
SBOS timekeeper's muse-cron rows. The cross-check itself found
registry drift, fixed on sight (see E).

## A. MOVE — pure ecosystem machinery; the alpha home is obvious

**Status 2026-11-17 ~04:10 (Brian: "start the move"):** A1 MOVED —
alpha crontab Mon 07:41, tool verified, Muse cron retired. A2
MOVED — `tools/sbos_public_push.py` built (selftest OK), first run
pushed 13 commits with a clean scan, heartbeat 'sbos-public-push'
in Lyra's table, QA 736 probes it, alpha crontab daily 04:41,
Muse cron retired. A3 MOVED — alpha crontab every 10m (stopgap;
NOTE-013 remains the real fix), Muse cron retired. All three
timekeeper rows now read alpha-crontab. A4 (the keeper) still
awaits Brian's surface choice.

1. **gamma-ping-weekly-rollup** (Muse cron, Mondays). The tool
   (`tools/gamma_ping_rollup.py`) already lives on alpha; the Muse
   cron only ssh-invokes it. → Alpha crontab (weekly), retire the
   Muse cron, timekeeper row to alpha-crontab.
2. **sbos-daily-public-push** (Muse cron, daily 04:41). Entirely
   alpha-side git work; the safety scan is deterministic patterns.
   → Alpha script + crontab; a held push files an Intel Bridge
   capture and a Lyra heartbeat gap instead of a chat report (the
   census-sweep pattern). Was also missing from the timekeeper —
   registered 2026-11-17 (see E).
3. **gamma-lyra-bridge** (Muse cron, every 10m). Runs an alpha
   script via ssh. → Alpha crontab immediately as a stopgap; the
   real fix is still NOTE-013 (gamma writes its heartbeat directly),
   after which both the bridge and its cron die.
4. **gamma-queue-keeper** (Muse cron, every 30m). The feeding is
   pure alpha DB work (read raw captures, insert bus events). Only
   its report lines are chat-shaped. → Keeper script on alpha +
   crontab; the report becomes a capture the clerk surfaces, or a
   thin delivery-only reader — Brian's call on the surface, since
   the lines currently land in his chat. The move also retires the
   per-run dedup workaround (`~/workspace/gamma-queue-keeper-insert.sql`)
   and bakes the proper dedup (match on `payload->>'prompt'`) into
   the alpha script — the cron-body fix Brian was asked about
   2026-11-15 becomes moot when the body moves.

## B. INTERIM-CAPABILITY — needs a Muse-only capability today

5. **dealsdesk-intel-feed-daily** (daily 08:41). Its eyes are the
   Muse browser + Facebook connector; alpha has no Marketplace
   access. All outputs already land in alpha tables (sightings,
   people.companies). Stays until alpha gains browser eyes; labeled
   interim. Census row 8's probe (QA 627) already watches its output.
6. **Connector-driven agent work** — friend-vetting-daily-10,
   ig-follower-enrich-daily, lead-intel-daily-plan,
   weekly-reach-snapshot, tier3-ads-feedback-weekly,
   tier3-review-poll-weekly. FB/IG/Threads connector work owned by
   goals (CampaignsDesk); agent work by design, outputs land in
   ecosystem stores. Not SBOS machinery; no move planned.

## C. INTERIM-DELIVERY / AGENT JUDGMENT — the agent layer's ruled job

7. **spencer-meghan-direct-line-watch** (every 15m). Surfaces gamma
   replies in chat. Its watermark file
   (`~/workspace/builds/spencer-direct-line/watermark.txt`) is
   operative Muse-side state. Interim: value is immediacy in chat;
   a future SBOS notifier door could thin it to nothing.
8. **Reminder bells** — alpha-sending-campaigns-talk-dec-2,
   reminder-va-video-visit-2026-12-09,
   reminder-eye-exam-bus-call-2027-03-23,
   reminder-eye-exam-2027-03-24, places-map-dig-start-dec-1. The
   SBOS life calendar holds the items; Muse rings the bell because
   SBOS has no chat delivery. Interim until it does. (Registered in
   the timekeeper 2026-11-17 — see E.)
9. **spencer-20min-cycle + ecosystem reviews (am/pm/weekend)**.
   Agent judgment loops: diagnose, repair, build, oversee. The
   judgment stays agent-side by Brian's design (deciders are
   agents; execution migrates, oversight remains). Their machinery
   already lives in SBOS (spencer_cycle.py reads alpha,
   heartbeat_builder.py, improvement_log). REAL holding inside
   this item: the operative planning documents —
   `~/workspace/builds/sbos-assembly/` (BUILD_QUEUE.md, PLAN.md,
   HEARTBEAT_BUILDER.md, USERS_AND_VERIFICATION.md,
   INTEL_DEPTHS.md) — are read by the cycle every 20 minutes but
   live in the Muse workspace. → Move the sbos-assembly docs
   into the successbrian-os repo; the cycle reads them from alpha.
10. **board-of-directors-saturday** — an agent session (advisory
    body), goal-owned. Not machinery; stays.
11. **local-brain-refresh** (every 8h) — the agent's own memory
    maintenance, fed from alpha stores. Agent-side by nature.

## D. DORMANT — disabled definitions (cleanup candidates)

ai-bubble-weekly-check, aptean-unite-2027-watch,
clerk-box-price-watch-2026, daily-flow-capture,
amd-stock-daily-watch, intc-stock-daily-watch,
duol-bottom-watch-2026, kalshi-earnings-mentions-weekly,
kalshi-weather-dataset-daily, kalshi-weather-midday-snapshot,
altair-improve-stop-20261026 (a past runonce). None run. Their
definitions and timekeeper rows linger on the Muse side;
removal is Brian's call, listed here so the pile is visible.

## E. Registry drift — found by this inventory, fixed on sight

- sbos-daily-public-push: live but had NO timekeeper row →
  registered.
- Five live runonce bells unregistered → registered.
- duol-bottom-watch-2026, intc-stock-daily-watch: timekeeper said
  active, scheduler says disabled → rows corrected to paused.

## F. Operative Muse-side state files (small, real)

- `~/workspace/builds/spencer-direct-line/watermark.txt` (item 7).
- `~/workspace/gamma-queue-keeper-insert.sql` (dies with item 4).
- `~/workspace/builds/sbos-assembly/*` (item 9 — the one that matters).
- Agent memory (MEMORY.md, daily logs): the agent's own memory.
  Rulings' operative copies belong in the census / decisions store;
  the census now covers the standing set (22 rows).

## G. Out of scope

Muse platform system jobs (feed-pulse ×24, deterministic-doctor,
profile-image, heartbeat) are Muse's own machinery, not Brian's
ecosystem. Hooks: none exist.

## Order of work (when Brian says go)

A1 → A2 → A3 are one-pattern moves (alpha crontab + retire Muse
cron), each verifiable the same day. A4 is the biggest (keeper) and
carries a surface decision for Brian. C9's doc move is quick and
removes the last operative paper from the Muse workspace.
