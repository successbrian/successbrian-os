# Alpha Offload & Hosting Plan — everything runs on the rack base, alpha goes inference-only

<!-- PURPOSE: the working plan to solve web hosting, SaaS hosting, database
     hosting, the desks, and SuccessBrian OS itself as ONE problem: move every
     service off k11-alpha onto the rack fleet, verify each move, and leave
     alpha as a pure inference machine supporting the ecosystem.
     CALLED BY: Brian's directive 2026-11-24: "we need to solve web hosting,
     saas hosting, database hosting, all of our 'desks', successbrian os ---
     it needs to run everything" and "we need to plan and get this up and
     running so we can fully offload alpha and turn alpha into an inference
     machine to support the ecosystem."
     RELATION TO OTHER DOCS: this plan executes fleet-roadmap item 0.8
     (k11-alpha OFFLOAD, Wave 2) and extends ecosystem-needs-plan sections 1
     (web hosting), 2 (scrapers) and 6 (databases). Where tonight's directive
     changes the needs plan, it is flagged inline as [2026-11-24 UPDATE].
     DECISION VENUE: the open items below are part of the Dec 2 package
     (NAS / database / rack / hosting), under the mid-December solve-by
     deadline for database + data storage. -->

## Goal state

- k11-alpha runs inference only (Colibri / Sonic-class seats). No services,
  no desks, no databases, no scrapers, no crons that the ecosystem depends on.
- Every service the ecosystem needs runs on the rack base: the VIVO 25U frame
  (decided 2026-11-24, CART-SR25U, $219.99, 1,200 lb, depth 22-40") and the
  Proxmox nodes racked in it.
- Public-facing services (web, SaaS) are reachable by the public through
  whatever edge the Dec 2 hosting decision selects (see Open decisions).

## The rack base (landing zone)

Current population (Brian, 2026-11-24): 2x DL380p Gen8 (Proxmox, 2U each),
2x Gertoli (decider heartbeats), 2x Aoostar, bravo (GMKtec K11) — the minis
on rack shelves. Later per the roadmap: Dell R630 (1U), Node Echo (2U),
Mantis-3/4 (4U each) — total planned 15U + shelves, fits the 25U frame.

The DL380p service capacity is real: 2x E5-2670 v2 (20 cores) and 128GB
DDR3 per box, Proxmox already their assigned role. The MI25 upgrade
(2x MI25 per box, 150W cap, single 750W PSU per box — ruled 2026-11-23)
adds the GPU tier beside the Colibri slices; it does not displace the
service-VM role.

## Workload inventory — what moves, from where, to where

| Workload | Runs now | Exposure | Landing zone |
|---|---|---|---|
| PostgreSQL (ecosystem_central) | k11-alpha | internal | DL380 VM or R630 — Dec 2 database decision (needs-plan s.6 open question: Echo vs DL380 #1 split) |
| SuccessBrian OS services (Altair, clerk/board, crons, Lyra) | k11-alpha | internal | DL380 / R630 VMs |
| Desks (CampaignsDesk, DealsDesk, blogging desk, TradesDesk) | k11-alpha | internal | DL380 / R630 VMs |
| Scrapers (MSV/Vera fleet), SearXNG | gamma / alpha (split history) | internal | Rack VMs (roadmap 0.8) |
| AnythingLLM, monitoring | k11-alpha | internal | Rack VM (light tenants; AnythingLLM is 5.4GB disk / ~0.55GB RAM) |
| Web hosting (sites + blog network) | Supabase + Netlify free tier (bolt.new stack); Hostinger VPS successbrianvps.com DOWN since 2026-11-15 (disk full, stopped by Hostinger) | PUBLIC | Open decision (Dec 2) |
| SaaS: TrafficStreemz ($30/mo), ContactFlowCRM ($20/mo) | not launched — gated on hosting + finished code (launch-readiness law) | PUBLIC | Open decision (Dec 2); internal components can live on rack VMs |
| Per-user private databases | design only (PER-USER-PRIVATE-DATABASES.md) | internal | Follows the Postgres decision |

[2026-11-24 UPDATE] The needs plan (2026-10-10) held public web apps on
Supabase + Netlify "until the home-lab web tier is ready" and the
cross-cutting gates held home-lab web hosting until after the move.
Tonight's directive starts the home-lab service tier now, on the movable
rack — the rack is RAV4-transportable by design (bolted open frame, breaks
down flat), which is what keeps it inside the nothing-moves-twice gate.
Whether the PUBLIC edge also comes home, or stays on an outside host, is
the open Dec 2 question — it is not settled by this plan.

## Migration sequence (roadmap 0.8 pattern: one by one, verify each)

0. Prerequisites — none of the moves below start until these hold:
   - Rack ordered, built, powered; DL380s racked and clustered.
   - A VERIFIED off-alpha backup exists. This is a standing gap since the
     2026-10-23 audit and it gates the database move absolutely: Postgres
     does not move until its backup has been restored-tested off alpha.
   - Dec 2 decisions taken: NAS, database home, hosting edge.
1. Stateless and light services first: SearXNG, monitoring, AnythingLLM.
   Verify each on its new home before the alpha copy is retired.
2. The desks and SBOS services: CampaignsDesk, DealsDesk, blogging desk,
   TradesDesk, clerk/board, crons, Lyra. One at a time, verify, retire.
3. Scrapers consolidate onto rack VMs per roadmap 0.8.
4. PostgreSQL moves LAST among the internal services, with the verified
   backup in hand and a rollback path (alpha copy stays intact, read-only,
   until the new home has run clean for an agreed window).
5. Public edge per the Dec 2 hosting decision; SaaS launches still gated
   on finished code (launch-readiness law — hosting solved is necessary,
   not sufficient).
6. Alpha cutover: remove the service tenants (backups relocate to the NAS
   per the Dec 2 storage decision; model stores stay), confirm nothing in
   the ecosystem points at alpha for a service, declare alpha
   inference-only.

## Gates that bind this plan

- Launch-readiness law (Brian, 2026-10-22): no coded project is launchable
  without reliable hosting AND finished code. Hosting systems are an
  ecosystem need, tracked like machine needs.
- Backup-before-database-move (above). No exceptions.
- Measure-first: no hardware bought for a workload that is not proven
  running (needs-plan standing gate).
- Approval scope: this plan authorizes planning and preparation. Each
  outward action (orders, vendor contact, DNS changes, migrations that
  touch production data) takes its own explicit go from Brian.
- Power: the rack's current population fits one household circuit in
  practice; the full Frame A population does not (see the rack plan,
  2026-11-24). Circuit capacity is checked before each population step.

## Open decisions — Dec 2 package

1. DATABASE HOME: DL380 VM vs R630 vs the Echo/DL380 split left open in
   needs-plan s.6. (The Dec 2 database solution.)
2. HOSTING EDGE (the public half): revive/replace the Hostinger VPS as a
   public edge in front of the rack / cloud hosting for the SaaS products
   outright / public services served from the home rack / hybrid. Inputs
   owed before the sitting: the workload inventory above with each
   service's public-or-internal exposure marked (done in this doc), plus
   priced options per shape.
3. NAS ROLE in the backup chain (the Dec 2 NAS solution): the off-alpha
   backup that step 0 requires lands here.

## Status

- 2026-11-24: plan written at Brian's direction. Rack decided (VIVO 25U),
  order awaiting Brian's explicit go. DL380p MI25 bundle priced; the
  secondary riser cage (728543-B21) is the scarce part (~$349.50 from the
  one Canada listing; no used US listing) — route decision is Brian's.
- Next: Dec 2 prep package assembles NAS + database + rack + hosting
  options priced, for one resolving pass.

## Ruling appended 2026-11-24 (later, Brian)

Brian: "this system needs to host contactflowcrm and trafficstreemz."

- The SaaS home is SETTLED: ContactFlowCRM and TrafficStreemz are hosted
  on this system — the rack base. Cloud-hosting the SaaS products outright
  is struck from Open decision 2; it is no longer an option shape.
- What Dec 2 still decides is only the public EDGE: how public traffic
  reaches the rack (revived/replaced VPS as edge + tunnel, direct home
  public exposure, or a hybrid where only static web sits outside).
- The inventory table's SaaS row is amended by this ruling: landing zone
  reads "this system (ruled 2026-11-24)".
- Consequence for the sequence: the rack base now carries two production
  SaaS products, which raises the weight of step 0 — the verified
  off-alpha backup and the circuit check are prerequisites for paying
  customers' systems, not just internal tools. Both products remain gated
  on finished code under the launch-readiness law; this ruling settles
  their hosting home, not their launch readiness.
