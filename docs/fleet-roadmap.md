# Fleet Roadmap — Brian's phase plan
<!-- PURPOSE: the build order for the fleet, in Brian's own phases.
     WHY: one authoritative sequence so sourcing, building, and deploying follow
     the same order.
     CALLED BY: Brian, Spencer, Altair, DealsDesk (sourcing follows the phases).
     NOTES: phases defined by Brian 2026-10-08, superseding the earlier draft.
     Standing gates: (1) scale-up spend only when making money; (2) measure
     before upgrading; (3) no prices in planning docs. -->

## Phase 0 — Everything we own, up and running
All currently-owned hardware assembled, installed, and working: X79 boards as far
as parts allow, DL380s Proxmox-sliced (2x 150B + remainder each), Colibri
resurrected on k11-alpha, fabric scripts deployed, multi-gig switch + cabling in.
EXIT: every owned box powered, networked, and doing its assigned job.

## Phase 1 — Complete the first two X79s
Finish the build of the first two X79 nodes (which two is Brian's call —
factory priority suggests Mantis-1/Mantis-2).
EXIT: two X79s fully built, NVMe + 2.5GbE in, factory workloads running.

## Phase 2 — Buy or complete a Node Echo
Echo is the special DDR4 one-off. Either complete the existing unit or source it.
EXIT: Node Echo online in its assigned role.

## Phase 3 — Complete the second two X79s
Finish Mantis-3/Mantis-4. All four X79s online: factories + training + fabric export.
EXIT: four X79s fully operational.

## Phase 4 — More Gen 8/9/10
Add rack servers to the mix: Gen8 (E5-2650 v2+, each = 2x 150B slices), Gen9
(E5-2650 v4+, DDR4, native NVMe — ideal fabric citizens), Gen10 as they come.
EXIT: inference lanes scaled to measured demand.

## Phase 5 — GPU / RAM / NVMe / SSD upgrades
Fleet-wide upgrades: GPUs where factories need them (Mantis-1, Mantis-2),
RAM/NVMe/SSD capacity where measurements show the bottleneck.
TRIGGER: Phase 0-4 measurements + revenue gate.

## Phase 6 — MS-02
Core Ultra 5 235HX + 128GB DDR5 + dual B70: DeepSeek 150B Q4 online on the
mini-PC track.
EXIT: MS-02 serving 150B.

## Phase 7 — Fill the 4U rack
More mini PCs until the 4U rack holds 8 minis + the MS-02.
EXIT: 4U rack full, mini-PC tier complete.

## What could change this
- Build blockers (parts availability) can swap Phase 1-3 order — Brian's call
- Measurements from Phase 0 rewrite bandwidth/upgrade assumptions (Phase 5)
- Revenue arriving early/late moves Phase 4-7 timing
- A model release that changes the footprint math
