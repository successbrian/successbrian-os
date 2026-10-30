# Brian's Decisions — System of Record Digest

**Generated:** 2026-10-28 19:55 UTC
**Source:** `altair.brian_decisions` (106 decisions)
**Note:** The PostgreSQL table is the source of truth. This document is the searchable view.

---

## Topic: INFRA

### INFRA-20260916: Fleet-wide psql fix: Should we fix all ~50 scripts using bare psql -U without -h/-p flags, or is there a centralized env fix approach? PGPORT=6432 from PID 1 breaks socket fallback across the fleet.
**Decided:** None

**Context:** 5 serendipity scripts fixed with -h 127.0.0.1 -p 5432. ~50 scripts in /home/successbrian/scripts/ still vulnerable to PGPORT=6432 socket fallback failure.

**Decision:** None

---

## Topic: dec

### dec-20261024-pp02: Post-prompt compression and integration workflow
**Decided:** 2026-10-24 02:46

**Context:** Brian ruled tonight: Hermes Altair runs Sonic, not Morpheus. Compression should happen at the end of every prompt, after Altair gives its output, it compresses. At the end of each prompt, Altair should integrate into the ecosystem as best possible, write new discoveries, and update needed things. This post-prompt integration is NOT related to the board.

**Decision:** Compression must occur at the end of every prompt after Altair's output. Altair will integrate into the ecosystem, write discoveries, and update necessary items, explicitly separate from the board.

---

### dec-20261024-pp01: Hermes Altair uses Sonic for compression
**Decided:** 2026-10-24 02:46

**Context:** Brian ruled tonight: Hermes Altair runs Sonic, not Morpheus. Compression should happen at the end of every prompt, after Altair gives its output, it compresses. At the end of each prompt, Altair should integrate into the ecosystem as best possible, write new discoveries, and update needed things. This post-prompt integration is NOT related to the board.

**Decision:** Brian ruled that Hermes Altair runs Sonic instead of Morpheus for auxiliary compression.

---

### dec-20261023-qwname: Is the process called the Qwemstral Dilemma?
**Decided:** 2026-10-23 16:47

**Context:** Brian 2026-10-23 16:46 CDT: its no longer a qwemstral dilemma — it no longer rhymes, but it is Qwemstral. He was never going to sell a Qemma Dilemma and then explain why Mistral got shoved in there.

**Decision:** No Dilemma suffix. The team, the process, and the flagship series are all simply QWEMSTRAL — one word that contains all three families (Qwen + Gemma + Mistral) and needs no explanation. The Dilemma name died with the rhyme.

---

### dec-20261023-qwrepl: Does Qwemstral replace Qemma?
**Decided:** 2026-10-23 16:43

**Context:** Brian 2026-10-23 16:42 CDT, after the engine namings (Morpheus / Rassilon / Mace Windu): qemma is replaced with qwemstral.

**Decision:** QWEMSTRAL replaces QEMMA everywhere as the current name: the judging team is Qwemstral, and the process is the QWEMSTRAL DILEMMA. Atlas nodes renamed in place (keys team:qemma / process:qemma-dilemma kept as stable IDs, display names updated); CampaignsDesk idea #22 retitled; living docs (charter, staging roadmap, content-edge brief, AMD strategy, PM spec, channel map) updated and re-embedded. Historical dated records keep the old word as history.

---

### dec-20261023-rass: What is the Gemma judge engine named?
**Decided:** 2026-10-23 16:41

**Context:** Brian 2026-10-23 16:41 CDT, from the Doctor Who judge slate (Valeyard / Inquisitor / Rassilon): 'rassilon -- only the true old whovians will get it'.

**Decision:** The GEMMA judge engine (seats 3-4, Gemma 4 12B Q6 on the Aoostar pair) is named RASSILON — Doctor Who: founder of Time Lord society, the ancient authority in The Five Doctors who sits in judgment over the Doctors in the Death Zone. All three Qwemstral engines now named: Morpheus (Qwen, the Matrix), Rassilon (Gemma, Doctor Who), Mace Windu (Mistral, Star Wars).

---

### dec-20261023-mace: What is the Mistral judge engine named?
**Decided:** 2026-10-23 16:38

**Context:** Brian 2026-10-23 16:38 CDT, in the engine-naming thread (Morpheus = Matrix character; Qwemstral = the three families together): 'mace windu --- reference from star wars'.

**Decision:** The MISTRAL judge engine (seats 5-7, Mistral Small 3.2 24B Q6 on the eGPU minis) is named MACE WINDU — the Star Wars Jedi Council master. Fleet engine names come from iconic film characters (Morpheus from the Matrix, Mace Windu from Star Wars). The Gemma judge engine name remains open.

---

### dec-20261023-qwem: What are the three judge families called together?
**Decided:** 2026-10-23 16:36

**Context:** Brian 2026-10-23 16:34 CDT, answering the open fleet-name item for the Gemma/Mistral judge engines: qwemstral (qwen, gemma, mistral). Qemma (ruled 10:30 CDT) remains the judging TEAM and the Qemma Dilemma remains the decision PROCESS; Morpheus remains the Qwen engine name.

**Decision:** The three judge model families as one engine set are QWEMSTRAL — Qwen + Gemma + Mistral fused in one name. Naming-world correction (Brian 2026-10-23 16:37 CDT): Morpheus is named for the MATRIX character, not the Greek god — fleet engine names live in the Matrix world. Individual names for the Gemma and Mistral engines stay parked; if picked, they come from the Matrix bench (Oracle / Seraph / Niobe / Trinity), not Greek myth.

---

### dec-20261023-qual: What is Brian's differentiator in the AI world?
**Decided:** 2026-10-23 16:12

**Context:** Brian 2026-10-23, his words: "it's the diversification and the extremely high confidence i'm requesting of these models. plus the higher than Q4 (usually) quant I run... i'm demanding high quality output over speed. when more people want speed."

**Decision:** QUALITY OVER SPEED: (1) diversification - multiple model families on independent machines, never one model grading itself; (2) the 0.98 confidence bar - the system may say not-sure; (3) Q6-standard quants instead of the field's Q4-for-speed habit. One thesis across the whole operation: verification over velocity.

---

### dec-20261023-oos: How are out-of-stock prices handled in the DealsDesk market-price database?
**Decided:** 2026-10-23 16:12

**Context:** Brian 2026-10-23: "do not show out of stock pricing.... this can simply be archived with price date. we want to gather regular price time stamps and look for market movements."

**Decision:** Out-of-stock and back-ordered prices are archived as timestamped history rows (in_stock=false, observation date kept) for market-movement analysis. They are NEVER shown or quoted as current offers; current-price statements use in-stock observations only.

---

### dec-20261023-slickdl: How is Slickdeals treated as a price/deal source?
**Decided:** 2026-10-23 16:12

**Context:** Brian 2026-10-23: distrusts Slickdeals but ruled VERIFY, NOT DISREGARD. Click-through test on the Bosgame M4 deal: Slickdeals thread marked EXPIRED; Amazon serves its AI-agent refusal wall to Muse, so retailer-side state is human-verified only.

**Decision:** LEADS ONLY. A Slickdeals post counts only when clicking through to the retailer confirms the advertised special still checks out; in Brian's experience ~75% of the time it does NOT. Never cite a Slickdeals price, spec, or deal as fact without retailer-side confirmation. Slickdeals-sourced tracker rows are flagged unverified leads.

---

### dec-20261023-amd1st: How is Brian's fleet described in pitches, videos, and profiles?
**Decided:** 2026-10-23 16:12

**Context:** Brian 2026-10-23 correction: "lots of AMD minis, some Xeon stuff. so i'm not a purist, but lots of amd focus." He owns X79 and X99 Xeon builds (cheaper than the 7 judge minis combined; smarter-per-job, slower, low parallel throughput).

**Decision:** AMD-FIRST, never all-AMD. The mini-PC/appliance fleet is AMD (680M-890M); Xeon iron serves in support roles. AMD Top Fan positioning builds on the AMD focus without claiming exclusivity the fleet photos would contradict.

---

### dec-20261023-nstar: What is the SBOS north star?
**Decided:** 2026-10-23 16:12

**Context:** Brian 2026-10-23: "i'm looking to build a true agentic autonomous system that manages the chaos of my life, finds new intel, helps me develop content, and make money without me having to worry about much 24/7 and not burn tons of tokens." Charter doc: sbos-autonomy-charter-2026-10-23.md (successbrian-os workspace).

**Decision:** Build SuccessBrian OS into a true agentic autonomous system with four jobs (life-chaos management, intel, content, money), always-on, low-touch, TOKEN-LEAN: deterministic machinery does the volume (zero tokens), the local fleet judges (sunk-cost inference), executive tokens are spent only where judgment earns it. Judge every future build proposal against this statement.

---

### dec-20261023-bizpref: Which contacts does Brian prefer for business ties?
**Decided:** 2026-10-23 13:15

**Context:** Raised 2026-10-23 in the Yuma context (Meghan Jean's ties to Yuma, AZ), then corrected by Brian the same day: preference for ALL business ties, not Yuma only.

**Decision:** CHRISTIAN, CONSERVATIVE EVANGELICAL FIRST: Assemblies of God, Pentecostal, Christian and Missionary Alliance, Baptist and closely related traditions; and people more likely to be MAGA / Trump supporters. A preference / prioritization for matching and ranking business ties - NOT an exclusion (no evidence = no boost, never ruled out) and evidence-only (never infer faith or politics from name, photo, location or demographics). Encoded as code: campaignsdesk/code/preference_match.py, seeding campaignsdesk.lead_preferences (ecosystem_central) and scoring leads from people_unified public-record fields; canonical document in AnythingLLM people-pipeline (brian-business-ties-preference.md), machinery doc in campaignsdesk, product spec in contactflowcrm; Atlas node decision:business-ties-preference.

---

### dec-20261022-compat: Where does Brians fleet stay compatible with Nous Research Hermes, and where does it stay sovereign?
**Decided:** 2026-10-22 09:31

**Context:** 2026-10-22, following the Murmur analysis (#93/#94) and the 0.20.0 -> 0.22.4 vetting dossier. Brian: "we want to be compatible with them in key areas that allow us to interface with murmur and other future developments they do." Verified from Murmurs code: its 0.21.4 floor is client.capabilities (agents asking before risky commands) + profiles.* + groups.* + session replay; the client surface is the dashboard/API (web_routers, auth, /api/ws) — the same door Hermes Desktop uses.

**Decision:** COMPATIBLE AT THE INTERFACE, SOVEREIGN AT THE CORE. The fleet TRACKS upstream — vetted per change — in the client interface layer only: dashboard HTTP API, client auth flows, the /api/ws live protocol + client.capabilities, the Hermes MCP surface, and the data shapes the dashboard reads (which makes the state.db writer-discipline port a compatibility prerequisite). The core NEVER tracks: Brians agent patches, gateway-per-profile topology, cron/heartbeat, install machinery (no hermes pm, no auto-update), plugin catalog. Compatibility means real API behavior with an honest version, never a spoofed number. Plan: research_notes/hermes-interface-compatibility-plan-2026-10-22.md — per-release diff of the layer only, four-part test gate, Brian approves each port batch.

---

### dec-20261022-vetup: When Nous Research changes Hermes — especially the dashboard/interface layer Murmur consumes — how do those changes reach Brians fleet?
**Decided:** 2026-10-22 05:12

**Context:** 2026-10-22, closing the Murmur/Hermes thread: the fleet runs a core-patched Hermes 0.20.0 on k11-alpha; Nous versions the client interface (dashboard/API) with the package, and current clients (Murmur) already expect 0.21.4+ behavior from that piece. Brian: "we bet [vet] the changes they make."

**Decision:** WE VET THE CHANGES THEY MAKE. No upstream change auto-applies to Brians fleet — not a framework upgrade, not the interface piece, not a client-driven bump. Vetting means: diff the upstream change against Brians core patches (agent/*.py, cli.py) and profile config formats, check gateway/heartbeat behavior, stage it on one surface first, and Brian approves adoption. The interface piece may move (per d261022-murmur-min) — but only as a vetted change, never a silent one.

---

## Topic: d261022

### d261022-murmur-min: Murmur adoption, refined: change the whole Hermes framework, or just the piece that lets Murmur connect?
**Decided:** 2026-10-22 04:58

**Context:** Refines dec-20261022-murmur (#93). Brian, 2026-10-22: "just that piece ... the piece that allows it to work with murmur". Verified same day: (1) Murmur never talks to the gateway/agent core — it connects to the Hermes DASHBOARD (hermes dashboard, port 9119, /api/status + dashboard auth). (2) No dashboard is currently running on k11-alpha (port 9119 dark). (3) Brians Hermes 0.20.0 checkout carries local core patches (agent/model_metadata.py, prompt_builder.py, skill_utils.py, system_prompt.py, cli.py all modified) — a wholesale framework upgrade would collide with them, which is what the no-change ruling protects.

**Decision:** JUST THE PIECE. Altair, the gateways, the patched agent core, profiles, and heartbeat stay untouched. The only component in scope is the dashboard surface Murmur connects to (port 9119): stand up / bring up only that piece to the behavior Murmur requires (0.21.4+ dashboard API). Scope verification (does the 0.20.0 dashboard already satisfy Murmur, or does the dashboard piece alone need updating) precedes any change, and the change itself waits for Brians explicit go.

---

## Topic: dec

### dec-20261022-murmur: Adopt Murmur (Umbrel front-end for Hermes) as the window into Altair and the agent fleet?
**Decided:** 2026-10-22 04:56

**Context:** 2026-10-22: Brian shared the Murmur + Hermes video (youtu.be/dHNNAzdNXAc) and asked whether customized Altair would still work with it. Checked: Murmur reads Hermes profiles/sessions directly (Altair customization is profile-level, so it carries), but Murmur requires Hermes Agent 0.21.4+; k11-alpha runs Hermes 0.20.0 (verified live from hermes_agent egg-info). Adoption therefore requires upgrading the fleet agent framework on k11.

**Decision:** NO CHANGE. Altair / Hermes stays as-is at 0.20.0 on k11-alpha. Do not upgrade the fleets agent framework — the heartbeat, council, and every profile run on it — to satisfy a front-end. Murmur is parked. It becomes available as a side effect if Hermes is ever upgraded for its own reasons (0.21.4+), and only then is it revisited.

---

### dec-20261022-aprscp: Does approving a route, plan, vendor, or direction authorize Muse to contact vendors, submit forms, send messages, or buy?
**Decided:** 2026-10-22 04:49

**Context:** 2026-10-22: Brian approved the TekBoost configure-to-order route for dual-V100 Sonic hosts ("we likely need that configure to order then. can we direct relationship with them" / "we need this"). Muse treated that as a send order and moved to submit a quote request, asking for Brians contact email/phone. Brian stopped it: "I didnt say send anything slow down." Nothing was sent.

**Decision:** NO. Approving a route/plan/vendor/direction approves the IDEA only — never the execution. Every outward action (contacting a vendor, submitting a form, sending a message or email, buying anything) requires Brians own explicit go ("send it" / "contact them" / "do it"). Drafts are prepared and PARKED: presented, then stopped. Enthusiasm about a plan is not a signature on the action.

---

### dec-20261017-v4unfrz: Should Meghan's V4 Pro freeze stand?
**Decided:** 2026-10-17 12:54

**Decision:** No - lifted 2026-10-17. Spend/freeze authority is Brian's alone; agents propose, never enact. V4 Pro routing resumes per live balance.

---

### dec-20261017-msvbox2: Which box gets the MSV scraping workload first?
**Decided:** 2026-10-17 10:40

**Context:** Supersedes dec-20261017-msvbox1 (which named Mantis-5). Brian clarified 2026-10-17: the R630 is being acquired first, so it is the first choice for the dedicated MSV scraping box.

**Decision:** R630 first - MSV scraping goes on the R630 once acquired. Mantis-5 is the backup, or the final home if needed. Mantis-5 keeps its broader role (MSV scraping + Vera + special code work) for whenever it is built. (Brian 2026-10-17)

---

### dec-20261017-msvbox1: Which box gets the MSV scraping workload, and what else runs there?
**Decided:** 2026-10-17 10:35

**Context:** MSV scrapers dark since 2026-06-22 (9.7M tasks pending). Brian decided 2026-10-17 to solve it by moving scraping to its own dedicated box rather than debugging the shared-box failure. Refines the earlier Mantis numbering decision which had Mantis-5 = MSV scraping + Vera.

**Decision:** Mantis-5. MSV scraping + Vera, plus special code and work of that nature - not a single-purpose box. (Brian 2026-10-17)

---

## Topic: d261012

### d261012-egpu2: What workload split across the 4 Maco+V100 OCuLink nodes, and where does 150B run?
**Decided:** 2026-10-12 05:00

**Context:** Brian 2026-10-12. Candidate models: Sonic (Qwen3.6-35B-A3B), Qwen3.8-Flash (125B MoE), Gemma-4-26B-A4B-it, DeepSeek 150B. 150B at ~85GB (Q4) vs 56GB of fast tiers (32GB VRAM + 24GB Maco RAM) = ~30GB on NVMe over OCuLink x4 — patience-testing slow. Each node runs exactly one model (per Lon's config: models-max=1, one model expects most of the GPU).

**Decision:** Sonic x1 node, Qwen3.8-Flash x1 node, Gemma-4-26B-A4B x2 nodes. 150B stays OFF these nodes -- it runs on the DL380 Colibri tier (deep RAM pools) / MS-02 on-ramp / EVO-X5 long-term plan. Rationale (corrected 2026-10-12 per Brian): these nodes serve AGENTIC workloads -- code, decisions, planning -- NOT bulk content generation. Gemma x2 = parallel agentic workers for concurrent coding/planning tasks; Sonic = interactive agent backbone; Flash = hardest planning and decisions. CONTINGENT on scaling to 4 nodes; 2-node interim split still open. V100-vs-B70 card choice still open (leaning V100, not decided).

---

### d261012-egpu1: How should the Maco + AG02-dock + V100 OCuLink eGPU sets be housed in the rack?
**Decided:** 2026-10-12 04:53

**Context:** Brian 2026-10-12. Options discussed: 3U shelf, closed 3U chassis, 4U ventilated space. The AG02 is an open-frame dock (22.5x11x6cm); the V100 stands ~11-12cm tall in it. A closed 3U chassis leaves ~10mm of air above the passive card with no airflow path. Two sets fit in 3U on a shelf but with only ~1-2cm clearance.

**Decision:** 4U ventilated shelf space — both sets on one shelf in 4U (45x40cm footprint), giving the V100s ~6cm of air. NOT a closed 3U chassis. Rationale: the AG02 is open-frame by design; enclosing it defeats its cooling model, and the passive V100 needs airspace, not a lid. Spends 4U of frame budget (Frame B has 12U free). CONTINGENT on the V100 eGPU plan going ahead.

---

### d261012-v100cap1: Should the fleet V100s run power-capped for 24/7 operation?
**Decided:** 2026-10-12 04:53

**Context:** Brian 2026-10-12, during Maco+V100 OCuLink eGPU planning. Tesla V100 is 250W stock; the 24/7 boxes bill by the watt. nvidia-smi -pl can cap the card; the cap resets on driver reload so it needs persistence. Scripts staged at /home/successbrian/bin/v100-powercap.sh (+ v100-powercap.service) and /home/successbrian/bin/v100-efficiency-bench.sh.

**Decision:** YES — cap the V100s. Apply via nvidia-smi -pl with persistence mode + systemd unit re-applying at boot. Run the efficiency benchmark at 250/200/175W and set the cap at the knee of the tok/s-per-watt curve. Rationale (Brian): watts are the 24/7 budget; ~10-15% throughput cost for ~20% power savings is the right trade for unattended boxes.

---

## Topic: d261011

### d261011-epyc6: Should the Colibri NVMe tier use DRAM-less NVMe drives (e.g. Lexar NM790 2TB)?
**Decided:** 2026-10-11 03:33

**Context:** Brian asked Spencer to make the call 2026-10-11. NVMe tier serves Colibri 3-tier inference weight offload (1T MoE Q3 = 470.6GB), read-dominant, large-block expert/layer weight reads. Alternative: Samsung PM9A1 2TB datacenter-OEM at ~5x the price (browser-verified $579/ea).

**Decision:** YES — buy DRAM-less (NM790 2TB or equivalent). Rationale: (1) workload is large-block sequential reads, the DRAM-less strong suit; (2) ~5x price gap for an estimated 10-15% real-world difference in this pattern; (3) failure is low-stakes — weights are reloadable; (4) 1500 TBW endurance is plenty for read-dominant use; (5) savings fund parts that matter more. Hedge: if a future Colibri I/O benchmark shows random-read bottleneck, the PM9A1 is the tracked upgrade path in epyc_colibri_bom_prices.

---

## Topic: d261010

### d261010-epyc5: Quant policy by model size for the fleet?
**Decided:** 2026-10-10 22:25

**Context:** Brian proposed tiering quants by model size after noting the industry uses Q3 for the biggest models. Distinct from the standing no-IQ3 rule (which covers agentic-loop quality).

**Decision:** 1T params and up: Q3 quants only. 500B to 1T: Q4. Under 500B: Q6. Encoded in dealsdesk scenario_config.json (quant_policy=brian-20261010); sweep evaluates each model at its policy quant.

---

### d261010-epyc3: Which GPUs for the all-AMD Colibri EPYC build?
**Decided:** 2026-10-10 22:11

**Context:** Brian wants to stay all-AMD (EPYC + Radeon under ROCm, one coherent stack per box). 16GB class, four cards.

**Decision:** 4x AMD RX 6800 16GB (RDNA2). Mature ROCm support; verify Colibri HIP build before purchasing.

---

### d261010-epyc2: RAM spec for the EPYC Colibri builds: 512GB (8x64GB) or 256GB (8x32GB)?
**Decided:** 2026-10-10 22:11

**Context:** Brian mused about 512GB systems, then judged 32GB sticks more realistic for used-market sourcing.

**Decision:** Stay with 8x32GB DDR4-3200 RDIMMs (256GB, 8-channel, one DIMM per channel).

---

### d261010-epyc4: Buy the HUANANZHI H12D-8D bundle from SZJN Security Store on AliExpress?
**Decided:** 2026-10-10 22:11

**Context:** Listing vetted 2026-10-10: 83.3% positive feedback, one 1.0/5 review (wrong RAM shipped, seller refused fix), CPU/RAM sold used, seller requires pre-order quotation so displayed prices are not honored, spec table sparse/contradictory.

**Decision:** No — reject this seller/listing. The H12D-8D board model itself stays on the table as the only verified 3x-M.2 SP3 option, to be sourced from a reputable seller.

---

### d261010-epyc1: Keep the strict 3x-onboard-M.2 filter for SP3 Colibri boards, or allow 2x + carrier card?
**Decided:** 2026-10-10 22:11

**Context:** Brian wants 512GB-class RAM systems with 3x M.2 NVMe on the motherboard for Colibri on EPYC Rome. Only the HUANANZHI H12D-8D is verified with 3x onboard M.2; the Supermicro H12 family is 2x.

**Decision:** Yes — keep the filter STRICT: 3+ NVMe M.2 slots physically on the motherboard. PCIe carrier cards do not count.

---

### d261010-mantis3gpu: Mantis-3 GPU: RTX 3090 24GB or Tesla V100 32GB?
**Decided:** 2026-10-10 04:36

**Context:** Mantis-3 = analysis box (Sonic-class local model). Market check 2026-10-09: V100 32GB now runs lower than the 3090; Sonic Q6 (~28-29GB) fits 32GB not 24GB. Mantis-4 already dual V100 32GB (2026-10-07).

**Decision:** Dual Tesla V100 32GB — same as Mantis-4. 4x V100 32GB total to source (2 per box). Passive cooling: verify X79 airflow per box.

---

### d261010-x3test: EVO-X3: buy one to test, or wait?
**Decided:** 2026-10-10 03:38

**Context:** EVO-X3 (128GB/395, OCuLink, blade, ~$3,600): no 4U-rack role (form factor); multi-unit builds need the 42U rack + top shelf + permanent home.

**Decision:** Buy ONE X3 early to test and evaluate (platform, OCuLink eGPU, 150B) — roadmap Phase 8. Units 2+ are Phase 13: open 42U rack top shelf with custom 3D-printed blade mounts, gated on a permanent home. Gate chain: permanent home -> 42U rack -> top shelf -> X3 fleet.

---

### d261010-x5cluster: What is the end-state goal for the EVO-X5 in the fleet?
**Decided:** 2026-10-10 03:38

**Context:** Roadmap Phase 11. EVO-X5 Pro verified: up to 4 units daisy-chain via USB4 V2; 4x 80mm-wide units fit side-by-side in 2U; dual 10GbE per node; GMKtec claims 320B LLMs locally on the cluster.

**Decision:** 4-node EVO-X5 Pro cluster in a 2U rack (Phase 9 unit becomes node 1; add 3 more): nodes daisy-chained via USB4 V2, dual 10GbE per node external into the fleet fabric. ~640GB+ pooled memory for 320B-class. The fleet's flagship inference tier (Phase 12). Flexibility: 4x independent 150B instances OR pooled cluster. GATED ON ECOSYSTEM READINESS (Brian 2026-10-10, not on revenue): network, power/cooling, proven multi-node software, ops/DASH, Phase 9 complete first. Distant future.

---

### d261010-150bhome: Where does the DeepSeek 150B live long-term: MS-02/B50 or EVO-X5 Pro?
**Decided:** 2026-10-10 03:38

**Context:** Live pricing 2026-10-10: MS-02/B50 build ~$4,950 (DDR5 memory-crunch pricing collapsed its old advantage); EVO-X5 Pro $6,799 (192GB+2TB). Throughput est: ~1 tok/s tiered on B50 build vs ~3-4 tok/s resident on EVO-X5 (arithmetic, not measured).

**Decision:** EVO-X5 Pro is the best long-term 150B home on current knowledge (Brian: "in what we know currently" — measured benchmarks could revise). Sequencing: MS-02/B50 in Phase 6 as the affordable on-ramp, EVO-X5 later (Phase 9) when revenue or need justifies it. No purchase yet.

---

### d261010-b70place: Where do Arc Pro B70 GPUs belong in the fleet?
**Decided:** 2026-10-10 03:12

**Context:** Brian 2026-10-10: dual B70 is not for the MS-02, but stays in the fleet on bigger iron.

**Decision:** Dual B70 goes on Xeon and AMD servers; single B70s on OCuLink eGPU adapters (the EVO-X3 has the port; EVO-X5 eGPU goes over USB4 V2 — the X5 has no OCuLink port, model mix-up resolved 2026-10-10). Never on the MS-02.

---

## Topic: ms02u

### ms02u-b70-150b-1007: MS-02 GPU configuration (SUPERSEDED)
**Decided:** 2026-10-10 03:01

**Context:** Decided 2026-10-07, superseded 2026-10-10.

**Decision:** SUPERSEDED 2026-10-10 by d261010-ms02gpu and d261010-b70place: MS-02 is internal Arc Pro B50 only; dual B70 moves to Xeon/AMD servers.

WHY DISCARDED (Brian 2026-10-14, his words): dual B70 belongs on server boards designed to handle dual or more GPUs, not on an MS-02 build that isn't really and honestly built for that. Principle: match the build to the chassis it was designed for.

---

## Topic: d261010

### d261010-ms02role: What is the MS-02/B50 build for in the fleet?
**Decided:** 2026-10-10 02:56

**Context:** Brian corrected 150B-only framing: with B50 + 128GB RAM + 2x 4TB NVMe the box has broader potential. 8B/32B models live elsewhere in the fleet (Mantis nodes, k11-alpha).

**Decision:** MS-02/B50 is the fleet 70B-and-up inference node. 70-72B class runs well (partial offload). It runs the 150B as the low-cost on-ramp right now — not the ideal long-term home.

---

### d261010-ms02gpu: MS-02 GPU configuration
**Decided:** 2026-10-10 02:53

**Context:** Fleet roadmap Phase 6. MS-02 Ultra (Core Ultra 5 235HX) + 128GB DDR5 + 2x 4TB NVMe.

**Decision:** Internal Arc Pro B50 only: 235HX + 128GB DDR5 + B50 16GB + 2x 4TB NVMe. Fleet 70B-and-up inference node; runs the 150B as the low-cost on-ramp.

---

## Topic: scale

### scale-gate-1007: When do we scale up scraping egress (proxies, more IPs)?
**Decided:** 2026-10-07 14:59

**Context:** Hardware architecture session 2026-10-07. Cloudflare per-IP limiting was the real 12-30k/day MSV ceiling; throughput = per-IP allowance x egress IPs. Egress today: gamma, node zero, k11-alpha (3 free IPs).

**Decision:** We scale up when we are making money. No proxy/egress spend until the operation generates revenue. Same philosophy as the 2026-10-05 no-outbound-calling-until-revenue decision.

---

## Topic: epyc

### epyc-names-1007: What do we call the DDR4 EPYC GPU boxes? What about the name Zeus?
**Decided:** 2026-10-07 14:59

**Context:** Hardware architecture session 2026-10-07. K11-Zeus was a paper plan (2x EPYC 7252, 6x MI50) named by unknown party; Brian asked who named it Zeus.

**Decision:** EPYC GPU boxes are named by silicon generation: Rome for Rome silicon, Milan for Milan, etc. The name Zeus is retired - Brian is a Christian and does not name anything after pagan gods. Standing rule: no pagan gods on anything ever; no NEW Greek/Roman mythology names. Mantis/Hornet (insects God created), Echo (NATO letter), Rome/Milan (cities) are all clean.

---

## Topic: mantis

### mantis-num-1007: How are the Mantis (DDR3) nodes numbered? Where do the new builds and DL380s land?
**Decided:** 2026-10-07 14:59

**Context:** Hardware architecture session 2026-10-07. Brian declared explicit numbering. Mantis = DDR3 (name encodes RAM generation).

**Decision:** Mantis-1..4 = the four X79 builds (capped, never more). Mantis-5..8 = the four new dual-LGA2011 builds from 8x spare E5-2650 v2 (5=MSV scraping+Vera, 6=SearXNG workers+AI analysis, 7/8=scraper overflow proposed). Mantis-9 = DL380 Gen8 1 (dedicated PostgreSQL, MSV/enrichment). Mantis-10 = DL380 Gen8 2 (self-hosted Supabase + fleet backup). Supersedes loose Mantis-5+=DL380s mapping.

---

## Topic: aoostar

### aoostar-mesh-261007: Build the Aoostar agent-home + inference mesh architecture?
**Decided:** 2026-10-07 06:46

**Context:** Morning design session 2026-10-07 (Spencer + Brian). Architecture: 2x owned 24GB Aoostar GEM10 as agent homes (Altair lean chat-brain appliance with custom Colibri-fork harness; Meghan executive workstation with own Postgres/n8n/AnythingLLM); 16GB units as Sonic workhorses + scheduler; Node Echo as shared-services box; deterministic mesh router; Colibri for fit on homes, Strata for speed on NVIDIA iron.

**Decision:** Yes - build it. Sequence: Echo spec survey first, then Aoostar bring-up + stock Colibri benchmark with decision gate (fallback: llama.cpp + gpt-oss-20b per aoostar-gptoss-q6), then custom harness, Meghan home, Echo migration, scheduler. Altair maintains the harness fork.

---

## Topic: dec

### dec-20261007-scope1: Blog network starting scope: 100 or 1000 blogs?
**Decided:** 2026-10-07 01:02

**Context:** 2026-10-05 Brian scaled the ambition from 100 to possibly 1000 blogs. 2026-10-07, after the content-factory strategy was drafted (200 articles/day capacity model), Brian set the starting scope. Rationale in Brian's words 2026-10-07: 100 blogs because one X79 can write the 200 daily articles with ~9 hours to spare, and those 9 hours go to optimization (QA passes, social posts, meme teases, distribution).

**Decision:** START with 100 blogs. 1000 blogs remains a horizon, not the plan. The 5-flagship validation gate stays as the on-ramp: prove write-improve-maximize-traffic on 5, then scale the factory to the full 100.

---

### dec-20261007-cf1: How should one X79 content-factory node spend its 24h?
**Decided:** 2026-10-07 00:57

**Context:** 100-blog network at 2 articles/blog/day = 200 articles/day (~2,700 tokens each). One dual-M40 X79 node produces ~320 articles/day at ~10 tok/s, leaving ~9h/day surplus. Discussed 2026-10-07 with Spencer; Brian specified the operating model.

**Decision:** One X79 node: (1) writes the 200 daily blog articles first (2 per blog x 100 blogs); (2) spends the remaining ~9h improving those articles (QA/rewrite passes), writing social posts, meme teases, and other content-maximizing strategies per the memes-tease/blog-pays-off/email-captures funnel. Quality passes before distribution.

---

### dec-20261004-brf1: What is the standing format for Brian's recurring briefings, and which channel does each use?
**Decided:** 2026-10-04 21:12

**Context:** Brian designed the full weekly briefing rhythm on 2026-10-04: Mon/Tue 5pm, Wed/Thu/Fri 10:30pm, Sunday 7:30pm.

**Decision:** CHANNELS: Mon/Tue 5pm go to Telegram via Altair's bot (only Telegram briefings all week — no TUI access on the bus). Wed/Thu/Fri 10:30pm and Sunday 7:30pm happen on Altair's TUI, handed to Altair via knowledge_bridge. FORMAT (standing briefing-conversation protocol, Altair conducts): 1) SUMMARY as one send (today bullets + tomorrow line, no issues yet); 2) ISSUES one at a time — present, ask Brian for feedback, follow-up questions on his feedback until satisfied, then next issue; 3) after issues, Altair asks its OWN questions one by one. On one-way Telegram each step is its own send in order.

---

### dec-20261004-lg1: Should LiveGood be added to the CryptoStreemz lineup?
**Decided:** 2026-10-04 18:41

**Context:** Emerged from the CryptoStreemz lineup discussion 2026-10-04; LiveGood ($9.95/mo, 2x15 matrix, 2.2M members) was considered but its income-claim marketing trips the perception test and its crypto-payout claim is unverified.

**Decision:** No. Brian will NOT promote LiveGood. It remains in the ecosystem only as SEO strategy fodder, competitive research, distributor scraping, and related strategies. Never add it to any skin lineup.

---

### dec-20261004-adb1: Who may read Altair's private database (the altair DB on k11-alpha)?
**Decided:** 2026-10-04 05:57

**Context:** Brian clarified the access rule for the Altair-specific database while placing the affiliate_intel schema there.

**Decision:** Spencer, Meghan, Lyra, Mavity, DealsDesk and other major workers/agents may all READ the altair database. It is NOT public — no public exposure of its contents.

---

### dec-20261004-adb2: Should successbrian-os give each user their own private altair-style database?
**Decided:** 2026-10-04 05:57

**Context:** Brian set the product direction: private per-user databases for user-specific workflows and business data.

**Decision:** Yes. successbrian-os should let each user create their own unique altair database — private tables/schemas relating to their specific workflows and business. This is a multi-tenancy product feature, not yet built.

---

## Topic: 150b

### 150b-off-alpha-1004: Should the DeepSeek 150B goal worker (altair-goal-loop) be removed from k11-alpha?
**Decided:** 2026-10-04 05:30

**Context:** Brian switched the local workhorse to Qwen3.6-35B-A3B (Sonic) on 2026-10-03. The old DeepSeek 150B goal worker (altair-goal-loop.service) was still enabled and running, potentially conflicting with the Qwen task worker.

**Decision:** Yes - remove DeepSeek 150B / altair-goal-loop from k11-alpha immediately (stopped and disabled 2026-10-04). Keep the option open to run and test 150B somewhere else on the ecosystem in the future.

---

## Topic: dec

### dec-20261003-a3b-opt: Keep Qwen3.6-35B-A3B as the workhorse model and optimize speed+quality via code/process tweaks instead of switching models?
**Decided:** 2026-10-03 20:12

**Context:** Brian 2026-10-03, after reviewing a Facebook post about a 2xA100 build running Qwen3.8-27B and a Spencer evaluation comparing it to the current Qwen3.6-35B-A3B workhorse (successbrian_os.reports id 22). Brian: 'I know Qwen 3.6 35B A3B isn't the smartest, but I want to tweek the code, the processes and tweek as much as possible to run workflows that optimize speed and quality.' Aligns with standing hardware principle: improvements from Python code and ecosystem integration, never bigger hardware or cloud spend.

**Decision:** Yes — optimize the A3B in place: server flags (speculative decoding, quant A/B incl. the Q4_K_M already on disk, batch pinning, KV cache type), plus workflow routing (penny/morpheus for easy work, A3B for hard), per-task reasoning budgets. A/B trials with a fixed task battery, one change at a time; live-server restarts need Brian's timing call.

---

### dec-20261003-os1: Should successbrian-os help its users research topics, build game plans, and file the resulting tasks/events into its project management system?
**Decided:** 2026-10-03 05:20

**Context:** Stated by Brian 2026-10-03 while setting up the local AI agent stack research goal (sbos_goals 12912) and the interview-webinar goal (12913). The OS should take a research topic, do the research, build the game plan, and put events and tasks into the main PM system (sbos_goals / sbos_projects / tasks / life_calendar / project_gates). successbrian-os is a public product for generic solopreneurs, so this workflow should become a reusable capability, not a one-off.

**Decision:** Yes. Research -> game plan -> PM filing becomes the standard workflow. Prove it end-to-end on the AI agent goal first, then spec it as a reusable OS module.

---

## Topic: aoostar

### aoostar-gptoss-q6: Model/quant for planned 8x Aoostar 24GB nodes?
**Decided:** 2026-10-02 20:40

**Context:** gpt-oss-20b Q8 (~21GB) too big for 24GB with OS+KV cache.

**Decision:** gpt-oss-20b Q6_K (~16GB), llama.cpp Vulkan. HW not purchased yet.

---

## Topic: dec

### dec-20261002-sub1: Should blog posts be reviewed before posting, or auto-posted?
**Decided:** 2026-10-02 19:19

**Context:** Friday Substack cadence during Idemia shift; applies to all blog posts.

**Decision:** Brian reviews every blog post before it is posted. Draft-for-review mode; no auto-posting.

---

## Topic: dealsdesk

### dealsdesk-gh-wire: Wire DealsDesk to GitHub?
**Decided:** 2026-10-02 13:32

**Context:** DealsDesk live at /home/dealsdesk (8.3G) had .git but no remote; private repo successbrian/dealsdesk existed empty.

**Decision:** Remote added (git@github.com:successbrian/dealsdesk.git). NOT pushed yet — uncommitted changes pending Brian review. .env and .price_cache/ are gitignored, safe.

---

## Topic: altair

### altair-q-escalation: How should Altair handle things it does not know?
**Decided:** 2026-10-02 13:32

**Context:** Per-project profiles cannot cover everything. Brian specified a tiered escalation.

**Decision:** 4-tier: (1) check project profile + codebase, (2) research it (web/docs), (3) stage question for Gemini or Spencer, (4) stage for Brian one at a time. Brian only sees what nobody else could resolve.

---

### altair-proj-profile: How should Altair manage context across many projects?
**Decided:** 2026-10-02 13:32

**Context:** Brian wants Altair to plan/write/debug/QA code across 40+ projects (SaaS sites, SEO blogs, DealsDesk, system upgrades) without scatter, run through GitHub. Survey found 11 projects (4 synced to GitHub, dealsdesk missing remote, saas/sites still planned).

**Decision:** Each project gets its own profile (rules, game plan, architecture, conventions) living in its GitHub repo. Altair loads the project profile when working on that project. Registry table: successbrian_os.projects_registry.

---

## Topic: kilo

### kilo-rm-000052: Remove remaining KiloCode services hitting kilo.ai (Brian 2026-10-02)
**Decided:** 2026-10-02 12:19

**Decision:** Done: stopped+disabled+deleted kilo-gateway.service (unused proxy to api.kilo.ai) and meghan-alpha-kilocode.service (old KiloCode Meghan CEO, redundant since Oct 1 OpenClaw rebuild). No kilo.ai traffic was actually flowing; kilo edge still blocks k11 IP. pipeline-healthcheck.service left in place — verified it never contacts kilo.ai (stale description only).

---

## Topic: alt

### alt-cap-000051: Fix Altair's side of the jive capture feed (Brian 2026-10-02)
**Decided:** 2026-10-02 12:05

**Decision:** Done by Spencer: Altair's Hermes plugin already captured every turn via its post_llm_call hook — the feed was never missing, just fragile. It shelled out to the decommissioned KiloCode helper and swallowed all failures silently. Repointed to canonical successbrian-os/tools/jive/capture.py; failures now log warnings instead of vanishing. Verified end-to-end in the real hermes venv. Original plugin backed up in place.

---

## Topic: jive

### jive-sbos-000050: Should jive become an official successbrian-os module and run only when needed?
**Decided:** 2026-10-02 10:48

**Context:** k11 cleanup 2026-10-02: jive.py was running every 30 min from the decommissioned KiloCode workspace, writing junk summary rows on idle runs; its capture feed froze 2026-10-01 when the old session hooks died.

**Decision:** Yes. Moved to successbrian-os/tools/jive/ (commits bf61fb5, bc14cf8), watermark-based on-demand worker, capture.py as sanctioned ledger writer, cron repointed, original quarantined to ~/.quarantine/20261002-jive/. Capture-hook spec sent to Altair (bridge 16966); he wires per-turn captures into his Hermes loop.

---

## Topic: manila

### manila-trip-onhold: December Manila trip to see Gina
**Decided:** 2026-10-02 04:57

**Context:** Brian 2026-10-02 confirmed: on hold is the decision. Originally planned Dec 2026, put on hold Sep 27 conversation, confirmed as formal decision Oct 2.

**Decision:** ON HOLD. The Dec 4-18 placeholder in the life plan is not active.

---

## Topic: skin

### skin-product-map-100: Skin to product mapping
**Decided:** 2026-10-02 04:54

**Context:** Brian 2026-10-02 correcting the income stream map. AnythingLLM workspaces confirm: TrafficStreemz, CryptoStreemz, AegeanVedaFlow as separate MLM/Network Marketing skins.

**Decision:** Three skins, three lanes: TrafficStreemz leads to Zilara. CryptoStreemz is the crypto lane (signals, analytics). AegeanVedaFlow is the Oliabo lane. Skins are marketing front-ends, not the products. Oliabo is part of AegeanVedaFlow, not TrafficStreemz or CryptoStreemz.

---

## Topic: ght

### ght-replacement-mlgs: GHT replacement pick
**Decided:** 2026-10-02 04:51

**Context:** Brian 2026-10-02 picked from GHT replacement shortlist. Replaces dropped Gotta Have Traffic.

**Decision:** My Lead Gen Secret - 30/mo plus 30 one-time setup. Closest done-for-you traffic analog to GHT.

---

## Topic: doc

### doc-vs-decision-time: How to resolve document vs reality mismatches
**Decided:** 2026-10-02 04:49

**Context:** Brian 2026-10-02: need decision dates to check if a document was written before the decision.

**Decision:** Check decision_timeline.py for the topic first. If the document predates the decision, it is not a conflict, just old. Update the doc with the decision date.

---

## Topic: drop

### drop-ght-focus-zilar: Income stream focus
**Decided:** 2026-10-02 04:42

**Context:** Brian 2026-10-02 during conflict-resolution session. GHT was $25/mo or $125/mo (Quint) in the original TrafficStreemz 5-stream plan.

**Decision:** Dropping Gotta Have Traffic (GHT). Current focus: Zilara + GotBackup.

---

## Topic: altair

### altair-no-private: Altair: no private system
**Decided:** 2026-10-01 20:39

**Context:** Brian 2026-10-01: the Sep 26 weekly-rhythm was invisible because it only existed in Altair-local SBOS.

**Decision:** Altair must not keep a private SBOS/system. All knowledge (decisions, learnings, session recaps, intel, second-brain) lives in the shared ecosystem tables (ecosystem_central) — never only in Altair-local sqlite/md stores. Migrate existing private stores in; quarantine originals, do not delete.

---

## Topic: sat

### sat-blast-rhythm: Saturday 12-hour blast rhythm
**Decided:** 2026-10-01 20:37

**Context:** Brian 2026-09-26 chat with Altair; recorded as SBOS goal #12081. Backfilled to shared table 2026-10-01 per Brian: document in the ecosystem, not just SBOS.

**Decision:** Weekly Saturday 7am-7pm intense work blast: CREW2 shift 7am-3:30pm + rest to 7pm. Ecosystem drives background work, zero pings during shift/rest, tight recap ~7pm.

---

## Topic: echo

### echo-nocolibri-1001: Should Colibri run on Node Echo?
**Decided:** 2026-10-01 17:57

**Context:** Node Echo = Xeon E3-1230 v6 + Supermicro X11SSL-F (16 PCIe lanes, 1x M.2, 6x SATA). Lane count cannot support 3-4x NVMe striped Colibri plan.

**Decision:** No. Node Echo is the infra node (16 planned services, GTX 980 utility GPU, bulk SATA storage). Colibri host decision remains open: Xeon Gold 62xx build, Aoostar Maco HX 470, or X79.

---

## Topic: meghan

### meghan-rebuild: Rebuild Meghan, strip what is not needed?
**Decided:** 2026-10-01 03:46

**Context:** Brian 2026-10-01: rebuild her, strip out what is not needed.

**Decision:** Done 2026-10-01. Model: local Morpheus (kilo.ai 403 from home IP was the root cause of her unavailable errors). Heartbeat: 30-min OpenClaw wake + deterministic systemd pass. Stripped: kilo.ai provider, telegram config, broad DB grants (least-privilege now), dead briefing pipeline. New: intel_buffer inbox, ceo_heartbeats proof-of-life. Left: gateway restart to load her new cron job.

---

## Topic: agent

### agent-integration-5: How are the agents integrated as a product?
**Decided:** 2026-10-01 03:25

**Context:** Brian 2026-10-01: make it a better product.

**Decision:** Five upgrades live 2026-10-01: shared work_queue (claim/ack); Lyra writes ecosystem_needs directly; ceo_directives table is Meghans steering wheel; AGENT_CONTRACT.md (generic, public repo); Spencer treated as scarce tier (routine to code/Altair/Lyra). Gap: Meghan does not read the bridge (5/161) - her inbound channel still unknown.

---

## Topic: build

### build-solves-map: How does DealsDesk avoid duplicate work when a need pops up?
**Decided:** 2026-10-01 03:20

**Context:** Brian 2026-10-01.

**Decision:** dealsdesk.build_solves maps each build to the ecosystem needs it addresses (with why). The daily audit flags uncovered needs for triage; covered needs never spawn duplicate plans. 11 links seeded.

---

## Topic: triage

### triage-to-dealsdesk: What happens when something is stuck in the ecosystem?
**Decided:** 2026-10-01 03:17

**Context:** Brian 2026-10-01.

**Decision:** Altair + Spencer + Meghan triage it: resolve, convert to a successbrian_os.ecosystem_needs row (read by DealsDesk), or escalate to Brian one at a time. OS ecosystem_needs is the single demand truth (26 rows).

---

## Topic: dealsdesk

### dealsdesk-autonomy: How autonomous is DealsDesk with ecosystem questions?
**Decided:** 2026-10-01 03:14

**Context:** Brian 2026-10-01.

**Decision:** Fully autonomous in ANSWERING: dealsdesk_responder.py tries deterministic strategies (deal check, budget, buy timing) and answers only with fresh data and high confidence. Unanswerable questions go to Brian one at a time. NEVER autonomous in purchasing: every buy is Brians call.

---

## Topic: who

### who-voices-questions: Who may ask Brian questions directly?
**Decided:** 2026-10-01 03:13

**Context:** Brian 2026-10-01.

**Decision:** Only Spencer or Altair voice questions to Brian (sweeper/outbox or check-ins). Meghan and Lyra write to pending_questions but never address Brian directly. surfaced_by tracks who asked.

---

## Topic: ask

### ask-queue-4agents: Which agents use the pending_questions queue?
**Decided:** 2026-10-01 03:12

**Context:** Brian 2026-10-01.

**Decision:** Spencer, Altair, Meghan, Lyra: all four can ask Brian via the queue (one at a time via sweeper). Every answered question auto-copies into altair.brian_learnings via trigger; all agents read those learnings.

---

### ask-queue-20261001: How should agents handle things they cannot answer themselves?
**Decided:** 2026-10-01 03:11

**Context:** Brian 2026-10-01.

**Decision:** Log them in successbrian_os.pending_questions (shared Spencer/Altair queue). Surface to Brian ONE AT A TIME via the sweeper (3x daily). Between passes, research open questions: attach options, mark researched, or resolve.

---

## Topic: public

### public-generic-20261: What may go into the public successbrian-os repo?
**Decided:** 2026-10-01 03:06

**Context:** Brian 2026-10-01: public product discipline.

**Decision:** Everything public — code, schemas, docs — must work for a GENERIC entrepreneur. Brian-specific customizations live outside the public git repo as a local overlay. No personal fleet data, pricing, or identifiers in public commits.

---

## Topic: why

### why-table-20261001: How should rationale be tracked for build items?
**Decided:** 2026-10-01 02:41

**Context:** Brian 2026-10-01: track multiple whys per item for future agent analysis.

**Decision:** dealsdesk.item_whys: one row per why per item (aspect: selection/price_target/timing/status_change/general; source: who recorded). item_why_latest view shows the newest. Rule: anything that sets or changes an item writes its why.

---

## Topic: no

### no-hardcoded-price: Should the solver hardcode prices?
**Decided:** 2026-10-01 02:39

**Context:** Brian 2026-10-01

**Decision:** No. Prices live in dealsdesk.market_prices and move with the market. Watch percentage changes against smart trend measures; watch news/intel to anticipate pricing trends and time purchases; expected drops factor into build priorities/timing.

---

## Topic: epyc

### epyc-timing-20261001: EPYC build timing?
**Decided:** 2026-10-01 02:39

**Context:** Brian 2026-10-01

**Decision:** Build ONE 256GB EPYC training system ASAP for model training. 2nd/3rd+ EPYC systems wait for expected 7402/SP3 price drops — be picky on pricing for those.

---

## Topic: watt

### watt-vs-budget-20261: Wattage vs budget tradeoff?
**Decided:** 2026-10-01 02:39

**Context:** Brian 2026-10-01

**Decision:** Prefer lower wattage unless exorbitantly cost-prohibitive. Early stages may require excessive wattage to protect the budget. Solver scores 2-year TCO and flags budget tension instead of deciding.

---

## Topic: no

### no-windows-tax-20261: Pay for Windows licenses or bundled extras?
**Decided:** 2026-10-01 02:39

**Context:** Brian 2026-10-01

**Decision:** No. Windows 10/11 tax is worth /bin/bash — stripped for Linux anyway. Same for any bundled extra he would strip and replace: compare on effective price of what he keeps.

---

### no-low-health-buys: What is the policy on buying used components with degraded health?
**Decided:** 2026-10-01 02:33

**Context:** Brian 2026-10-01, generalizing the drive health rule.

**Decision:** We do not buy low-health batteries or low-health storage drives. Same bar as drives: under 70% health or unknown health = reject, no exceptions.

---

## Topic: drive

### drive-health-scale: How should used drive prices scale with drive health?
**Decided:** 2026-10-01 02:32

**Context:** Brian 2026-10-01: sliding scale pricing targets based on health of the drives.

**Decision:** Sliding scale in dealsdesk.drive_price_tiers: 95-100% -> 70% of new, 90-94% -> 55%, 85-89% -> 40%, 80-84% -> 30%, 70-79% -> 20% steal-only, under 70% or UNKNOWN health -> reject. Never buy a drive blind. Health from SMART via drive_valuator.py.

---

## Topic: nvme

### nvme-gen4-20261001: Should DealsDesk default to Gen 4 NVMe, and when is Gen 3 acceptable?
**Decided:** 2026-10-01 02:31

**Context:** Brian 2026-10-01: Gen 4 is the better ecosystem asset even in a Gen 3 slot.

**Decision:** Buy Gen 4 NVMe by default; Gen 3 only on a steal (under half of Gen 4 street price, i.e. < 4 for 1TB).

---

## Topic: buildtrk

### buildtrk-20261001: How does the ecosystem track builds, prices, and budgets?
**Decided:** 2026-10-01 02:15

**Context:** DealsDesk held build docs as static markdown; deal pipeline hunted flips, not build parts.

**Decision:** DONE 2026-10-01 ~02:20 Spencer built it into DealsDesk routine: dealsdesk.builds canonical (25 builds), alert loop on systemd timer, dead gens deprecated-not-deleted. Altair lane: repair stale price_history feed (0/56 refreshes failing), Phase 3 upgrades, deal_flags vet destination.

---

## Topic: rack4u

### rack4u-20261001: What goes in the 4U rack case (final topology)?
**Decided:** 2026-10-01 01:39

**Context:** 4U case: MS-02 Ultra 235HX + 8x Aoostar 24GB + in-case NAS/extended storage. Network: cheapest 16-port 2.5GbE unmanaged switch (keepLiNK ~68 or Vimin ~16); one cable per node, no bonding. MS-02 10GbE port stays free for future use.

**Decision:** MS-02 Ultra 235HX (image gen/video edit/B50 box; Colibri node when GPU idle; 128GB DDR5-4800 target starting 2x32GB; 1 NVMe growing to 4) + 8x Aoostar 24GB (parallel Colibri 150B inference fleet, MS-02 as faster primary with 128GB RAM) + in-case NAS as ecosystem cold storage (model library, media vault, backups, QLoRA datasets) on 2.5GbE. Fleet LAN: 10 ports used (NAS+MS-02+8x Aoostar), 1 uplink to home network, 5 free for growth. Open items: rack cooling/thermals, power budget for 9 nodes + NAS + switch.

---

### rack4u-net-20261001: How is the 4U rack networked?
**Decided:** 2026-10-01 01:24

**Context:** 4U case: MS-02 Ultra 235HX + 8x Aoostar 24GB + in-case NAS, all on one 16-port 2.5GbE switch (single cable per node, no bonding).

**Decision:** In-4U NAS/extended storage on 2.5GbE as device 10 on the 16-port fleet switch (no 10GbE needed: spinning-disk arrays cannot saturate 2.5G). Role: ecosystem-wide cold storage - model weight library (150B, GLM 5.3 391GB INT4, quants), media vault (B50 image output, video projects, webinar recordings, blog-network assets), backups (AnythingLLM library, k11-alpha configs, node images), QLoRA training datasets. Hot data stays on local NVMe. MS-02 10GbE port stays free for future use.

---

## Topic: ms02u

### ms02u-role-20261001: What is the MS-02 Ultra 235HX box for?
**Decided:** 2026-10-01 01:11

**Context:** Core Ultra 5 235HX barebone (90). Future Arc Pro B50 LP (16GB, 70W, ~00 street, 49 MSRP) in Gen5 x16 slot when budget allows. B70 does not fit (full-height, 230W over the ~140W GPU power budget).

**Decision:** Primary: image generation + video editing box (B50). Secondary: Colibri inference node when the GPU pipeline is idle. Storage tiers: hot model weights on local NVMe (striped), cold bulk storage on NAS / extended storage box over the onboard 10GbE. Grows over time: 2x32GB RAM now -> 4x32GB, 1 NVMe now -> 2 striped -> dual-M.2 carrier for 4 total.

---

### ms02u-nvme-20261001: NVMe storage plan for the MS-02 Ultra 235HX Colibri box?
**Decided:** 2026-10-01 01:03

**Context:** 235HX has 2 onboard M.2 2280 PCIe 4.0 x4 slots (4 slots is 285HX-only via its NIC card). PCIe 5.0 x16 slot supports bifurcation for a future quad-M.2 carrier card.

**Decision:** Start with 1 NVMe. Add a 2nd onboard later (stripe RAID 0 for Colibri weight streaming). Later: quad-M.2 carrier card in the PCIe 5.0 x16 slot (only slot with x4/x4/x4/x4 bifurcation) to reach 4+ NVMe drives. Note: that slot is also the low-profile GPU slot, so quad-NVMe and dGPU are either/or.

---

### ms02u-ram-20261001: What RAM configuration for the MS-02 Ultra 235HX build?
**Decided:** 2026-10-01 01:01

**Context:** MS-02 Ultra (Core Ultra 5 235HX) barebone at 90 Newegg sale 2026-10-01. Board max DDR5-4800, 4x SODIMM slots, non-ECC only on 235HX. 256GB via 4x64GB sticks unaffordable at current spiked DDR5 prices.

**Decision:** 128GB DDR5-4800 SODIMM target (4x32GB, e.g. Crucial CT32G48C40S5), non-ECC. START with 2x32GB (64GB); add the other two sticks later. 256GB deferred until DDR5 prices cool.

---

## Topic: X79

### X79-20260927-13: Is blog hosting limited to the four X79 nodes?
**Decided:** 2026-09-27 14:47

**Context:** No — many nodes throughout the ecosystem will run blogs, not just the X79s. Decided 2026-09-27.

**Decision:** Fleet-wide hosting fabric. Blogs are distributed across all capable nodes (X79s, K11s, EPYC, etc.). Blog-to-node placement becomes a scheduling problem — Lyra's domain as health monitor and workflow organizer. The CMS must be fleet-aware: blogs can move between nodes. Database topology (central vs distributed) is now a bigger design question for Altair.

---

### X79-20260927-12: When and how do we launch the CMS publicly?
**Decided:** 2026-09-27 14:45

**Context:** Timing question from X79-20260927-11, decided 2026-09-27.

**Decision:** Public from day one. Framed as a beta: old DDR3 hardware that primarily runs AI inference, and oh by the way also serves as many blog domains as we can throw at it. The pitch is efficiency — every watt doing double duty. Inference is the main job; the entire blog network is the side gig. The budget constraint is the story.

---

### X79-20260927-11: Do we open-source the custom CMS?
**Decided:** 2026-09-27 14:43

**Context:** Brian decided 2026-09-27: yes, publish publicly on GitHub.

**Decision:** Yes — the CMS core goes public on GitHub. Private stays private: blog content, keyword/SEO strategies, affiliate configurations, API keys, and ranking tactics. Open: license choice (GPL vs MIT vs AGPL), publish timing (build-in-public from day one vs working release first).

---

### X79-20260927-09: How do we handle WordPress plugin functionality?
**Decided:** 2026-09-27 14:42

**Context:** No WP compatibility layer. Instead: read the plugins we want, adapt/rebuild their features natively into the custom CMS.

**Decision:** Cherry-pick, don't compat. For each plugin we want (SEO, schema, sitemaps, affiliate, etc.), read its approach and reimplement the functionality natively in our CMS. No WordPress core fork, no plugin API surface to maintain. Smaller build, cleaner codebase, no inherited cruft.

---

### X79-20260927-10: How are the four X79 nodes organized?
**Decided:** 2026-09-27 14:42

**Context:** Hardware stays identical (test-once-deploy-four-times). Software workload is organized by plugin/feature profile: blogs are assigned to nodes based on which adapted-plugin features they need.

**Decision:** Identical hardware, specialized software profiles. Each node runs the plugin set its assigned blogs need. Keeps per-node memory footprint lean (no unused plugin code loaded) and isolates plugin issues to one node's blog set. Open: one shared database vs per-node database — Altair to recommend.

---

### X79-20260927-08: What CMS architecture serves the SEO blog network?
**Decided:** 2026-09-27 14:40

**Context:** Not static sites. Brian wants database-driven, custom-built off WordPress concepts: SEO-focused, marketing-focused, able to run WordPress plugins, one system + one database serving many blog domains.

**Decision:** Custom multi-tenant CMS: one system, one database, many domains (domain-scoped content). Database-driven, SEO/marketing-first, WordPress-plugin compatible. This is a significant software build — Altair's domain. Replaces the static-vs-WordPress question.

---

### X79-20260927-07: Do the X79 nodes serve the SEO blog network directly?
**Decided:** 2026-09-27 14:38

**Context:** Originally framed as batch content generation + background worker jobs. Brian clarified 2026-09-27: the X79s will SERVE the SEO blogs.

**Decision:** Yes. Each X79 node is a production web host for ~25 blogs (100 blogs / 4 nodes). This makes uptime, SSL, deployment pipeline, and backups first-class requirements — not just batch throughput. The M.2 boot drive + CPU threads allocation now has a concrete job: serving live traffic. Static-site vs WordPress architecture still open (see question for Brian).

---

### X79-20260927-06: What is the hardware sourcing principle going forward?
**Decided:** 2026-09-27 14:30

**Context:** X79-SERVER V1.3 boards are Chinese aftermarket with no manual and unknown provenance. Brian will not buy mystery hardware again.

**Decision:** No more mystery hardware. Future buys are known-quantity only (K11s, EPYC from Core 4, anything with a real manual). The X79s get documented as a community use case for existing owners — "here's what I built, here's what worked" — NOT a buying recommendation. Spirit is generosity, not a warning label. All four builds as identical as possible for test-once-deploy-four-times.

---

### X79-20260927-01: What is the final X79 node architecture?
**Decided:** 2026-09-27 14:30

**Context:** Four X79-SERVER V1.3 dual-LGA2011 boards (Chinese aftermarket, no manual). Each has 2x Xeon E5-2650 v2, 4x DDR3 DIMM slots (64GB max), 2x PCIe Gen 3 x16 slots, 2x smaller PCIe (likely Gen 2) slots, 1x onboard M.2 NVMe.

**Decision:** Four identical dual-role nodes. Per node: 2x GPU for inference + 2x Gen 2 NVMe striped (RAID 0) for a Colibri-streamed model + 1x motherboard M.2 NVMe (single, boot) + remaining CPU threads for web hosting/scraping. No phase transition — inference AND worker jobs simultaneously from day one. Long-term ecosystem design.

---

### X79-20260927-04: Where does Shakespeare (70B) live permanently?
**Decided:** 2026-09-27 14:30

**Context:** Shakespeare needs ~40GB at Q4. Dual M40 = 48GB VRAM. Originally considered interim; Brian corrected to permanent.

**Decision:** Shakespeare's permanent home is the dual-M40 X79 node. "Always home for Shakespeare." 70B Q4_K_M (~40GB) fits in 48GB with headroom for context. ~8-12 tok/s at 150W power limit.

---

### X79-20260927-03: Is the Tesla M40 still the right GPU for the X79 nodes?
**Decided:** 2026-09-27 14:30

**Context:** M40 24GB at ~$105-150 used ($5/GB, cheapest 24GB path). P40 24GB at ~$220-300 (better arch, ~2x price for ~30-50% more throughput). $400-700 cards (3060 12GB, A4000 16GB, 3090 24GB) cannot provide 48GB across two slots for 70B.

**Decision:** M40 stays. 2x per node (48GB VRAM), power-limited to 150W each via nvidia-smi (decode is VRAM-bandwidth bound, ~10 tok/s holds at 150W; only prefill slows). Buy 7 more M40s (~$125 each) for uniformity across all four nodes. P40 premium does not pay back for batch inference.

---

### X79-20260927-02: What is the X79 storage layout?
**Decided:** 2026-09-27 14:30

**Context:** Each board has 1x onboard M.2, 2x small PCIe slots (Gen 2) for NVMe adapters, plus SATA ports. Triple-stripe vs split debated.

**Decision:** Boot from single motherboard M.2 NVMe (simple, reliable, I/O isolation). 2x Gen 2 NVMe striped via PCIe adapters as model volume (~4GB/s, 4TB). SATA SSD for databases/active scrape data, SATA HDD for logs/archives/cold storage. Full tiering: NVMe (hot) / SATA SSD (warm) / HDD (cold). Do NOT triple-stripe all three — keep OS isolated from model streaming I/O.

---

### X79-20260927-05: What workload do the X79 nodes serve?
**Decided:** 2026-09-27 14:30

**Context:** Not interactive chat. Batch content generation for the 100-blog network and related properties.

**Decision:** Batch content factory: blog posts, web page sales content, video scripts, email sequences. Nobody waits interactively — throughput over hours matters, not latency. ~10 tok/s = ~100+ articles per node overnight. Also absorbs AnythingLLM nightly maintenance (dedup, embeddings, hygiene) offloaded from k11-alpha.

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
