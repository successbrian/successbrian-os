# NEEDS PLAYBOOK — how a good agent reads successbrian-os and decides what to scream about

The OS can't scream for itself. It can only show its state honestly. Your job
as a reading agent (Spencer, Altair, Sonic, or a future watcher) is:

1. Read the state: run `plugins/needs-watch/state_snapshot.py`. It prints JSON:
   `state` (raw numbers) and `candidates` (deterministic proposals from the
   thresholds below).
2. Judge the candidates: the thresholds are tripwires, not orders. Check the
   evidence, consider context the snapshot can't see (is Brian about to buy
   hardware anyway? is a worker just slow, not stuck?), then decide.
3. Scream: for each real need, run `plugins/needs-watch/scream.py` with a
   generic workload spec. Then verify the row landed in
   `successbrian_os.sbos_need_requests` with status 'new'.

## Rules for a good scream

- **Generic spec, never a specific machine.** Describe the workload: what it
  must run, what it must hold, what throughput it needs, what constraints
  matter (power, cost, 24/7). The interpreting agent (DealsDesk) picks hardware.
- **Never put prices in a spec.** Qualitative constraints only ("low-cost
  preferred", "power-efficient").
- **Include the why.** The evidence that drove the signal (queue depth,
  throughput, ages) goes in --why so the interpreter can sanity-check it.
- **Right priority.** 1-10. A screaming need that blocks the whole factory is
  8+. A nice-to-have is 4-5. Don't cry wolf: a false 10 trains everyone to
  ignore the channel.
- **One signal per need.** Check for an existing open signal on the same item
  first (scream.py doesn't dedupe — you do).
- **Escalate, don't duplicate.** If a 'new' signal sits unpromoted past the
  stale threshold, raise its priority and re-broadcast; don't file a second row.

## Threshold tripwires (also coded in state_snapshot.py)

| Rule | Tripwire | Proposal |
|---|---|---|
| QUEUE_BACKLOG | pending tasks > 50 | scream for more sonic inference workers |
| WORKER_DOWN | qwen-task-worker service not active | restart it; if restart fails, scream for worker host repair |
| BRIDGE_PILEUP | any bridge target > 200 unread | that target has no live consumer — reroute or retire |
| STALE_NEED | 'new' signal unpromoted > 48h | escalate priority + re-broadcast |

## Who reads the snapshot

- **Qwen worker discovery pass** (future wiring): read the snapshot each pass;
  candidates become queue tasks for agent review.
- **Altair / Spencer briefings**: read the snapshot, judge candidates, scream
  where warranted.
- **Scheduled watcher** (suggested): run state_snapshot.py hourly, write JSON
  to the plugin dir; agents read the latest file. The snapshot never files
  anything itself — filing is always an agent decision.

## The loop

```
state_snapshot.py  ->  agent reads + judges  ->  scream.py  ->
sbos_need_requests (OS-owned)  ->  bridge broadcast + dashboard Inbox  ->
DealsDesk reads, interprets, promotes to its private table  ->  sources  ->
status_sync marks satisfied  ->  quiet.
```

The OS screams. DealsDesk listens. Nobody reaches into anyone else's private
structure. That's the whole design.
