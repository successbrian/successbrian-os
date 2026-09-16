# The Model Fleet — named, specialized, local

SuccessBrian OS runs a named fleet of small models, each QLoRA-fine-tuned for ONE
narrow job, on self-owned hardware. The thesis: decompose, don't brute-force. A small
model can't be generally smart, but it can be excellent at one narrow task — at a
fraction of the cost of a frontier API, fully private.

## The fleet

- **Chuck** — MiniCPM5 2B — the narrow-task specialist: lead tagging, classification,
  routing, filtering. Fast, cheap, local.
- **Penny** — Qwen 2.5 7B — the extraction workhorse: structured data, heavier
  classification.
- **Morpheus** — Qwen 2.5 13B — deep analysis and intelligence discovery.
- **Shakespeare** — Llama 3.3 70B — long-form content writing.
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
