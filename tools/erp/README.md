# ERP integration — deterministic loop, no AI inference

## PURPOSE
Wire successbrian-os project management to DealsDesk sourcing as executable code:
task -> need -> sourced options -> budget gate -> task. Database + PicClick
scraping + Python. Nothing here asks a model for judgment.

## WHY
Before this, the loop ran by hand: Spencer relayed sourcing changes to DealsDesk
through bridge rows one at a time. That doesn't scale and it depends on chat.
The ERP replaces the relay with code both sides own.

## OWNERSHIP (the boundary Brian asked for)
- **successbrian-os owns:** projects/tasks (`public.projects`, `public.sbostasks`),
  the staging table (`successbrian_os.sbos_need_requests`), and the two scripts
  that touch them (`need_from_task.py`, `need_status_sync.py`).
- **DealsDesk owns:** `dealsdesk.ecosystem_needs`, `dealsdesk.solution_options`,
  sourcing, budget. Its scripts (`needs_intake.py`, `sourcing_worker.py`) are the
  only writers of those tables.
- **The contract:** `sbos_need_requests` is the handoff. successbrian-os writes
  `new`; DealsDesk promotes to `promoted` and writes the need; status flows back
  through the same table. Neither side writes the other's tables.

## THE LOOP
1. A task carries `source_ref = {"hardware_need": {"item", "specs", "qty",
   "max_cost"}}`. Set it when the task is created (by a human or by task-creation
   code — still deterministic).
2. `need_from_task.py` (cron): stages new needs. Idempotent via UNIQUE(task_id, item).
3. `needs_intake.py` (cron, 15 min): promotes staged rows into
   `dealsdesk.ecosystem_needs` (source=`sbos_task:<id>`). Marks rows promoted.
4. `sourcing_worker.py` (cron, hourly max): for each open task-raised need —
   PicClick scrape -> seller blocklist filter -> rack scorer (server needs) ->
   writes `dealsdesk.solution_options`, marks need `planned`.
5. Budget gate (inside sourcing_worker): `recommended` only if `est_cost` is
   within the task's `max_cost` (or no cap). Cheapest recommended option wins;
   the rest stay `candidate`. **Never buys anything.**
6. `need_status_sync.py` (cron): satisfied needs -> request satisfied; all of a
   task's requests satisfied -> task done. Never moves a task backwards.

## CALENDAR (extension point, not yet wired)
When an option is marked `chosen`, a `life_calendar` entry should schedule
Brian's hands-on build slot. The schema wasn't verified during this build;
wire it when the calendar contract is confirmed.

## RESEARCH (extension point)
Altair's research digests already land in `altair.research_digest`. The
`sourcing_worker` query builder can append digest-derived spec refinements per
need later — deterministic lookup, still no inference in the loop.

## DEPLOY
Canonical: `successbrian-os/tools/erp/`, `successbrian-os/tools/dealsdesk/`.
Deployed: `/home/dealsdesk/scripts/` on k11-alpha (same pattern as budget_guard).
DDL: `tools/erp/schema.sql` (run once, needs CREATE on successbrian_os).
Suggested timers: need_from_task hourly, needs_intake every 15 min,
sourcing_worker hourly, need_status_sync every 30 min.

## PROVENANCE
Built 2026-10-08 per Brian: "code this integration so it's not AI inference
that solves the logic, it's actual database/scraping (picclick)/python."
