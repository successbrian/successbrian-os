# Per-user private databases — design spec

<!--
PURPOSE: Design for giving every successbrian-os user their own private
database ("their altair database") for user-specific workflows and business data.

WHY: Today the system is single-user: one shared database holds product tables
and one private database holds the operator's own data. To serve more than one
entrepreneur, each user needs the same private-data home without seeing anyone
else's. This spec defines the shape before any code is written.

CALLED BY: Future implementer (human or agent) building multi-tenancy.
Decided 2026-10-04 (dec-20261004-adb2). Spec approved by Brian before build.

NOTES: This repo is PUBLIC. Nothing in this spec may contain user-private
details, credentials, or business data. All examples use placeholders.
-->

## 1. Background and terms

- **Shared product DB**: one database holding everything the product needs to
  run identically for every user (migrations registry, product-level config,
  shared reference data). In the current single-user deployment this is the
  `ecosystem_central` database's product schemas.
- **Private user DB** ("the user's altair database"): one database per user
  holding that user's own data — their decisions, learnings, intel, workflows,
  business records. In the current deployment this is the separate `altair`
  database. It is readable by the user's own agent fleet and by nobody else.
- **Operator**: whoever runs a successbrian-os instance (self-hosts it).
  Today there is one operator; the design must not assume there will always
  be one.

## 2. Architecture options

### Option A — one Postgres database per user, on the operator's cluster (RECOMMENDED)

Each user gets `CREATE DATABASE sbos_u_<slug>` on the same Postgres cluster
that hosts the shared product DB. This is exactly the pattern already proven
in production: the private `altair` database lives on the same cluster as
`ecosystem_central`.

### Option B — one schema per user inside the shared database

Each user gets `CREATE SCHEMA user_<slug>` inside the single shared database.

### Option C — one Postgres cluster per user

Each user gets their own Postgres server/cluster (separate VM, separate port).

### Option D — managed database per user (e.g. Supabase project per user)

Each user's private DB is a hosted service project, provisioned via API.

### Recommendation: Option A

| Concern | A: DB per user | B: schema per user | C: cluster per user | D: managed per user |
|---|---|---|---|---|
| Isolation | Strong — Postgres databases are a real security boundary; no cross-DB queries without explicit bridges, privileges are per-database | Weak — one misconfigured GRANT or `search_path` bug leaks across users; shared catalogs, shared connection pool | Strongest | Strong, but trust moves to the vendor |
| Cost | ~Free — a database is catalog entries plus files on the existing cluster | Free | High — a server per user | Recurring $ per user per month |
| Backup | Clean unit — `pg_dump` per database; per-user export is trivial ("take your data with you") | Fiddly — schema-scoped dumps, easy to miss dependencies | Clean, but N backup jobs | Vendor tooling, export limits vary |
| Ops complexity | Low — `CREATE DATABASE` is a one-liner a deterministic script runs | Low, but every query must be schema-qualified and audited | High — N clusters to patch, monitor, secure | Low ops, high bill; API-provisioning code needed |
| Noisy neighbors | Good — per-DB connection limits and statement controls are available | Poor — one user's heavy query shares everything | Best | Vendor-handled |

Reasoning:

1. **It is already proven.** The current deployment runs this exact shape:
   shared DB plus a private user DB on one cluster. Generalizing a proven
   pattern beats inventing a new one.
2. **Postgres means it when it says "database".** Cross-database access
   requires explicit grants; the default is no access. Option B's isolation
   is convention-only — one bad migration away from a leak. For data the
   product promises is private, convention-only isolation is not enough.
3. **It fits the operator's economics.** No per-user server (C), no per-user
   subscription (D). The heaviest cost is discipline, not money — which
   matches the project's hardware-is-the-budget principle.
4. **Backup is the feature.** A per-user database dumps, restores, and
   exports as one unit. That makes "your data is yours, take it anytime" a
   true product promise instead of a support ticket.

## 3. Provisioning flow

Provisioning is a **deterministic script**, never a chat-model decision. A
model may propose, the user approves, the script executes.

### 3.1 The script

`tools/userdb/provision.py` (new; exact path is the implementer's call):

```
sbos userdb create <user-slug>   # create DB, roles, default schemas, seed tables
sbos userdb list                  # list private DBs on this cluster
sbos userdb backup <user-slug>    # pg_dump to a timestamped file
sbos userdb drop <user-slug>      # DISABLED by default; requires explicit
                                  # operator confirmation (destructive)
```

Behavior of `create`:

1. Validate `<user-slug>`: lowercase, alphanumeric plus hyphens, max 32 chars.
   Reject anything else — the slug becomes a database and role name.
2. `CREATE DATABASE sbos_u_<slug>` (naming convention; see 3.2).
3. `CREATE ROLE sbos_u_<slug>_owner LOGIN` and
   `CREATE ROLE sbos_u_<slug>_reader LOGIN`, with generated passwords stored
   **only** in the operator's credential store (Secure Vault or env files on
   the operator's machines — never in this repo, never in chat).
4. `GRANT CONNECT ON DATABASE` to the two roles; `REVOKE` from `PUBLIC`.
   Default: nobody else can even connect.
5. Create default schemas and seed tables (see 3.3), owned by the owner role.
6. `GRANT SELECT` on all seed tables to the reader role
   (`ALTER DEFAULT PRIVILEGES` so future tables inherit it).
7. Print a connection summary (host, dbname, roles) — **never the passwords**.

Idempotency: re-running `create` for an existing slug is a no-op that reports
"already provisioned" rather than erroring or duplicating.

### 3.2 Naming convention

- Database: `sbos_u_<slug>` (e.g. `sbos_u_acme`).
- Roles: `sbos_u_<slug>_owner`, `sbos_u_<slug>_reader`.
- The existing single-user private database keeps its current name (see
  section 6, migration). New users follow the convention from day one.

### 3.3 What ships by default vs what the user adds

**Seeded by provisioning** (the product's promise — every private DB has these):

- `core` schema: the tables the product's own features expect —
  user decisions, user learnings, research digest, and the agent-activity
  tables the fleet writes. Exact table list is the implementer's call; the
  rule is: if product code reads it without user configuration, it ships
  in the seed.
- `private` schema: empty, owned by the user — the user's own tables for
  their specific workflows and business go here. The product never creates
  tables in `private` unasked.

**Added by the user** (or their agents, on their instruction): any further
schemas/tables in the private DB. The product treats unknown schemas as
opaque — it backs them up, it never reads them for product purposes.

## 4. Access-control model

Decisions dec-20261004-adb1 (fleet may read; never public), generalized:

1. **Owner role** (`sbos_u_<slug>_owner`): the user's primary agents and
   approved automation. Full read/write on that user's private DB.
2. **Reader role** (`sbos_u_<slug>_reader`): the user's wider worker/agent
   fleet. `SELECT` only, via `ALTER DEFAULT PRIVILEGES`. This is the
   generalization of today's "Spencer, Meghan, Lyra, Mavity, DealsDesk may
   read" rule — per user, not global.
3. **No cross-user access, ever.** Roles are per-database; Postgres grants no
   cross-database access by default, and the provisioning script grants none.
   An agent serving user A has no credentials for user B's database, full stop.
4. **Never public.** Private DBs are reachable on localhost / the operator's
   private network (tailnet) only. The product must not offer a "make public"
   toggle for private databases. Any future sharing feature is a separate
   design with its own approval.
5. **Credentials.** Per-role passwords live in the operator's Secure Vault or
   host env files. Product code reads them from the environment at runtime.
   Hardcoded credentials are already a known violation in this repo
   (`tools/ventures/ideas.py` hardcodes a dbname, user, and password) —
   **fixing that is a prerequisite of this feature, not a follow-up.**
   Twenty-one tools currently hardcode the shared database name; all must
   read it from config (see section 7).

## 5. What belongs where — the generic/private split applied to data

The repo's standing rule (generic product code, private customizations kept
separate) applies to data the same way:

**Shared product DB** — true for every user, identical shape:

- Migration registry (which schema version each database is on).
- Product-level configuration and feature flags.
- Shared reference data the product ships (e.g. industry lists, program
  directories — data any entrepreneur would use).

**Private user DB** — true for one user:

- Their decisions, learnings, goals, journal/digest entries.
- Their intel (market scans, launch tracking, research findings).
- Their contacts, customers, business records.
- Their workflow state (threads, pending questions, project gates).

**The test:** if deleting it would break the product for *everyone*, it is
shared. If deleting it would break things for *one user*, it is private.
When in doubt, it is private — over-sharing is the failure mode that
destroys trust; over-isolating is merely inconvenient.

Current-deployment note: the second brain and several agent tables live in
shared-DB schemas today. They are user-specific data and belong in the
private DB under this model. Moving them is migration work (section 6),
not a day-one requirement — but new tables must follow the split from
the start.

## 6. Migration path — the current operator becomes user one

Goal: minimal churn. The running system keeps running.

1. **The existing private database is grandfathered.** It keeps its name and
   contents. It becomes the documented reference implementation of "user
   one's private DB." Renaming a live database buys nothing and risks
   everything; the naming convention (3.2) applies to new users.
2. **Config, not code, selects the database.** All 21 tools that hardcode the
   shared database name switch to environment-driven config with the current
   values as defaults — so nothing changes behavior on day one, and the
   multi-user shape becomes possible on day two. Same for the private-DB
   name wherever it is referenced.
3. **The fleet read rule becomes the reader role.** Today's informal
   "these agents may read" becomes `sbos_u_<slug>_reader`-style grants,
   documented per user.
4. **No data moves on day one.** Existing tables stay where they are until a
   specific migration is approved. The split in section 5 governs *new* tables
   immediately and *old* tables when their migration is scheduled.

## 7. API / config surface (minimal, user-facing)

Environment (read at runtime; secrets via the operator's vault, never the repo):

```
SBOS_SHARED_DB      # product database name (default: current single-user value)
SBOS_PRIVATE_DB     # this user's private database name
SBOS_DB_HOST        # Postgres host (default: localhost)
SBOS_DB_USER        # role for this process (owner or reader)
SBOS_DB_PASSWORD    # from vault/env, never code
```

CLI (deterministic; see 3.1):

```
sbos userdb create <user-slug>
sbos userdb list
sbos userdb backup <user-slug>
```

Product-code contract:

- Every database connection takes its dbname from config. Hardcoded database
  names are a bug under this design.
- Code that touches user data connects to `SBOS_PRIVATE_DB`; code that
  touches product machinery connects to `SBOS_SHARED_DB`. A module that
  needs both says so in its docstring (WHY it crosses the boundary).
- The A2A / knowledge-bridge channel between agents is unchanged by this
  design — it is a transport, not a database. Which database a bridge
  *writer* persists to follows the split in section 5.

## 8. What this spec does NOT cover

- Managed-hosting onboarding (Supabase-per-user and friends) — recorded as
  open question 1 below. This spec covers the self-hosted operator model,
  which is the current reality.
- A public sharing / collaboration feature for private data — explicitly out
  of scope until its own design and approval.
- Quotas and resource limits per user — needed before the second *real*
  user, not before the first.

## 9. Open questions for Brian

1. **Who hosts?** Self-hosted Postgres per operator (this spec) vs managed
   database per user (e.g. a hosted project per signup)? This decides the
   cost model and whether onboarding a new user means "run a script on your
   machine" or "click a button in our cloud." It also interacts with the
   standing deployment stance (hosted stack for public apps, home lab for
   private).
2. **Does the private DB hold secrets?** API keys and tokens the user's
   workflows need — do they live in the private DB, or stay exclusively in
   the Secure Vault with the DB holding only data? Scope of "private" is a
   real fork: convenience vs blast radius.
3. **How strong is the export promise?** Is per-user one-click full export
   ("take your data and leave") a launch requirement or a later feature?
   The architecture makes it cheap; the product promise makes it load-bearing.
4. **Grandfather or rename?** Keep the current private database's name as the
   user-one reference, or rename it to the `sbos_u_<slug>` convention for
   consistency? (Spec recommends grandfathering; renaming is churn.)
5. **Cross-user reads, ever?** Default is never — but is there a legitimate
   case (e.g. your fleet doing work *for* a client user) where a scoped,
   audited, user-approved cross-user read should exist? If the answer is
   "never," that gets written into the product's invariants.
