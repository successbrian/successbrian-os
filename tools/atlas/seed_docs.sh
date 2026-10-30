#!/bin/bash
# Atlas doc-source seed: all documentation mapped to the projects/items it tracks.
cd /home/successbrian/successbrian-os/tools/atlas
# DB auth via ~/.pgpass (through atlas.py) — no password in this script.
A="python3 atlas.py"

# ---- Project nodes for the docs to map to ----
$A add-node proj:shared-brain project "Shared community brain" --status active
$A add-node proj:audience project "Audience system" --status active
$A add-node proj:pm project "PM (master)" --status active
$A add-node proj:tiktok project "TikTok Shop affiliate" --status active
$A add-node proj:atlas project "Atlas" --status active

# ---- Repo docs (successbrian-os) ----
$A add-node doc:shared-brain-strategy doc "SHARED-BRAIN-STRATEGY.md" --details '{"kind": "repo_doc", "path": "docs/SHARED-BRAIN-STRATEGY.md"}'
$A add-node doc:audience-architecture doc "AUDIENCE-ARCHITECTURE.md" --details '{"kind": "repo_doc", "path": "docs/AUDIENCE-ARCHITECTURE.md"}'
$A add-node doc:audience-harness doc "AUDIENCE-HARNESS.md" --details '{"kind": "repo_doc", "path": "docs/AUDIENCE-HARNESS.md"}'
$A add-node doc:audience-tool-integrations doc "AUDIENCE-TOOL-INTEGRATIONS.md" --details '{"kind": "repo_doc", "path": "docs/AUDIENCE-TOOL-INTEGRATIONS.md"}'
$A add-node doc:audience-needs-brian doc "AUDIENCE-NEEDS-BRIAN.md" --details '{"kind": "repo_doc", "path": "docs/AUDIENCE-NEEDS-BRIAN.md"}'
$A add-node doc:pm-master-contract doc "PM-MASTER-CONTRACT.md" --details '{"kind": "repo_doc", "path": "docs/PM-MASTER-CONTRACT.md"}'
$A add-node doc:fleet-map doc "fleet-map.md" --details '{"kind": "repo_doc", "path": "docs/fleet-map.md"}'
$A add-node doc:fleet-roadmap doc "fleet-roadmap.md" --details '{"kind": "repo_doc", "path": "docs/fleet-roadmap.md"}'

# ---- Skill / reference docs ----
$A add-node doc:fridley-relocation-strategy doc "Fridley Live-Work Relocation Strategy" --details '{"kind": "skill_file", "path": ".hermes/profiles/dealsdesk/skills/deal-desk/deal-desk-operations/references/fridley-live-work-relocation-strategy.md"}'

# ---- Goal docs ----
$A add-node doc:tiktok-starter-primer doc "tiktok-shop-affiliate-starter-primer.md" --details '{"kind": "goal_doc", "path": "goals/tiktok-shop-affiliate-income-stream/files/"}'
$A add-node doc:tiktok-channel-strategy doc "tiktok-channel-strategy-2026-10-13.md" --details '{"kind": "goal_doc", "path": "goals/tiktok-shop-affiliate-income-stream/files/"}'

# ---- Second brain topics ----
$A add-node doc:sb-shared-brain-v1 doc "second_brain: shared-brain-strategy-v1" --details '{"kind": "second_brain"}'
$A add-node doc:sb-msv-social-strategy doc "second_brain: msv-social-enrichment-strategy-2026-10-17" --details '{"kind": "second_brain"}'
$A add-node doc:sb-atlas-v1 doc "second_brain: atlas-v1-planning-graph" --details '{"kind": "second_brain"}'
$A add-node doc:sb-university-center-ii doc "second_brain: university-center-ii-fridley-office-option" --details '{"kind": "second_brain"}'

# ---- Business brain rules ----
$A add-node doc:rule-atlas doc "business_core rule: Atlas planning graph" --details '{"kind": "business_rule"}'
$A add-node doc:rule-msv-sociallinks doc "business_core rule: MSV social_links are junk" --details '{"kind": "business_rule"}'
$A add-node doc:rule-msv-triage doc "business_core rule: enrichment triage by recency" --details '{"kind": "business_rule"}'

# ---- Edges: docs -> what they document ----
$A add-edge doc:shared-brain-strategy proj:shared-brain documents
$A add-edge doc:sb-shared-brain-v1 proj:shared-brain documents
$A add-edge doc:audience-architecture proj:audience documents
$A add-edge doc:audience-harness proj:audience documents
$A add-edge doc:audience-tool-integrations proj:audience documents
$A add-edge doc:audience-needs-brian proj:audience documents
$A add-edge doc:pm-master-contract proj:pm documents
$A add-edge doc:fleet-map proj:homelab documents
$A add-edge doc:fleet-roadmap proj:homelab documents
$A add-edge doc:fridley-relocation-strategy fridley-move documents
$A add-edge doc:fridley-relocation-strategy era3-homestead documents
$A add-edge doc:sb-university-center-ii fridley-move documents
$A add-edge doc:tiktok-starter-primer proj:tiktok documents
$A add-edge doc:tiktok-channel-strategy proj:tiktok documents
$A add-edge doc:sb-msv-social-strategy msv-revival documents
$A add-edge doc:rule-msv-sociallinks msv-revival documents
$A add-edge doc:rule-msv-triage enrichment-engine documents
$A add-edge doc:sb-atlas-v1 proj:atlas documents
$A add-edge doc:rule-atlas proj:atlas documents
echo SEED-DOCS-DONE
