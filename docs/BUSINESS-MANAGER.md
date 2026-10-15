# Business Manager — Data Model

The business management core of SuccessBrian OS. This is the schema that lets a home-based entrepreneur plan, organize, and manage multiple businesses from one PostgreSQL database.

## The graph

It's a graph, not a tree. The core insight: **income streams flow through marketing channels (or standalone), goals set targets for streams, projects do the work, decisions record the calls.** Everything links to everything.

```
                    ┌─────────────┐
                    │  businesses │
                    └──────┬──────┘
                           │ 1:1 (optional)
                    ┌──────▼──────┐     ┌───────────────────────┐
                    │income_streams│◄────│income_stream_targets  │
                    └──────┬──────┘     └───────────────────────┘
                           │ skins TEXT[] (many-to-many via array)
                           │ e.g. {'TrafficStreemz','CryptoStreemz'} or '{}'
                    ┌──────▼──────┐     ┌──────────────┐
                    │  sbos_goals │◄────│sbos_projects │
                    └─────────────┘     └──────┬───────┘
                                               │ 1:N
                                        ┌──────▼───────┐
                                        │    tasks     │
                                        └──────────────┘

  decisions ──► decision_project_links ──► sbos_projects
  life_calendar ──► sbos_projects (optional)
  project_gates ──► sbos_projects (gates)
  life_plan_items (standalone milestones)
```

## Tables

### `successbrian_os.businesses`
Your ventures. One row per business.
| Column | Type | Notes |
|--------|------|-------|
| business_name | text | Unique. e.g. "Wellness MLM", "Cloud Backup" |
| skin | text | Marketing channel/front-end, if any. Optional. |
| product_company | text | The underlying product or company. |
| status | text | active, research, on_hold, etc. |
| income_stream_id | int | FK to income_streams. Optional. |
| notes | text | Free-form. |

### `successbrian_os.income_streams`
What earns money. The graph lives here.
| Column | Type | Notes |
|--------|------|-------|
| name | text | Unique. |
| type | text | e.g. MLM, affiliate, freelance, ecommerce, trading |
| category | text | e.g. wellness, tech, finance |
| skins | text[] | **The graph.** Array of marketing channel names this stream flows through. Empty array = standalone. A stream can be in many channels; a channel carries many streams. |
| status | text | active, test, parked, etc. |
| priority | int | Higher = more important. |
| roi_score | real | Return-on-investment score, if tracked. |

**Why an array, not a join table:** Fewer tables. The skin↔stream relationship is simple enough for a Postgres array, queryable with `WHERE 'ChannelName' = ANY(skins)`. If it ever needs attributes on the relationship itself (e.g. conversion rate per channel), promote to a join table then.

### `public.income_stream_targets`
Targets vs actuals per stream.
| Column | Type | Notes |
|--------|------|-------|
| stream_name | text | Matches income_streams.name. |
| target_monthly_revenue | numeric | The goal in dollars. |
| current_monthly_revenue | numeric | Where you actually are. |
| status | text | ideation, building, launched, scaling, maintenance, sunset |
| launch_date | date | When it started earning. |

### `successbrian_os.sbos_goals`
What you're aiming for. Links to streams via success_metrics or naming convention.
| Column | Type | Notes |
|--------|------|-------|
| goal_name | text | e.g. "40 signups/month" |
| goal_slug | text | URL-safe identifier. |
| category | text | business, personal, health, etc. |
| status | text | planning, active, completed, etc. |
| success_metrics | jsonb | Quantified targets: `{"monthly_target": 40}` |
| parent_goal_id | int | For goal hierarchies. Optional. |

### `successbrian_os.sbos_projects`
The work. Each project belongs to a goal.
| Column | Type | Notes |
|--------|------|-------|
| project_name | text | |
| goal_id | int | FK to sbos_goals. |
| status | text | See Statuses below. |
| phase | int | Which phase (1, 2, 3...). |
| gate_key | text | FK to project_gates. The gate this project must pass. |
| priority | text | low, medium, high, urgent |
| target_date | date | Deadline. |
| progress_pct | int | 0-100. |

### `successbrian_os.project_statuses`
The canonical status list. Includes `research` and `on_hold` as first-class states.
| Status | Meaning |
|--------|---------|
| planning | Not started, being scoped |
| research | Gathering info before committing |
| pending | Waiting to start |
| active | Currently being worked |
| in_progress | Work underway |
| at_risk | In danger of missing target |
| blocked | Cannot proceed — needs resolution |
| on_hold | Paused by decision — will resume later |
| completed | Done |

### `successbrian_os.project_gates`
Quality gates between phases. A project doesn't advance until its gate passes.
| Column | Type | Notes |
|--------|------|-------|
| gate_key | text | Primary key. e.g. "mvp_ready" |
| project_id | int | FK to sbos_projects. |
| gate_name | text | Human-readable. |
| gate_order | int | Sequence. |
| status | text | pending, passed, blocked |
| criteria | text | What "passed" means. |
| passed_at | timestamptz | When it passed. |

### `successbrian_os.tasks`
Actionable work items. Link to projects and goals.
| Column | Type | Notes |
|--------|------|-------|
| title | text | |
| project_id | int | FK. Optional. |
| goal_id | int | FK. Optional. |
| status | text | pending, in_progress, completed, etc. |
| priority | text | |
| target_date | date | |
| gate_key | text | If this task is gated. |

### `successbrian_os.life_calendar`
Your life and business events in one place.
| Column | Type | Notes |
|--------|------|-------|
| title | text | |
| event_date | timestamptz | When. |
| end_date | timestamptz | Optional. |
| event_type | text | work, health, business, personal, etc. |
| project_id | int | FK. Optional — link events to projects. |
| status | text | scheduled, completed, cancelled |

### `successbrian_os.life_plan_items`
Long-term milestones (from your life plan document, now queryable).
| Column | Type | Notes |
|--------|------|-------|
| category | text | housing, business, relationship, health, etc. |
| title | text | |
| target_date | date | |
| status | text | planned, active, on_hold, completed |

### `successbrian_os.decision_project_links`
Links decisions (in your decisions table) to projects. Many-to-many.
| Column | Type | Notes |
|--------|------|-------|
| decision_id | text | Matches your decisions table. |
| project_id | int | FK to sbos_projects. |

## Key views

- `v_project_hub` — projects with goal names, gate counts, event counts
- `v_income_hub` — streams with targets vs actuals
- `v_finance_hub` — budgets with last transfers
- `v_business_manage` — per-business rollup: streams, targets, project/task counts

## The decision-timeline principle

When a document disagrees with current reality: **check the decision date first.** If the document predates the decision, it's not a conflict — it's just old. Update the doc with the decision date; don't treat it as a live disagreement. Decisions are timestamped precisely so old docs never confuse you again.

## Seed data vs core

The schema above is the generic core. Any rows referencing specific businesses, people, or dollar amounts are **seed/example data**, not core. When you set this up for yourself, replace the seed data with your own. See `docs/SEPARATION.md` for the full pattern.
