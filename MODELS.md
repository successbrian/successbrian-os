# The Model Fleet — named, specialized, local

SuccessBrian OS runs a named fleet of small models, each QLoRA-fine-tuned for ONE
narrow job, on self-owned hardware. The thesis: decompose, don't brute-force. A small
model can't be generally smart, but it can be excellent at one narrow task — at a
fraction of the cost of a frontier API, fully private.

## The fleet

- **Chuck** — MiniCPM5 2B — the narrow-task specialist: lead tagging, classification,
  routing, filtering. Fast, cheap, local.
- **Penny** — Qwen 2.5 7B — the extraction workhorse: structured data, heavier
  classification. (32K context)
- **Morpheus** — Qwen 2.5 14B — deep analysis and intelligence discovery. (32K context)
- **Sonic** — Qwen3.6 35B A3B (Q6_K) — the workhorse: reasoning, coding,
  synthesis. A base model, not a QLoRA trainee; the routing source of truth
  for Sonic is `tools/model_tiers.py`.
- **Shakespeare** — Llama 3.3 70B — long-form content writing. (24K context)
- **Prometheus** (32K / 128K) — long-context reasoning.
- **Vision / Code / Embeddings / Speech** — the functional specialists.

## Routing

narrow + fast → Chuck · extraction → Penny · deep analysis → Morpheus ·
workhorse reasoning/coding → Sonic · writing → Shakespeare · long context → Prometheus.

## The training loop

Altair and Lyra work together to QLoRA-fine-tune each model for its specific job in its
specific ecosystem. The models are trained, not just downloaded — that's what makes a 2B
tagger competitive with a 70B generalist on its one task.

## Efficiency

Token usage is tracked across processes, and Lyra actively finds ways to shrink it.
Self-measured, self-trained, self-improving.

## Deployment (k11-alpha — verified 2026-09-29)

Deployment is a snapshot, not identity (Brian's rule, 2026-10-20): a named
model is itself wherever it lives or runs — Shakespeare is Shakespeare on
any node. This table records where each model currently lives; hosts
change, names don't.

| Model | Weight file | Quant | Service | Port | Ctx | Status |
|-------|------------|-------|---------|------|-----|--------|
| Chuck | MiniCPM5-2B-Q8_0.gguf | Q8_0 | chuck.service (disabled) | 11439 | 8K | Weight ready, not running |
| Penny | qwen2.5-7b-instruct-q6_k (2 parts, ≈6.25 GB) | Q6_K | penny.service | 11438 | 32K | Running, healthy |
| Morpheus | qwen2.5-14b-instruct-q6_k (4 parts, ≈12.1 GB) | Q6_K | morpheus.service | 11437 | 32K | Running, healthy — Altair's chat engine |
| Shakespeare | — | Q4 | — | — | 24K | X79 node (2x Tesla M40), not on k11 |
| Prometheus | meghan-q6.gguf (Gemma 4 26B A4B) | Q6 on disk / Q8 per Jul-31 lock | — | — | — | Weight on k11, no service |

Note: Penny's service raised 16K → 32K on 2026-09-29 per Brian's spec (32K was never a decision — the 16K was deploy drift; spec confirmed in altair-model-ecosystem-training.md).

## Streaming tier — Colibri (verified 2026-10-20)

The big MoEs don't fine-tune or route like the fleet above; they stream.
Colibri (github.com/JustVugg/colibri) keeps dense/attention weights resident
in RAM and streams routed experts from NVMe behind a learning/LRU cache.
Backends: Vulkan + CUDA + CPU + Metal — an AMD iGPU is usable via Vulkan.

- **DeepSeek 150B** — DeepSeek V4 Flash REAP 150B (Colibri id
  `deepseek-v4-flash-reap`): V4-Flash pruned 256 → 132 experts. The 85 GB
  INT4 build lives on k11-alpha (17 safetensors shards); measured
  0.66 tok/s streaming on k11-alpha (Sep 2026). Colibri catalog: 16 GB RAM
  minimum, 32 GB as-measured; upstream publishes no speed for this build.
  RETIRED as an Altair routing tier 2026-10-02 (tools/model_tiers.py) — as
  fleet inference capacity it remains the goal: background lanes on DL380
  slices and cheap DDR4 nodes, where running at all beats raw speed
  (Brian 2026-10-20).
- **Sonic under Colibri** — the catalog entry for Qwen3.6-35B-A3B: 23 GB
  download, 10/20 GB RAM, measured 6.0 tok/s CPU and 9.9 tok/s Vulkan (iGPU)
  on a Ryzen 7 PRO 8700GE test box. The architecture is hybrid: 40 layers,
  only 10 full-attention (2 KV heads, head-dim 256), the rest Gated
  DeltaNet — KV ≈ 20 KB/token at FP16 (~2 GB at 98K context), not the
  ~10 GB a naive full-attention estimate gives.
- **Candidates, unconfirmed** — "qwen 3.8 flash" is likely Colibri's
  Qwen3.8-Flash-Next (125B + 51B n-gram, 186 GB download, 24/32 GB RAM,
  1.9–2.6 tok/s CPU measured); "jevos" is likely Colibri's System One API,
  which implements the Jev decision API (Laya / GLiNER2.5-Decide / Clef).
  Brian to confirm both.
