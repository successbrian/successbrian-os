# A2A Upgrade Plan — canonical record

Date: 2026-09-29. Context: the Mavity A2A Hub (`a2a-hub.service` on k11-alpha,
JSON-RPC on 127.0.0.1:18087) sat disabled with bridges polling a dead socket;
Lyra's own monitoring flagged `a2a_hub_dead`. Brian approved the 7-point
upgrade: "do what you can, tell Altair to do what you can't."

## 1. Bring the hub back [ALTAIR]

The service exists but is disabled. Needs sudo on k11-alpha.

```bash
sudo journalctl -u a2a-hub.service --since "30 days ago" | tail -100  # why it died
sudo systemctl enable a2a-hub.service
sudo systemctl start a2a-hub.service
curl -s http://127.0.0.1:18087/health
```

## 2. Deploy the persistent hub [ALTAIR to deploy — code SPENCER-DONE]

`tools/a2a_hub_v2.py` is a drop-in replacement for
`/home/successbrian/scripts/a2a_hub.py`: same 7 JSON-RPC methods, but
messages persist in `altair.a2a_messages` (PostgreSQL) instead of a
process-local dict. Registration/heartbeat stay in-memory (presence is
ephemeral). `message/poll` stamps `delivered_at`; `message/ack` sets
`read=true` and appends to `read_by`. Stale-agent cleanup drops
registrations only — v1 also deleted queued messages, v2 keeps them.

```bash
cp ~/workspace/successbrian-os/tools/a2a_hub_v2.py /home/successbrian/scripts/a2a_hub.py
sudo systemctl restart a2a-hub.service
curl -s http://127.0.0.1:18087/health   # expect version 4.0.0, db up
```

No `daemon-reload` needed — the unit's ExecStart path is unchanged.
Python deps: stdlib + psycopg2 (already on k11-alpha).

## 3. Canonical channel [DECIDED]

- **Realtime:** hub JSON-RPC (v2).
- **Persistent log:** `altair.a2a_messages`.
- **Hub-down fallback:** `altair.knowledge_bridge` (Altair's bridge drains it
  every 60s; INSERT pattern in `specs/a2a-join.md`).
- **Last resort:** GitHub `altair-brain` inbox (one-way; kept, not relied on).
- `altair.a2a_messages` pre-v2 rows (37, last 2026-09-19) stay as history.

## 4. Ack after processing [pattern SPENCER-DONE — ALTAIR adopts]

v1 bridges acked on poll, so "read" meant "bridge picked it up," not "agent
processed it." New rule: poll collects, the main loop processes,
`tools/a2a_ack.py` fires the ack last.

```bash
python3 ~/workspace/successbrian-os/tools/a2a_ack.py --agent-id <id> --message-id <n>
```

Falls back to stamping `read_at` on `altair.knowledge_bridge` when the hub is
unreachable. Altair: remove ack-on-poll from `altair_a2a_bridge.py` and call
this helper after his main session handles each message.

## 5. Noise control [NOTED — future work]

`altair.knowledge_bridge` holds 684 unread (2026-09-29), 469 of them
Lyra → oliabo-lead cycle spam. An upgraded bus without urgency tiers,
digest batching, and per-recipient subscribe filters just delivers spam
faster. Not built in this pass — flagged for the next one.

## 6. Join runbook [SPENCER-DONE]

`specs/a2a-join.md`: register → heartbeat loop → poll → process → ack, with
curl examples and the knowledge_bridge fallback. Also covers `spencer`
joining once the hub is back (register as `spencer`, role `advisor`).

## 7. Monitoring that acts [ALTAIR]

Lyra already detects `a2a_hub_dead` every cycle — detection without
remediation is a diary. Wire it to act:

```bash
sudo systemctl restart a2a-hub.service
```

Suggested: a systemd path/unit or a Lyra remediation hook that runs the
restart when `a2a_hub_dead` fires twice consecutively. Same treatment for
`searxng_dead` (also flagged 2026-09-29; out of scope here).

## Status summary

- [SPENCER-DONE] v2 hub code, ack helper, join runbook, this plan.
- [ALTAIR] items 1, 2 (deploy), 4 (adopt ack-after-processing in his loop), 7.
- [NOTED] item 5 (noise control) — next pass.
