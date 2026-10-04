# SuccessBrian OS

The operating system for solo entrepreneurs running multiple income streams.
PaperclipOS for the one-person business: it manages the ventures, the
audience, the focus, and the institutional memory — so the founder can spend
their attention on decisions, not administration.

Built for founders whose brains go in 100 directions at once: every module is
deterministic code, not vibes. **Scores propose. You decide.** No chat model
ever decides anything in this repo.

## The systems

**Decide what to pursue**
- `tools/ventures/` — idea capture → flesh-out → deterministic score → goal
  draft. Fixed rubric, bands not verdicts, every point traceable to a field.
- `tools/focus/` — the focus coach. `evaluate` scores any new opportunity
  (MLM, affiliate program, product, side stream) on life value, ecosystem fit,
  future fit, focus load, and the pride test (can you promote it for the
  product alone, to your own followers?). `review` is
  the regular grounding pass: every active pursuit reduced to facts — what
  earns, what is promoted, what is tested, what is attention rent.

**Grow the audience**
- `tools/audience/` — weekly audience-size tracking per channel, so growth
  compounds instead of being guessed at.

**Learn and remember**
- `tools/second_brain.py` — durable learnings with confidence, expiry, and
  verification, so stale knowledge can't silently poison future reasoning.

**Run the operation**
- Employment intel pipeline, marketer watch, email launch parser, intake
  triage, daywatch/fleet health, DealsDesk vetting, and the A2A agent mesh —
  the working machinery of a real multi-stream business. (Most of these were
  built against one founder's infrastructure; see tiers below.)

## What runs where

Not everything needs the same setup. Three tiers, honestly labeled:

- **Tier 1 — runs anywhere.** Pure Python 3, local JSON config, zero
  infrastructure. Start here: `tools/focus/`.
- **Tier 2 — needs PostgreSQL.** `tools/ventures/`, `tools/audience/`, and
  friends expect a Postgres database. Point them at yours
  (`PGPASSWORD` or a `~/.pgpass` entry); the schemas ship in each module.
- **Tier 3 — needs your own infrastructure.** Some tools were built against
  a home lab (SSH + tailnet + API keys). They work, but you'll adapt the
  connectors — see each module's docstring.

## 5-minute quickstart

```bash
git clone https://github.com/successbrian/successbrian-os.git
cd successbrian-os

# The onboarding interview: builds your private registry in ~5 minutes.
# (Your answers stay on this machine — gitignored, never committed.)
python3 tools/setup/init.py

# The boot check: verifies every tier and tells you exactly what's missing.
python3 tools/setup/doctor.py

# The grounding review: facts about your commitments
python3 tools/focus/focus.py review

# Score the next shiny object before it eats your quarter
python3 tools/focus/focus.py evaluate --name "Your Next Thing" \
  --benefit 1 --unique-lane --recurring --momentum 1 --attention-cost 1
```

## Conventions (read before contributing)

- **Your data stays yours.** Anything named `user_*.json` is personal
  config: gitignored, never committed. The product ships templates
  (`user_*.example.json`); you ship nothing about yourself.
- **Scores propose, you decide.** Bands, not verdicts. If a module ever
  needs a human call, it says so instead of guessing.
- **`docs/CODE-STANDARDS.md`** — every module documents PURPOSE / WHY /
  CALLED BY / NOTES. The WHY is mandatory.
- **No secrets in this repo. Ever.** Tokens and keys live in environment
  variables on the machines that need them.

## Specs

- [`specs/altair-apis.md`](specs/altair-apis.md) — HTTP APIs for the agent
  layer: research digest, library catalog, pipeline status, session recaps.
- [`specs/a2a-upgrade.md`](specs/a2a-upgrade.md) — persistent A2A hub v2,
  ack-after-processing, agent mesh upgrade.
- [`specs/a2a-checkin.md`](specs/a2a-checkin.md) — twice-daily agent
  standup protocol.
- [`specs/a2a-join.md`](specs/a2a-join.md) — join runbook for new agents.
- [`specs/anythingllm-cleanup.md`](specs/anythingllm-cleanup.md) — library
  cleanup automation (quarantine, never delete).

## Status

Under active daily development by its founder, who runs a real
multi-stream business on it. Expect velocity over polish: the test suite is
thin, the docs are growing, and Tier 3 modules still carry the fingerprints
of one person's infrastructure. What's here is real, used, and compounding.

## License

Apache-2.0 — see [LICENSE](LICENSE). Use it, fork it, build on it, sell
what you build. The only things you can't take are the founder's name,
trademarks, and private data (which was never in the repo to begin with).
