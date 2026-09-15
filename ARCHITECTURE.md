# Architecture — SuccessBrian OS

A high-level view of the generalizable patterns. The production specifics (data,
pipelines, the deal-finding system) stay private — this is the design you can steal.

## The fleet

8 agents + 16 specialized workers. Each agent owns a domain — infrastructure, deals,
revenue, knowledge, content — and hands off verification to the agent that owns it.
Workers are single-purpose: vision grading, enrichment orchestration, graph
architecture, revenue scanning, decision gating.

## The knowledge layer — "a second brain that doesn't rot"

Two layers, because facts and prose have different shapes:

- **PostgreSQL** (structured facts) — every fact carries `confidence`, `expires_at`,
  and a `verification` status. Stale facts expire; unverified claims get re-checked.
- **AnythingLLM** (semantic / narrative) — the readable context.

Routing rules keep it clean:

| Content | Destination |
|---------|-------------|
| Durable fact / rule | PostgreSQL (the second brain) |
| Narrative prose | AnythingLLM |
| Operational noise (system_state, quick-scan) | a worker state log — never the brain |
| Procedure / workflow | a skill |

The lesson: separate *durable knowledge* from *operational noise*. Most agent memory
systems rot because they don't — they dump everything into one store and it becomes
unusable in a week.

## Orchestration — the simple/complex boundary

- **Simple tasks** (shell, single SQL, single HTTP, process, monitor) → a high-volume
  work queue. Fast, cheap, no ceremony.
- **Complex workflows** (conditional routing, retries, webhooks, multi-stage pipelines)
  → a visual orchestrator (n8n).

The rule: *never put a simple task in the complex orchestrator.* Most people do the
reverse and drown a heavy tool in trivial jobs.

## The graph, not the tree

The ecosystem is a directed graph — initiatives → goals → nodes, typed edges
("feeds", "depends_on", "blocked_by"). A tree can't express that a revenue stream
depends on a deal pipeline that depends on a hardware node. Model reality as a graph.

## Hardware

Self-sourced, financed by flipping deals. Roughly $500 of used hardware runs the whole
thing — because renting the cloud for 8 agents is a monthly bill, and owning the box is
a one-time cost you can resell.

## The generalizable lessons

1. Memory decays unless you give it confidence, expiry, and verification.
2. Route operational noise away from the knowledge store.
3. Keep simple tasks simple, complex tasks complex — and never mix them.
4. Model the system as a graph, not a tree.
5. Own the hardware; rent nothing you can resell.
