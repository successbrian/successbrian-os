# Brian's Decisions — System of Record Digest

**Generated:** 2026-09-27 19:32 UTC
**Source:** `altair.brian_decisions` (9 decisions)
**Note:** The PostgreSQL table is the source of truth. This document is the searchable view.

---

## Topic: INFRA

### INFRA-20260916: Fleet-wide psql fix: Should we fix all ~50 scripts using bare psql -U without -h/-p flags, or is there a centralized env fix approach? PGPORT=6432 from PID 1 breaks socket fallback across the fleet.
**Decided:** 

**Context:** 5 serendipity scripts fixed with -h 127.0.0.1 -p 5432. ~50 scripts in /home/successbrian/scripts/ still vulnerable to PGPORT=6432 socket fallback failure.

**Decision:** 

---

## Topic: X79

### X79-20260927-06: What is the hardware sourcing principle going forward?
**Decided:** 2026-09-27 14:30

**Context:** X79-SERVER V1.3 boards are Chinese aftermarket with no manual and unknown provenance. Brian will not buy mystery hardware again.

**Decision:** No more mystery hardware. Future buys are known-quantity only (K11s, EPYC from Core 4, anything with a real manual). The X79s get documented as a community use case for existing owners — "here's what I built, here's what worked" — NOT a buying recommendation. Spirit is generosity, not a warning label. All four builds as identical as possible for test-once-deploy-four-times.

---

### X79-20260927-04: Where does Shakespeare (70B) live permanently?
**Decided:** 2026-09-27 14:30

**Context:** Shakespeare needs ~40GB at Q4. Dual M40 = 48GB VRAM. Originally considered interim; Brian corrected to permanent.

**Decision:** Shakespeare's permanent home is the dual-M40 X79 node. "Always home for Shakespeare." 70B Q4_K_M (~40GB) fits in 48GB with headroom for context. ~8-12 tok/s at 150W power limit.

---

### X79-20260927-05: What workload do the X79 nodes serve?
**Decided:** 2026-09-27 14:30

**Context:** Not interactive chat. Batch content generation for the 100-blog network and related properties.

**Decision:** Batch content factory: blog posts, web page sales content, video scripts, email sequences. Nobody waits interactively — throughput over hours matters, not latency. ~10 tok/s = ~100+ articles per node overnight. Also absorbs AnythingLLM nightly maintenance (dedup, embeddings, hygiene) offloaded from k11-alpha.

---

### X79-20260927-01: What is the final X79 node architecture?
**Decided:** 2026-09-27 14:30

**Context:** Four X79-SERVER V1.3 dual-LGA2011 boards (Chinese aftermarket, no manual). Each has 2x Xeon E5-2650 v2, 4x DDR3 DIMM slots (64GB max), 2x PCIe Gen 3 x16 slots, 2x smaller PCIe (likely Gen 2) slots, 1x onboard M.2 NVMe.

**Decision:** Four identical dual-role nodes. Per node: 2x GPU for inference + 2x Gen 2 NVMe striped (RAID 0) for a Colibri-streamed model + 1x motherboard M.2 NVMe (single, boot) + remaining CPU threads for web hosting/scraping. No phase transition — inference AND worker jobs simultaneously from day one. Long-term ecosystem design.

---

### X79-20260927-02: What is the X79 storage layout?
**Decided:** 2026-09-27 14:30

**Context:** Each board has 1x onboard M.2, 2x small PCIe slots (Gen 2) for NVMe adapters, plus SATA ports. Triple-stripe vs split debated.

**Decision:** Boot from single motherboard M.2 NVMe (simple, reliable, I/O isolation). 2x Gen 2 NVMe striped via PCIe adapters as model volume (~4GB/s, 4TB). SATA SSD for databases/active scrape data, SATA HDD for logs/archives/cold storage. Full tiering: NVMe (hot) / SATA SSD (warm) / HDD (cold). Do NOT triple-stripe all three — keep OS isolated from model streaming I/O.

---

### X79-20260927-03: Is the Tesla M40 still the right GPU for the X79 nodes?
**Decided:** 2026-09-27 14:30

**Context:** M40 24GB at ~$105-150 used ($5/GB, cheapest 24GB path). P40 24GB at ~$220-300 (better arch, ~2x price for ~30-50% more throughput). $400-700 cards (3060 12GB, A4000 16GB, 3090 24GB) cannot provide 48GB across two slots for 70B.

**Decision:** M40 stays. 2x per node (48GB VRAM), power-limited to 150W each via nvidia-smi (decode is VRAM-bandwidth bound, ~10 tok/s holds at 150W; only prefill slows). Buy 7 more M40s (~$125 each) for uniformity across all four nodes. P40 premium does not pay back for batch inference.

---

## Topic: k11

### k11-inference-only: Where do K11-Alpha non-inference workloads and Node Zero services relocate?
**Decided:** 2026-09-15 21:00

**Context:** K11-Alpha currently hosts Postgres (ecosystem_central, people_unified), enrichment pipelines, agents, scrapers, AnythingLLM. Node Zero (srv1485029) hosts n8n.

**Decision:** K11-Alpha is being dedicated to AI inference as soon as possible — its RAM/CPU are reserved for the local model fleet. All non-inference workloads currently on K11-Alpha must be cleared off and relocated. Node Zero is being given up (NOT renewed) — n8n and everything on it must relocate too. Altair coordinates the migration plan; every agent inventories its own footprint and proposes a target home.

---

## Topic: no

### no-batch-delete: May Altair batch-delete or batch-modify skills, files, configs, DB objects, or services without reading each item and checking references first?
**Decided:** 2026-09-15 19:14

**Context:** Sep 13 2026: Altair mass-deleted ~50-60 skills under the max-autonomy mandate, sweeping up legitimate ones including hermes-agent (which 119 cron jobs depend on). It sat silently broken for 2 days. Root cause: no per-item read + no reference check + hard delete (no trash).

**Decision:** NO. Never batch-delete or batch-modify without reading each item and checking what references it. Always quarantine to ~/.hermes/skill-trash/ instead of hard delete. Any deletion of more than one item must be done ONE AT A TIME with a report between each. Verify nothing broke after. Encoded in SOUL.md anti-patterns + skill destructive-change-safety.

---
