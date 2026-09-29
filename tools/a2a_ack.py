#!/usr/bin/env python3
"""Ack an A2A message AFTER the agent's main loop has processed it.

Usage:
    python3 a2a_ack.py --agent-id altair --message-id 123
    python3 a2a_ack.py --agent-id altair --message-id 456 --source kb

WHY:
    v1 bridges acked on poll, so "read" meant "a bridge script picked the
    message up" — not "the agent processed it." That made read receipts
    meaningless and hid real silence (the exact failure behind the
    spencer->altair one-way GitHub inbox). The rule going forward: poll
    collects, the main loop processes, and THIS helper fires the ack last.
    No ack without processing.

CALLED BY:
    - Agent main loops / bridge scripts on k11-alpha after handling a
      message (replaces inline message/ack-on-poll calls).
    - Humans debugging delivery: ack a stuck message by hand.

NOTES:
    - Default path is the hub's message/ack JSON-RPC. If the hub is
      unreachable and --source is auto/kb, falls back to stamping
      read_at on altair.knowledge_bridge (the hub-down fallback channel).
    - knowledge_bridge and a2a_messages have SEPARATE id spaces. The kb
      fallback only makes sense for messages that came FROM
      knowledge_bridge — pass --source kb explicitly in that case.
    - Exit 0 on acked, 1 on failure. Prints which path was used.
    - stdlib + psycopg2 only.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

HUB_URL = os.environ.get("A2A_HUB", "http://127.0.0.1:18087")
PG_DSN = os.environ.get(
    "PG_DSN_WRITER",
    "host=localhost dbname=ecosystem_central user=successbrian password=postgres",
)


def ack_via_hub(agent_id, message_id):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "message/ack",
        "params": {"agent_id": agent_id, "message_id": message_id},
        "id": 1,
    }).encode()
    req = urllib.request.Request(
        HUB_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def ack_via_kb(message_id):
    import psycopg2
    conn = psycopg2.connect(PG_DSN, connect_timeout=5)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE altair.knowledge_bridge SET read_at = now()"
            " WHERE id = %s AND read_at IS NULL",
            (int(message_id),),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Ack an A2A message after processing it.")
    ap.add_argument("--agent-id", required=True)
    ap.add_argument("--message-id", required=True)
    ap.add_argument("--source", choices=["auto", "hub", "kb"], default="auto",
                    help="auto: hub first, kb fallback on connection failure")
    args = ap.parse_args()

    if args.source in ("auto", "hub"):
        try:
            res = ack_via_hub(args.agent_id, args.message_id)
        except Exception as e:
            if args.source == "hub":
                print(f"hub ack failed: {e}", file=sys.stderr)
                return 1
            print(f"hub unreachable ({e}); trying knowledge_bridge fallback")
            res = None
        else:
            if "error" in res:
                print(f"hub ack error: {res['error']}", file=sys.stderr)
                return 1
            print(f"acked via hub: message {res['result'].get('message_id')}")
            return 0

    # kb path (explicit or fallback)
    try:
        n = ack_via_kb(args.message_id)
    except Exception as e:
        print(f"knowledge_bridge ack failed: {e}", file=sys.stderr)
        return 1
    if n:
        print(f"acked via knowledge_bridge: message {args.message_id}")
        return 0
    print(f"message {args.message_id} not found unread in knowledge_bridge",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
