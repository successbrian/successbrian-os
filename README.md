# SuccessBrian OS

Specs and tooling for Brian's agent ecosystem:

- **Altair** — agent on k11-alpha (infra, research, builds the APIs)
- **Spencer** — Muse agent (organizer, consumer of the APIs, Brian's interface)

## Specs

- [`specs/altair-apis.md`](specs/altair-apis.md) — the three HTTP APIs Altair builds on
  k11-alpha for Spencer to poll: research digest, library catalog, pipeline status.

## Rules

- No secrets in this repo. Ever. Tokens and keys live in environment variables
  on the machines that need them.
- Specs are written for an AI implementer: precise schemas over prose.
