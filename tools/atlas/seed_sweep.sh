#!/bin/bash
# Atlas sweep seed: deduped candidates from 5 reviewers
# (Altair 2nd brain, Altair chats, Spencer memory, Meghan heartbeats, AnythingLLM)
cd /home/successbrian/successbrian-os/tools/atlas
export PGPASSWORD=postgres
A="python3 atlas.py"
N() { $A add-node "$1" "$2" "$3" --status "$4" --details "$5"; }
E() { if [ -n "$4" ]; then $A add-edge "$1" "$2" "$3" --notes "$4"; else $A add-edge "$1" "$2" "$3"; fi; }

# ---------- PROJECTS ----------
N proj:colibri project "Colibri (EPYC Rome 150B program)" active '{"note":"150B local-inference program; BOM, 4 purchase gates, daily price watch"}'
N proj:epyc-colibri-builds project "EPYC Rome Colibri builds" planned '{"note":"DDR4 EPYC Rome builds; 8x32GB DDR4-3200, DRAM-less NVMe tier"}'
N proj:150b-inference project "150B inference program" planned '{"note":"DeepSeek 150B: MS-02/B50 Phase 6 on-ramp, EVO-X5 Pro Phase 9 home"}'
N proj:aoostar-mesh project "Aoostar agent-home + inference mesh" planned '{}'
N proj:per-user-db project "Per-user private databases" planned '{"note":"each successbrian-os user gets own private altair-style DB"}'
N proj:zilara project "Zilara income stream" active '{"note":"flagship MLM; Executive rank deadline Nov 1"}'
N proj:blog-network project "100-blog network" active '{"note":"100 niche blogs as lead magnets + custom CMS"}'
N proj:substack project "Substack (Friday cadence)" active '{"note":"weekly Friday post, draft-for-review"}'
N proj:contactflowcrm project "ContactFlowCRM" active '{"note":"sellable SaaS for network marketers; shared data layer"}'
N proj:trafficstreemz-plugin project "TrafficStreemz plugin" active '{"note":"public repo v0.1.0; first agentic AI for network marketers"}'
N proj:saturday-podcast project "Saturday podcast (private learning)" active '{"note":"Brian-only learning feed, NOT audience content"}'
N proj:plugin-ecosystem project "Plugin ecosystem" planned '{"note":"plugin.yaml manifests, lifecycle, sbos plugin install"}'
N proj:timeblock-engine project "Timeblock engine (Reclaim replacement)" planned '{}'
N proj:chicago-tardis project "Chicago TARDIS 2026" active '{"note":"Nov 27-29, Westin Chicago Lombard"}'
N proj:mavity project "Mavity" active '{"note":"agent system with own architecture doc"}'
N proj:oliabo project "Oliabo (Vera campaign)" active '{"note":"MLM income engine"}'
N proj:mountain-north project "Mountain North Rural Network" active '{}'

# ---------- GATES ----------
N gate:zilara-executive-nov1 gate "Zilara Executive by Nov 1" pending '{"note":"hard deadline; unlocks invite-only leadership Zoom"}'

# ---------- PLANS (Meghan CEO enforcement layer + build plans) ----------
N plan:msv-freeze plan "MSV/enrichment write freeze" active '{"note":"12 scraper units masked, self-healing loop stopped, 24 rows quarantined"}'
N plan:v4-freeze plan "DeepSeek V4 Pro freeze + reroute" active '{"note":"balance frozen; all V4 jobs rerouted to Sonic/local"}'
N plan:outbox-repair plan "Telegram outbox delivery repair" active '{"note":"188 msgs queued since Sep 30; prove 1 delivery by Mon 9 AM"}'
N plan:price-feed-repair plan "DealsDesk price feed repair" active '{"note":"market_price_history 388h stale; no profit numbers until live"}'
N plan:dealsdesk-dedup plan "DealsDesk dedup + one-question-per-issue" active '{"note":"outbox 85% duplicates; dedup keyed on listing id + price"}'
N plan:trading-halt plan "Trading + hardware flipping halt" active '{"note":"board directive: halt until data pipelines reliable"}'
N plan:scheduler-rebalance plan "Scheduler rebalance (jitter)" planned '{"note":"0-14 min jitter per agent; fixes quarter-hour thundering herd"}'
N plan:permission-grants plan "Agent permission grants" researching '{"note":"blocks CEO verification of own decisions"}'
N plan:intel-bus-fix plan "Intel bus self-echo fix" planned '{"note":"all 127 intel_buffer rows are meghan-alpha self-echo"}'
N plan:fleet-node-2 plan "Second fleet node for agent workloads" planned '{"owner":"altair"}'
N plan:mlm-resource-call plan "MLM resource redirect" researching '{"note":"open allocation decision, left with Brian"}'
N plan:proxmox-dl380s plan "Proxmox on 2x DL380s" active '{"note":"build order #1, before R630 purchase"}'
N plan:vera-on-r630 plan "Vera home on R630" planned '{"note":"MSV scraping + Vera/enrichment on R630, no Mantis-5 wait"}'

# ---------- INFRA ----------
N infra:node-echo infra_node "Node Echo" planned '{"note":"rack timekeeper, always-on scheduler, 8th Proxmox node"}'
N infra:evo-x5-pro infra_node "EVO-X5 Pro" planned '{"note":"best long-term 150B home; Phase 9"}'

# ---------- HARDWARE ----------
N hardware:mantis-1 hardware "Mantis-1 (X79)" planned '{"owned":"board+CPUs","note":"build order #3"}'
N hardware:mantis-2 hardware "Mantis-2 (X79)" planned '{"owned":"board+CPUs","note":"long-term home of first 100 SEO blogs"}'
N hardware:mantis-3 hardware "Mantis-3 (X79)" planned '{"note":"dual Tesla V100 32GB decided"}'
N hardware:mantis-4 hardware "Mantis-4 (X79)" planned '{"note":"dual Tesla V100 32GB"}'
N hardware:mantis-6 hardware "Mantis-6 (dual LGA2011)" planned '{"note":"SearXNG workers + AI analysis"}'
N hardware:mantis-7 hardware "Mantis-7 (dual LGA2011)" planned '{"note":"scraper overflow (proposed)"}'
N hardware:mantis-8 hardware "Mantis-8 (dual LGA2011)" planned '{"note":"scraper overflow (proposed)"}'
N hardware:maco-v100-oculink hardware "4x Maco+V100 OCuLink eGPU nodes" planned '{"note":"4U ventilated shelf Frame B; CONTINGENT on 4-node scale-up"}'
N hardware:evo-x5-cluster hardware "EVO-X5 Pro 4-node cluster" planned '{"note":"4 nodes in 2U; distant future, gated on readiness"}'
N hardware:evo-x3-test hardware "EVO-X3 test unit" planned '{"note":"buy ONE early to test"}'
N hardware:rx6800-x4 hardware "4x AMD RX 6800 16GB" planned '{"note":"GPUs for all-AMD Colibri build"}'
N hardware:arc-b70 hardware "Arc Pro B70 GPUs" planned '{"note":"dual B70 on servers, single on OCuLink eGPU"}'

# ---------- INTEGRATIONS ----------
N int:whatsapp integration "WhatsApp" active '{"note":"deepening standard: serious members get WhatsApp + Email"}'
N int:n8n integration "n8n" researching '{"note":"wanted ecosystem-wide for events/webhooks/triggers"}'

# ---------- MODELS ----------
N model:shakespeare-70b model "Shakespeare 70B" planned '{"note":"blog content factory + 70B ecosystem generalist"}'
N model:qwen38-flash-125b model "Qwen3.8-Flash-Next 125B MoE" planned '{"note":"Strata engine target for dual-V100 nodes"}'
N model:gemma4-26b model "Gemma-4-26B-A4B" planned '{"note":"parallel agentic workers on 2x OCuLink nodes"}'

# ---------- CODE ----------
N code:memory-ai-intel code "memory-ai-intel collector" active '{"note":"SEC EDGAR + news + YouTube + retail drift; stock watch, bubble radar"}'
N code:ecosystem-write-mcp code "ecosystem-write MCP server" active '{"note":"submit_intel -> outreach.memory_ai_intel"}'
N code:colibri-engine code "Colibri inference engine" active '{"note":"JustVugg/colibri; pure-C NVMe-streaming MoE"}'
N code:infra-sourcing-engine code "infra_sourcing_engine.py" active '{"note":"DealsDesk infra sourcing"}'
N code:dealsdesk-repo code "DealsDesk tracker repo" active '{"note":"ratified source of truth for DealsDesk work"}'

# ---------- DOCS (AnythingLLM finds) ----------
N doc:sbos-agent-architecture doc "SBOS_AGENT_ARCHITECTURE.md" active '{"kind":"allm","workspace":"home-lab"}'
N doc:shared-enrichment-architecture doc "SHARED_ENRICHMENT_ARCHITECTURE" active '{"kind":"allm","workspace":"home-lab"}'
N doc:msv-improvements-plan doc "msv-improvements-plan" active '{"kind":"allm","workspace":"mlm-income"}'
N doc:server-buying-strategy doc "server-buying-strategy-2026-09-11.md" active '{"kind":"allm","workspace":"home-lab"}'
N doc:llm-fallback-architecture doc "LLM Fallback Architecture" active '{"kind":"allm","workspace":"home-lab"}'
N doc:agent-comms-strategy doc "AGENT_COMMS_STRATEGY.md" active '{"kind":"allm","workspace":"home-lab"}'
N doc:oliabo-outreach-blueprint doc "OLIABO_OUTREACH_BLUEPRINT.md" active '{"kind":"allm","workspace":"mlm-income"}'
N doc:oliabo-business-system-plan doc "oliabo-business-system-plan" active '{"kind":"allm","workspace":"mlm-income"}'
N doc:oliabo-recruitment-playbook doc "OLIABO_RECRUITMENT_PLAYBOOK.md" active '{"kind":"allm","workspace":"mlm-income"}'
N doc:audience-growth-master-matrix doc "Audience Growth Master Matrix" active '{"kind":"allm","workspace":"blog-network"}'
N doc:affiliate-launch-radar-charter doc "Affiliate Launch Radar Charter" active '{"kind":"allm","workspace":"blog-network"}'
N doc:fridley-intelligence-stack doc "fridley-intelligence-stack" active '{"kind":"allm","workspace":"blog-network"}'
N doc:patience-procurement-strategy doc "patience-procurement-strategy.md" active '{"kind":"allm","workspace":"dealsdesk"}'
N doc:node-profit-model doc "node-profit-model.md" active '{"kind":"allm","workspace":"dealsdesk"}'
N doc:sbos-dealsdesk-integration-plan doc "sbos-dealsdesk-integration-plan" active '{"kind":"allm","workspace":"mlm-income"}'
N doc:sbos-integration-architecture doc "sbos-integration-architecture" active '{"kind":"allm","workspace":"mlm-income"}'
N doc:cryptostreemz-yield-architect doc "CryptoStreemz_Yield_Architect_Master.md" active '{"kind":"allm","workspace":"crypto-trading-yield"}'
N doc:mavity-architecture doc "MAVITY-ARCHITECTURE.md" active '{"kind":"allm","workspace":"home-lab"}'
N doc:contactflowcrm-architecture doc "ContactFlowCRM DB architecture" active '{"kind":"allm","workspace":"contactflowcrm"}'
N doc:mountain-north-strategy doc "mountain-north-strategy-CONDENSED.md" active '{"kind":"allm","workspace":"mountain-north"}'
N doc:x79-board-specs doc "x79-board-specs-canonical" active '{"kind":"second_brain","note":"4 DIMM, 64GB max, dual E5-2650 v2"}'
N doc:quant-policy doc "Quant policy" active '{"kind":"business_rule","note":"1T+ Q3, 500B-1T Q4, <500B Q6"}'
N doc:v100-powercap doc "V100 power cap policy" active '{"kind":"business_rule"}'
N doc:freeze-protocol doc "Freeze protocol" active '{"kind":"meghan_doctrine"}'
N doc:deal-alert-criteria doc "Deal-alert criteria" active '{"kind":"meghan_rule","note":"escalate only <$150 shipped, 16GB+ RAM, 30% margin"}'
N doc:enrichment-vendor-stance doc "Enrichment vendor stance" active '{"kind":"decided","note":"no vendor, no spend"}'
N doc:tcpa-stance doc "TCPA stance" active '{"kind":"compliance","note":"lawyer review before outbound AI calling"}'

# ---------- EDGES ----------
E proj:zilara gate:zilara-executive-nov1 requires
E int:adilo proj:zilara supports
E int:whatsapp proj:audience supports
E proj:contactflowcrm proj:trafficstreemz-plugin supports
E proj:colibri infra:ms-02 requires
E proj:colibri proj:homelab maps-to
E proj:colibri proj:epyc-colibri-builds requires
E proj:epyc-colibri-builds proj:150b-inference enables
E infra:ms-02 proj:150b-inference supports
E infra:evo-x5-pro proj:150b-inference supports
E plan:proxmox-dl380s proj:aoostar-mesh enables
E hardware:mantis-2 proj:blog-network hosts
E model:shakespeare-70b proj:blog-network supports
E model:shakespeare-70b proj:saturday-podcast supports
E model:qwen38-flash-125b hardware:mantis-3 runs-on
E model:qwen38-flash-125b hardware:mantis-4 runs-on
E model:qwen38-flash-125b hardware:maco-v100-oculink runs-on
E model:gemma4-26b hardware:maco-v100-oculink runs-on
E model:sonic-qwen36-35b hardware:maco-v100-oculink runs-on
E hardware:evo-x5-cluster model:deepseek-150b hosts
E hardware:rx6800-x4 proj:colibri maps-to
E hardware:maco-v100-oculink proj:homelab maps-to
E hardware:mantis-1 proj:homelab maps-to
E hardware:mantis-2 proj:homelab maps-to
E hardware:mantis-3 proj:homelab maps-to
E hardware:mantis-4 proj:homelab maps-to
E hardware:mantis-6 proj:homelab maps-to
E hardware:mantis-7 proj:homelab maps-to
E hardware:mantis-8 proj:homelab maps-to
E hardware:evo-x3-test proj:homelab maps-to
E hardware:arc-b70 proj:homelab maps-to
E code:memory-ai-intel db:ecosystem-central supports
E code:infra-sourcing-engine proj:dealsdesk maps-to
E code:dealsdesk-repo proj:dealsdesk maps-to
E coding-harness proj:plugin-ecosystem requires
E allm:blog-network proj:blog-network maps-to
E allm:mlm-income proj:zilara maps-to
E proj:substack proj:audience maps-to
E proj:blog-network proj:audience feeds
E proj:substack proj:audience feeds
E infra:node-echo rack-20u-a maps-to
E infra:node-echo proj:homelab supports
E plan:vera-on-r630 r630-acquire requires
E plan:msv-freeze msv-revival blocks
E plan:msv-freeze enrichment-engine blocks
E plan:v4-freeze model:sonic-qwen36-35b requires
E plan:outbox-repair proj:dashboard supports
E plan:price-feed-repair proj:dealsdesk enables
E plan:dealsdesk-dedup proj:dealsdesk supports
E plan:dealsdesk-dedup plan:permission-grants requires
E plan:trading-halt proj:dealsdesk blocks
E plan:scheduler-rebalance proj:pm supports
E plan:intel-bus-fix proj:pm supports
E plan:fleet-node-2 proj:homelab supports
E doc:sbos-agent-architecture proj:atlas documents
E doc:agent-comms-strategy proj:atlas documents
E doc:sbos-integration-architecture proj:atlas documents
E doc:shared-enrichment-architecture enrichment-engine documents
E doc:msv-improvements-plan msv-revival documents
E doc:server-buying-strategy proj:dealsdesk documents
E doc:patience-procurement-strategy proj:dealsdesk documents
E doc:node-profit-model proj:dealsdesk documents
E doc:sbos-dealsdesk-integration-plan proj:dealsdesk documents
E doc:llm-fallback-architecture proj:homelab documents
E doc:oliabo-outreach-blueprint proj:oliabo documents
E doc:oliabo-business-system-plan proj:oliabo documents
E doc:oliabo-recruitment-playbook proj:oliabo documents
E doc:audience-growth-master-matrix proj:audience documents
E doc:affiliate-launch-radar-charter proj:audience documents
E doc:fridley-intelligence-stack fridley-move documents
E doc:cryptostreemz-yield-architect proj:shared-brain documents
E doc:mavity-architecture proj:mavity documents
E doc:contactflowcrm-architecture proj:contactflowcrm documents
E doc:mountain-north-strategy proj:mountain-north documents
E doc:x79-board-specs hardware:mantis-1 documents
E doc:quant-policy proj:colibri documents
E doc:quant-policy proj:dealsdesk documents
E doc:v100-powercap hardware:maco-v100-oculink documents
E doc:freeze-protocol plan:msv-freeze documents
E doc:deal-alert-criteria proj:dealsdesk documents
E doc:enrichment-vendor-stance enrichment-engine documents
E doc:tcpa-stance proj:audience documents

# ms-02 details refresh (decided config)
$A add-node infra:ms-02 infra_node "MS-02" --status planned --details '{"config":"235HX + 128GB DDR5 + Arc Pro B50 16GB + 2x 4TB NVMe","role":"70B-and-up inference; Phase 6 150B on-ramp"}'
echo SWEEP-SEED-DONE
