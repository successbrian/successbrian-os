# Decision Conflict Report

**Generated:** 2026-10-23 04:13 UTC
**Conflicts/gaps found:** 4

These are flags for Brian's review — nothing is auto-changed. Quarantine, never delete.

---

### [INFO] psu_oversized

Plan specs 1200W PSU but decisions power-limit M40s to 150W each (~300W GPUs + ~190W CPUs + overhead ~= 600W). 1200W is oversized; consider 750-850W to save cost.

_Checked: 2026-10-23T04:13:41.580676+00:00_

---

### [REVIEW] plan_gap

Decisions add 2x PCIe NVMe adapters per node (8 total) for the striped Gen 2 model volume, but no adapter line exists in the build plan.

_Checked: 2026-10-23T04:13:41.580772+00:00_

---

### [REVIEW] plan_gap

Decisions add SATA SSD + HDD tiering per node, but no SATA drives exist in the build plan.

_Checked: 2026-10-23T04:13:41.580780+00:00_

---

### [INFO] stale_notes

Decisions killed the Phase 1/Phase 2 split (dual-role from day one). Check plan notes/source_type fields for stale phase language.

_Checked: 2026-10-23T04:13:41.580881+00:00_

---
