# scheduler — the schedule governor

77 crons grew organically with no map of what feeds what. This is the map.

## What it does

- **Registry** (`successbrian_os.cron_registry`): every job — schedule,
  purpose, weight (light/heavy), upstream deps, downstream consumers,
  min stagger gap. Hand-enriched chains are verified; the rest import
  as unenriched.
- **Audit** (`scheduler.py --audit`): parses the LIVE crontab and reports
  collisions (3+ jobs/minute), unregistered jobs, sequence violations
  (downstream running before upstream + gap), and the load map.
- **Planner** (`scheduler.py --plan`): for a NEW cron, finds the best slot —
  least-loaded minute honoring upstream deps and min gaps.

```bash
python3 scheduler.py --audit
python3 scheduler.py --plan --frequency hourly --weight light \
    --upstream derive_needs.py --purpose "claim new screams"
```

## The rule it enforces

New crons don't pick their own time. The planner picks it. That's how the
thundering herds (:00 = 30 jobs, :30 = 18) never come back.

## Phase 2 (not built yet)

- Runtime/efficiency watch: time each run, alert on slow or failing jobs.
- Rebalancer: propose moving existing jobs out of herds (needs approval).
