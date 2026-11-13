# Hire Workflows, Not Agents — SBOS Factoring Spec (2026-11-12)

**Origin:** Brian's thesis, stated 2026-11-12 20:40 CST: most AI people "hire agents" — a researcher agent, a this agent, a that agent — and that is "highly 'simplified' thinking. What is really needed is an operating system like SBOS with databases and code, crons... actual software that uses harnesses and grabs qualified models from anywhere and says, 'do this work now'... and routes that work through a repeatable process or harness. So instead of hiring agents, I'm hiring workflows or harnesses."

**Companion doctrine (same evening):** inference capacity is buildable — never design against one machine; work is JOB CLASSES, not persons; overflow runs UPWARD; the hardest work is assigned to the smarter engines; all worker queues balance as a team; Atlas manages balancing by priority and by goal; the planner seat rotates through ALL goals; seats are LOCATION-INDEPENDENT.

**Test applied by this audit:** a piece of SBOS is *harness-shaped* if (1) work is addressed to a role / job class / queue, not a named agent, model, or host; (2) state lives in PostgreSQL or the repo, not in an agent's files or chat context; (3) the procedure is code, not prose a specific agent must remember; (4) the capability keeps working when any one agent, model, or machine is absent; (5) a model's location is configuration, never part of an address. Everything below that fails the test is a finding, with the file/table evidence.

**Already harness-shaped (the pattern to extend, not findings):** the engine queues — `sbos_common.ENGINE_JOB_TABLES` + `tools/engine_jobs.py` address jobs to engine classes (morpheus / penny / sonic / reap) that any instance can claim; `sbos_common.py` lines 57–62 hold env-overridable model endpoints; agent-cycle state was moved into `successbrian_os.agent_cycle_state` (PostgreSQL); the PM system itself (`successbrian_os.pm_projects` / `pm_steps` / `pm_project_checks`) is database state with command-type QA checks; `tools/atlas/atlas_completion_sync.py` completes Atlas tasks on mirrored *evidence* (a PM step finished, a QA check green), not on an agent's say-so.

---

## Findings, ranked by leverage

### 1. Atlas goal machinery + planner rotation — ALREADY DESIGNED, NOT BUILT (Size L)
- **Evidence:** census of `atlas.nodes` node_type, live 2026-11-12: `plan` 1,897, `atlas_task` 1,695, `person` 500, `doc` 490, `project` 228 — **zero `goal` nodes**. `tools/atlas/atlas.py` is graph CRUD (add-node / add-edge / impact / depends) with no goal→task or goal→calendar conversion. The only goal code, `tools/goal_driver.py`, holds exactly three hardcoded monthly goals as a scorecard + fit-link registry and, by its own docstring design, generates no tasks.
- **Change:** as designed in the planner-rotation design (2026-11-12): goal-type nodes in Atlas, goal→task conversion, and the planner-seat rotation that loops all goals over several days, doing work as required, balanced by Atlas priority. This spec does not re-design it; it ranks it #1 because every other change below routes by goal and priority once this exists.
- **Risk:** high touch — new node type + conversion path beside 1,695 live tasks. Build behind the existing PM/QA registration pattern.
- **Proof:** a goal node exists whose spawned tasks complete through the normal PM/queue path; rotation coverage report shows every goal looked at inside the window.

### 2. Atlas tasks are addressed to named models, not job classes (Size M)
- **Evidence:** `tools/atlas/atlas.py` `task_add()` — every task is auto-routed by `route_model()` to one of two named models; the CLI enforces it (`--model choices=['sonic','v4pro']`, line 302); the assignee is stored as `details->>'model'` and `atlas.py tasks --model` filters the work list by model. There is no class, no queue, no claim: a task waits for the named model's lane, and completion arrives only via mirror rules in `atlas_completion_sync.py`.
- **Change:** address tasks to a JOB CLASS (bulk / medium / judgment / deep) resolved to a qualified engine at claim time through the engine-queue pattern; keep `details->>'model'` as provenance — who actually served it — written after the fact, never as the address.
- **Risk:** medium — 1,695 existing task rows carry the old field; migrate as read-compatibly as the engine queues did (old field kept, new field authoritative).
- **Proof:** a task filed with no model named is claimed and completed by whichever qualified engine is free, including from a different host; `harness_audit.py report` shows the model-addressed share of open tasks falling.

### 3. PM heartbeat work is claimed through per-named-agent code paths (Size M/L)
- **Evidence:** `tools/pm/heartbeat_claim.py` implements the three work layers as hardcoded branches for LYRA / ALTAIR / MEGHAN in one file; alpha's crontab invokes it separately per named agent (`--agent altair` at :17/:47, `--agent meghan` at :02/:32, each with its own flock file), and Altair's judgment branch calls a hardcoded `SONIC = "http://127.0.0.1:11439"` (line 48). The work itself is generic — `successbrian_os.pm_steps` sits 665 rows `queued` with `actor` NULL — but if a named agent's cron stops, that layer stops, even though the layer rules exist only as the file's docstring prose.
- **Change:** make the layer a data record (which step kinds a layer claims, which engine class serves its judgment, its cadence) in PostgreSQL/config; the heartbeat runner claims *for a layer*, and the current seat-holder (agent + model + host) is written to `actor` as provenance. Named agents become seat-holders, not code paths.
- **Risk:** high if rushed — this is the live 24/7 queue. Stage it: config record first (read-only mirror), runner switch per layer, one layer at a time.
- **Proof:** stop one seat-holder's cron in a drill and the layer's steps are still claimed by the next qualified holder; QA check on unclaimed-step age stays green.

### 4. Model endpoints are location literals scattered outside the shared config (Size S/M)
- **Evidence:** `sbos_common.py` does it right (env-overridable `SONIC_URL` / `MORPHEUS_URL` / `PENNY_URL`). Hardcoded duplicates with no override: `tools/pm/morpheus_worker.py:40`, `tools/pm/heartbeat_claim.py:48`, `tools/governor.py:16`, `tools/altair_heartbeat_v4pro.py:78–79`, `tools/ventures/ideas.py:37`, `tools/altair/post_prompt_integrate.py:37`. Moving Morpheus to gamma today means editing many files instead of changing one value — the location is baked into the addresses.
- **Change:** sweep call sites to the `sbos_common` constants, one file per commit, non-heartbeat paths first; `harness_audit.py` counts remaining literal sites so the sweep is measurable.
- **Risk:** low per file (same default value); the heartbeat files go last and one at a time.
- **Proof:** `MORPHEUS_URL` set to a test endpoint changes behavior without a code edit; audit count of literal sites reaches zero outside `sbos_common` and the repair ladder (which legitimately starts servers by port).

### 5. Standing tasks are addressed to named agents in `successbrian_os.tasks` (Size M)
- **Evidence:** live census 2026-11-12 — `assigned_to='altair'` holds 115 pending rows, `'brian'` 46 pending; historical assignees are worker instance names (`sbos-worker-1` 33,213 completed, `sbos-crewai-1`, `meghan-fixer-1`). `tools/daily_director.py` — the only task→calendar converter — reads these agent-addressed rows, so the daily plan inherits the addressing.
- **Change:** role assignees (`role:decider`, `role:worker`, `role:research`) resolved to the current seat-holder at claim/display time. Brian-addressed rows stay as-is — the owner is not a seat.
- **Risk:** medium — daily_director and dashboards read `assigned_to`; add role values alongside names before switching readers.
- **Proof:** pending counts by *role* replace pending counts by *name*; reassigning a seat moves the work with a config change, not a 115-row update.

### 6. Fleet host addresses are raw tailnet IP literals in code (Size S/M)
- **Evidence:** `tools/pm/dashboard.py:26` `VPS = "root@100.118.196.66"`; `tools/review/review.py:74` `GAMMA_HOST = "root@100.118.196.66"` — the variable is *named* for one machine while holding another's address (the VPS/node-zero), exactly the confusion location-literals breed; `tools/marketing/link_tracking.py:22` and `linktrack_ingest.py:21` `GAMMA = "root@100.118.196.66"`; `tools/backups/ecosystem_backup.py:97`; `tools/dashboard/inbox_refresh_opportunistic.py:21` (scp to a literal IP). A registry already exists: `tools/fleet_registry.json`.
- **Change:** resolve hosts by fleet name from the registry (or tailnet DNS names); rename the misnamed constants after what they address (the VPS), not after a model or agent.
- **Risk:** low per file; backup/deploy paths get individual verification after the change.
- **Proof:** grep for tailnet IP literals in `tools/` returns only the registry and docs; an IP change is a one-line registry edit.

### 7. Standing procedures live in per-agent profile directories, outside the repo (Size M)
- **Evidence:** alpha's crontab runs behavior-critical scripts from profile homes — `/home/successbrian/bin/altair_briefing.py` (four cron entries), `/home/successbrian/.hermes/profiles/altair/scripts/spencer_checkin.py` (twice daily) — and agent wake behavior rides `tools/agent_wake.py altair` per named agent. Combined with the AGENT_CONTRACT prose model, a capability's procedure can exist only where one agent's profile remembers it; lose the profile, lose the procedure.
- **Change:** inventory the profile-dir scripts; move the standing ones into repo `tools/` with crons repointed; profiles keep identity/voice, procedures live in code. (Doctrine text like AGENT_CONTRACT.md stays prose — it governs agents; it is not a procedure.)
- **Risk:** medium — each moved script needs its cron repoint verified on the next scheduled run.
- **Proof:** inventory list with a repo path (or an explicit Brian-approved exception) for every cron line that runs code from a home/profile directory.

### 8. Agent-to-agent messaging still runs through a home-directory markdown file (Size M — needs Brian's scope call)
- **Evidence:** `~/A2A-INBOX.md` plus its residue trail in the home directory — `A2A-INBOX.cleared.*` (multiple), `A2A-INBOX.md.consumed`, `A2A-INBOX.md.2026-09-17.stale`, and a family of `a2a_*.py` scripts beside it — while a database bus already exists and is in use (`altair.knowledge_bridge`, consumed by the Lyra layer's digest in `heartbeat_claim.py`).
- **Change:** declare PostgreSQL the record and retire the file as transport, or formally demote the file to a transport cache with the bridge as the system of record. Ranked last because A2A may involve parties outside SBOS; the scope is Brian's to set.
- **Risk:** medium — external correspondents may depend on the file path.
- **Proof:** a message round-trips through the bridge with no file touched; the inbox file stops growing.

---

## First code step (this pass)
`tools/harness_audit.py` — a new, read-only harness that turns this audit from a one-off agent pass into a repeatable process: `report` prints the live counts behind findings 1, 2, 4, 5, 6; `selftest` proves the audit queries run and this spec is present in the repo docs, printing `HARNESS_AUDIT_OK`. Registered as a command-type QA check on PM project `sbos-hire-workflows`. It changes no behavior of any running system and is removable in one commit — the smallest clearly-safe step, and itself an instance of the thesis: the audit is now a workflow, not an agent's memory of having looked.

## Registration
- PM project: `sbos-hire-workflows` (successbrian_os.pm_projects), QA check `harness-audit-selftest` (command type, daily).
- Atlas task: `task:sbos-hire-workflows-factoring`, filed via `tools/atlas/atlas.py task-add` — the route prior desk builds used (precedent: `task:campaignsdesk-content-pm`).
- Repo copy of this spec: `docs/hire-workflows-factoring-spec-2026-11-12.md` in successbrian-os.
