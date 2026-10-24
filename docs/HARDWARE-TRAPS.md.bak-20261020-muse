# Hardware traps — GPUs to never recommend

Owner directive 2026-10-12: the Tesla K80 is a trap. This rule is enforced in
the agent contract ("What you never do" / contract rules). This doc is the
rationale, so no future agent has to re-derive it.

## Banned: NVIDIA Tesla K80 (Kepler)

- Dual GK210 GPUs, 12 GB each — **not** a single 24 GB pool. Two weak GPUs,
  not one big one.
- ~300 W power draw for Kepler-era throughput.
- R470 is the final driver branch; CUDA 11.x is the last toolkit. No security
  updates, no new features, ever.
- No tensor cores. Modern inference stacks (PyTorch 2.x, vLLM, CUDA 12+) have
  moved on; Kepler can't follow.
- It looks like 24 GB VRAM value. It isn't. Never recommend it, never buy it
  for AI inference, never let a deal scan surface it as a win.

## The EOL generation (R580 final driver, CUDA 12.x ceiling) — usable with pins

These lost driver support too, but their architectures still run a modern
inference stack if you pin versions:

- **Tesla V100 16/32 GB** (Volta, sm_70) — tensor cores, HBM2. The EOL value
  pick for inference.
- **Tesla P40 24 GB** (Pascal, sm_61) — 24 GB, server blower design, runs
  llama.cpp well.
- **Tesla M40 12/24 GB** (Maxwell, sm_52) — no tensor cores, but serviceable
  inference overflow.

Pin rules for the whole R580 generation:

1. Driver: never past R580 (580.xx). R580 LTS is supported through Aug 2028.
2. CUDA toolkit: 12.x only. CUDA 13 dropped sm_70 entirely.
3. PyTorch: 2.10 cu128 or 2.11 cu126 wheels. Never cu130 / PyPI-default wheels.
4. cuDNN below 9.15.1 (9.15.1 is what forced PyTorch to drop Volta).
5. vLLM: 0.8.x wheels, or 0.21 built from source on CUDA 12.6 + cu126 torch.
6. GCC ≤ 13 for anything compiled against CUDA 12 nvcc headers.

## Rule of thumb

When NVIDIA ends driver support for an architecture, enterprise supply floods
the secondary market — that is the buying opportunity. But it only counts for
cards whose architecture still runs a modern stack. Kepler doesn't. The R580
generation does, with the pins above. VRAM number alone is never the analysis.
