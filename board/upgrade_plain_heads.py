#!/usr/bin/env python3
"""Stage 2 of the plain-words head backfill: for queued packets
whose code-composed head FAILS the plainness test, ask Morpheus
for a constrained restatement and swap ONLY the head block
(everything before the original SCATTER PACKET body, which is
preserved byte-for-byte). Packets whose model head also fails
keep their code head — a head never blocks a filing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/board"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
import pm_core  # noqa: E402
import scatter_clerk as sc  # noqa: E402

sc._MODEL_BUDGET["left"] = 25

c = pm_core.conn()
cur = c.cursor()
cur.execute(
    "SELECT node_key, details FROM atlas.nodes "
    "WHERE node_key LIKE 'task:ssb-packet-%' AND status='queued' "
    "ORDER BY node_key")
rows = cur.fetchall()
tried = upgraded = kept = 0
for key, details in rows:
    if isinstance(details, str):
        details = json.loads(details)
    q = details.get("question") or ""
    if sc.HEAD_MARKER not in q[:300]:
        continue
    head_part, sep, rest = q.partition("\n\nSCATTER PACKET")
    if not sep:
        continue
    if sc._head_plain_enough(head_part):
        continue
    ids = details.get("source_captures") or []
    members = [m for m in (sc.fetch_capture(i) for i in ids) if m]
    if not members:
        continue
    tried += 1
    mh = sc._model_head(members)
    if mh and sc._head_plain_enough(mh):
        new_q = mh + "\n\nSCATTER PACKET" + rest
        cur.execute(
            "UPDATE atlas.nodes SET "
            "details = jsonb_set(details, '{question}', "
            "to_jsonb(%s::text)), updated_at = now() "
            "WHERE node_key = %s", (new_q, key))
        c.commit()
        upgraded += 1
        print(f"UPGRADED {key}", flush=True)
    else:
        kept += 1
        print(f"KEPT-CODE {key} (model head unavailable/failing)",
              flush=True)
c.close()
print(f"UPGRADE tried={tried} upgraded={upgraded} kept_code={kept}")
