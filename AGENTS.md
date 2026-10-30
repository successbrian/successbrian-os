# AGENTS.md — operating this repository

You are an agent arriving at **SuccessBrian OS**, Brian Lathe's
personal operating system. `README.md` is the human-facing pitch;
this file is the operator's map: what the pieces are, who owns what,
where things actually run, and how to avoid breaking the machine.

**The one law: Brian is the boss.** Code proposes — scores, bands,
recommendations, prepared drafts. Brian decides. Nothing here buys,
sends, publishes, deploys, or contacts anyone on the strength of a
plan or an approval of an idea; every outward action needs his
explicit go for that action. (Purpose layer: `board/CHARTER.md`.)

**The spine is deterministic.** The loops in this repo run on code,
database state, and scraping — no chat model decides anything inside
them. Models sit only at defined judgment points (the board's seats).

## The map: spine, desks, tail

**The spine** — the OS itself:

| Piece | Home | What it is |
|---|---|---|
| Atlas | `tools/atlas/` | The knowledge graph (nodes/edges), workspace registry + placement, queue watch, workload gates (`atlas.workload_gates_v`) |
| Board | `board/` | The judgment layer: panel harness, clerk + scatter clerk, minutes, configs |
| PM plane | `tools/pm/` | Projects, steps, the decision stream, QA checks, the chat brief Altair reads |
| ERP seam | `tools/erp/` | The contract between the core and DealsDesk (see Ownership) |
| Capacity | `tools/capacity/` | Demand meters: model demand, site-fleet demand, capacity reconciliation |
| Heartbeat & watch | `tools/altair_heartbeat_v4pro.py`, `tools/governor` pieces, `plugins/needs-watch/` | Pulses, handoffs, Lyra's watching — the anti-silent-death layer |

**The desks** — Brian's applications on the spine, separately owned.
They are not "the OS," and the OS is mostly a bridge without them:

- **DealsDesk** — sourcing and build planning. Code:
  `tools/dealsdesk/` (canonical) deployed to `/home/dealsdesk/scripts/`.
  Tables: everything under the `dealsdesk.*` schema.
- **CampaignsDesk** — the campaign/site-fleet desk. Separate repo at
  `/home/successbrian/campaignsdesk/`; its registry tables live in
  `successbrian_os.marketing_*`.

**The tail** — ~35 venture tool families under `tools/` (audience,
trading intel, travel, employment, ventures, focus, …). They use the
spine; they are not the spine. `second-brain-for-agents/` is a
packaged sub-project; `specs/` holds design documents.

## Ownership — the contract that keeps the seam clean

- **SuccessBrian OS owns:** projects/tasks (`public.projects`,
  `public.sbostasks`), the need handoff
  (`successbrian_os.sbos_need_requests`), Atlas, the PM plane.
- **DealsDesk owns:** `dealsdesk.ecosystem_needs`,
  `dealsdesk.solution_options`, `dealsdesk.builds` and everything
  else under `dealsdesk.*`. Its scripts are the only writers of
  those tables.
- **Neither side writes the other's tables.** Cross-side flow goes
  through the handoff table and each side's own scripts.
  `tools/erp/README.md` is the full contract — read it before
  touching the loop.
- **Sanctioned homes (R32):** documents/knowledge → AnythingLLM;
  state → PostgreSQL; automation → n8n; logic → real code in this
  repo. A loose file or one-off script is a migration candidate,
  never a destination.

## Where it actually runs

- Host: **k11-alpha**. Repo: `/home/successbrian/successbrian-os`.
  Database: PostgreSQL `ecosystem_central` (schemas
  `successbrian_os`, `atlas`, `altair`, `dealsdesk`, and the legacy
  `public` the OS grew up in).
- Canonical code lives here, but some families run from **deployed
  copies**: the ERP/DealsDesk scripts run from
  `/home/dealsdesk/scripts/` on cron. Edit canonical, then sync the
  deployed copy, or your change does nothing. (Verified in sync
  2026-10-26.)
- Schedules live in the owning system: the successbrian crontab
  (chat brief every 5 min; the ERP chain staggered 05:50–07:20;
  board Saturday 02:30) and DealsDesk's own systemd timers. Never
  park an ecosystem schedule in an outside scheduler.

## Read in this order

0. `tools/guardrails/state/AGENT_BRIEF.md` — the rendered agent
   context pack (agent_brief.py, every 15 min): operating model,
   live capacity, open gates, and Brian's newest decisions.
   Read this FIRST, before everything below.
1. This file.
2. `docs/AGENT_CONTRACT.md` — how agents behave here.
3. `board/CHARTER.md` — Brian first, then the ecosystem.
4. `docs/PM-MASTER-CONTRACT.md` — the project/decision plane.
5. `tools/erp/README.md` — the core↔desk contract.
6. `docs/capacity-loop-contract.md` — demand → capacity.
7. `docs/CODE-STANDARDS.md` — the house style (every tool carries
   PURPOSE / WHY / CALLED BY docstrings; keep it that way).

## Verify before you trust

Docs and `schema.sql` files describe the **intended** system. The
**live database is the truth**, and the two drift silently. Before
believing either, run the selftests:

- `python3 tools/atlas/workload_gates.py selftest`
- `python3 tools/erp/build_loop.py selftest`
- `python3 tools/capacity/site_demand.py selftest`
- `python3 tools/pm/project_qa.py run-due` (the standing QA net)

If code and live state disagree, believe live state, repair toward
the documented intent, and record the repair.

## Key commands

- `tools/pm/chat_brief.py --print` — what Altair sees right now.
- `tools/atlas/workload_gates.py summary|blocked|show <workload>` —
  what is gated, by what, and why.
- `tools/atlas/queue_watch.py` — pending gates and queue health.
- `tools/erp/build_loop.py status` — the SBOS↔DealsDesk loop:
  needs raised, plans published, joint priorities, gates set.
- `tools/pm/project_qa.py list` — registered projects and QA state.
- `tools/atlas/allm_workspaces.py placement` — where every body
  lives (R14: the core determines placement; desks build to it).

## Landmines — learned 2026-10-26, do not reintroduce

- `sbos_need_requests.need_id` existed in `tools/erp/schema.sql`
  but not in the live table for weeks: intake could not record
  promotions, duplicate needs accumulated, and
  `need_status_sync.py` failed daily in a log nobody read. If a
  loop "should" work, prove each leg — a schedule is not proof.
- `dealsdesk.builds` lifecycle: the transition trigger walks
  planning → components_priced → parts_ordered → parts_received →
  building → testing → deployed → retired, **one step at a time**,
  and the status CHECK must contain every chain state
  (parts_received/testing were missing; builds were stuck at
  parts_ordered forever).
- `needs_intake.py`'s field parser crashed on a trailing empty
  field (a need with NULL max_cost). Parsers must tolerate
  trailing empties.
- `.bak` files: 82 of them were archived out of this tree on
  2026-10-26 to `/home/successbrian/repo-archive/2026-10-26-bak/`.
  Do not leave new ones — that is what git is for.

## House rules for changes

- Register real projects in the PM plane
  (`tools/pm/project_qa.py register`) with QA checks. A change
  without a check is a hope.
- File discoveries — breakages, contradictions, silently dead
  machinery — into the Intel Bridge (`atlas.scattered_captures`),
  the ecosystem's work queue. Never leave them only in a chat.
- Commit in this repo; state plainly in your report if you did
  not push.
