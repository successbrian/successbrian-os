# Zero to Hero: building a local-AI ecosystem on a savings budget

SuccessBrian coaching roadmap, 2026-10-20. Companion to
`price-power-zones-2026-10-20.md` (the systems map). This doc is
the PEOPLE map: who needs what, what it costs over 2–3 years of
saving, and where each person can STOP.

Prices checked Oct 2026 — a RAM-crisis market. Every price here
is a snapshot: re-verify at purchase time. Basis tags:
● measured ◐ published ○ estimated.

## The two rules that shape everything

1. **Over $500 is a several-month save.** For most people Brian
   coaches, $50–150/month is the gear budget. $50/mo = $300 /
   $600 / $1,200 / $1,800 at 6 / 12 / 24 / 36 months. $100/mo
   doubles that; $150/mo = $900 / $1,800 / $3,600 / $5,400.
   So the lower zones must be STRONG — a real, working
   ecosystem — not a waiting room for the expensive zones.
2. **Not everyone is climbing to the same summit.** Most people
   are not Brian. They want to blog a little, answer emails,
   scrape some leads, crunch CRM analytics, make a few videos.
   Each workload scenario below has a TERMINAL CEILING: a setup
   that is a complete ecosystem for that work. Reaching your
   ceiling is finishing, not falling behind.

**Zone 0 is free.** An existing laptop/desktop + llama.cpp or
Ollama (1–3B models on 8GB RAM, 7–8B on 16GB) plus a 90-day
skills sprint — Linux, the inference stack, Docker, networking,
market literacy — done WHILE saving the first tranche.
Skills are the first zone. They cost nothing and every later
zone runs on them.

**The capability ladder (Q4-class, by RAM):** 16GB → 7–8B ·
32GB → 14B + Sonic-class 35B MoE · 64GB → 32B properly ·
128GB → 70B dense resident · 256–512GB → 150B
resident/distributed. RAM is the ladder; that's why, in a RAM
crisis, you buy RAM *installed in machines*, never loose sticks.

**Absolute traps (all zones, all scenarios):** Tesla K80
(Kepler, dead CUDA, no usable FP16 — and beware "Tesla 24GB"
listings that are a K80 in a trenchcoat; the P40 is the real
24GB card) and Intel 13th/14th-gen Raptor Lake (the
self-degrading Vmin class). Enforced in code
(`hardware_traps.py`), not folklore.

## THE LOW-END DESTINATION — "The Homestead Spec" (Brian, 2026-10-20)

For the low-end group, the destination is a defined machine
(or 2–3), not a direction:

- **The 150B, running SLOWLY.** REAP as a background /
  contributing mind (0.3–1 tok/s class is fine — speed was
  never the point; Colibri runs it from ~32GB RAM + 85GB of
  NVMe, less RAM = slower, still running).
- **Sonic at 10 tok/s or better.** The interactive bar for
  a daily-driver workhorse.
- **The whole household aboard:** their agent, n8n, crons,
  Postgres, the CRM — the service stack is only ~6–10GB.
  This is the customer pattern ("everyone gets an Atlas
  and a Sonic") at homestead scale.

**The honest gate:** a plain DDR4 CPU node does Sonic at
~3–7 tok/s — it does NOT clear the bar alone. Exactly four
things clear it, cheapest first:

1. **A P40 24GB in a gated tower** — Sonic-class MoE
   ~15–18 tok/s ○.
2. **A 3060 12GB host with 64GB RAM** — MoE offload
   11–17 tok/s ◐.
3. **A Vulkan APU mini** — 8700GE/780M measured 9.9 tok/s
   ● (right AT the line); HX 370/470 + 890M clears it
   (~14–22 ○).
4. **Strix Halo class** — 53–75 tok/s ●; clears it five
   times over, at five times the money. Not the low end.

**Three shapes that meet the spec:**

| Shape | Build | Total | Notes |
|---|---|---|---|
| D1 "One Tower" | gated tower, 64GB installed, P40, 1.92TB NVMe | ~$650–850 ○ | everything in one box; Sonic + REAP contend for the machine — schedule the 150B for nights |
| D2 "Two-Box Homestead" | $199 i7 mini (always-on: agent, n8n, crons, Postgres — 35W) + P40 tower or APU mini (inference seat, wakes for work) | ~$600–800 over time ○ | the power-sipping answer; REAP slices live on both; this is Path A's natural end-state |
| D3 "One Mini" | K11-class HX mini, 64GB | ~$1,000 ● price | Sonic ~14 ○, REAP streamed slow, services aboard; simplest and quietest, priciest per seat |

64GB is the honest RAM floor for the one-box shapes
(REAP ~32 + Sonic ~20 + services ~6–10 + OS). On two
boxes, each carries half and 32GB apiece works. A $199
node's role in the destination is now precise: it is the
always-on household seat and a REAP swarm member — the
stepping stone AND a permanent part of the house. It is
just never the Sonic-10 seat by itself.

## The under-$750 zones (expanded)

### Zone A — under $300: "The Stream Floor" (DDR4)

The story of this zone is the TWO-PRICE MARKET: the same
EliteDesk 800 G4 Mini i7-8700T is **$199.99 delivered** on eBay
street (patience required) vs **$509** at Grade-A refurb
retailers. Zone math uses street prices; a refurb-retail buyer
effectively pays one zone up for a warranty.

| Shape | Typical street price | What it runs |
|---|---|---|
| 1L mini, i7-8700T/9700T, 16–32GB | $165–200 | 7B ~7–11, 14B ~3.5–5.5 tok/s ○ |
| 1L mini, i5-8500T/9500T, 16GB | $150–190 | same class, fewer threads (fails Brian's best-CPU gate; fine for a learner's first node) |
| SFF (EliteDesk 800 G4/G5 SFF, i7) | $199–249 | Zone A speed + PCIe slot for 10GbE later |
| Tower (i7, GPU-host gates met) | $249–299 | an empty GPU host is a Zone C down-payment |
| Ryzen APU mini (EliteDesk 705 G4, verified $170) | $170–250 | iGPU/Vulkan wildcard |

Sonic-class 35B MoE on a Zone A box: ~3–7 tok/s ○ — agent /
background speed, and it wants 32GB to sit resident at Q4.
That is genuinely useful: overnight enrichment, drafting,
tagging, a personal assistant that never phones home.

### Zone B — $300.01–$499.99: "Headroom"

This zone buys RAM installed and GPU headroom BEFORE the
GPU money exists.

- **Precision 3630 (renewed, 32GB/1TB) — $467.99** ●: the best
  RAM-per-dollar verified in the band.
- **Z2 G4 Tower, 500W PSU config**: the PSU is the product —
  the 250W config of the same tower is bait.
- **M920q i7-9700T / 32GB**: $489–589 at retail; street patience
  pulls it toward the band's floor.
- What it unlocks: 32B Q4 resident on CPU at usable background
  speed, a real Postgres + analytics seat, 10+ browser
  instances for scraping, and a tower that takes a P40/3060
  the day the next tranche lands.
- Traps: the Quadro P1000 "AI card" tax, 250W-vs-500W PSU
  bait, Raptor Lake towers creeping into refurb channels
  at $499.

### Zone C — $500–$750: "First Real GPU"

- **RTX 3060 12GB route.** Used 3060 pricing CONFLICTS across
  trackers (~$291–303 trackers vs ~$505 median of 52 eBay sold
  listings, Oct 2026): plan at **$300–400, ceiling $500**.
  Measured: 7/8B 42–65 tok/s, 14B 23–36 tok/s ●. A 3060 tower
  built patiently lands $600–750 all-in.
- **Tesla P40 24GB route: $520–680 all-in** (card $220–300
  sold range + a gated tower). The cheapest seat where 32B
  and Sonic Q6 sit RESIDENT in VRAM. Slow per token vs the
  3060; wins on capacity.
- Sonic on a 3060 host (CPU-MoE offload): 8.7–11.5 tok/s at
  32GB host RAM, ~11–17 at 64GB ◐.
- What it unlocks: interactive 14B, resident 32B, image
  generation (SDXL/Flux), light local video (see the
  Videographer-Lite scenario before buying for video).

**The coaching stack:** ~$199 → ~$450 → ~$700 across three
purchases, each fully useful the day it arrives, and nothing
in the lower zones gets retired — Zone A nodes become the
swarm, the scraper, the satellite.

## The rack shelf: 1U/2U servers by generation

Three colliding "Gen" ladders, aligned. The breaks that
matter: **DDR3→DDR4** at Dell 13G / HPE Gen9 · **PCIe 4.0**
at Dell 15G / HPE Gen10 Plus · **DDR5** at Dell 16G / HPE
Gen11.

| Class | Dell / HPE / Supermicro | Bare → configured | Verdict |
|---|---|---|---|
| A — DDR3 | R620/R720 · DL380p Gen8 · X9 | $50–150 bare; $150–300 w/ RAM | cheapest capacity in existence |
| B — DDR4 entry | R630/R730 · DL380 Gen9 · X10 | chassis $80–200; FINISHED 128GB box $600–1,200 | default first rack — buy configured |
| C — Xeon Scalable 1/2 | R640/R740 · DL380 Gen10 · X11 | bare $199–462 (anchor: R640 + 2× Gold 6150 + 64GB at $258.88 ●) | R740 = best cheap multi-GPU host (3× 300W, needs GPU kit + ≥1100W PSU) |
| D — PCIe 4.0 | R650/R750 · Gen10 Plus · X12/H12 | bare chassis $3,000–4,937 | THE CLIFF: same money buys a whole 14G cluster. Later. |
| E — DDR5 | R660/R760 · Gen11 · X13/H13 | cheapest complete $7,275 | not a 2026–27 purchase |

**EPYC is the single-socket cheat code.** One socket gives
8 memory channels (~204GB/s) and 128 PCIe lanes — the two
things Colibri-style NVMe+GPU builds eat. Rome/Milan 'P'
SKUs are the value (7302 ~$112–117 used ◐); H11SSL-i boards
~$200, H12SSL-i $300–599; a DIY 16-core/8-channel/128-lane
host ≈ $750–900 ○. WARNINGS: vendor-locked (PSB) EPYC CPUs
exist — a locked chip is a paperweight in another board —
and H11 board revisions matter.

**Power & noise reality:** a populated 1U/2U idles
~100–200W real (SPECpower floors are marketing; an R730
floor is 44.6W ◐ but nobody runs a bare chassis). 1U fans
are the loudest thing in the building. Budget rails
($40–90), caddies ($8–15 ea), freight (~$99 on a $200 R730
listing ●) BEFORE the sticker impresses you: a bare server's
true cost is sticker +40–70%.

## The big-RAM shelf: 256GB / 512GB

| Build | Price (Oct 2026) | Note |
|---|---|---|
| 256GB DDR3 (DL380 Gen8 / R720, 16×16GB) | $450–1,000 ○ | ~4–5× less bandwidth than DDR4 — a contribution node, not a speed node |
| 512GB DDR3 (16×32GB LRDIMM) | $600–1,700 ○ | the cheapest half-terabyte that exists |
| 256GB DDR4 configured | $1,700–2,800 ○ | buy it populated |
| 512GB DDR4 configured | $3,000–4,600 ○ | EPYC 1-socket: 256GB = just 8×32GB RDIMM |
| 512GB of RAM alone | refurb DDR4 $2,500–3,800 vs new DDR5 $6,400–8,000 ◐ | the refurb loophole is the whole game |

RAM crisis facts: server DRAM contract prices rose 90–95%
in Q1 2026 alone; new 32GB RDIMM median $358 (Sep 2026),
refurb $160–235. No relief before H2 2027–28. RDIMM ≠ UDIMM
≠ LRDIMM, and they never mix.

**With multi-GPU:** R740 (3× double-wide, GPU enablement
kit required) · Supermicro 4029GP 4U (8–10 GPUs, 2000W
PSUs; a loaded 8×P40/256GB example listed $8,979 ◐) ·
Z840/P920 towers = the quiet option. GPU prices now:
P40 24GB $230–300 (+~$58 cooling mod) · V100 32GB $350–660
(wide spread, HIGH uncertainty) · M40 24GB $150–200
(Maxwell caveats) · **RTX 3090 $1,199–1,540 — CORRECTED,
see the note in price-power-zones; the ~$700 era ended
during 2026.**

## The storage & fabric shelves

**Multi-x4 NVMe (the Colibri storage tier).** Streaming
weights is a bandwidth business: 1× Gen3 x4 ≈ 3.5GB/s ·
4× Gen3 ≈ 13GB/s (rivals DDR3 bandwidth) · 8× Gen4 ≈
50GB/s+. Bifurcation cards (ASUS Hyper M.2 Gen4, $69.99 ●)
vs PLX switch cards ($400–900) — check the board supports
bifurcation first. Enterprise drives at the 1.92TB+
standard: PM983 1.92TB $250–450 used (spread HIGH),
3.84TB $450–750.

**NVMe-oF physics check:** streaming over the wire caps at
network speed — 10G ≈ 1.1GB/s (slow lanes only) · 40G ≈
one Gen3 drive · 100G ≈ a 4-drive array. Streaming from a
remote box only pays at 40G+. This is why the fabric is its
own leg, separate from the main network.

**Networking ladder (NIC + switch + cables, 4-node fabric):**

| Tier | Total | When |
|---|---|---|
| 1GbE | ~$0 | one node; always the management leg |
| 2.5GbE | $120–250 | two nodes, light sync |
| **10GbE** | **$300–500** | **the sweet spot** — ConnectX-3 $25–55, CRS309 $269 fanless |
| 25GbE | $900–1,800 | SFP28 takes SFP+ at 10G — the graceful upgrade |
| **40GbE** | **$400–900** | **the value hack** — the industry skipped 40G, so ConnectX-3 Pro QSFP+ is $48–115; ideal for a CLOSED inference fabric |
| 100GbE | $1,800–3,500 | when NVMe-oF streaming is real |

DAC > optics > 10GBase-T (the hot, expensive trap).

**Worked stacks (appendix of the research):** Capacity Mule
$1.6–3.2K · Balanced Node $3.8–5.8K · GPU Barn $6–11K.

## The three budget paths (2–3 years)

Order of value, defended in the research: first node →
RAM/NVMe → 10GbE fabric → second node → GPU → big-RAM
server. Each step waits its turn because each step makes
the next one worth more.

### Path A — "The Patient Swarm" — $50/month ($1,800 / 36 mo)

i7 1L ≤$199 in Q2 of year 1 → NVMe/RAM tranches → second
node in year 2 → 10GbE kit (~$230, CRS305 class) → UPS →
year 3: third node OR the P40 fork. **Ends as:** a 3-node
DDR4 swarm — 35B MoE daily driver, 150B distributed —
for under $10/month in power. This is a complete ecosystem,
not a starter kit.

### Path B — "The Balanced Climb" — $100/month ($3,600 / 36 mo)

First node with 32GB installed → gated tower (≤$299,
x16-electrical + ≥400W PSU) bought EMPTY in Q3 → P40 24GB
(~$230) in Q4 → fabric + second mini in year 2 → late
year 3: a BARE R730/R740-class server, populated over time
with refurb DDR4 RDIMMs, 128GB → 256GB (70B resident).
**Ends as:** GPU seat + swarm + a big-RAM anchor.

### Path C — "The Fast Track" — $150/month ($5,400 / 36 mo)

One strong 64GB node at $500–750 in Q1 (the one
several-month save, spent right) → GPU tower + P40 by Q2 →
3-node fabric inside year 1 → a POPULATED 256GB server
≤$1,800 delivered in year 2 → year 3 consolidation; EPYC
512GB only via sell-to-climb. **Ends as:** everything Path B
has, a year sooner, plus a real anchor.

### The costs nobody budgets

Electricity is a second, silent purchase — 24/7 math:

| Idle draw | $/mo @ $0.15/kWh | $/mo @ $0.30/kWh |
|---|---|---|
| 15W (mini asleep-idle) | $1.64 | $3.29 |
| 35W (1L node) | $3.84 | $7.67 |
| 100W (R730-class) | $10.96 | $21.92 |
| 150W (populated 1U/2U) | $16.44 | $32.88 |
| 400W (small cluster) | $43.83 | $87.67 |

A 150W server at $0.30/kWh eats **66% of a $50/month
saver's entire gear budget** — forever. Coaching
consequence: at high power rates, big iron runs
wake-for-work, not always-on. Plus: noise (a 1U in an
apartment is a hairdryer with an IP address), freight,
rails, caddies, a second PSU, management licenses, and a
UPS ($150–250 + battery every ~3 years). No UPS = the
mistake you only make once.

### Sell-to-climb

Used enterprise gear holds value; the market is a ladder,
not a sink. Plan on 70–90% recovery (ServeTheHome's
playbook: resell in 3–6 months and it "basically evens
out," ±10–15% ◐). 2026 twist: populated RAM APPRECIATED —
value the DIMMs separately when you sell. Keep machines
complete, sell inside the community first (the cohort is
its own classifieds), and never buy ancient/illiquid gear
as a first purchase — you can't climb on a rung nobody
else wants.

### Mistakes that strand money (the short list)

1. K80 or Raptor Lake — absolute traps, any price.
2. Loose DDR5 in the crisis (a 64GB kit ≈ five i7 nodes).
3. A 1U server before you have somewhere to put it.
4. A GPU before a gated host exists (PSU/slot/clearance).
5. Networking before node #2 exists.
6. Sub-floor parts (≤8GB sticks, <256GB NVMe, <1.92TB SSD).
7. UDIMM/RDIMM mismatch.
8. Maxing one machine instead of balancing the system.
9. No power meter — guessing at your second purchase.
10. Skipping the UPS.

## The scenarios: six people, six ceilings

| Persona | The work | Lives in | TERMINAL CEILING ■ |
|---|---|---|---|
| **The Operator** | CRM, email, contacts, campaign analytics | Zones A–B | one 64GB node ($300–450 comfortable) |
| **The Creator** | blog, SEO, social, repurposing | Zones B–C | 64GB node + optional 3060 |
| **The Scout** | lead scraping + enrichment | Zones A–B | one 64GB 8-core node + storage |
| **The Videographer-Lite** | a few videos a month + images | Zone C or $0 | RENTING, forever — a legitimate finish |
| **The Builder** | coding, agents, automation | Zones C → Interactive Shelf | one strong node + one GPU + one $199 satellite |
| **The Architect** | the platform itself (Brian) | every zone + the rack shelf | no ceiling — the work IS the ecosystem |

Four of the six finish under $750 total. Two finish under
$500. One finishes at $0 of hardware.

**The Operator** is a CPU+RAM person. Postgres analytics
over a solo contact base is trivial compute; drafting and
tagging are 7B–14B jobs; concurrency is one human plus a
few background agents. Minimum $199 (1L i7, 16–32GB). A
GPU in this house is an idle ornament — the bottleneck is
the owner's approval time, not tokens. (This is the
ContactFlowCRM customer, exactly.)

**The Creator** buys quality, not speed. The 32GB vs 64GB
line: 32GB = a 14B resident OR a 32B alone with everything
else closed; 64GB = 32B Q4 resident alongside the whole
desk, plus a Sonic-class MoE. Ceiling: that 64GB node,
with a 3060 only if images enter the work.

**The Scout** buys cores and RAM-per-browser: a headless
tab is 150–300MB, an instance 300–500MB, ~10 pages ≈
3–5GB — browser concurrency is a RAM budget. Inference is
a 2B–7B batch tagger. **Do NOT buy a GPU first**: it
accelerates the one step already fast enough and steals
the RAM money. At scale the real spend is proxies
(~$8–15/GB), not compute. Growth = a second identical
node, not a bigger one.

**The Videographer-Lite** is the reality check. Local
video, honestly: Wan 2.2 TI2V-5B is officially a 24GB
model (GGUF squeezes it to 8–12GB, ~9 min per 5s 720p
clip on a 3060 ○); the A14B is 65–80GB native, FP8/offload
on 24GB; HunyuanVideo 60–80GB native. Meanwhile renting
is cheap: fal hosts Wan A14B at $0.20–0.40 per 5s clip ●,
Runway Standard $12/mo, Pika $8/mo. At a few videos a
month (~30 generations with rerolls ≈ $7–15/mo), payback
on a $520–750 GPU node is **4–6 years — renting wins and
it isn't close.** Own only when: >~100 generations/month,
privacy/offline needs, or a GPU already bought for another
persona's work. Images are the cheap on-ramp (SDXL ~7–8GB
VRAM, Flux dev FP8 ~12GB). Renting forever is a terminal
state, ■.

**The Builder** is a residency person: a 32B coder + 14B
chat + 7B utility + a tagger ≈ 36GB of weights before the
OS — so 64GB floor, 96–128GB comfort. Minimum $500–750
(3060 tower), comfortable $900–2,200. Ceiling: one strong
node + one GPU + one $199 satellite mini. Brian-lite, and
proud of it.

**The Architect** (Brian) is the only persona whose work
is the platform itself — fleet, streaming, the council,
other people's ecosystems. His ceiling doesn't exist,
which is precisely why everyone else's does: their
ceilings are drawn so they never pay his costs.

### Scenario × budget (where the money lands)

- **Operator / Scout** on ANY path: done in year 1; the
  remaining budget becomes storage, a second node, and
  time — not a climb.
- **Creator**: Path A finishes them in ~year 2; B/C add
  the 3060.
- **Videographer-Lite**: $0 hardware on every path; the
  "gear budget" is a $8–15/mo rental line.
- **Builder**: needs Path B or C pace to finish inside
  2 years.
- **Architect**: Path C pace + sell-to-climb, 3 years to
  the rack shelf done right (configured, quiet-managed,
  fabric first).
- **The low-end group as a whole**: whatever the persona,
  the shared graduation is the Homestead Spec (above) —
  the 150B slow, Sonic ≥10 tok/s, agent + n8n + crons
  aboard, 1–3 machines total.

## The coaching structure (how a cohort climbs without casualties)

- **One versioned buy-list** — delivered-price caps,
  sourcing floors, traps enforced in code
  (`hardware_traps.py` REJECT / UNVERIFIED discipline).
- **Gated quarters**: nobody buys rack gear without a
  signed noise/power/space worksheet. Nobody buys a GPU
  without a gated host. Nobody buys networking before
  node #2.
- **Delivered-price comparisons only** — sticker prices lie
  (freight is a line item, not a surprise).
- **A shared spares pool + internal classifieds** —
  sell-to-climb starts inside the cohort.
- **Demo days per tier** — each zone shows what it unlocks
  before anyone saves toward it.
- **Running-cost honesty as a badge** — every build posts
  its watts next to its tokens.
- **The 2–3 year arc as syllabus**: Year 1 = skills + the
  first node. Year 2 = fabric + GPU (for the personas who
  need one). Year 3 = big RAM (for the two who do).

*Research annexes (full tables, sources, uncertainty
ledgers): `research_notes/` — under750-zones, rack-servers,
large-ram-nvme-net, zero-hero-economics,
workload-scenarios. Planning instrument, not a benchmark
paper. Re-verify prices at purchase; the RAM crisis moves
monthly.*
