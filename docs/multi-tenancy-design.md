# PROPOSAL — SBOS Multi-Tenancy Design

**PROPOSAL — Brian has not approved this design. Nothing in this document is built.**
Project: `sbos-multi-tenancy-design` (SBOS PM, registered 2026-10-27, requested by Brian)
Date: 2026-10-27

## Why design this now

SBOS is heading toward an **appliance business**: the same system,
run for other operators. Tenancy retrofitted after the fact is a
rewrite — every table, query, secret, and agent prompt has to be
re-audited for "whose data is this?". Designing the tenant model now,
while there is exactly one tenant, costs a document. Retrofitting it
later costs the codebase. This design is that document.

## Core definition

**Tenant = operator.** A tenant is the person who operates one SBOS
instance's desks for their own business/life — Brian is tenant zero.
A tenant is NOT a user account inside Brian's system, and tenants
never see each other's anything.

## Isolation model — evaluated against the current schemas

Current state (honest): `atlas.*`, `campaignsdesk.*`, and
`successbrian_os.*` in `ecosystem_central` carry **no tenant column
anywhere**. Rows are implicitly Brian's. Desks share tables
(e.g. campaignsdesk.publications mixes what would, for another
operator, be entirely separate publications).

Two candidate models:

### Option A — schema-per-tenant
One Postgres schema set per tenant (`t_<tenant>.atlas`,
`t_<tenant>.campaignsdesk`, …), same DDL, migrations applied per
tenant.

- Pros: strongest isolation by construction; a missing WHERE clause
  cannot leak across tenants; per-tenant backup/restore/export (the
  portability bundle maps 1:1 to a schema set); per-tenant drop is
  trivial; matches how desks already group into schemas.
- Cons: migration fan-out grows with tenant count; cross-tenant
  analytics need explicit federation; connection handling must carry
  a search_path discipline.

### Option B — row-level, `tenant_id` on every table
- Pros: one schema, simpler migrations, easy global queries.
- Cons: every query in existing code must gain a tenant predicate —
  the current codebase has hundreds of unscoped queries; **one missed
  predicate is a cross-tenant leak**. RLS policies can enforce it,
  but retrofitting RLS + predicates onto atlas/campaignsdesk is the
  riskiest version of the rewrite this design exists to avoid.

**Recommendation (proposal): Option A, schema-per-tenant**, for the
state stores; AnythingLLM already isolates by workspace, and n8n /
file artifacts isolate by per-tenant directory roots. Brian's current
schemas become tenant zero by rename/copy during migration, not by
rewriting every query.

## Scoped secrets

- Secrets live per-tenant, never in shared config: a tenant's API
  keys (Wix, AnythingLLM, model providers, network dev apps) are
  stored under that tenant's own secret scope and injected only into
  that tenant's desk sandboxes.
- No global `.env` with everyone's keys (the current single-operator
  `.env` pattern does not scale and must not be copied per tenant by
  hand — it needs a per-tenant secret store with the same
  never-print / never-commit rules).
- The portability export's secret scrubber applies per tenant; one
  tenant's bundle can never contain another tenant's material because
  the schemas are disjoint (Option A).

## Per-connection action policy

Every external connection (a network account, an API, a mailbox) is
registered per tenant with an action policy, enforced at the desk:

- **Allowed** — the agent may act without asking (e.g. read own
  analytics).
- **Ask first** — the agent prepares the action and surfaces it in
  the operator's chat for an explicit go (posting, sending,
  publishing defaults live here — mirroring Brian's standing
  approval law, which is per-action, not per-plan).
- **Off** — the connection is read-only or fully disabled for agents.

Policy is data (per tenant, per connection), not code branches, so
an operator's risk posture is a settings surface, not a fork.

## Shared-agent / personal-account split

Appliance operators will, like Brian, mix *the system's* accounts
with *their own personal* accounts (a personal Facebook profile vs a
business page is the live example in campaignsdesk.publications).
The design keeps these as distinct connection records:

- **Shared/agent accounts**: created for the system, policy may be
  Allowed for routine work.
- **Personal accounts**: default policy **Ask first** for every
  outward action, **Off** for anything bulk/automated; the agent
  never treats a personal account as a marketing channel by default.
- A connection record names its class explicitly; nothing is
  inferred from its name or platform.

## Migration sketch (proposal, not a plan of record)

1. Freeze the tenant-zero schema DDL as the canonical template
   (from the live atlas/campaignsdesk/successbrian_os schemas).
2. Introduce a `tenants` registry (control plane only: tenant id,
   display name, schema prefix, status) — no tenant data in it.
3. Parameterize the connection/config layer: code takes a tenant
   context (schema search_path + secret scope + workspace slugs)
   instead of hardcoding `ecosystem_central` schemas and one `.env`.
   This is the one real code refactor; it is far smaller now, with
   one tenant, than later.
4. Provisioning script: create schema set from template, create
   AnythingLLM workspaces, create secret scope, register the
   operator as tenant, seed zero content conclusions/projects.
5. Brian stays tenant zero throughout; his instance migrates by
   being *declared* tenant zero first and only physically renamed
   when the parameterized code is proven against it.

## What needs Brian

- Approval of this design and of Option A vs B — **proposal only**.
- The appliance business shape itself (who tenants are, pricing,
  hosting) is unruled; this design deliberately does not assume it.
- When/if a first external tenant is ever onboarded — that is a
  separate, explicit Brian decision, not implied by this document.

Nothing was built or migrated in this pass.
