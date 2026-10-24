# Fleet Map — current servers + expansion ideas
<!-- PURPOSE: one-page map of every server in Brian's fleet, its role, its fabric
     participation, and candidate additions with what each unlocks.
     WHY: the fleet grew by accretion; this is the first single view so new
     hardware goes where it pays instead of where it fits.
     CALLED BY: humans (Brian, Spencer, Altair) and DealsDesk sourcing.
     NOTES: updated 2026-10-08; expansion idea 9 added 2026-10-20. No prices in this doc (planning). -->

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

### 9. DDR4 1L mini-PC nodes — cheap REAP background lanes
Used 1-liter business minis (ThinkCentre Tiny, EliteDesk/ProDesk Mini,
OptiPlex Micro class) as streaming nodes for the REAP 150B: Colibri's floor
is 16 GB RAM, speed is secondary — the job is contributing lanes to the
fabric, not winning benchmarks. Machines are judged on platform, not on
the cost of their RAM: a machine shipping 8 GB stays in the search, its
sticks are simply worth $0 in the deal math (and 8 GB sticks are never
sourced as parts — `sourcing_floors.py`). Extremely selective spec (Brian
2026-10-20): best-in-class CPUs only — i7-8700 / i7-9700 / i9-9900 class
and up (an i5 is a settled-for node; not here), AVX2 always, never Celeron/Pentium-class, and never Intel
13th/14th-gen Raptor Lake — the degradation/burn-out class), two DDR4 SO-DIMM slots
with nothing soldered, 64 GB ceiling preferred, at least one M.2 NVMe
wired x4, storage (512 GB NVMe much more desired, 1 TB+ ideal, holding
the whole working set locally; an included 128 GB drive is worth $0 — it
gets pulled for a 256/512 GB drive — not a rejection), GbE minimum with a network upgrade path (the Lenovo Tiny PCIe
riser takes a real 10G NIC; a Wi-Fi M.2 slot can become a second wired
port; USB 3.2 Gen2 is the fallback). Buy RAM already installed — under the
2026 price regime the RAM in the deal can be worth more than the box.
Encoded as code in DealsDesk's `mini_node_scorer.py`; prices live there and
in `ram_price_reference.json`, not in this doc. Delivered-price caps are per
form factor (Brian 2026-10-20): 1L mini/micro $199, SFF $249, tower $299.

The SFF and tower siblings of the same families are in scope and worthy
(Brian 2026-10-20): native PCIe slots (a real 10GbE NIC drops in; towers
can later host a GPU lane), 4× UDIMM slots (128 GB ceilings vs the minis'
32), full-power non-T CPUs for CPU-bound streaming, and 3.5" bays that
satisfy the HDD floors inside the node. The trade is idle draw and
footprint. The scorer takes `form_factor: sff|tower` plus `dimm_slots`,
`pcie_slots` and `drive_bays_35` fields; example shapes score 112–137
vs 75–90 for the 1L finalists.

Towers are held REALLY strict (Brian 2026-10-20): a tower's job is hosting
big GPUs — V100-class and other 24 GB+ cards (V100 32 GB, P40 24 GB,
M40 24 GB, 3090-class), power-capped ("toned down") to about 150 W. Hard
gates in the scorer: a true PCIe Gen3+ x16 slot (x16 electrical — an
x16-shaped x4 slot does not count; the GPU class is generation-sensitive),
PSU ≥ 400 W with a GPU power lead (8-pin PCIe/EPS), and physical room for
a full-height dual-slot card. A tower that cannot host the GPU has no job
in this fleet — 1L/SFF already cover CPU-only nodes. Build note: these
server cards are passive — a tower build needs directed airflow over the
card.

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

## Network topology — the inference tier is its own world (Brian 2026-10-20)

The Colibri/inference machines run on their own network(s), separate
from the main network. Inference-to-inference traffic (cluster routing,
expert movement, node chatter) stays on those networks and never crosses
to the main one. The larger ecosystem communicates with the inference
tier over the main network in exactly two directions: jobs in, final
answers out. Everything heavy is private; everything that crosses is
small. This is why the hardware doctrine cares about multiple NICs per
node: one leg for the main network, one for the inference fabric, and
Wi-Fi/management as a third plane where needed.

## Inference access doctrine — outsiders don't get in (Brian 2026-10-20)

It must be HARD for anyone outside our Tailscale network to use the
inference machines for their work. The locks, in order:
1. Tailscale is the perimeter. Inference services bind to the tailnet
   interface (100.x) and the private fabric interfaces — never 0.0.0.0
   on a LAN-facing NIC. No Tailscale Funnel (that publishes publicly);
   Serve only, which stays inside the tailnet.
2. Tailnet ACLs: only feeder/operator devices may reach inference
   ports. Being on the tailnet is necessary, not sufficient.
3. COLI_API_KEY is always set on coli serve — a second, per-service
   lock, so even a foreign or stray tailnet device cannot call the API.
4. The inference fabric segments carry no internet route and no route
   to the main LAN. The feeder is the single audited door between the
   ecosystem and the inference tier.
5. Host firewall: default-deny inbound; inference ports answer only
   tailnet and fabric sources.

Audit snapshot 2026-10-20 (k11-alpha, read-only): model endpoints on
11436–11439 are bound 127.0.0.1 (correct); 443 is bound to the tailnet
IP only (correct); NO Colibri engine was running; one open item — a
uvicorn dashboard-api on 0.0.0.0:8000, reachable LAN-wide. Closing that
bind is the first remediation item when the hardening pass runs.

## Travel nodes — Dell Vostro + Dell Latitude 7420 (Brian 2026-10-20)

Two Dell laptops (a Vostro; a Latitude 7420 — corrected by Brian,
not a 5420) travel with Brian on Ubuntu 26.04. Neither is powered on
or tailnet-enrolled yet. (The active Windows tailnet device
'laptop-7civ44bf' is Brian's Acer 3 15 — a bigger, heavier Windows 11
machine that stays home; it is not a travel node.) Integration design:
- Tailscale members first: that puts them inside the inference access
  doctrine's perimeter as operator devices — SSH to k11-alpha, tailnet
  services, k11's exit node when a network is hostile.
- Code plane: SBOS + DealsDesk are git repos — clone to both laptops,
  k11-alpha stays the hub; commit/push/pull over Tailscale SSH from
  anywhere. The DealsDesk doctrine stack (scorers, trap registry,
  floors, class registry) is pure Python 3 stdlib — it runs on the
  laptops exactly as on k11, hotel Wi-Fi or not.
- Altair plane: Altair/model endpoints bind 127.0.0.1 on k11 today,
  so laptops reach them via SSH local-forward now; the durable form
  is a tailnet bind + ACL + API key, per the access doctrine (the
  laptops are operator devices, the highest-trust class of caller).
- Muse plane: enable Tailscale SSH on the laptops and Muse can work
  on them the same way it works on k11-alpha — provision, sync,
  diagnose, run the scorers on the road.
- Class fit: code runners + operator consoles by design; spare cycles
  can carry Chuck/Penny-class local models for offline travel work.
- Step zero: tonight's k11 code batch is uncommitted — commits are the
  sync mechanism, so committing it is what makes laptop clones real.

## The road core — k11 bravo travels too (Brian 2026-10-20)

Road trips (likely by train) carry THREE machines: both Dell laptops
AND k11 bravo. Bravo's current spec: 512 GB NVMe, 96 GB RAM. That
already runs the fleet's biggest models locally on the road — the REAP
150B needs 85 GB of disk and ~32 GB RAM as measured; Sonic needs 23 GB
and ~20 GB. Bravo on the road is the inference hub: the laptops are
consoles, bravo is the engine room, all on a private travel network
(the topology doctrine, portable edition), with Tailscale as an
optional uplink when the world offers one. Brian is willing to upgrade
bravo before the trip he calls the "Chicago TARDIS". The upgrade that
matters is STORAGE, not RAM: 96 GB already exceeds every Colibri
catalog recommendation; a 1–2 TB NVMe turns bravo into the full weight
library on wheels (REAP 85 GB + Flash-Next 186 GB + Sonic 23 GB, with
room for the library to grow).
Offline doctrine (Brian 2026-10-20): long no-Wi-Fi stretches are a
designed mode. Power up bravo and the convoy has AI power of its own —
weights mirrored from alpha pre-trip (REAP + Sonic + Penny/Morpheus),
laptops as consoles on the travel LAN, link_up failing over from alpha
(tailnet) to bravo (local) as its hub. Tailscale is a bonus uplink,
never a lifeline.
