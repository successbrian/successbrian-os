#!/usr/bin/env python3
"""A2A Hub v2 — persistent agent-to-agent messaging mesh for SuccessBrian OS.

Drop-in replacement for /home/successbrian/scripts/a2a_hub.py with the SAME
JSON-RPC 2.0 API (agents/register, agents/heartbeat, agents/list,
message/send, message/broadcast, message/poll, message/ack), but messages
are persisted in altair.a2a_messages (PostgreSQL) instead of an in-memory
dict. A hub restart no longer wipes the bus.

WHY:
    v1 kept every message in a process-local dict. When the hub died (it did
    — a2a-hub.service sat disabled with Lyra flagging a2a_hub_dead), all
    queued messages vanished and bridges polled a dead socket. v2 writes
    every send to altair.a2a_messages, so the bus survives restarts, and
    delivery/read state is queryable by any agent with DB access.
    Registration and heartbeat state stay in-memory: presence is ephemeral
    by nature and rebuilding it on restart is correct.

CALLED BY:
    - systemd unit a2a-hub.service (ExecStart points at the deployed copy of
      this file). Deploy: copy over /home/successbrian/scripts/a2a_hub.py,
      then `sudo systemctl restart a2a-hub` (no daemon-reload needed; the
      ExecStart path is unchanged).
    - Agent bridges (altair_a2a_bridge.py, a2a-agent-bridge.py) via JSON-RPC
      on http://127.0.0.1:18087.

NOTES:
    - Registration/heartbeat/list are in-memory and unchanged from v1.
    - message/poll returns rows where read=false for the agent (at-least-once
      redelivery, same as v1) and stamps delivered_at on first delivery.
    - message/ack sets read=true and appends the agent to read_by. Bridges
      must ack AFTER the agent's main loop processes the message, not on
      poll — ack-on-poll is what made "read" meaningless in v1.
    - Stale-agent cleanup drops registrations only. v1 also deleted the
      agent's queued messages; v2 keeps them (persistence is the point).
    - altair.a2a_messages.topic is a FK into altair.a2a_topics (intel,
      tasks, alerts, fleet-status). v1's free-form types ("direct",
      "broadcast") are mapped: direct->tasks, broadcast->intel, unknown->tasks.
    - ThreadingHTTPServer: one psycopg2 connection per request, closed after.
    - stdlib + psycopg2 only.
"""

import http.server
import json
import os
import threading
import time

import psycopg2

HUB_HOST = "0.0.0.0"
HUB_PORT = 18087
HEARTBEAT_TTL = 300  # seconds before agent considered offline
CLEANUP_INTERVAL = 60

PG_DSN = os.environ.get(
    "PG_DSN_WRITER",
    "host=localhost dbname=ecosystem_central user=successbrian password=postgres",
)

# ── Ephemeral presence state (in-memory, like v1) ──────────────────
agents = {}  # agent_id -> {host, role, status, registered_at, last_heartbeat}
lock = threading.Lock()


def pg_conn():
    return psycopg2.connect(PG_DSN, connect_timeout=5)


# ── A2A Protocol Methods ──────────────────────────────────────────

def handle_agents_register(params):
    agent_id = params.get("agent_id") or params.get("agentId")
    host = params.get("host", "unknown")
    role = params.get("role", "unknown")
    if not agent_id:
        return {"error": "agent_id required"}
    with lock:
        agents[agent_id] = {
            "host": host,
            "role": role,
            "status": "active",
            "registered_at": time.time(),
            "last_heartbeat": time.time(),
            "heartbeat_ttl": HEARTBEAT_TTL,
        }
    return {"registered": agent_id, "heartbeat_ttl": HEARTBEAT_TTL}


def handle_agents_heartbeat(params):
    agent_id = params.get("agent_id") or params.get("agentId")
    if not agent_id:
        return {"error": "agent_id required"}
    with lock:
        if agent_id in agents:
            agents[agent_id]["last_heartbeat"] = time.time()
            agents[agent_id]["status"] = "active"
            return {"heartbeat": "ok", "agent_id": agent_id}
        return {"error": f"agent {agent_id} not registered"}


def handle_agents_list(params):
    with lock:
        now = time.time()
        active = {
            aid: {**a, "status": "active" if now - a["last_heartbeat"] < a["heartbeat_ttl"] else "offline"}
            for aid, a in agents.items()
        }
    return {"agents": active}


# altair.a2a_messages.topic is a FK into altair.a2a_topics (values:
# intel, tasks, alerts, fleet-status). v1 used free-form types ("direct",
# "broadcast"), so map them onto real topics; unknown types fall back
# safely instead of violating the FK.
TOPIC_MAP = {
    "direct": "tasks",
    "broadcast": "intel",
    "intel": "intel",
    "tasks": "tasks",
    "alerts": "alerts",
    "fleet-status": "fleet-status",
}
VALID_TOPICS = set(TOPIC_MAP.values())


def _resolve_topic(msg_type, payload):
    if isinstance(payload, dict):
        t = payload.get("topic")
        if t in VALID_TOPICS:
            return t
    return TOPIC_MAP.get(msg_type, "tasks")


def _store_message(sender, recipient, msg_type, payload):
    """Persist one message row. Returns the integer PK."""
    subject = payload.get("subject") if isinstance(payload, dict) else None
    urgency = "routine"
    if isinstance(payload, dict):
        urgency = str(payload.get("urgency", payload.get("priority", "routine")))
    body = json.dumps(payload) if isinstance(payload, dict) else str(payload)
    topic = _resolve_topic(msg_type, payload)
    conn = pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO altair.a2a_messages (topic, sender, target, subject, body, urgency)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (topic, sender, recipient, subject, body, urgency),
        )
        msg_id = cur.fetchone()[0]
        conn.commit()
        return msg_id
    finally:
        conn.close()


def handle_message_send(params):
    sender = params.get("from")
    recipient = params.get("to")
    msg_type = params.get("type", "direct")
    payload = params.get("payload", {})

    if not sender or not recipient:
        return {"error": "from and to required"}
    if not isinstance(payload, dict):
        return {"error": "payload must be a dict"}

    try:
        msg_id = _store_message(sender, recipient, msg_type, payload)
    except Exception as e:
        return {"error": f"persist failed: {e}"}
    return {"sent": True, "message_id": msg_id, "to": recipient, "delivery": "persisted"}


def handle_message_broadcast(params):
    sender = params.get("sender") or params.get("from")
    msg_type = params.get("type", "broadcast")
    payload = params.get("payload", {})

    if not sender:
        return {"error": "sender required"}
    if not isinstance(payload, dict):
        return {"error": "payload must be a dict"}

    with lock:
        recipients = [aid for aid in agents if aid != sender]
    sent = 0
    first_id = None
    for recipient in recipients:
        try:
            mid = _store_message(sender, recipient, msg_type, payload)
            if first_id is None:
                first_id = mid
            sent += 1
        except Exception:
            continue
    return {"broadcast": True, "sent_to": recipients, "count": sent,
            "first_message_id": first_id, "delivery": "persisted"}


def _row_to_wire(row):
    msg_id, topic, sender, target, subject, body, urgency, read, created_at = row
    try:
        payload = json.loads(body) if body else {}
    except (json.JSONDecodeError, TypeError):
        payload = {"_raw_body": body}
    if not isinstance(payload, dict):
        payload = {"_raw_body": payload}
    created = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    return {
        "id": msg_id,
        "from_agent": sender,
        "to_agent": target,
        "type": topic or "direct",
        "payload": payload,
        "status": "ack" if read else "unread",
        "created_at": created,
        "priority": urgency,
    }


def handle_message_poll(params):
    agent_id = params.get("agent_id") or params.get("agentId")
    if not agent_id:
        return {"error": "agent_id required"}

    conn = pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, topic, sender, target, subject, body, urgency, read, created_at"
            " FROM altair.a2a_messages"
            " WHERE target = %s AND read = false"
            " ORDER BY created_at",
            (agent_id,),
        )
        rows = cur.fetchall()
        ids = [r[0] for r in rows]
        if ids:
            cur.execute(
                "UPDATE altair.a2a_messages SET delivered_at = now()"
                " WHERE delivered_at IS NULL AND id = ANY(%s)",
                (ids,),
            )
            conn.commit()
        return [_row_to_wire(r) for r in rows]
    finally:
        conn.close()


def handle_message_ack(params):
    agent_id = params.get("agent_id") or params.get("agentId")
    message_id = params.get("message_id") or params.get("messageId")
    if not agent_id or message_id is None:
        return {"error": "agent_id and message_id required"}

    try:
        message_id = int(message_id)
    except (TypeError, ValueError):
        return {"error": f"message_id must be an integer, got {message_id!r}"}

    conn = pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE altair.a2a_messages"
            " SET read = true,"
            "     read_by = CASE WHEN %s = ANY(read_by) THEN read_by"
            "                   ELSE array_append(read_by, %s) END"
            " WHERE id = %s AND target = %s AND read = false",
            (agent_id, agent_id, message_id, agent_id),
        )
        conn.commit()
        if cur.rowcount:
            return {"acked": True, "message_id": message_id}
        return {"error": f"message {message_id} not found unread for {agent_id}"}
    finally:
        conn.close()


# ── HTTP Request Handler ──────────────────────────────────────────

class A2AHubHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            self.send_json_rpc_error(None, -32700, "Parse error")
            return

        method = req.get("method")
        params = req.get("params", {})
        req_id = req.get("id")

        handlers = {
            "agents/register": handle_agents_register,
            "agents/heartbeat": handle_agents_heartbeat,
            "agents/list": handle_agents_list,
            "message/send": handle_message_send,
            "message/broadcast": handle_message_broadcast,
            "message/poll": handle_message_poll,
            "message/ack": handle_message_ack,
        }

        handler = handlers.get(method)
        if not handler:
            self.send_json_rpc_error(req_id, -32601, f"Method not found: {method}")
            return

        try:
            result = handler(params)
            if isinstance(result, dict) and "error" in result:
                self.send_json_rpc_error(req_id, -32000, result["error"])
            else:
                self.send_json_rpc_result(req_id, result)
        except Exception as e:
            self.send_json_rpc_error(req_id, -32603, f"Internal error: {str(e)}")

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            db_ok = True
            try:
                c = pg_conn()
                c.close()
            except Exception:
                db_ok = False
            self.wfile.write(json.dumps({
                "status": "ok" if db_ok else "degraded",
                "server": "k11-alpha-a2a",
                "version": "4.0.0",
                "db": "up" if db_ok else "down",
                "uptime": time.time() - self.server.start_time,
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def send_json_rpc_result(self, req_id, result):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"jsonrpc": "2.0", "result": result, "id": req_id}).encode())

    def send_json_rpc_error(self, req_id, code, message):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(
            {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}
        ).encode())


class A2AHubServer(http.server.ThreadingHTTPServer):
    def __init__(self, host, port):
        super().__init__((host, port), A2AHubHandler)
        self.start_time = time.time()
        self.daemon_threads = True


# ── Stale Agent Cleanup (registrations only — messages persist) ───

def cleanup_stale_agents():
    while True:
        time.sleep(CLEANUP_INTERVAL)
        now = time.time()
        with lock:
            stale = [
                aid for aid, a in agents.items()
                if now - a["last_heartbeat"] > a["heartbeat_ttl"] * 2
            ]
            for aid in stale:
                del agents[aid]


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Fail fast if the DB is unreachable — a hub that can't persist
    # must not pretend to deliver.
    probe = pg_conn()
    probe.close()

    cleanup_thread = threading.Thread(target=cleanup_stale_agents, daemon=True)
    cleanup_thread.start()

    server = A2AHubServer(HUB_HOST, HUB_PORT)
    print(f"A2A Hub v2 (persistent) starting on {HUB_HOST}:{HUB_PORT}")
    print(f"PID: {__import__('os').getpid()}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down...")
        server.shutdown()
