# Fleet Map — current servers + expansion ideas
<!-- PURPOSE: one-page map of every server in Brian's fleet, its role, its fabric
     participation, and candidate additions with what each unlocks.
     WHY: the fleet grew by accretion; this is the first single view so new
     hardware goes where it pays instead of where it fits.
     CALLED BY: humans (Brian, Spencer, Altair) and DealsDesk sourcing.
     NOTES: updated 2026-10-08. No prices in this doc (planning). -->

## Current fleet

| Node | Hardware | Fabric | Role |
|---|---|---|---|
| k11-alpha | Ryzen-class, NVMe, 2.5GbE | exporter + source | Main node: PostgreSQL (ecosystem_central), 150B weight source of truth, agent home |
| k11-bravo | 2.5GbE | exporter | Second k11 node |
| Mantis-1 | X79 dual E5-2650 v2, 64GB DDR3, NVMe RAID0 | exporter | Image-first / video-capable factory |
| Mantis-2 | X79 dual E5-2650 v2, 64GB DDR3, NVMe RAID0 | exporter | Text factory (Shakespeare 70B lives here, dual M40) |
| Mantis-3 | X79 dual E5-2650 v2, 64GB DDR3, NVMe RAID0, dual Tesla V100 32GB | exporter | Analysis / strategy box (Sonic-class local) |
| Mantis-4 | X79 dual E5-2650 v2, 64GB DDR3, NVMe RAID0, dual Tesla V100 32GB | exporter | Training machine (35B QLoRA) |
| Mantis-5 | dual-LGA2011 build | future exporter | MSV scraping + Vera/enrichment |
| Mantis-6 | dual-LGA2011 build | future exporter | SearXNG workers + AI analysis |
| Mantis-7 | dual-LGA2011 build | future exporter | Scraper-fleet overflow (proposed) |
| Mantis-8 | dual-LGA2011 build | future exporter | Scraper-fleet overflow (proposed) |
| Mantis-9 (DL380 #1) | 2x E5-2670 v2, 128GB DDR3, 4x 1GbE | consumer (+pinch exporter) | Proxmox: 2x 150B inference slices + people.people PostgreSQL slice |
| Mantis-10 (DL380 #2) | 2x E5-2670 v2, 128GB DDR3, 4x 1GbE | consumer (+pinch exporter) | Proxmox: 2x 150B inference slices + blog app tier slice |
| Aoostar x2 | 24GB, NVMe, 2.5GbE | exporter | General utility (6 more planned for 4U rack) |
| MS-02 | Core Ultra 5 235HX, 128GB DDR5, Arc Pro B50 | future | 70B-and-up inference node; 150B low-cost on-ramp |
| EVO-X5 ×1 | Ryzen AI Max+ PRO 495, 192GB LPDDR5X, dual 10GbE, DASH | future | 150B long-term home (Phase 9; becomes cluster node 1) |
| EVO-X5 ×4 | 4 units in 2U, USB4 V2 daisy-chain, dual 10GbE/node | future | 4× independent 150B or 320B-class cluster (Phase 12; gated on ecosystem readiness) |
| EVO-X3 ×1 | Ryzen AI Max+ 395, 128GB LPDDR5X, OCuLink | future | Test unit (Phase 8) — Halo/OCuLink/150B eval |

Inference lanes today: 4 (DL380 slices) + MS-02 track. X79s keep their factory jobs.

## Expansion ideas

### 1. More DL380 Gen8s — linear inference scaling
Each additional Gen8 = 2 more 150B Colibri slices + 1 remainder slice, same Proxmox
pattern as #1/#2. Cheapest path to more lanes; fabric consumer from day one.
DealsDesk: already sourcing 64GB+ racks; Gen8 floor E5-2650 v2+.

### 2. Gen9 rack servers — the ideal fabric citizens
DDR4, native NVMe, 2.5GbE+ onboard. Both exporter AND inference in one box.
Replaces the Gen8 "consumer-only" limitation. DealsDesk: Gen9 floor E5-2650 v4+.

### 3. Backup box — fleet backups need a home
The old plan put fleet backup on DL380 #2; it's inference now. A HDD-heavy box
(big slow spinning disks, 1GbE fine) as the backup target for Proxmox dumps,
PostgreSQL dumps, and model weight archives.

### 5. Fabric coordinator — model sync + health on a schedule
An Aoostar runs `model-sync.sh` on cron after any weight update and
`fabric-health.sh` on a schedule, writing results to Postgres. Zero-Hatch-operation
per the autonomy mandate. (Could also live on k11-alpha; separate box is cleaner.)

### 6. Inference router — deterministic job routing
Python router: job in → pick host by queue depth + health (reads the fabric health
table). Dumb frontend, smart backend; no model ever routes. Home: Aoostar or
k11-alpha. Build when lanes exceed what manual placement handles (~8+).

### 7. GPU expansion for Mantis-1 — image/video factory
The image/video factory will want GPUs eventually. M40s are the known-good cheap
path on X79; B70s are the future. Not urgent — factory isn't built yet.

### 8. SearXNG / scraping scale-out
As the scraper fleet grows past Mantis-5..8, more dual-2011 builds or Z240 SFFs.
Egress stays on the free IPs (gamma, node zero, k11-alpha) until revenue.

## Priority order (Spencer's read — Brian decides)
1. Get the current fleet UP AND RUNNING (below) — everything else waits
2. Fabric coordinator on existing Aoostar (near-zero cost, unlocks autonomy)
3. More Gen8s (linear inference lanes, known pattern)
4. Backup box (unblocks Proxmox dumps safely)
5. Gen9s (when DealsDesk finds the right units — quality over speed)
6. Router (when manual placement hurts)
7. Mantis-1 GPUs, scraping scale-out (demand-driven)

## Critical path to UP AND RUNNING (2026-10-08)
1. X79s built (Mantis-1..4) with NVMe + 2.5GbE NICs
2. DL380s: SSDs in, Proxmox on, 3 slices each (2x 150B + remainder)
3. Colibri resurrection on k11-alpha — MEASURE NVMe tier traffic per worker
4. Multi-gig switch in place, fabric cabled (3x 1GbE DL380s, 2.5GbE exporters)
5. Deploy tools/fleet-fabric (fill conf per node, export, connect, sync, verify)
6. First 150B slice live on DL380, streaming from the fabric
