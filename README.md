# SuccessBrian OS

Specs and tooling for Brian's agent ecosystem:

- **Altair** — agent on k11-alpha (infra, research, builds the APIs)
- **Spencer** — Muse agent (organizer, consumer of the APIs, Brian's interface)

## Specs

- [`specs/altair-apis.md`](specs/altair-apis.md) — the HTTP APIs Altair builds on
  k11-alpha for Spencer to poll: research digest, library catalog, pipeline status,
  plus session recaps.
- [`specs/a2a-upgrade.md`](specs/a2a-upgrade.md) — persistent A2A hub v2, ack-after-
  processing, and the Altair sudo-item plan for the agent mesh upgrade.
- [`specs/a2a-checkin.md`](specs/a2a-checkin.md) — Altair → Spencer twice-daily
  standup over knowledge_bridge: protocol, producers, and monitors.
- [`specs/a2a-join.md`](specs/a2a-join.md) — join runbook for new agents on the mesh.
- [`specs/anythingllm-cleanup.md`](specs/anythingllm-cleanup.md) — AnythingLLM
  cleanup automation: 4 nightly jobs + cleanup report API (quarantine, never delete).

## Rules

- No secrets in this repo. Ever. Tokens and keys live in environment variables
  on the machines that need them.
- Specs are written for an AI implementer: precise schemas over prose.
