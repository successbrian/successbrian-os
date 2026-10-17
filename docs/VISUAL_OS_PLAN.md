# Visual OS — plan

Brian 2026-10-17: "visual things to show processes is nice. able to interact
with my ecosystem through a visual interface. able to visually build the
100 blogs."

The dashboard (Node Zero, /successbrian-os/) grows into the visual OS.
No new system — this extends the existing fragment architecture, per the
integration law.

## What exists today

- Fragments built on k11 (`tools/dashboard/build_*.py`, psycopg2, inline
  dark-theme CSS) -> `/home/successbrian/dashboard-fragments/` -> scp to
  Node Zero `/var/www/fleet-builds/*.html`, assembled by `index.html`
  via `fetch()`. Per-fragment cron deploys (5:15, 5:45, 11/17:15...).
- Live APIs already on Node Zero: Flask in `/root/dash/` (api_server.py,
  upload_api.py), podcast-api, videos api — all query k11 Postgres over
  tailnet (100.118.53.47). nginx proxies `/successbrian-os/<name>/`.
- The inbox fragment already renders answer buttons calling
  `answerQuestion()` — but that JS function exists nowhere. Dead buttons.
  Phase 2 fixes this.

## Phase 1 — Ops console (this build)

New fragment `ops-console.html`, built on k11, static, deployed like the
others. Sections:

1. **Cron fleet** — from `cron_registry` (81 jobs): count by area, by
   weight, peak-load minutes from the scheduler audit. Per-job: schedule,
   purpose, enriched flag.
2. **Worker heartbeats** — from `worker_heartbeats`: who is alive, last
   beat, last status/error. Honest gap: only 2 workers report today
   (lyra_watchdog, ingest_router). The console shows "N silent" to drive
   adoption — heartbeat coverage is the follow-up project.
3. **Live activity** — recent `ecosystem_events` (last 20), unacknowledged
   first.
4. **Pipelines** — life_ops: hard dates in next 14 days + overdue task
   count; podcast: next episode event + stage (from event_tasks).
5. **Scheduler health** — audit summary: overloaded minutes, unregistered
   jobs, sequence violations (from `scheduler.py --audit`).

Cron run history: `cron_runs` exists but has 0 rows — nothing writes it.
v1 shows schedule + heartbeat instead of run history and names the gap.
A lightweight run-logger (wrapper that logs start/end per cron) is a
follow-up, not this phase.

## Phase 2 — Action API (next)

Extend the proven Node Zero Flask pattern with `dash-actions`:

- `POST /api/questions/answer` {id, answer} — fixes the dead inbox buttons
- `POST /api/tasks/done` {id} — complete PM/life_ops tasks from dashboard
- `POST /api/run` {job} — trigger a registered job on demand (k11 exec)
- `GET /api/ops/summary` — live ops numbers for the console (replaces some
  static content later)

Auth: same-network only (nginx allow tailnet/localhost) + a shared token
in the fragment JS. No new credentials hardcoded — read from env.

## Phase 3 — Blog builder board (after)

Visual pipeline for the 100-blog goal: candidate -> validated (50K/mo
filter) -> scaffolding -> live. Needs: blog candidate data model (Altair's
research output location TBD — check tools/audience + goal workspace),
per-blog card (niche, status, traffic, revenue). Data model first, then
fragment.

## Phase 4 — Interactivity everywhere

Wire every fragment's buttons to the action API. Inbox answers, PM task
toggles, podcast QA flags — all clickable.

## Non-goals

- No JS framework. Server-rendered fragments + tiny fetch() calls, same as
  today. Free-first: no build step, no npm.
- No real-time websockets in v1. Fragments rebuild on cron; the action API
  returns fresh state on demand.
- The console reports what is silent/missing (dead buttons, empty
  cron_runs, thin heartbeats) — it does not fake coverage.
