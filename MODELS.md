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
- **Shakespeare** — Llama 3.3 70B — long-form content writing. (24K context)
- **Prometheus** (32K / 128K) — long-context reasoning.
- **Vision / Code / Embeddings / Speech** — the functional specialists.

## Routing

narrow + fast → Chuck · extraction → Penny · deep analysis → Morpheus ·
writing → Shakespeare · long context → Prometheus.

## The training loop

Altair and Lyra work together to QLoRA-fine-tune each model for its specific job in its
specific ecosystem. The models are trained, not just downloaded — that's what makes a 2B
tagger competitive with a 70B generalist on its one task.

## Efficiency

Token usage is tracked across processes, and Lyra actively finds ways to shrink it.
Self-measured, self-trained, self-improving.

## Deployment (k11-alpha — verified 2026-09-29)

| Model | Weight file | Quant | Service | Port | Ctx | Status |
|-------|------------|-------|---------|------|-----|--------|
| Chuck | MiniCPM5-2B-Q8_0.gguf | Q8_0 | chuck.service (disabled) | 11439 | 8K | Weight ready, not running |
| Penny | qwen2.5-7b-instruct-q6_k (2 parts) | Q6_K | penny.service | 11438 | 32K | Running, healthy |
| Morpheus | qwen2.5-14b-instruct-q6_k (4 parts) | Q6_K | morpheus.service | 11437 | 32K | Running, healthy — Altair's chat engine |
| Shakespeare | — | Q4 | — | — | 24K | X79 node (2x Tesla M40), not on k11 |
| Prometheus | meghan-q6.gguf (Gemma 4 26B A4B) | Q6 on disk / Q8 per Jul-31 lock | — | — | — | Weight on k11, no service |

Note: Penny's service raised 16K → 32K on 2026-09-29 per Brian's spec (32K was never a decision — the 16K was deploy drift; spec confirmed in altair-model-ecosystem-training.md).
