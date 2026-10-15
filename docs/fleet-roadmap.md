# Fleet Roadmap — Brian's phase plan
<!-- PURPOSE: the build order for the fleet, in Brian's own phases.
     WHY: one authoritative sequence so sourcing, building, and deploying follow
     the same order.
     CALLED BY: Brian, Spencer, Altair, DealsDesk (sourcing follows the phases).
     NOTES: phases 0-7 defined by Brian 2026-10-08, superseding the earlier draft;
     phases 8-13 defined by Brian 2026-10-10. MERGED 2026-10-10: the five
     activation waves (cluster core → k11-alpha offload → content factories →
     heavy compute → scale) are now woven into the phases as LIGHT-UP blocks —
     one plan, hardware and workloads together.
     Each phase below has BUILD (the hardware) and LIGHT-UP (what goes live on it).
     Standing gates: (1) scale-up spend only when making money — EXCEPTION: Phase 12
     cluster is gated on ecosystem readiness, not revenue (Brian 2026-10-10);
     (2) measure before upgrading; (3) no prices in planning docs.
     ERAS (Brian 2026-10-10): the plan runs in three eras. ERA 1 — BUILD WHAT WE OWN:
     assemble and operationalize owned hardware (X79s, Echo, everything on hand).
     ERA 2 — SCALE THE FLEET: grow with new acquisitions, but ONLY items that are
     RAV4-transportable — smaller rack systems, nothing that can't be carried out
     in a RAV4. ERA 3 — THE HOMESTEAD (post-move, permanent home): the 42U rack
     goes up and the serious rack builds land. -->

# ERA 1 — BUILD WHAT WE OWN
<!-- Owned hardware, assembled and working. X79s, Echo, everything on hand. -->

## Phase 0 — Everything we own, up and running (WAVE 1: cluster core)
BUILD:
0.0 Source the 2x 20U frames: DealsDesk wishlist row 24035 (ACTIVE) — 20U
    open-frame 4-post, adjustable depth to ~30in for DL380 rails,
    disassemblable (bolts not welds) for RAV4 transport to Fridley. Used OK,
    local pickup preferred. Assemble at Chaska: Frame A = 15U planned
    (Mantis-3/4, DL380s, R630, Echo), Frame B = 8U planned (Mantis-1/2).
    Both become satellite racks at Fridley.
0.1 Close the R630: get Aaron's reply → confirm RAM DIMM type (RDIMM?), exact
    1TB SATA count/type, 8- vs 10-bay backplane, caddies, rails, 10GbE
    included/optional, PCIe riser layout → arrange pickup → rack on Frame A.
0.2 Buy Echo: verify Drew's $550 listing still available → buy → rack on
    Frame A → Proxmox install → join cluster as 8th node → iGPU passthrough
    configured for transcoding.
0.3 Inventory both DL380s: exact gen, CPUs, RAM, storage, NICs, PSUs → per-box
    max-out plan (UPGRADE-FIRST rule) → Proxmox install → join cluster.
0.4 Switch check: count drops (R630 multi-port + 2x DL380 + 4x X79 + Echo ≈
    10+) → verify multi-gig switch covers it → cable both frames to one switch.
0.5 Cluster networking: corosync on its own VLAN/link, VM traffic separate,
    storage network for ZFS/NFS exports. Set VM CPU type to Haswell (common
    denominator for v2 + v4 mix) for live migration.
LIGHT-UP:
0.6 Echo becomes RACK TIMEKEEPER: timetable skeleton — hourly 150B slot,
    content-pipeline stages, maintenance windows, quiet hours.
0.7 Postgres job queues live on R630 (jobs, stages, locks — no Redis).
0.8 k11-alpha OFFLOAD (WAVE 2): Altair's service inventory → migration map →
    move scrapers, SearXNG, Postgres, monitoring, crons to R630/DL380 VMs one
    by one → verify each → k11-alpha goes AI-inference-only.
EXIT: every owned box powered, networked, clustered, and doing its assigned
job; k11-alpha pure inference; Echo keeping time.

## Phase 1 — Complete the first two X79s (WAVE 3: content factories)
BUILD:
1.1 Mantis-1: finish build — GTX 980 + RTX 5000 16GB in, NVMe + 2.5GbE in,
    verify airflow (5000 is blower-style, the easier of the two).
1.2 Mantis-2: finish build — dual M40s in, NVMe + 2.5GbE in, verify airflow
    (M40s are passive — cooling plan per box).
LIGHT-UP:
1.3 Both join Proxmox with GPU passthrough (Mantis-1: 980 + 5000; Mantis-2:
    dual M40) to their factory VMs. Build golden factory VM images — snapshot
    before any driver update.
1.4 CONTENT PIPELINE live: Postgres stages (written → rendered → transcoded →
    queued). Mantis-2 writer jobs (Shakespeare 70B batch) → Mantis-1 render
    jobs (SD1.5 volume + SDXL flagship) → Echo transcode (Quick Sync iGPU) →
    publish queue. Each stage pulls when ready; Echo's timetable sets the
    publishing cadence (e.g. Friday Substack).
1.5 Kill-and-repurpose drill: after the first batch completes, shut the
    factory VMs down and verify the GPUs/compute re-slice cleanly to a test
    workload. Proves the elastic pattern before it's needed for real.
1.6 First blogs publishing from the pipeline — income starts here.
EXIT: two X79s fully built, content pipeline running end-to-end, blogs feeding.

## Phase 2 — Buy Node Echo
Echo is the special DDR4 one-off — DECIDED 2026-10-10: BUY (not complete).
2.1 Verify Drew Covi's listing still available ($550, was $599 OBO — verified
    2026-10-10, 18mi, rails/IPMI/Noctua included, no drives).
2.2 Buy → transport (RAV4) → rack on Frame A → Proxmox install → join cluster
    as 8th node → iGPU passthrough configured for transcoding.
2.3 Echo becomes RACK TIMEKEEPER: timetable service live — hourly 150B slot,
    content-pipeline stages, maintenance windows. Other nodes take their
    schedules from Echo.
EXIT: Node Echo online on Frame A, in the Proxmox cluster, keeping time.

## Phase 3 — Complete the second two X79s (WAVE 4: heavy compute)
BUILD:
3.1 Source 4x Tesla V100 32GB (2 per box — DECIDED 2026-10-10). DealsDesk
    watch when Brian gives the word; verify X79 airflow per box (passive
    cards, 2x250W each).
3.2 Mantis-3: finish build — dual V100 32GB in, NVMe + 2.5GbE in.
3.3 Mantis-4: finish build — dual V100 32GB in, NVMe + 2.5GbE in.
LIGHT-UP:
3.4 Both join Proxmox with V100 passthrough to their VMs (Mantis-3: analysis/
    Sonic-class local; Mantis-4: 35B QLoRA training).
3.5 DL380s get the Colibri 3-tier (VRAM→RAM→NVMe): NVMe setup → Colibri
    config → first 150B test run → measure. ECHO GUARANTEES THE HOURLY 150B
    SLOT (Brian 2026-10-10: at least one big 150B process every hour).
3.6 Elastic worker fleet: golden Penny (7B) / Morpheus (14B) VM templates →
    worker pool that floods the cluster off the 150B window → scrape-parsing
    queue drains. Spin-up is seconds for these sizes.
3.7 Colibri on all GPU nodes (Mantis-1/2/3/4, DL380s, R630 once its NVMe
    lands). DECISION NEEDED: Echo exclusion (Brian 2026-10-01) vs "as much
    Colibri as possible" (Brian 2026-10-10) — revisit before this step.
3.8 MSV/Vera enrichment and TikTok Shop product research at full scale on
    the worker fleet.
EXIT: four X79s fully operational; hourly 150B + elastic parse fleet live.

# ERA 2 — SCALE THE FLEET (RAV4-movable only)
<!-- Grow with new acquisitions. Every item in this era must be RAV4-transportable.
     Smaller rack systems only — no full rows, no 42U, nothing that can't be
     carried out in a RAV4. WAVE 5: the scale wave — everything from here
     grows the fleet's capacity against measured demand and revenue. -->

## Phase 4 — More Gen 8/9/10 (movable units only)
Add rack servers to the mix: Gen8 (E5-2650 v2+, each = 2x 150B slices), Gen9
(E5-2650 v4+, DDR4, native NVMe — ideal fabric citizens), Gen10 as they come.
UPGRADE-FIRST RULE (Brian 2026-10-10): the two owned DL380s get maxed out
(CPU/RAM/storage/NIC) to serve ecosystem needs BEFORE buying anything new that
adds tension to the 20U's scarcity. Inventory both boxes first, then plan the
max-out per box against the workload list.
MOVABLE-ERA RULE: a few standalone units, RAV4-transportable one trip each —
not full rows. Era 2 rack target: TWO 20U open-frame 4-post frames (Brian
2026-10-10 — the X79s alone need 16U, so one 20U can't hold the fleet).
Frame A: 2x X79 @ 4U (Mantis-3 analysis, Mantis-4 training) + 2x DL380
@ 2U + Dell R630 @ 1U + Node Echo @ 2U = 15U (5U free).
Frame B: 2x X79 @ 4U = 8U (12U free) — the CONTENT frame
(Brian 2026-10-10): Mantis-1 (image/video factory) + Mantis-2 (text factory)
for the blog network.
Proxmox cluster (Brian 2026-10-10): all 8 nodes across BOTH frames — R630 +
2x DL380 + Mantis-1/2/3/4 + Echo. Mantis-1's 980+5000, Mantis-2's dual M40,
Mantis-3/4's V100s, Echo's iGPU all via PCIe passthrough. Echo = rack
timekeeper (scheduling/timing for the rack).
Dell R630 details: from Aaron Jongbloedt (in negotiation 2026-10-10 — DDR4; ROLE (Brian 2026-10-10):
Proxmox multi-role node — scraper/code VMs (Vera/MSV, SearXNG workers, code
execution) + ZFS bulk storage pool (backups, media) on the HDD bays. 4+
ecosystem needs in 1U. Start with Aaron's 1TB SATAs, backfill remaining bays
with 4TB 2.5" SATA HDDs). UPGRADES (Brian 2026-10-10): CPUs stay; RAM → 192GB
via matching 8GB sticks; dual NVMe via PCIe adapters (3 slots total, 1 spare
after dual NVMe); 1x 10GbE + 1GbE onboard. Note: rack scheduling moved to
Node Echo (Brian 2026-10-10) — the R630 keeps its workload roles (scrapers,
DBs, ZFS storage).
Frame B's 12U free holds Era 2 growth (B70 servers, more Gen 8/9/10). Both
frames break down to flat posts in ~20 bolts for the RAV4 move; both become
satellite racks at Fridley.
Either way: 4-post with adjustable depth (~30") for DL380 rails. The serious
rows wait for the Homestead.
EXIT: inference lanes scaled to measured demand.

## Phase 5 — GPU / RAM / NVMe / SSD upgrades
Fleet-wide upgrades: GPUs where factories need them (Mantis-1, Mantis-2),
RAM/NVMe/SSD capacity where measurements show the bottleneck.
TRIGGER: Phase 0-4 measurements + revenue gate.

## Phase 6 — MS-02 (B50, 70B-and-up inference node)
Core Ultra 5 235HX + 128GB DDR5 + internal Arc Pro B50 (16GB) + 2× 4TB NVMe.
Role: the fleet's 70B-and-up inference node (not 8B/32B — those live elsewhere);
runs the 150B as the low-cost on-ramp.
EXIT: MS-02 serving 70B+ models, 150B reachable.

## Phase 7 — Fill the 4U rack
More mini PCs until the 4U rack holds 8 minis + the MS-02.
EXIT: 4U rack full, mini-PC tier complete.

## Phase 8 — X3 test unit (single EVO-X3)
One EVO-X3 (Ryzen AI Max+ 395, 128GB LPDDR5X, OCuLink): buy early to test and
evaluate — Halo platform, OCuLink eGPU (B70 or AMD dGPU), 150B fully resident
in the 96GB VRAM allocation. De-risks the Halo buys downstream (Phases 9-10)
and answers whether the X3 has a bigger fleet role. Desktop blade, no rack
needed for one unit.
EXIT: X3 evaluated — keep as 150B box or reassign.

## Phase 9 — EVO-X5 Pro (long-term 150B home)
GMKtec EVO-X5 Pro (Gorgon Halo, 192GB unified): the 150B's long-term home —
whole model resident in one pool, single-box simplicity, DASH remote management.
GATED on revenue or measured need (Brian 2026-10-10): the MS-02/B50 on-ramp
covers 150B duty until this phase is justified. USB4 V2 eGPU upgrade path
(Phase 10) available later if throughput needs grow.
EXIT: 150B resident on the EVO-X5, MS-02 freed to 70B-class duty.

## Phase 10 — EVO-X5 + USB4 V2 eGPU (only if measured need)
Single Arc Pro B70 (or AMD dGPU, e.g. Radeon PRO W7900 48GB) on the EVO-X5's
USB4 V2 port via eGPU dock: ~192–208GB GPU-addressable, zero DDR5/NVMe tiers.
CORRECTION 2026-10-10: the EVO-X5 Pro has NO OCuLink port — that was the
EVO-X3 (Brian's confusion, resolved via spec check). eGPU runs over USB4 V2's
tunneled PCIe, with more overhead than a direct OCuLink link. Only happens if
the bare EVO-X5 proves too slow for the workload.
GATED on measured throughput shortfall in Phase 9, not on ambition.
EXIT: 150B running at target tok/s on one system.

## Phase 11 — Dual B70 on Xeon/AMD servers
B70s go where the iron can feed them: dual B70 (2× 32GB ECC) on Xeon/AMD
servers with the PCIe lanes, power budget, and cooling the MS-02 never had.
Roles: high-throughput inference, concurrent model serving, second 150B lane.
GATED on revenue and measured fleet demand.
EXIT: server-class GPU inference online.

# ERA 3 — THE HOMESTEAD (post-move, permanent home)
<!-- The 42U rack goes up here. Serious rack builds only. Gated on the move. -->

## Phase 12 — 4-node EVO-X5 cluster in 2U (the goal)
Brian 2026-10-10: the end-state is four EVO-X5 Pro units in a 2U rack —
verified fit (4× 80mm-wide units side-by-side horizontally in 2U/89mm).
The Phase 9 unit becomes node 1 — add 3 more, not 4.
Interconnect: USB4 V2 daisy-chain between nodes (2 ports per box chains all 4,
up to 4 supported). External: dual 10GbE per node into the fleet fabric
(8× 10GbE total — switch port count matters at buy time). ~640GB+ pooled
memory — 320B-class models resident, per GMKtec's own claim. Four external
330W bricks to place; verify rack airflow for desktop-cooled boxes.
The long-term destination of the whole plan: the fleet's flagship inference tier.
GATED ON ECOSYSTEM READINESS (Brian 2026-10-10 — not on revenue):
network (8× 10GbE switch ports + cabling in place), power/cooling (rack budget
and airflow verified for 4 nodes + 4 bricks), software (multi-node inference
proven — at least a 2-node cluster measured working), operations (DASH fleet
management, monitoring, unattended operation validated), and Phase 9 complete
(single EVO-X5 proven as the 150B home first). Distant future.
EXIT: 4-node Halo cluster serving 300B-class.

Flexibility note (Brian 2026-10-10): the nodes don't have to act as one —
split them (4× independent 150B instances, one per box, for parallel workloads)
or pool them (4-node cluster for 300B-class) depending on what the fleet needs
that day.

## Phase 13 — X3 fleet, units 2+ (top-shelf blades)
Additional EVO-X3 units with GPUs on the open 42U rack's top shelf, in custom
3D-printed blade mounts. Builds: X3 + B70 (or AMD dGPU) via OCuLink per unit —
the direct-PCIe dGPU hybrid the X5 can't do. GATED on the full chain
(Brian 2026-10-10): permanent home → 42U rack → top shelf available.
Distant future, after Phase 12's ecosystem is proven.
EXIT: X3 blade tier online.

## What could change this
- Build blockers (parts availability) can swap Phase 1-3 order — Brian's call
- Measurements from Phase 0 rewrite bandwidth/upgrade assumptions (Phase 5)
- Revenue arriving early/late moves Phase 4-11 timing (Phase 12 is gated on ecosystem readiness, not revenue)
- The move sets the Era 2/3 boundary: Era 2 ends when the fleet packs into the RAV4; Era 3 begins at the permanent home
- A model release that changes the footprint math
