#!/usr/bin/env python3
"""Targeted head upgrade for specific packets, one fresh DB
connection per packet (the batch script's long-lived connection
died during slow model calls). Prints the model head and why the
plainness test accepts/rejects it."""
import os
import re
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/board")
sys.path.insert(0, "/home/successbrian/successbrian-os/tools/pm")
import scatter_clerk as sc
import pm_core

IDS = [int(x) for x in sys.argv[1:]] or [154, 156, 38, 180]

for cid in IDS:
    key = f"task:ssb-packet-{cid}"
    conn = pm_core.conn()
    cur = conn.cursor()
    cur.execute("SELECT details->>'question' FROM atlas.nodes "
                "WHERE node_key=%s", (key,))
    row = cur.fetchone()
    if not row:
        print(cid, "no packet row")
        conn.close()
        continue
    q = row[0]
    head_part = q.partition("\n\nSCATTER PACKET")[0]
    if sc._head_plain_enough(head_part):
        print(cid, "already passing; skip")
        conn.close()
        continue
    m = sc.fetch_capture(cid)
    conn.close()  # close before the slow model call
    mh = sc._model_head([m]) if m else None
    if not mh:
        print(cid, "model returned nothing; code head kept")
        continue
    ok = sc._head_plain_enough(mh)
    print(f"--- {cid} model head (plain_enough={ok}):")
    print(mh)
    if not ok:
        low = mh.lower()
        stripped = re.sub(r'"[^"]*"', "", low)
        hits = [j for j in sc._HEAD_JARGON
                if re.search(r"(?<![a-z0-9])" + re.escape(j) +
                             r"(?![a-z0-9])", stripped)]
        long_lines = [ln for ln in mh.splitlines() if len(ln) > 300]
        print("    jargon hits:", hits, "| lines>300:", len(long_lines),
              "| terminators:", len(re.findall(r"[.!?]", mh)))
        continue
    rest = q.partition("\n\nSCATTER PACKET")[2]
    conn = pm_core.conn()
    cur = conn.cursor()
    cur.execute("UPDATE atlas.nodes SET details = jsonb_set(details, "
                "'{question}', to_jsonb(%s::text)) WHERE node_key=%s",
                (mh + "\n\nSCATTER PACKET" + rest, key))
    conn.commit()
    conn.close()
    print(cid, "UPGRADED")
print("TARGETED_DONE")
