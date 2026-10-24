# PM Master Contract

**Ratified by Brian 2026-10-15.** successbrian-os's project management system is the
master event/project/goals/tasks system for the entire ecosystem. Every plugin and
MCP reads from it and feeds into it.

## The law

1. **successbrian-os PM is the master source of record** for: events, projects,
   goals, tasks, gates, slideable dates, and project budgets. No plugin keeps its
   own competing master for any of these.
2. **Plugins and MCPs read from the PM system.** Plans, statuses, budgets, and
   gates are read from `successbrian_os.*` tables/views, never from a plugin's
   private copy.
3. **Plugins and MCPs feed into the PM system** by writing events to
   `successbrian_os.ecosystem_events` — never by writing directly into another
   plugin's tables, and never by inventing a parallel event log.
4. **DealsDesk never gets gates.** DealsDesk tracks deals, builds, and sourcing.
   Its events feed into successbrian-os; gates, slideable dates, and budget
   masters live here. Direction is DealsDesk → successbrian-os, never the reverse.
5. **The dashboard shows what the PM system sees.** Dashboard fragments read from
   PM tables and views. If it's not in the PM system, the dashboard doesn't show
   it; if the PM system knows it, the dashboard shows it.

## The tables

| Table / view | Purpose | Who writes |
|---|---|---|
| `successbrian_os.ecosystem_events` | Unified feed-in: every plugin/MCP event lands here | All plugins, MCPs, pm-system |
| `successbrian_os.project_gates` | Gated checkpoints per project | PM system (crew); plugins read |
| `successbrian_os.project_budgets` | Master project budgets (multiple at once) | PM system; spend reported via events |
| `successbrian_os.v_project_budget_status` | Budget read-out (remaining, pct used) | View — dashboard reads this |
| `successbrian_os.sbos_projects` | Projects and phases | PM system |
| `successbrian_os.tasks` | Task queue | PM system, workers |

## Feeding an event

```sql
INSERT INTO successbrian_os.ecosystem_events
  (event_type, source_plugin, project_ref, title, detail)
VALUES
  ('deal_found', 'dealsdesk', 'October 2026 hardware',
   'R630 candidate at $255', 'Hastings MN, dual E5-2650 v4, 16GB, 1TB SAS');
```

- `event_type`: short snake_case noun (`gate_slid`, `deal_found`, `build_update`,
  `budget_spent`, `plugin_note`).
- `source_plugin`: your plugin's name (`dealsdesk`, `vera`, `mcp:ecosystem_data`…).
- `project_ref`: which project or budget this relates to (free text key).
- Keep `title` human-readable — it shows on the dashboard.

## Sliding a gate

Gates slide; dates are not carved in stone. When a predecessor slips, dependents
follow automatically:

```sql
SELECT * FROM successbrian_os.slide_gate('gate_key_here', '2026-12-01');
```

- Sets the gate's `target_date` and pushes every dependent gate
  (`depends_on_gate_key`) forward by the same delta, recursively.
- Logs a `gate_slid` event into `ecosystem_events` automatically.
- Wire predecessors with `depends_on_gate_key` on `project_gates`.

## Budgets

- Masters live in `successbrian_os.project_budgets`. `is_master` is true; mirrors
  elsewhere must be labeled as mirrors, never masters.
- Report spend by updating `spent` on the budget row and/or writing a
  `budget_spent` event. The dashboard reads `v_project_budget_status`.
- Multiple budgets at once is the norm — one row per project envelope.

## What this contract is not

- It does not grant plugins write access to each other's private tables.
- It does not replace per-plugin schemas — it only governs the shared
  event/project/goals/tasks surface.
- Private IP (DealsDesk pricing, people_unified, offer pipelines) never crosses
  an MCP boundary; the MCP portability rule still applies.
