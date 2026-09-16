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

Self-sourced, financed by flipping deals. A ~$1,600 machine (barebones + storage + RAM
that's appreciated) runs the whole thing — because renting the cloud for 8 agents is a
monthly bill, and owning the box is a one-time cost you can resell.

## The inference strategy — decompose, don't brute-force

Don't run one big "smart" model on everything. Break every workflow into narrow tasks,
and run each on a small (7B-14B) model fine-tuned with QLoRA for that specific task.

A small model can't be 95% as smart generally — but it can be 95% effective at a
*narrow* task: extraction, classification, routing, structured output. Decomposition is
what makes small models competitive — each narrow task fits a specialized model, run
locally, at a fraction of the cost of a frontier API.

Result: near-frontier quality on owned hardware, fully private, no per-token bill.

## The worker-builder — an agent that assembles and tunes its own workforce

The newest layer. Instead of shipping a fixed team of agents, the OS runs a
headless operator that:

1. Watches what the ecosystem actually needs.
2. Builds a specialized worker for each need — on its own, no instruction.
3. Continuously fine-tunes each worker so it gets better for *that specific*
   environment.

Two things separate this from "another multi-agent framework":

- **Decouple conversation from execution.** The operator is never chatted with,
  so it ships *lean* — no chat, gateway, or connection code. All of that lives in
  the one front-end agent the user talks to. The worker stays cheap and swappable.
- **Ship a builder, not a workforce.** A fixed fleet is a generic team nobody
  configured for themselves. A builder grows a team around *your* actual needs
  and keeps sharpening it.

`worker_builder.py` is the runnable version of the pattern (assemble → tune →
improve); the production workers are real agents + fine-tuned models, kept private.

## The generalizable lessons

1. Memory decays unless you give it confidence, expiry, and verification.
2. Route operational noise away from the knowledge store.
3. Keep simple tasks simple, complex tasks complex — and never mix them.
4. Model the system as a graph, not a tree.
5. Own the hardware; rent nothing you can resell.
6. Decompose workflows so small QLoRA-tuned models can run them — don't brute-force with one big model.
7. Decouple the conversation layer from the execution layer — the worker ships lean.
8. Ship a builder, not a workforce — let the team assemble and sharpen around the user's needs.
