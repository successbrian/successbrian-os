# Broken and Missing — the 24/7 autonomy audit

Audited live on k11-alpha, 2026-10-23 ~00:45 CDT, at
Brian's order: "find all the broken and non working
things that need to be built to make this actually work
agentically and autonomously 24/7."

Design law behind the audit (Brian, same message): he is
forgetful and scattered, likely severe ADHD, "half awake
most of the time" — so THE MACHINE CARRIES THE
REMEMBERING. A system that produces briefings nobody is
guaranteed to see, or holds deadlines only in chats and
heads, fails that law even when every process is running.

Every build item below is filed as an Atlas task
(found_by=broken-audit) so the machine tracks its own
defect list.

## P0 — autonomy blockers (24/7 cannot be trusted yet)

1. NO BACKUPS OF THE RECORD. No pg_dump in crontab, no
   dump in ~/backups (only code .bak files). One disk
   death takes ecosystem_central (decisions, calendar,
   Atlas, 214M people rows) and the AnythingLLM storage
   with it. → task:broken-audit:backup-the-record
2. POSTGRES TAILNET BIND RACE. The unit declares
   After=tailscaled, but on 2026-10-22 Postgres bound
   before the tailnet address existed and never retried
   — the fleet lost its database until a manual restart.
   Ordering is not readiness. → task:broken-audit:pg-tailnet-bind-race
3. GAMMA PATH DARK + RESCUE STALLED. Zero live
   gamma_fleet connections at sweep time; the 12 session
   archives, both database archives, and the config
   bundle are still on gamma; the gamma_fleet credential
   is still unrotated (42 files + a gamma.db row).
   → task:broken-audit:gamma-transfer-finish,
     task:broken-audit:gamma-fleet-rotation
4. NO DELIVERY CHANNEL TO BRIAN. ~90 cron entries
   produce briefings, watches, and digests as files and
   logs (altair_briefing, gap_watch, life_ops,
   personal_os_watch, digest.py). Nothing is verified to
   REACH him — no push, no composed morning brief in one
   place he actually looks. → task:broken-audit:delivery-channel
5. MEGHAN CANNOT THINK. Her engine (Prometheus /
   Gemma 4 26B) is not served — no endpoint exists. The
   CEO layer of the fleet is headless.
   → task:broken-audit:meghan-engine

## P1 — the remembering layer (Brian's direct ask)

6. GOAL DEADLINES LIVED NOWHERE. His calendar holds
   shifts, not goals; the launches had no Atlas nodes
   and no dates. BUILT TONIGHT: deadline_radar.py
   (calendar + Medium slot + standing goal deadlines,
   nightly 04:35) and the two launch nodes + hosting
   need in Atlas. STILL MISSING: dates for the launches
   (invisible until set) and deadlines-as-data.
   → task:broken-audit:goal-deadlines-as-data
7. MEDIUM SLOT STALLED. Week 2026-W43 closes Sunday
   2026-10-25; the slot table is empty, all 4 register
   ideas sit at stage 'idea', idea #9 has waited since
   Oct 22. The radar now flags it weekly; assignment is
   still Brian's tap.
8. KNOWLEDGE BRIDGE DEAD SINCE 2026-08-28. 1,611 rows
   frozen; Altair's bridge into AnythingLLM has been
   silent two months. → task:broken-audit:knowledge-bridge
9. IDEA FLYWHEEL HALF-WIRED. campaignsdesk.signals has
   only ever received hand-seeded rows; no producer
   writes to it; idea_scout generate has no cron.
   → task:broken-audit:idea-producers
10. PRODUCERS NOT ROUTED. decision_sync embeds only
    into home-lab; the determine() routing layer (R27)
    is not wired into any producer.
    → task:broken-audit:producer-routing
11. CRONTAB CARRIES PASSWORDS. Multiple cron lines hold
    the Postgres password in plaintext (also the
    DealsDesk scrapers). → task:broken-audit:crontab-passwords

## P2 — capability gaps

12. TRAVEL LAPTOPS NEVER ENROLLED. road-vostro and
    road-7420 are not powered on or on the tailnet;
    the Chicago acceptance test (trip: 2026-11-27, 35
    days out) cannot have run.
    → task:broken-audit:travel-laptops
13. ATLAS HAS BLANK NODES. ~12 projects carry empty
    summaries (mavity, bookkeeping-wedge, group-buying,
    smb-transformation-agency, vertical-crm-suite,
    timeblock-engine, per-user-db, shared-brain,
    plugin-ecosystem, trafficstreemz-plugin, tiktok,
    audience-growth-engine) — scanners cannot judge
    what they cannot read.
    → task:broken-audit:atlas-summaries
14. HIRO.FM ACCOUNT BLOCKED. Sign-in rejects the saved
    password; a reset is the unblock. Parked by Brian
    2026-10-22 — listed so it is not forgotten.
15. UNVERIFIED (not claimed broken): n8n workflow
    executions; keystone_digest and cross-system-
    broadcaster picking up the AnythingLLM key from
    successbrian-os/.env; the Sunday decision_sync run
    (first post-fix Sunday is 2026-10-25/26).

## Verified WORKING tonight (for the record)

- Council cron: INSTALLED and logging (00:41) — this
  corrects the 2026-10-20 record that said not
  installed.
- Altair heartbeat v4pro logging (00:35); Lyra watchdog
  every 10 min (00:40); system_health_checks fresh
  (00:40); sbos-watchdog timer cycling; ingest router
  running; anythingllm cleanup crons present; SSB
  triage cron (04:30) and deadline radar (04:35)
  installed tonight; friend-vetting daily cron enabled
  on the Muse side.

## The build order the audit implies

1. Backups (P0-1) — before anything else is trusted.
2. Delivery channel + morning brief (P0-4) — the
   remembering law is meaningless without reach.
3. Bind-race fix (P0-2) + Meghan's engine (P0-5).
4. Gamma transfer + rotation (P0-3).
5. Dates for the invisible goals (P1-6), then the P1
   wiring (bridge, producers, routing).
