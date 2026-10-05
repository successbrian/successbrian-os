# Ecosystem Capacity Report

**Generated:** 2026-10-05 02:11 UTC

The ecosystem's read on capacity vs demand. Verdicts: `healthy` / `tight` / `gap` / `watch`.
Numbers carry source tags (measured / by_design / plan_target / plan_stated / estimate_unverified) — trust measured and by_design, treat the rest as planning figures.

---

## Fleet (from tools/fleet_registry.json)

- **k11-alpha** (live): Interactive node (Altair/Morpheus/Penny/Sonic) + goal loop. Not a batch content node. (verified: 2026-10-04 via kssh: up 7d 18h, 16 CPUs, 92GB RAM, load ~18)

- **k11-bravo** (in_pieces): Build runbook drafted 2026-10-03 evening; build window was the Sun 2026-10-04 2:00 AM–2:30 PM Idemia shift. Future: chuck (2B), penny (7B), morpheus (14B), Qwen3.6-35B-A3B + task router. (verified: 2026-10-04 via kssh tailscale status on k11-alpha: no bravo node on tailnet)

- **x79-node-1..4** (planned) [throughput: estimate_unverified]: Content factory. 2x striped NVMe per node for Colibri, M.2 + threads for web/scraping. (verified: 2026-10-04 via kssh tailscale status on k11-alpha: no x79 nodes on tailnet)

- **epyc-rome** (evaluating): $48 chip at Core 4. Was the QLoRA training fit; 150B-tier scrapped 2026-10-03 (Qwen A3B switch). Role TBD.

- **aoostar-1..2** (planned): GLM 5.3 on striped NVMe. Not batch content nodes. (Memory notes 8x planned for the rack; registry tracks the 2 that entered the build plan — expand when funded.)

## Demand

- **blog_network** [source: plan_stated (blog count) + plan_target (articles/day, batch window) + estimate_unverified (tokens/article)]: 100 blogs x 2 articles/day, 8h overnight batch window.

- **anythingllm_maintenance** [source: estimate_unverified (cpu_hours_per_night)]: Dedup, embeddings, hygiene. Offload target: X79s.

---

## Analysis

### [OK] inference

**Verdict:** healthy

- available_tok_s: 40
- available_source: by_design+estimate_unverified
- needed_tok_s: 18.8
- needed_source: plan_stated (blog count) + plan_target (articles/day, batch window) + estimate_unverified (tokens/article)
- headroom_tok_s: 21.2

**Recommendation:** Capacity covers demand with 50%+ headroom. No action needed.

---

### [OK] storage

**Verdict:** healthy

- nvme_tb_planned: 24
- nvme_tb_source: plan_target
- model_hot_gb: 100
- model_hot_gb_source: estimate_unverified

**Recommendation:** 24TB NVMe planned (4 nodes x 3x 2TB NVMe.) vs ~100GB hot models. Ample. SATA tier sizes still open (see X79 Q3 for Brian).

---

### [WATCH] web_serving

**Verdict:** watch

- sites_per_node: 25
- sites_per_node_source: derived: 100 plan_stated blogs / 4 x79 nodes (derived_from_registry)
- stack_options: static (Hugo->nginx) vs WordPress

**Recommendation:** Architecture decision needed: static-site generator (Hugo/Jekyll -> nginx) vs WordPress. Static: 25 sites/node is trivial, near-zero maintenance, perfect for SEO content blogs. WordPress: 25 PHP pools + 25 DBs per node strains 64GB DDR3 and creates 100 installs to patch. Recommendation: static unless a specific blog needs WP features. This is a question for Brian.

---

### [WATCH] build_bandwidth

**Verdict:** watch

- queue_depth: 4

**Recommendation:** 4 systems in build queue: k11-bravo, x79-node-1..4, epyc-rome, aoostar-1..2. Brian is heads-down at two jobs. Recommendation: sequence builds one at a time (X79s first — parts on hand, highest content ROI), don't parallelize hardware builds against limited shop time.

---
