# Ecosystem State

**Generated:** 2026-09-27T20:00:11.113633+00:00

---

## Fleet

- **k11-alpha** (live): Altair/Morpheus/Penny/DeepSeek 150B. Interactive + goal loop.

- **k11-bravo** (in_pieces): 96GB RAM in wrapping. Future QLoRA training for small models.

- **x79-node-1..4** (planned): Dual M40 per node (48GB VRAM), 2x striped NVMe for Colibri, M.2 + threads for web/scraping. Content factory.

- **epyc-rome** (evaluating): $48 chip at Core 4. 256GB build for dual 150B + QLoRA.

- **aoostar-glm-1..2** (planned): GLM 5.3 on triple-striped NVMe. Not batch content nodes.

## Recent Decisions

## Capacity

- **inference**: healthy — Capacity covers demand with 50%+ headroom. No action needed....

- **storage**: healthy — 24TB NVMe planned vs ~220GB hot models. Ample. SATA tier sizes still open (see X79 Q3 for Brian)....

## Pending Inputs

- **live_health**: not_yet_available — Lyra will populate per-node CPU/RAM/disk/GPU utilization.

- **blog_placement**: not_yet_available — CMS will populate blog->node assignments.

- **anythingllm**: api_key_pending — Library stats once AnythingLLM API access lands.
