#!/usr/bin/env python3
"""Refresh code heads on packets where a Brian quote is now findable.
Packets: those headed 'WHAT HAPPENED' whose capture now yields a quote
head (after the scanner fixes). Rebuilds just the head block in place;
the body below the head is preserved byte-for-byte."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/successbrian/successbrian-os/tools/pm")
import scatter_clerk as sc
import pm_core

conn = pm_core.conn()
cur = conn.cursor()
cur.execute(
    "SELECT node_key, details->>'question' FROM atlas.nodes "
    "WHERE node_key LIKE 'task:ssb-packet-%'")
rows = cur.fetchall()
refreshed = 0
for key, question in rows:
    if not question:
        continue
    head_part, sep, rest = question.partition("\n\nSCATTER PACKET")
    if not sep or "WHAT HAPPENED:" not in head_part:
        continue
    cid = int(key.rsplit("-", 1)[1])
    m = sc.fetch_capture(cid)
    if not m:
        continue
    head, how = sc.plain_head([m])
    if how in ("code", "model"):
        continue  # only quote-built heads upgrade WHAT HAPPENED
    new_q = head + "\n\nSCATTER PACKET" + rest
    cur.execute("UPDATE atlas.nodes SET details = jsonb_set(details, '{question}', "
                "to_jsonb(%s::text)) WHERE node_key=%s", (new_q, key))
    refreshed += 1
    print("REFRESHED", key, "via", how)
conn.commit()
print("done, refreshed =", refreshed)
