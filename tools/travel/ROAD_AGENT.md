# The road agent — one stripped Hermes profile per laptop

Brian's direction (2026-10-20): each travel laptop gets a **stripped
down, customized, RoadChat-type Hermes agent**, very tightly
integrated into the laptop, built for a mobile environment that
**may or may not have Wi-Fi**.

**Daily drivers (Brian, 2026-10-20):** these laptops will likely
become Brian's daily drivers *even at home* — probably the most
useful thing he needs every day. So "road" is a MODE, not a
place: the agent is the resident on his primary machines, full
stop. Consequences: provisioning is the critical path (ahead of
trip specifics); either-laptop continuity is a design goal —
state syncs through home so he can pick up EITHER laptop and
continue mid-thought; a dead laptop is a daily problem, not a
trip problem, so the pair is each other's spare; and the
console's daily ergonomics matter as much as its trip readiness.

## What it is

A Hermes profile per machine — `road-vostro`, `road-7420` —
authored at provisioning time with the standard profile anatomy
(SOUL.md / IDENTITY.md / AGENTS.md / MEMORY.md / config.yaml),
cloned from the fleet's template pattern and then *cut down*, not
built up. It is the console's resident on that machine: the SBOS
Console (roadchat.py) is the face Brian touches; the road agent is
the hands and senses underneath it.

## Its job (the AGENTS.md responsibilities)

1. **Sense this machine** — battery, link, tailnet, reachable hubs,
   disk — via `road_sense.py`, continuously and cheaply. Every
   other decision keys off the senses. Its time-sense is the
   **calendar snapshot** (road_sync pulls calendar_snapshot.json
   from home's canonical altair.calendar): travel days, meeting
   posture and the shape of Brian's day are inputs, not surprises.
2. **Keep the console alive** on localhost, in the right mode for
   the current link state (see the ladder).
3. **Hold the queues** — the road inbox lives here: outbound
   messages, posts, commits, card photos, follow-up tasks. Nothing
   created offline is ever lost; everything syncs when a link
   appears (link_up is its right hand). Queued comms sends fire
   from HOME's account gateways after sync (WhatsApp/Telegram/
   email doors live at home) — the laptop drafts and queues, it
   never originates a send.
4. **Sync opportunistically, in both directions** — any link
   (train Wi-Fi burst, station stop, phone tether, home LAN) runs
   `road_sync.py`: a **manifest-driven** exchange with the home
   ecosystem (road_sync.py's SYNC_SETS is the manifest). Road →
   home: trip log, inbox items, commits. Home → road: fresh Brain
   knowledge, council notes, prepared work, data snapshots —
   home will be *bigger* by trip time, so sync moves deltas by
   manifest, never "everything". Bravo is a **relay**: on the
   road it accepts the laptops' outboxes over the travel LAN and
   carries them home. The phone is a **feeder**: its captures
   (card photos, voice notes) land in the same road inbox, and on
   cellular it can ferry small vital items home — gated questions
   out, Brian's answers in — while the laptops stay dark. Weights are never link-synced — they're
   staged before departure (trip_prep). Sync never forces, never
   merges, never touches a dirty tree: it HELDs and says why.
5. **File the trip log home** — what happened on the road, in the
   repo, where the council reads it. The road agent doesn't
   deliberate; it *reports*, and the heartbeat council thinks.
6. **Escalate, never improvise** — road agent → Altair → Meghan →
   Brian. It can *ask* the fleet for compute; it cannot command
   the fleet (the inference access doctrine applies to it too).

## Topology — their own mini (Brian, 2026-10-20)

The laptops do not attach to "the network." They attach to
**their own mini** as their first hop, everywhere. Which mini is
an OPEN decision (Brian, 2026-10-20; Atlas:
plan:laptops-mini-decision): k11-bravo is the default (96GB,
exists, paid for) — but a NEW dedicated mini is on the table:
HX 370/470-class, **64GB LPDDR5X, Radeon 890M**. For this role
the soldered RAM is defensible — the job is sized once, and the
role's physics are LPDDR5X bandwidth + iGPU Vulkan (Sonic),
not RAM ceilings.

- **At home:** laptops → **WiFi** → the mini. The mini bridges
  onward to the house LAN, alpha, and the fleet; it escalates
  the laptops' heavy work the way a feeder does — jobs in,
  answers out.
- **On the road:** laptops → **Ethernet wire** → the mini (a
  compact travel switch + cables ride in the kit; trip_prep
  checks them as pack items). Wired on purpose: a cable ignores
  train Wi-Fi, captive portals, and RF noise, runs at wire
  speed for staging and sync, and is a physical security
  boundary in a public car.

The design property that matters: **the laptops' world never
changes — only the mini's uplink does.** Same hub, same
services, same addresses at the kitchen table and in the
lounge car. road_sense's modes follow the mini: hub present +
alpha reachable = home; hub present alone = road-linked;
no hub = road-dark (a laptop out solo). (road_sense v2 will
sense the mini as the primary hub axis; today it already keys
on bravo's engines.)

## The ladder (chosen automatically from road_sense's mode)

| Mode | Meaning | Engines | Behavior |
|---|---|---|---|
| home | alpha's engines answer | alpha (Sonic/Penny/Morpheus) | full console, sync everything |
| road-linked | bravo answers, alpha doesn't | bravo's mirrored set | full console on the travel LAN |
| road-dark | no hub answers | none (laptops are consoles) | console in saver posture: capture, queue, draft locally, Brain search over local docs |
| dark + battery | road-dark on battery | none | minimal polling, protect the battery for capture + notes |

An onboard emergency model (Chuck-class, ~3 GB) is a provisioning
*option* per laptop, off by default — the doctrine is that laptops
are consoles and hubs are engines.

## Stripped means

- **Skills:** the road set only — senses, console care, sync,
  queue, card capture, trip log. No wide A2A net, no cloud-model
  dependence, no business-agent tooling (that's the home
  profiles' world).
- **Footprint:** stdlib-grade helpers (road_sense.py is the model),
  small state under `~/sbos-road/` (queues/, logs/, cache/).
- **Power:** it is the component that *enforces* the power
  doctrine — on battery it slows itself and the console down.

## Tight integration

- Runs as a **user service** on the laptop (starts at login,
  restarts on failure), next to the console.
- Reacts to **link changes** (polls road_sense on a slow tick;
  a NetworkManager hook is a provisioning refinement).
- Knows its own machine: hostname, role, disk budget, which
  laptop-specific knobs (below) are set.

## Per-laptop knobs (set at provisioning)

| Knob | Vostro | Latitude 7420 |
|---|---|---|
| profile name | road-vostro | road-7420 |
| role | Brian picks primary/spare | Brian picks |
| engine order | bravo → alpha → queue | same |
| onboard emergency model | optional | optional |
| disk budget for cache/queues | per machine | per machine |

## Sync doctrine — divergence is normal (Brian, 2026-10-20)

"the mini and the actual ecosystem may often be out of sync
with each other... so sync is important." A sovereign node
DIVERGES as its normal state; sync is reconciliation, not
copying. The laws:

1. **Small, often, prioritized.** Every link is used, even a
   30-second burst — and the manifest moves the small vital
   things first: decisions and gated questions, then captures,
   then queue state, then bulk. Partial + resumable beats
   rare + total.
2. **Conflict classes, decided in advance.** Append-only data
   never conflicts. Home-authoritative data treats the mini's
   copy as cache. Road-created data is road-authoritative
   until home accepts it. The genuinely shared-writable class
   is kept as small as possible by design — what remains
   resolves last-writer-wins with the loser PRESERVED, never
   silently dropped.
3. **Unresolvable = a gated question.** When sync cannot
   decide, it does not guess: Lyra files the conflict as a
   question and Brian rules. Conflict resolution is judgment
   capture wearing work clothes.
4. **Sync health is visible.** Last-synced time, held items,
   pending conflicts — a tile on the board (it is an
   infrastructure fact) and a line in the Sunday board pack.
   Drift is seen, never discovered.
5. **Verified, or it didn't happen.** Hashes and row counts
   after every pass; the sync log is the audit trail; an
   unverifiable sync reports UNVERIFIED (trip_prep checks
   sync freshness before departure).
6. **Anti-entropy at home.** On the wire at home, a periodic
   deep reconciliation (per-table digests, file-manifest
   diff) so small drifts cannot accumulate silently for weeks.

## The mini's service stack — a sovereign node

The mini Brian brings is not just an inference hub; it carries
a complete, smaller copy of home's service tiers (Brian,
2026-10-20; Atlas: plan:road-mini-service-stack):

- **Its own PostgreSQL** — a working replica of the shared
  state (work_queue, pending_questions, learnings/decisions,
  calendar and people subsets). Sync is per-table contracts,
  home as system-of-record: append-only tables (learnings,
  decisions, captures) merge cleanly; authoritative-at-home
  tables (calendar, people) arrive as snapshots; road-created
  work pushes home through the outbox discipline.
- **Its own second brain** — the knowledge subset, with
  embeddings computed at home and shipped as data into the
  local Postgres (pgvector). Retrieval is local even road-dark;
  the console's Brain room is its face. Tonight's keyword search
  over docs is the seed of this, not the grown form. (Landscape
  checked 2026-10-20: no turnkey "mini RAG that syncs with a
  main RAG" product exists — the pattern is hand-rolled from
  embedded vector stores; pgvector-if-you-run-Postgres is the
  sovereign-RAG consensus; edge nodes consume versioned
  knowledge packs / index deltas and ship captures UP as data
  for central ingest. This design follows that pattern.)
- **Its own n8n** — the road workflow set: capture processing
  (card photo → contact draft), sync triggers on link changes,
  local scheduled jobs. Flows are designed link-aware — they
  queue in the dark instead of failing.
- **AnythingLLM: open question.** Its home role (ingestion,
  workspaces, RAG chat) is largely covered on the mini by the
  brain-as-data + the console as face. It rides only if Brian
  uses its workspace/agent features in ways the console won't
  replicate by trip time. Default: it stays home; its *outputs*
  travel.

Sizing consequence: the stack itself wants ~6–10GB, which is
bravo's 96GB column's best argument against the 64GB HX box —
on the HX, engines + stack fit with lanes prioritized, but the
margin is thinner. The mini decision (plan:laptops-mini-
decision) prices both columns honestly.

## Identity — how the system knows it's THE laptop

The laptops hold the dangerous verbs *because they are the
laptops* — so identity can't rest on a hostname (copyable) or on
tailnet membership alone (a tailnet can gain devices). Layers:

1. **Tailscale node identity** — cryptographic node keys; a
   device cannot impersonate another node's key. Device approval
   stays ON; the drivers get their own tag, and ACLs give that
   tag the road endpoints (engines, sync) — random tailnet
   devices get less.
2. **The identity bundle** — public fingerprints the machine
   reports about itself (road_sense.py, BUILT): tailnet node
   ID, SSH host key fingerprints, a hash of /etc/machine-id (the
   full ID never travels). At provisioning, a TPM-backed key
   joins the bundle — the 7420's TPM 2.0 makes the key
   un-copyable, sealed to that physical machine.
3. **The registry at home** — provisioning is an *identity
   ceremony*: with Brian present, home records each laptop's
   bundle (in the fleet registry / ecosystem_central). From
   then on, sync verifies the bundle before accepting pushes
   or releasing snapshots and profile state — the sets that
   carry his briefings, calendar, and people data. Mismatch =
   random device, whatever it calls itself.
4. **Two kill switches** — a lost laptop must die twice and
   either suffices: revoke it in Tailscale (Brian, from his
   phone, in a minute) AND flag it revoked in the registry
   (sync refuses it even if the tailnet still trusts it).
   Identity runs both ways, too: the laptop pins home's keys
   and refuses a "home" it cannot verify.

## What it is not

- **Not the board.** The board is infrastructure facts; the road
  agent *supplies* some of those facts about its own machine.
- **Not the council.** It doesn't think in meetings; it files the
  trip log the council reads.
- **Not a second Altair.** One orchestrator. The road agent is a
  trusted field operator with a narrow charter. Brian considered
  carrying Altair himself on the road (2026-10-20) and rejected
  it — wisely, for four compounding reasons:
  1. **Split-brain.** Altair's authority comes from sitting at
     the center with the full state. A carried copy either forks
     (two orchestrators, diverging memories, conflicting routing
     — a reconciliation nightmare) or is a mere puppet terminal,
     which is what the console already is.
  2. **Identity.** By Brian's own rule, a named agent is model +
     role + accumulated context. A fresh Altair booted on a
     laptop has the SOUL.md but not the years — an impersonator
     wearing his name, not Altair.
  3. **The crown jewels travel badly.** Altair holds the keys:
     credential stores, ecosystem_central, A2A trust, the email
     gates. That belongs in the hub, not in a bag on a train that
     can be lost, stolen, or left in a café car.
  4. **Home must not go headless.** Altair's heartbeat runs the
     home ecosystem — briefings, watchdogs, Lyra's workers, the
     council — whether Brian is home or not. If Altair travels,
     the ecosystem stops thinking while Brian is away, which is
     precisely backwards.
  What travels instead: **a door and a delegate.** The console is
  the door (when a link exists, Brian talks to the real Altair,
  enthroned at home with his DB and fleet). The road agent is the
  delegate — narrow charter, senses and queues, escalating to
  Altair the moment a link allows.

## Build order

1. `road_sense.py` — the senses (BUILT, verified on k11-alpha).
2. `road_sync.py` — the supply line (BUILT, verified on k11-alpha:
   git orchestration + outbox store-and-forward; the scp transport
   is exercised for real when a second machine exists).
3. Profile authoring — at laptop provisioning (needs the laptops
   powered + Ubuntu + Hermes installed; rides the provisioning
   runbook).
4. Agent wiring — the profile calls road_sense / road_sync /
   link_up on link changes and a slow tick.

## Interface direction — RoadChat as an MCP server (OPEN)

Brian, 2026-10-20 ("maybe it's an mcp ... ???"): RoadChat the
plugin gets TWO faces. The console is its face to Brian; an
**MCP server** is its face to agents — road_sense readings,
sync status/trigger, brain search, outbox queueing, board
state, trip readiness, podcast progress, exposed as standard
MCP tools/resources over the tailnet (same access locks as
every service: tailnet bind, keys, no public exposure). Any
MCP host — Altair/Hermes, Muse, a customer's own assistant —
can then interrogate and drive a road node without bespoke
integration. MCP is the agent-facing interface layer, not the
plugin itself: the services (console, sync engine, Postgres
replica) still exist beneath it. Status: open direction,
to settle at provisioning/build time.
Brian's rationale, same morning: "being an mcp makes it
speak ai... and if someone had other tools, it integrated."
Interoperability is the point — RoadChat as MCP server can be
driven by any MCP host; RoadChat's own surfaces act as MCP
clients toward other tools (a user's calendar, email, their
own servers). Integration becomes configuration, not code,
and someone else's tools make their RoadChat more valuable
without SuccessBrian writing a single connector.
Assessment (Muse, 2026-10-20, at Brian's asking — does MCP
make RoadChat better?): NET YES, as the agent-facing layer.
Wins: Altair/Hermes (and Muse) get standard handles on the
road node instead of SSH-and-logfiles; integration with a
user's other tools becomes configuration; the typed tool list
doubles as enforcement of the safe-verbs doctrine (the MCP
surface IS the bounded verb set); protocol longevity outlives
any one agent framework; product install story shortens to
"add RoadChat to your agent." No help: sync, identity, power,
the console itself — the hard core is unchanged. Risks,
honestly: the protocol is young (auth story still maturing,
expect some rework), and an MCP server is a new tool-wielding
listener — it inherits the access locks, and tool results are
an injection surface, so road tools stay data + safe verbs
with sends home-gated (already doctrine). SEQUENCE: core
first (provisioning, sync, console), MCP wrap once the module
shapes stop moving — the functions already exist as clean
modules (road_sense, road_sync, eco_status), so the wrap is
cheap when its time comes.
