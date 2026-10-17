# Visual interaction — research findings (2026-10-17)

Brian asked: what are the best ways our visual system can interact with
the ecosystem? Researched against his constraints: free-first, no build
step, own hardware, Python-first, server-rendered fragments.

## The headline: HTMX

The 2026 consensus for exactly this architecture (server-rendered admin
dashboards) is HTMX, not React. His fragment builders already return HTML;
HTMX is one 14KB JS include that lets buttons swap fragments in place —
no page reloads, no build step, no node_modules, no new paradigm. The
dash-actions API I built returns JSON today; the HTMX pattern is the same
endpoints returning HTML fragments instead. GitHub itself runs this
pattern (server-rendered + targeted JS islands).

Adopt: yes. It is the single highest-leverage change to how the dashboard
feels.

## Ranked interaction mechanisms

1. **HTMX fragment swaps** — buttons/links that replace part of the page
   with fresh server HTML. Covers 90% of what the dashboard needs: answer
   a question -> the row updates; complete a task -> it fades; change a
   filter -> the list re-renders. No client state to manage.
2. **Server-Sent Events** — one-way live stream from Flask (stdlib-friendly,
   no extra deps). For the ops console's live activity feed and TTS batch
   progress. Adopt for live feeds only.
3. **Command bar** — Mitcham's "Ask, make, or explore something" pattern. A
   natural-language bar on the dashboard that files a task/question for the
   agents. Highest-leverage single widget: Brian types what he wants, the
   system does it. Build after HTMX.
4. **Native HTML5 drag-drop** — for the blog builder board (kanban). No
   library needed; persist positions via dash-actions. Build with the board.
5. **n8n as the visual builder** — n8n is already running on k11 (since Sep
   27) with real workflows. Don't rebuild it: link it from the dashboard and
   let n8n webhooks be action backends where a visual workflow fits. Brian
   building automations visually = n8n's canvas, not a new thing.

## Explicitly not recommended

- **React/Vue SPA** — violates no-build-step; 2026 consensus says overkill
  for admin dashboards.
- **Activepieces / switching off n8n** — churn; n8n already runs.
- **Grafana** — metrics visualization, not actionable; heavy for what it gives.

## Interaction inventory (what becomes clickable, by system)

- **Inbox**: answer (built), snooze, dismiss reports.
- **Ops console**: run-now (built), pause/enable cron, acknowledge events.
- **Scheduler**: visual load map + one-click reschedule via the planner
  (the planner already computes the slot — the dashboard just exposes it).
- **PM**: complete/reassign tasks, slide dates through slide_gate(), create tasks.
- **Life**: mark done, mark/unmark hard dates.
- **Podcast**: approve topics, flag QA issues, trigger generation.
- **Intel**: flag stale facts, promote findings to the digest.
- **Agents**: file a nudge task to Altair, heartbeat detail view.

## Suggested build order

1. HTMX include + convert dash-actions endpoints to return fragments
   (answers/tasks/run-now become in-place swaps).
2. SSE live activity on the ops console.
3. Command bar.
4. Blog builder board with drag-drop.
5. Scheduler load map + one-click reschedule.
