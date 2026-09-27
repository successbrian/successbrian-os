# Ecosystem Capacity Report

**Generated:** 2026-09-27 19:36 UTC

The ecosystem's read on capacity vs demand. Verdicts: `healthy` / `tight` / `gap` / `watch`.

---

## Fleet

- **k11-alpha** (live): Altair/Morpheus/Penny/DeepSeek 150B. Interactive + goal loop.

- **k11-bravo** (in_pieces): 96GB RAM in wrapping. Future QLoRA training for small models.

- **x79-node-1..4** (planned): Dual M40 per node (48GB VRAM), 2x striped NVMe for Colibri, M.2 + threads for web/scraping. Content factory.

- **epyc-rome** (evaluating): $48 chip at Core 4. 256GB build for dual 150B + QLoRA.

- **aoostar-glm-1..2** (planned): GLM 5.3 on triple-striped NVMe. Not batch content nodes.

## Demand

- **blog_network**: 100 blogs x 2 articles/day, 8h overnight batch window.

- **anythingllm_maintenance**: Dedup, embeddings, hygiene. Offload target: X79s.

---

## Analysis

### [OK] inference

**Verdict:** healthy

- available_tok_s: 40
- needed_tok_s: 18.8
- headroom_tok_s: 21.2

**Recommendation:** Capacity covers demand with 50%+ headroom. No action needed.

---

### [OK] storage

**Verdict:** healthy

- nvme_tb_planned: 24
- model_hot_gb: 220

**Recommendation:** 24TB NVMe planned vs ~220GB hot models. Ample. SATA tier sizes still open (see X79 Q3 for Brian).

---

### [WATCH] build_bandwidth

**Verdict:** watch

- queue_depth: 4

**Recommendation:** 4 systems in build queue: k11-bravo, x79-node-1..4, epyc-rome, aoostar-glm-1..2. Brian is heads-down at two jobs. Recommendation: sequence builds one at a time (X79s first — parts on hand, highest content ROI), don't parallelize hardware builds against limited shop time.

---
