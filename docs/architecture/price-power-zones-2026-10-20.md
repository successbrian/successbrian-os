# Price → Power: cluster zones of the local-AI market

SuccessBrian fleet planning, 2026-10-20. Companion data to the
Price-to-Power map. Rule of the house: tok/sec is meaningless
without the model class. Primary yardstick = Sonic-class MoE
(35B, ~3B active); second number = dense 70B Q4
(Shakespeare-class). Basis tags: ● measured ◐ published
○ estimated. Prices checked Oct 2026 — a RAM-crisis market;
re-verify before buying.

## Systems

| System | Price | MoE tok/s | 70B Q4 | Basis | Note |
|---|---|---|---|---|---|
| DDR4 fleet node (i7 + 64GB, used) | $199 | ~2 | streams | ○ | REAP 0.66 tok/s measured on k11-alpha; power = count |
| Tesla P40 tower (used, whole) | $450 | ~18 | won't fit | ○ | VRAM $6–13/GB ◐ |
| Ryzen 8700GE mini (Colibri test class) | ~$800 | 9.9 | won't fit | ◐ | Colibri catalog, Vulkan |
| GMKtec K11 (64GB) | $1,000 | ~14 | ~2 | price ● | Walmart $999.59, 2026-10-20; speeds ○ |
| AOOSTAR MACO 470 (32GB) | $1,099 | ~22 | won't fit | price ● | direct, 2026-10-20; speed ○ |
| RTX 3090 tower (used, whole) | ~$1,900 | ~55 | won't fit (1 card) | ◐ | 32B dense = 37 tok/s measured (CFG); MoE ○; price CORRECTED (see note) |
| GMKtec EVO-X2 64GB | $2,200 | ~60 | ~5 | ◐ | speeds ○ (same iGPU/bandwidth as 128GB) |
| 2× RTX 3090 towers | ~$3,800 | ~55 | 15–22 | ◐ | dual-card 70B published; price ○ CORRECTED |
| Framework Desktop 128GB | $3,449 | 53–75 | ~5 | ● | measured band, class tests |
| GMKtec EVO-X2 128GB | $3,499 | 53–75 | ~5 | ● | measured band; price ◐ direct |
| AMD Ryzen AI Halo 128GB | $3,999 | 53–75 | ~5 | ● | same silicon; 10GbE, 1.2 kg, 1× M.2 |
| NVIDIA DGX Spark 128GB | $4,699 | 38.5 (120B MoE) | ~3–4 | ● | prefill ~5× Strix (RAG/agents) |
| Mac Studio 128GB | ~$4,999 | ~40 | ~9 | ○ | 546 GB/s; price band $4,799–5,400 ◐ |
| GMKtec EVO-X5 Pro 192GB | $6,799 | ~65–80 | ~6 | ○ | hosts 235B Q4 resident; dual 10GbE; 3× M.2 |
| 2× EVO-X2 cluster (RPC) | $7,000 | capacity | 235B ~3–5 | ○ | latency-bound layer split |

**CORRECTION (2026-10-20, later research pass):** the used
RTX 3090 is no longer a ~$700 card. Oct 2026 US sold prices
are **$1,199–1,540** (up ~70% during 2026). The two 3090
rows above are re-priced accordingly; their tok/s figures
stand. Any plan that assumed a cheap 3090 should re-run its
math — the P40 ($230–300) is now the undisputed capacity
buy, and the 3060 12GB (plan $300–400, tracker conflict
flagged) is the speed buy under it.

## Expansion (2026-10-20): under $750, the rack shelf, big RAM, fabric

Full detail in `zero-to-hero-roadmap-2026-10-20.md`. Summary:

- **Under $300 (Zone A, expanded):** the two-price market —
  an i7-8700T 1L mini is $199.99 street vs $509 refurb
  retail. Zone A speeds (○, bandwidth-scaled): 7B ~7–11,
  14B ~3.5–5.5, Sonic-class MoE ~3–7 tok/s (32GB to sit
  resident). SFF/tower siblings add the PCIe future.
- **$300.01–$499.99 (Zone B, "Headroom"):** buy RAM
  installed + GPU-host headroom. Anchor: Precision 3630
  renewed 32GB/1TB at $467.99. Traps: P1000 tax, 250W PSU
  bait, Raptor Lake creep at $499.
- **$500–$750 (Zone C, "First Real GPU"):** 3060 12GB
  tower (measured 7/8B 42–65, 14B 23–36 tok/s) or the P40
  24GB route at $520–680 all-in — the cheapest resident
  32B / Sonic Q6 seat.
- **The rack shelf (1U/2U):** DDR3 class (R720/DL380 Gen8)
  $50–300 · DDR4 entry (R730/Gen9) finished 128GB
  $600–1,200 · Xeon Scalable (R740/Gen10) bare $199–462,
  best cheap multi-GPU host · PCIe 4.0 class (R750) bare
  $3,000+ = THE CLIFF, buy later · DDR5 class $7,275+ =
  not 2026–27. EPYC single-socket (8 channels, 128 lanes)
  is the cheat code; watch PSB vendor lock.
- **Big RAM:** 256GB DDR3 $450–1,000 · 512GB DDR3
  $600–1,700 · 256GB DDR4 $1,700–2,800 · 512GB DDR4
  $3,000–4,600. Refurb DDR4 RDIMM is the loophole
  (32GB $160–235 vs $358 new median).
- **Storage/fabric:** 4× Gen3 NVMe ≈ 13GB/s of weight
  streaming; NVMe-oF only pays at 40G+. Networking ladder
  (4-node totals): 10GbE $300–500 = the sweet spot;
  **40GbE $400–900 = the value hack** for a closed
  inference fabric (ConnectX-3 Pro $48–115).

## Zones and their sourcing rules

- **Z1 The Stream Floor ($100–450)** — sub-3 tok/s per node on
  big models; clustering/streaming is the only way in. Buy by
  the node, win by the count. (The DDR4 fleet + REAP program.)
- **Z2 The Interactive Shelf ($900–2,200)** — 10–65 tok/s on
  MoE daily models; 70B mostly need not apply. Daily drivers.
- **Z3 The GPU Tower Belt ($450–3,200)** — fastest $/tok/s
  INSIDE the VRAM wall (24–48GB); the wall is the law.
  (Tower doctrine: V100/P40/3090-class, ~150W caps.)
- **Z4 The Unified Heavy Zone ($3,400–7,100)** — everything
  fits (128–192GB); MoE flies, dense 70B crawls (~5). A
  capacity play, not a speed play.
- **Z5 The Cluster Shelf ($6,600–14,000)** — pairs pool
  256–384GB; 235B+ resident; RPC pays a latency tax; a 10GbE
  fabric leg suits expert-streaming (Colibri-style).
- **Z6 The Rental Sky (no capex)** — rented API frontier
  (DeepSeek V4 Pro class): $/token, someone else's hardware.
  The rental balance ran dry 2026-09-27; the fleet exists
  because of it.

## Function × price (who fills the job)

- **Road hub (travels):** K11/MACO (light) · EVO-X2 64 ·
  AMD Halo (1.2 kg).
- **Home anchor / laptops' hub:** k11-bravo (owned) ·
  EVO-X2 128 · Halo · EVO-X5 Pro.
- **Interactive daily (Sonic):** 8700GE mini · K11 · MACO ·
  EVO-X2 · 3090 tower · Halo class.
- **Big-model resident (70–235B):** Strix 128GB · X5 Pro
  192GB · 2× Halo-class cluster.
- **Fleet stream node (REAP):** DDR4 nodes · P40 towers ·
  X5 pair on the fabric.
- **GPU burst (32B speed / prefill):** P40 tower · 3090 tower ·
  L40S-class.
- **Other classes (database, web, scrapers, code runners):**
  the DDR4 node class fills the cheap bands (machine-class
  registry: tools/dealsdesk/machine_classes.py).

*Planning instrument, not a benchmark paper. Sources: Colibri
catalog; ServeTheHome / Level1Techs / community llama.cpp
tests via Oct 2026 roundups; ComputingForGeeks GPU tests;
AMD + Micro Center; retailer checks 2026-10-20.*
