# Mini-PC evaluation — primary node class (checked 2026-10-20)

PURPOSE: verified specs and delivered totals for the four mini PCs Brian
compared for the fast/interactive tier, so no future evaluation re-derives
lane widths or prices from listings. Companion to fleet-map.md (which is
planning-only, no prices) and docs/HARDWARE-TRAPS.md (the x2-slot and
soldered-RAM traps came out of this evaluation).

Prices are item + shipping, BEFORE TAX (checkout never entered), checked
2026-10-20. Amazon is excluded — it refuses AI-agent access, so its prices
were never visible to this process.

## The machines

| Machine | CPU / iGPU | RAM | M.2 slots | NICs | Best delivered |
|---|---|---|---|---|---|
| GMKtec K11 | Ryzen 9 8945HS (8C/16T) / Radeon 780M | 2× DDR5 SO-DIMM, up to 96 GB | **2× Gen4 x4** (both full width) | 2× 2.5GbE (Intel I226-V) | **$999.59** Walmart (free ship, next-day) / $999.99 Newegg |
| AOOSTAR MACO 470 | Ryzen AI 9 HX 470 (12C/24T) / Radeon 890M | 32 GB LPDDR5-8000 **soldered, max 32 GB** | 3× 2280: 1× Gen4 x4 + **2× Gen4 x2** | 2× 2.5GbE | **$1,099** aoostar.com (site promo AI470 advertises $1,049, unverified at checkout); AliExpress $1,224.49 delivered |
| Bosgame VTA-439 | Ryzen AI 9 HX 470 / Radeon 890M | 2× DDR5 SO-DIMM (ceiling plausibly 96 GB; Newegg's "256 GB" claim is not credible) | 3× M.2; primary Gen4 x4 verified, **expansion-slot widths unpublished everywhere** | 2× 2.5GbE | $1,227 Newegg (incl. $50 promo gift card) |
| Acemagic F5A (barebones) | Ryzen AI 9 HX 470 / Radeon 890M | SO-DIMM variant, ships empty | 3× 2280: 1× Gen4 x4 + 2× Gen4 x2 | 2× 2.5GbE | $569 direct — no RAM/SSD/OS; the 32 GB + 1 TB prebuilt on the same page is $1,029 |

All four: OCuLink (PCIe Gen4 x4 — can host a real 10/25GbE NIC via adapter),
2× USB4 (Bosgame: at least 1 front USB4 verified). Dual 2.5GbE on every
machine means the both-ports fabric plan works on any of them; note a single
NVMe-oF flow over bonded links still rides one link (~2.5GbE) under LACP —
NVMe-oF native multipath is what actually stripes.

## Verdicts under Brian's rules

- **Upgradeability is priced by the moving RAM market.** At Oct 2026 prices
  (DDR5 64 GB SO-DIMM kits $800–$1,700 new), taking a K11 to 64 GB costs
  roughly the whole machine again — so the K11's upgradeability scores near
  zero TODAY and rises only if RAM falls. The F5A barebones math collapses
  the same way: $569 + market RAM/SSD ≈ bundled money for a worse position.
- **Cheapest complete system:** K11 at ~$999.59.
- **Cheapest HX 470 complete system:** MACO 470 direct at $1,099 — but its
  RAM is soldered at 32 GB and two of its three M.2 slots are x2. It is the
  stronger CPU/iGPU sealed appliance, not a platform.
- **Dark horse:** the VTA-439 (HX 470 + SO-DIMM + 3 slots) would be the
  best of both if its expansion slots are x4. Nobody publishes the widths —
  Bosgame support or a teardown decides it.

## Colibri fit (catalog facts, Colibri repo)

- Sonic (Qwen3.6-35B-A3B): 23 GB download, 10/20 GB RAM; measured on a
  Ryzen 7 PRO 8700GE box (780M): 6.0 tok/s CPU, 9.9 tok/s Vulkan iGPU.
  HX 470 / 890M boxes should beat that; the K11 is roughly that class at
  half the RAM.
- DeepSeek V4 Flash REAP 150B: 85 GB download, 16 GB RAM minimum / 32 GB
  as-measured, no upstream speed published. Disk-bound: put the model file
  on a full-x4 drive. The DeepSeek engine is not in Colibri's
  measured-faster-on-iGPU set (Vulkan can be forced, unmeasured).
- Qwen3.8-Flash-Next (candidate for Brian's "qwen 3.8 flash"): 186 GB
  download, 24/32 GB RAM, 1.9–2.6 tok/s CPU measured, 3.99 with int4
  experts.

## Open items

- Bosgame expansion-slot lane widths (support ticket or teardown).
- Amazon prices (requires Brian at the keyboard — agent access is refused).
- Brian has not picked a primary machine as of 2026-10-20.
