# Ownership Register — what we own, what we don't, and what nobody may plan on

<!-- PURPOSE: the canonical answer to "do we own it, and can it be used in
     planning?" for every machine and build claimed anywhere in
     SuccessBrian OS or DealsDesk. Written 2026-11-24 at Brian's direction:
     "if there is any confusion in successbrian os and dealsdesk about
     whether things are owned or not, and whether something can be used in
     planning or not, let's please clear that up completely."
     CALLED BY: Brian, Spencer, Altair, DealsDesk, any planner.
     SOURCES AUDITED: public.owned_hardware (16 rows), public.ai_inventory
     (19 rows), successbrian_os.model_seats, dealsdesk.builds (25 rows),
     docs/fleet-roadmap.md, docs/fleet-map.md,
     docs/architecture/hardware-2026-10-07.md, Brian's statements on
     record (MEMORY.md and the 2026-11-24 session). -->

## The rule (Brian, 2026-11-24)

Brian: "you cannot plan that we own anything UNTIL I tell you we own it."

- A machine is OWNED for planning purposes only when Brian has said we
  own it. That set is called BRIAN-ATTESTED below, and it is the only
  planning-eligible set.
- A row in owned_hardware, a row in ai_inventory, a line in a roadmap or
  architecture doc, and a DealsDesk build are all CLAIMS. A claim is
  evidence to check with Brian — never ownership, never a planning base.
- Statuses like 'active' inside the tables describe the record's own
  bookkeeping. They do not attest ownership and must never be read as if
  they do. (This is exactly how the R630 — a roadmap purchase that was
  never closed — got planned on as a landing zone on 2026-11-24.)
- DealsDesk build statuses (planning / components_priced /
  parts_ordered / dream) are PLAN states. 'parts_ordered' means parts.
  A build becomes a machine only when Brian says it exists.

## A. Brian-attested owned — PLANNING-ELIGIBLE

| Item | Attestation |
|---|---|
| DL380-Gen8-1 (Mantis-9) | Brian, repeatedly; specs ruled in session 2026-11-23 (dual CPU, dual 750W PSU, 8x SFF bays, SFF confirmed) |
| DL380-Gen8-2 (Mantis-10) | Same as above |
| K11-Alpha (GMKtec K11) | Brian's working machine throughout the record |
| K11-Bravo (GMKtec K11) | Brian, 2026-11-24 rack-population statement ("bravo") |
| Aoostar pair, 6850H / 680M / 24GB (ai_inventory MACO-6850H-001/002; owned_hardware Aoostar-Charlie1/2) | Brian, 2026-11-24 ("the two aoostars"); matches his standing description of his Aoostars |
| Gertoli x2 | Brian, 2026-10-25 and 2026-11-24. NOT PRESENT in either inventory table — attested but unrecorded (see D6) |
| Tesla M40 24GB — ONE | Brian has confirmed owning an M40. Exact count and variant are NOT confirmed; plan on one, never more |

model_seats audited clean: seats sit only on Mantis-9/10, with honest
'current' vs 'design' states. No seat is planned on an unattested machine.

## B. Claimed in the records, NOT Brian-attested — NOT planning-eligible

These stay out of every plan until Brian rules on them (residue, section F).

| Item | Where claimed | Note |
|---|---|---|
| Veriton SFF-1 / SFF-2 (i5-8500T, RTX A2000 12GB / 6GB) | owned_hardware 'active'; hardware-2026-10-07 lists "Veriton SFFs (RTX A2000s)" as fleet | Bulk-seeded 2026-07-19. No statement from Brian on record |
| X79-Node-1 / X79-Node-2 | owned_hardware 'active' (64GB / 128GB, no GPU) | See the X79 conflict, D4 |
| B250-Mining-1 | owned_hardware 'active' | No statement from Brian on record |
| M1 Mac Mini | owned_hardware 'active'; ai_inventory 'active'; hardware-2026-10-07 lists it | No statement from Brian on record |
| Aoostar 7840HS pair (ai_inventory aoostar-maco-01/02, 'maintenance') | ai_inventory; hardware-2026-10-07 lists "2x Aoostar 7840HS" as fleet | Brian attests TWO Aoostars (the 6850H pair). Whether a second pair exists is residue R5 |
| X79 Build-01..04 (ai_inventory, 'maintenance') | ai_inventory build specs: 128GB, 2x M40 each | Build SPECS, not machines; they claim 8x M40 against one attested M40. See D4 |

## C. Planned / paper — records agree these are NOT owned

| Item | Evidence |
|---|---|
| K11-Zeus (2x EPYC 7252, 512GB, 6x MI50 — on paper) | owned_hardware status 'planned', location 'planned' |
| Precision 3620 | owned_hardware status 'planned'. DealsDesk is assigned to it in its workload_profile — that assignment is a plan, not a fact (see D5) |
| Supermicro 4U E5-2650v2 x4 (ai_inventory smc-4u-*) | source 'planned', details 'PENDING BUILD' |
| Supermicro 2027TR 4-node x2 (ai_inventory smc-2027tr-*) | source 'ebay', details 'PENDING_PURCHASE' |
| Dell R630 | fleet-roadmap 0.1 only: an unclosed purchase from Aaron. No table row anywhere. The 2026-11-24 offload plan was corrected to remove it (commit b7a6b84) |
| Node Echo | See D1 — split records, resolved to NOT eligible |

## D. Contradictions found, and their dispositions

D1. NODE ECHO — the two tables disagreed. owned_hardware: status
    'planned'. ai_inventory: status 'active' (a nearly empty row created
    2026-10-01), while fleet-roadmap 0.2 frames Echo as a purchase to
    make (Drew's $550 listing). Under the rule, the dangerous direction
    loses: Echo is NOT confirmed owned and NOT planning-eligible.
    Action taken 2026-11-24: ai_inventory's status check had no value
    able to say "unconfirmed" (active/standby/idle/maintenance/
    decommissioned all assert existence), so the constraint was widened
    by one value and the row set to 'unconfirmed':
      ALTER TABLE public.ai_inventory DROP CONSTRAINT ai_inventory_status_check;
      ALTER TABLE public.ai_inventory ADD CONSTRAINT ai_inventory_status_check
        CHECK (status = ANY (ARRAY['active','standby','idle','maintenance','decommissioned','unconfirmed']::text[]));
      UPDATE public.ai_inventory SET status='unconfirmed' WHERE node_id='node-echo';
    Reversible in one statement each. Residue R8 asks Brian to settle it.

D2. K11 CPUs were wrong in owned_hardware: 'Ryzen 9 7950X' / socket
    'AM5' for both Alpha and Bravo. ai_inventory, hardware-2026-10-07,
    and the K11's own 780M iGPU all say Ryzen 9 8945HS (FP7). Corrected
    2026-11-24:
      UPDATE public.owned_hardware SET cpu_model='Ryzen 9 8945HS', socket='FP7' WHERE id IN (13,14);
    Flagged, not changed: cpu_tdp still reads 170 for both K11 rows,
    which does not fit a 8945HS; the correct figure is not established
    from the record, so it stays until measured.

D3. DL380 details in ai_inventory are stale: '24 SFF bays',
    'PENDING_INSTALL', DDR3-1866. Attested truth: 8x SFF bays, in
    service under Proxmox running the Colibri slices, DDR3-10600R
    (owned_hardware rows 6/7 carry the corrected specs). The register's
    Section A governs; ai_inventory's free-text for the DL380s should be
    refreshed from owned_hardware when next touched.

D4. X79 is counted three incompatible ways: owned_hardware lists 2
    nodes (no GPUs); ai_inventory lists 4 'Build' rows (2x M40 each —
    8 M40s against one attested M40); DealsDesk carries 8 X79 board
    builds (Board #1-#8) plus a shared parts pool. No record can say how
    many X79 machines exist. NOT resolvable from the records — residue
    R2. Until Brian rules, no plan may rest on any X79 count.

D5. DealsDesk has no owned node. owned_hardware's Precision 3620 row
    assigns DealsDesk to a 'planned' machine; DealsDesk build #4
    'DealsDesk Node (3620)' is 'parts_ordered' and build #23 plans an
    R730 node instead. Fact: DealsDesk runs on k11-alpha today (its
    schema lives in ecosystem_central on alpha) and moves under the
    alpha-offload plan like every other desk. The 3620 and R730 are
    plans. Residue R9 covers the 3620 itself.

D6. The Gertolis are attested but unrecorded: Brian named them
    2026-10-25 and again 2026-11-24; neither inventory table has a row
    for them, and no ecosystem doc mentions the name. Rows get added
    when their identity is confirmed (residue R6) — guessing a mapping
    (e.g. that they are the Veritons under another name) would repeat
    the R630 error in reverse.

## E. DealsDesk hygiene (standing)

- dealsdesk.builds and its children describe intentions. Statuses stay
  in plan vocabulary; nothing in the dealsdesk schema confers ownership.
- buy_triggers and build_decisions record decisions to buy. A decision
  is not a purchase, and a purchase is not a machine in hand — Brian's
  statement is.
- A table COMMENT encoding the ownership rule now sits on
  public.owned_hardware, public.ai_inventory, and dealsdesk.builds, so
  the rule travels with the data (set 2026-11-24).

## F. Residue — only Brian can settle these

Each is UNKNOWN until he rules; none blocks the attested base.

- R1. Veriton SFF-1/2 — are they yours? (Fleet docs list them; the
  A2000s inside them feed DealsDesk build #26's planned GPU pool.)
- R2. X79 — how many X79 machines actually exist in hand?
- R3. B250-Mining-1 — yours, and still around?
- R4. M1 Mac Mini — yours?
- R5. Aoostars — two (6850H pair), or four (plus the 7840HS pair the
  architecture doc lists)?
- R6. Gertolis — what are they in spec terms, and are they any of the
  existing table rows under another name?
- R7. Tesla M40 — exactly how many do we own?
- R8. Node Echo — owned or not? (Currently marked unconfirmed/planned.)
- R9. Precision 3620 — owned, or still a plan?

## Changes made 2026-11-24 under this clearing

1. owned_hardware K11 cpu_model/socket corrected (D2).
2. ai_inventory status vocabulary gained 'unconfirmed'; Node Echo set
   to it (D1).
3. Ownership-rule COMMENTs placed on owned_hardware, ai_inventory,
   dealsdesk.builds (section E).
4. docs/alpha-offload-hosting-plan-2026-11-24.md corrected (R630
   removed as a landing zone, commit b7a6b84; ownership rule appended,
   commit 8e5a02c).
5. This register created. Nothing was deleted; every demotion is toward
   "not confirmed", never toward a false negative about what Brian owns.
