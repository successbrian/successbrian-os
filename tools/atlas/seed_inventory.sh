#!/bin/bash
# Atlas inventory seed: everything that maps to a project.
cd /home/successbrian/successbrian-os/tools/atlas
# DB auth via ~/.pgpass (through atlas.py) — no password in this script.
A="python3 atlas.py"

# ---- AnythingLLM workspaces (15, doc counts 2026-10-17) ----
$A add-node allm:blog-network allm_workspace "Blog Network" --details '{"docs": 78}'
$A add-node allm:career allm_workspace "Career" --details '{"docs": 2}'
$A add-node allm:contactflowcrm allm_workspace "ContactFlowCRM" --details '{"docs": 7}'
$A add-node allm:crypto-trading-yield allm_workspace "Crypto Trading & Yield" --details '{"docs": 55}'
$A add-node allm:dealsdesk allm_workspace "DealsDesk" --details '{"docs": 610}'
$A add-node allm:gina-immigration allm_workspace "Gina & Immigration" --details '{"docs": 1}'
$A add-node allm:home-lab allm_workspace "Home Lab" --details '{"docs": 1255}'
$A add-node allm:mlm-income allm_workspace "MLM Income" --details '{"docs": 306}'
$A add-node allm:money-investing allm_workspace "Money & Investing" --details '{"docs": 10}'
$A add-node allm:mountain-north allm_workspace "Mountain North Rural Network" --details '{"docs": 6}'
$A add-node allm:people-pipeline allm_workspace "People Pipeline" --details '{"docs": 14}'
$A add-node allm:quarantine allm_workspace "Quarantine" --details '{"docs": 10}'
$A add-node allm:successbrian-os allm_workspace "successbrian-os" --details '{"docs": 1}'
$A add-node allm:trafficstreemz allm_workspace "TrafficStreemz" --details '{"docs": 2}'
$A add-node allm:unsorted allm_workspace "Unsorted" --details '{"docs": 135}'

# ---- Cron jobs ----
$A add-node cron:phone-location-pings cron_job "phone-location-pings" --details '{"schedule": "every 30m"}'
$A add-node cron:allm-workspaces-fragment cron_job "anythingllm-workspaces fragment" --details '{"schedule": "daily 06:35"}'
$A add-node cron:pm-master-fragment cron_job "pm-master fragment" --details '{"schedule": "daily 05:45"}'
$A add-node cron:unified-inbox cron_job "unified inbox" --details '{"schedule": "daily 05:15"}'
$A add-node cron:p9-snapshot cron_job "vera P9 social snapshot" --details '{"schedule": "daily 06:47"}'
$A add-node cron:tiktok-affiliate-intel cron_job "tiktok affiliate intel" --details '{"schedule": "daily 16:42"}'

# ---- Code ----
$A add-node code:atlas-cli code "Atlas CLI" --details '{"path": "tools/atlas/atlas.py"}'
$A add-node code:allm-workspaces-fragment-builder code "allm workspaces fragment builder" --details '{"path": "tools/dashboard/build_anythingllm_workspaces_fragment.py"}'
$A add-node code:pm-master-builder code "pm-master fragment builder" --details '{"path": "tools/dashboard/build_pm_master_fragment.py"}'
$A add-node code:spencer-briefing code "spencer-briefing" --details '{"path": "~/workspace/bin/spencer-briefing"}'

# ---- Integrations ----
$A add-node int:gmail integration "Gmail"
$A add-node int:systemeio integration "systeme.io" --details '{"role": "email"}'
$A add-node int:flexifunnels integration "FlexiFunnels" --details '{"role": "capture"}'
$A add-node int:hirofm integration "hiro.fm" --details '{"role": "audio nurture"}'
$A add-node int:adilo integration "adilo" --details '{"role": "video"}'
$A add-node int:instagram integration "Instagram"
$A add-node int:facebook integration "Facebook"

# ---- Models ----
$A add-node model:sonic-qwen36-35b model "Sonic (Qwen3.6-35B Q6_K)" --details '{"role": "workhorse"}'
$A add-node model:qwen3-30b-a3b model "Qwen3-30B-A3B" --details '{"role": "classify/chat on GT103s"}'
$A add-node model:deepseek-150b model "DeepSeek 150B" --details '{"role": "heavy reasoning"}'
$A add-node model:penny-7b model "Penny 7B" --details '{"role": "intent classifier"}'
$A add-node model:morpheus-14b model "Morpheus 14B" --details '{"role": "chat engine"}'

# ---- Infra nodes ----
$A add-node infra:k11-alpha infra_node "k11-alpha" --status active --details '{"role": "main: Postgres, Sonic, core services"}'
$A add-node infra:node-zero infra_node "Node Zero" --status active --details '{"role": "web hosting, dashboard"}'
$A add-node infra:r630 infra_node "R630" --status planned --details '{"role": "scrapers, script boxes, utility DBs"}'
$A add-node infra:mantis-5 infra_node "Mantis-5" --status planned --details '{"note": "backup MSV box"}'
$A add-node infra:ms-02 infra_node "MS-02" --status planned --details '{"role": "150B inference"}'
$A add-node infra:dl380-1 infra_node "DL380 #1" --status active --details '{"role": "Proxmox"}'
$A add-node infra:dl380-2 infra_node "DL380 #2" --status active --details '{"role": "Proxmox"}'

# ---- Databases ----
$A add-node db:ecosystem-central database "ecosystem_central" --status active
$A add-node db:people-unified database "people_unified" --status active
$A add-node db:altair database "altair (private)" --status active

# ---- Projects ----
$A add-node proj:dashboard project "Dashboard" --status active
$A add-node proj:homelab project "Home lab" --status active
$A add-node proj:dealsdesk project "DealsDesk" --status active

# ---- Edges: inventory maps to projects ----
$A add-edge allm:home-lab proj:homelab maps-to
$A add-edge allm:dealsdesk proj:dealsdesk maps-to
$A add-edge cron:allm-workspaces-fragment proj:dashboard maps-to
$A add-edge cron:pm-master-fragment proj:dashboard maps-to
$A add-edge cron:unified-inbox proj:dashboard maps-to
$A add-edge code:allm-workspaces-fragment-builder proj:dashboard maps-to
$A add-edge code:pm-master-builder proj:dashboard maps-to
$A add-edge infra:k11-alpha db:ecosystem-central hosts
$A add-edge infra:k11-alpha db:people-unified hosts
$A add-edge infra:node-zero proj:dashboard hosts --notes "serves the dashboard"
$A add-edge model:sonic-qwen36-35b infra:k11-alpha runs-on
$A add-edge r630-acquire infra:r630 maps-to --notes "acquisition yields the node"
$A add-edge db:people-unified enrichment-engine supports
$A add-edge db:people-unified msv-revival supports
$A add-edge int:instagram social-crosslink supports
$A add-edge int:facebook social-crosslink supports
$A add-edge cron:p9-snapshot social-crosslink supports
$A add-edge cron:phone-location-pings proj:homelab maps-to --notes "weekly-flow telemetry"
echo SEED-DONE
