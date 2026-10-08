# Fleet Roadmap — phases with entry/exit gates
<!-- PURPOSE: the long-term plan past "up and running": what gets built, in what
     order, and what triggers each phase.
     WHY: hardware without a phased plan becomes a pile of boxes. Every phase has
     an exit gate so we know when to move on.
     CALLED BY: Brian, Spencer, Altair, DealsDesk (sourcing follows the phases).
     NOTES: 2026-10-08. Standing gates apply throughout: (1) scale-up spend only
     when the operation is making money; (2) measure before upgrading (network,
     etc.); (3) no prices in planning docs. -->

## Phase 0 — UP AND RUNNING (now)
Defined in fleet-map.md critical path: X79s built, DL380s Proxmox-sliced, Colibri
resurrected on k11-alpha, multi-gig switch + fabric cabled, fabric scripts deployed,
first 150B slice live streaming from the fabric.
EXIT: one 150B slice serving jobs over the fabric.

## Phase 1 — VALIDATE
Measure everything the later phases depend on:
- Colibri NVMe-tier traffic per worker (does 1GbE/2.5GbE suffice?)
- Tokens/sec per slice per box class (DL380, X79)
- KV cache growth vs context length (resets working as designed?)
- Fabric failover: kill an exporter, confirm the fleet doesn't notice
- 150B INT4 local quality check (unmeasured since the RSS correction)
EXIT: numbers recorded, fabric proven under load and failure.

## Phase 2 — SCALE INFERENCE
- More Gen8s, same pattern: each = 2x 150B slices + remainder slice
- Deploy Qwen3.8-Flash-Next Q6 and Qemma 4 26B on the fabric
- Build the deterministic inference router when manual placement hurts (~8+ lanes)
- Gen9s as DealsDesk finds the right units (DDR4, native NVMe, ideal exporters)
TRIGGER: measured demand + revenue gate (scale-up spend only when making money).

## Phase 3 — FACTORIES ONLINE
The X79s' real jobs, now with inference behind them:
- Mantis-1: image/video factory (+ GPUs when the factory needs them)
- Mantis-2: text factory (Shakespeare 70B on dual M40)
- Mantis-3: analysis/strategy box
- Mantis-4: training machine (QLoRA datasets -> local training)
- Blog network content pipeline running on local inference
EXIT: the 100-blog content engine fed by the fleet, not by rented APIs.

## Phase 4 — NEXT SILICON
- MS-02 + dual B70: 150B Q4 online (approved track, runs parallel to Phase 0-2)
- EPYC Rome/Milan 6-GPU builds when justified by measured load + revenue
- Retire or repurpose the weakest nodes as the fleet modernizes
TRIGGER: Phase 1 numbers show the need + revenue funds it.

## End state
Fully autonomous fleet (zero Hatch dependency for operation), all inference local
across CPU/NVMe/GPU tiers, 100-blog network fed by local models, agent escalation
ladder (Sonic -> 150B -> V4 Pro when credits allow) running on owned hardware,
income from the blogs and streams funding the next hardware cycle.

## What could change this
- Colibri measurements (Phase 1) rewrite bandwidth assumptions
- A model release that changes the footprint math (smaller 150B-class, bigger MoE)
- Revenue arriving early/late moves Phase 2/4 timing
- Hardware failures promote contingency work (then we plan spares — not before)
