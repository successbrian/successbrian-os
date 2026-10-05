# Ecosystem State

**Generated:** 2026-10-05T02:11:56.844752+00:00

---

## Fleet (tools/fleet_registry.json)

- **k11-alpha** (live): Interactive node (Altair/Morpheus/Penny/Sonic) + goal loop. Not a batch content node.

- **k11-bravo** (in_pieces): Build runbook drafted 2026-10-03 evening; build window was the Sun 2026-10-04 2:00 AM–2:30 PM Idemia shift. Future: chuck (2B), penny (7B), morpheus (14B), Qwen3.6-35B-A3B + task router.

- **x79-node-1..4** (planned): Content factory. 2x striped NVMe per node for Colibri, M.2 + threads for web/scraping.

- **epyc-rome** (evaluating): $48 chip at Core 4. Was the QLoRA training fit; 150B-tier scrapped 2026-10-03 (Qwen A3B switch). Role TBD.

- **aoostar-1..2** (planned): GLM 5.3 on striped NVMe. Not batch content nodes. (Memory notes 8x planned for the rack; registry tracks the 2 that entered the build plan — expand when funded.)

## Recent Decisions

## Capacity

- **inference**: healthy — Capacity covers demand with 50%+ headroom. No action needed....

- **storage**: healthy — 24TB NVMe planned (4 nodes x 3x 2TB NVMe.) vs ~100GB hot models. Ample. SATA tier sizes still open (see X79 Q3 for Brian...

## Pending Inputs (NOT-IMPLEMENTED)

- **blog_placement**: not_implemented — CMS feed of blog->node assignments. The blog network content factory is not built yet (x79 nodes: not_on_tailnet), so there is nothing to place.

- **anythingllm**: not_implemented — AnythingLLM API access (api_key_pending since before 2026-09-28). Once granted: workspace/document counts, embedding backlog, dedup stats.

## Node Health

- **x79-node-1..4**: not_on_tailnet — Verified absent from tailnet 2026-10-04 (`tailscale status` on k11-alpha). Content factory nodes not built yet.

- **k11-bravo**: not_on_tailnet — Verified absent from tailnet 2026-10-04 (`tailscale status` on k11-alpha). Build runbook drafted 2026-10-03; build window was Sun 2026-10-04 2:00 AM-2:30 PM Idemia shift — no tailnet sign-in yet.

- **epyc-rome**: not_on_tailnet — Verified absent from tailnet 2026-10-04 (`tailscale status` on k11-alpha). Evaluating; role TBD after the 2026-10-03 Qwen A3B switch scrapped the 150B tier.

- **aoostar-1..2**: not_on_tailnet — Verified absent from tailnet 2026-10-04 (`tailscale status` on k11-alpha). Planned rack nodes.

- **k11-alpha**: measured — Disk + queues + CPU load + RAM measured read-only via kssh. GPU/temp: no verified telemetry source on k11-alpha (780M iGPU) yet — marked not_measured, not 0.
