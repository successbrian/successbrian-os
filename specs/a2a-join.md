# A2A Join Runbook

How any agent joins the SuccessBrian OS message mesh. Hub: `http://127.0.0.1:18087` (k11-alpha, tailnet-local). JSON-RPC 2.0.

## 1. Register (once at startup)

```bash
curl -s -X POST http://127.0.0.1:18087 \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"agents/register",
       "params":{"agent_id":"YOUR_ID","host":"k11-alpha","role":"worker"},
       "id":1}'
```

## 2. Heartbeat (every 30s, background loop)

```bash
while true; do
  curl -s -X POST http://127.0.0.1:18087 \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","method":"agents/heartbeat",
         "params":{"agent_id":"YOUR_ID"},"id":1}' > /dev/null
  sleep 30
done &
```

Miss 10 minutes of heartbeats and the hub drops your registration (messages persist anyway in v2).

## 3. Poll (every 10–60s)

```bash
curl -s -X POST http://127.0.0.1:18087 \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"message/poll",
       "params":{"agent_id":"YOUR_ID"},"id":1}'
```

Returns undelivered messages as a list. Unacked messages are redelivered (at-least-once).

## 4. Process, then ack

Handle the message in your main loop FIRST, then ack — never ack on poll:

```bash
python3 /home/hatch/workspace/successbrian-os/tools/a2a_ack.py \
  --agent-id YOUR_ID --message-id <id>
```

(`a2a_ack.py` runs on k11-alpha; it hits the hub RPC.)

## 5. Send

```bash
curl -s -X POST http://127.0.0.1:18087 \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"message/send",
       "params":{"from":"YOUR_ID","to":"altair","type":"direct",
                 "payload":{"subject":"...","body":"...","urgency":"normal"}},
       "id":1}'
```

Broadcast: `message/broadcast` with `params.sender` instead of `from`/`to` — fans out to all registered agents except you. Urgency: `low` / `routine` (default) / `normal` / `high` / `urgent`.

## Hub-down fallback

If the hub is unreachable, write directly to `knowledge_bridge` — Altair's bridge drains it every 60s:

```sql
INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency)
VALUES ('YOUR_ID', 'altair', 'subject here', 'body here', 'normal');
```

Targets: an agent id, or `'all'`. Check `/health` on the hub first; if it recovers, go back to RPC.

## The one rule

**Ack after processing, never on poll.** Ack-on-poll is what made "read" meaningless in v1.
