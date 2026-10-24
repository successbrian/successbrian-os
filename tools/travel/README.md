# SBOS travel kit — the ecosystem, in your bag

Brian 2026-10-20: the Dell travel laptops (Vostro + Latitude 7420,
Ubuntu 26.04) exist so travel doesn't mean disconnection. This kit is
the specialized code that lives on them. Design rules: pure Python 3
stdlib (runs on a fresh Ubuntu install), Tailscale is the only network
assumption, everything degrades honestly — offline is a mode, not an
error.

## Pieces

4. **council.py — the heartbeat council (BUILT, first sitting
   verified live 2026-10-20, note council/2026-10-20-0421.md).**
   Brian's order: Altair, Meghan and Lyra think through the
   build-out with each heartbeat. Cron :07/:37 (just after Altair's
   :05/:35 heartbeat; log ~/logs/council.log). Snapshots state,
   asks each seat through its real channel (Altair via Sonic :11439,
   Lyra via Morpheus :11437, Meghan ABSENT until Prometheus is
   served), writes one verbatim note per sitting to council/.
   Thinks only — never commits, never acts. A sitting costs ~7 min
   of local model time; a lockfile prevents overlap. Stop switch:
   delete the council line from crontab.

5. **ROAD_AGENT.md + road_sense.py + road_sync.py — the laptop
   resident (BUILT + verified on k11-alpha).** Each laptop gets a
   stripped Hermes profile (road-vostro / road-7420, authored at
   provisioning). road_sense.py = its senses (battery/link/
   tailnet/hubs -> mode home|road-linked|road-dark).
   road_sync.py = the supply line: manifest-driven sync TO AND
   FROM the home ecosystem on any link (git done safely — ff-only,
   never a dirty tree, diverged = HELD for a human; outbox
   store-and-forward with bravo as relay; weights staged, never
   link-synced). Live run on alpha: both repos HELD (dirty), outbox
   EMPTY, exactly as designed.

1. **eco_status.py — presence (BUILT, verified on k11-alpha).**
   One command answers "is my ecosystem there?": tailnet peers,
   Morpheus / Penny / dashboard liveness, SBOS + DealsDesk clone state.
   `--home` on k11 itself; away-mode probes the tunnel mouths below.

3. **SCENARIOS.md + trip_prep.py — readiness for UNKNOWN work
   (BUILT, verified live on k11-alpha).** Brian can't know which
   work the train trip will demand, so the kit targets coverage:
   SCENARIOS.md is the matrix (13 scenarios — people, work,
   failure — each with needs / covered-by / honest gap).
   trip_prep.py verifies the packable items tri-state (READY /
   MISSING / UNVERIFIED) and ends with the ecosystem verdict law.
   First live run: NOT READY — 42 uncommitted SBOS changes (step
   zero), the dealsdesk home-repo's standing backlog, REAP 150B
   UNVERIFIED (Colibri keeps it outside ~/models; its real home
   must be recorded so the bravo mirror can be verified), and
   bravo UNVERIFIED (not visible on the tailnet).

2. **roadchat.py + roadchat_tui.py — the travel console (BUILT,
   verified live on k11-alpha).** Brian's direction (2026-10-20):
   UNIFIED software managing the ENTIRE workflow. RoadChat is now
   the SBOS Console v1 — one app, room navigation: Chat (streaming,
   engines + native tools), Fleet (the board, full-size), Code (repo
   state + the machine-class and trap registries rendered from the
   live modules), Brain (search over the SBOS knowledge on the host;
   the exact slot AnythingLLM / Altair's second brain occupies when
   its API is wired), and More Rooms with People / Comms / Content
   as honestly-labeled planned tiles (wiring: Google Contacts +
   train-card inbox; Gmail + WhatsApp side channel; SEO → blogging
   pipeline). One app, one brain, every room — built in stages.
   One-file web chat (stdlib server, binds 127.0.0.1:8799) plus a
   line-based terminal twin with the same commands. Streaming chat
   against Penny/Morpheus (any OpenAI-compatible engine drops in);
   audio-visual ready in the browser — microphone in via Web Speech,
   spoken replies via speech synthesis, image attach that rides to
   the engine as an OpenAI image part for vision-capable home
   engines. Native tools in the chat: /status (eco_status, live) and
   a DealsDesk scorer panel that runs mini_node_scorer in-process and
   drops the verdict into the conversation. A graphical status
   board (📊 board) renders the same live data as tiles — home hub,
   each engine with its latency, each tailnet peer, each repo —
   green up / red down / amber dirty, auto-refreshing: what's up
   and what's not, at a glance (Brian 2026-10-20).

3. **link_up (planned) — one command to connect.**
   Verifies Tailscale is up, k11-alpha is reachable, then opens the SSH
   tunnels the away-mode tools expect:
   `ssh -L 11437:127.0.0.1:11437 -L 11438:127.0.0.1:11438 -L 8000:127.0.0.1:8000 successbrian@k11-alpha`
   and finishes with a git pull of both repos. When link_up exits 0,
   the laptop is, for every practical purpose, *on the fleet* — and
   RoadChat needs no changes, because home was always localhost
   through the tunnel mouths.
   HUB FAILOVER (Brian 2026-10-20): link_up picks its hub by reach-
   ability — k11-alpha over the tailnet when the world offers a
   network; k11 BRAVO on the travel LAN when it doesn't. Long dark
   stretches (train, no Wi-Fi) are a designed mode, not an outage:
   power up bravo and the convoy has real AI power of its own.

4. **Road tier (planned) — Altair's routing, extended to the road.**
   Chuck/Penny-class models run locally on the laptop for offline work
   (plane, dead zone, hostile network). The heavy offline tier rides
   on BRAVO (see fleet-map.md, "the road core"): weights mirrored from
   alpha before departure — REAP 150B (85 GB, ~32 GB RAM), Sonic
   (23 GB), Penny/Morpheus GGUFs — so a dark train still has the
   workhorse fast and the flagship present. Speeds grade honestly:
   Sonic is the road's interactive engine; the REAP is the slow deep
   lane, which was always its fleet doctrine — the point is running
   it at all. Bravo needs seat-outlet-class power (a large USB-C PD
   bank buys hours, not days), and the travel LAN is bravo-as-hotspot
   or a pocket router: laptops as consoles, bravo as the engine room. When the tailnet is up, the
   same requests can escalate to the home fleet — Morpheus, Sonic, the
   REAP lanes — through the tunnels. Local-first, home when reachable:
   the model-tier doctrine, with connectivity as the routing signal.
   RoadChat's engine picker is the manual seed of this.
   POWER DOCTRINE (Brian 2026-10-20): the kit must sip. Local
   inference is PLUGGED-IN work — on battery the laptop is a console
   and home is the engine; the road tier routes accordingly. RoadChat
   itself polls politely (30 s visible, paused hidden, 120 s in
   saver mode), caches status probes server-side, and turns saver on
   by itself when the battery runs low unplugged.

5. **Road inbox (planned) — nothing done on the road is stranded.**
   Notes, scored listings, code changes made offline queue locally and
   sync home on the next link_up. DealsDesk already runs offline (the
   doctrine stack is stdlib); the inbox is what carries its results
   back into the ecosystem.

## Doctrine ties
- The laptops are operator devices under the inference access doctrine
  (fleet-map.md): highest-trust callers, inside the Tailscale perimeter.
- Class fit: code runners + operator consoles (machine_classes.py).
- Step zero for all of it: the k11 code batch gets committed — git is
  the sync mechanism.
