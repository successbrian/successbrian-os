# Capacity Loop Contract — successbrian-os (demand) ↔ DealsDesk (supply)

Owner: successbrian-os (master). DealsDesk is the private plugin that answers.
Version: 1.0 — 2026-10-13.

## The deal

- **successbrian-os** emits GENERIC demand: "we need this much <model>".
  Never machine-specific. Tables: `successbrian_os.model_demand` (measurements),
  `successbrian_os.sbos_need_requests` (signals; screamed on the live bridge).
- **DealsDesk** answers with the WHAT: exact machines and configurations that
  deliver that capacity, then budgets by priority.
- **Proxmox** is the elastic actuator: `tools/capacity/proxmox_ctl.py`
  starts/stops worker VMs as the plan dictates.

## Demand side (successbrian-os)

`demand_meter.py` (cron, every 30 min) writes one row per model per run into
`successbrian_os.model_demand`:

| model | tier | paid | what it means |
|---|---|---|---|
| penny / chuck / morpheus | cheap | no | triage tier; heartbeat escalation pool |
| sonic | workhorse | no | 35B-class local coder/chat |
| deepseek-v4-pro | deep | YES | rented cloud; tracked for burn, never a machine signal |
| deepseek-150b-reap | deep | no | planned: MS-02 + dual B70 |
| qwen-3.8-flash | deep | no | planned: Strata, Mantis-3/4 dual-V100 |
| glm-5.3-flash | deep | no | planned: Strata fork, Mantis-3/4 dual-V100 |
| shakespeare | content | no | content workflow ONLY — excluded from capacity signals |
| vision | multimodal | no | supply TBD ("supplied somehow") |

Columns: `measured_at, model, tier, queue_depth, throughput_per_hr,
est_cost_usd_per_hr, paid, note`.

**Signal rule (v1):** when a model's `queue_depth` crosses its threshold,
the meter files/updates ONE generic row in `sbos_need_requests`
(item e.g. "sonic inference capacity", generic `specs`, `qty` = concurrent
workers, `priority` from severity) and screams it on `altair.knowledge_bridge`
(sender=successbrian-os, target=dealsdesk, urgency=high). One open signal per
item — update qty, don't file duplicates. v4pro burn is reported, not signaled.

## Supply side (DealsDesk)

DealsDesk reads `sbos_need_requests` (status='new') and answers in its own
table — suggested shape:

```
dealsdesk.capacity_recommendations (
  id serial PK,
  need_id integer,            -- sbos_need_requests.id
  model text,                -- which model this serves
  machine_config text,       -- EXACT: box, CPUs, RAM, GPU(s), storage, NIC
  source text,               -- fleet | buy | proxmox-vm
  est_cost_usd numeric,      -- capex (buy) or $0 (fleet/proxmox)
  monthly_power_usd numeric, -- estimated running cost
  capacity_units numeric,    -- concurrent workers / tok/s this config yields
  priority_rank integer,     -- 1 = fund first
  rationale text,            -- why this config wins (price/perf, on-hand, lead time)
  status text DEFAULT 'proposed',  -- proposed | approved | building | live | rejected
  created_at timestamptz DEFAULT now()
)
```

**Budget-by-priority rule:** rank by (need severity × capacity per dollar).
Severity comes from the signal's priority and measured queue_depth/throughput
gap. Fleet/proxmox-vm sources outrank buys at equal capacity (no capex).
Report the ranked list to Brian — he funds in order.

## VM lifecycle

- New worker VMs are defined by DealsDesk (config above, source=proxmox-vm).
- `proxmox_ctl.py` performs start/stop/shutdown. Dry-run default; --live acts.
- Needs PROXMOX_HOST + PROXMOX_TOKEN in the environment on the control node.
- v1: humans approve each scale action. v2 (Brian's call): auto-reconcile
  desired vs actual from the approved capacity plan.

## Efficiency objective (the whole point)

Most efficient token burn at high quality:
1. Triage on cheap tier (penny/chuck/morpheus) — free, always.
2. Standard work on sonic — free, local.
3. Deep work on V4 Pro ONLY when available and worth the burn.
4. Future models slot into the ladder as they come online (150B-Reap >
   Qwen3.8 > GLM5.3 for deep-local; vision for multimodal).
5. Never burn paid tokens on "all clear" — heartbeat skeletons stay cheap.

The meter makes the burn visible (`est_cost_usd_per_hr`); the loop makes
the capacity follow the demand instead of the demand waiting on capacity.
