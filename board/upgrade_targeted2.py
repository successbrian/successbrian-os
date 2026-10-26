#!/usr/bin/env python3
"""Targeted head upgrade v2: own raw Morpheus call per packet with
full diagnostics (raw output + which plainness gate rejected it).
Fresh DB connection per packet; writes only a passing head."""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, "/home/successbrian/successbrian-os/board")
sys.path.insert(0, "/home/successbrian/successbrian-os/tools/pm")
import scatter_clerk as sc
import pm_core

IDS = [int(x) for x in sys.argv[1:]] or [154, 156, 38, 180]


def why_fail(head):
    low = head.lower()
    stripped = re.sub(r'"[^"]*"', "", low)
    hits = [j for j in sc._HEAD_JARGON
            if re.search(r"(?<![a-z0-9])" + re.escape(j) +
                         r"(?![a-z0-9])", stripped)]
    return {"jargon": hits,
            "long_lines": [len(ln) for ln in head.splitlines()
                           if len(ln) > 300],
            "terminators": len(re.findall(r"[.!?]", head)),
            "has_what": "WHAT THIS IS:" in head}


def raw_model_head(m):
    src = [f"TITLE: {m.get('title', '')}"]
    if m.get("context"):
        src.append("CONTEXT: " + m["context"][:700])
    if m.get("raw"):
        src.append("TEXT: " + m["raw"][:1300])
    prompt = (
        "Write exactly three short parts, each starting with its "
        "label, in plain ordinary words a tired person can follow "
        "at a glance:\n"
        "WHAT THIS IS: one sentence saying what this filing is "
        "about.\n"
        "WHAT BRIAN SAID: one or two sentences saying what Brian "
        "said or decided, or what happened if he did not speak.\n"
        "WHY IT IS HERE: one sentence — the board is asked to "
        "judge whether this becomes planned work, waits for its "
        "moment, or is set aside.\n\nTEXT:\n" + "\n".join(src))
    payload = {"model": "morpheus",
               "messages": [
                   {"role": "system",
                    "content": "You restate text in plain, ordinary "
                               "words. Use ONLY facts in the text "
                               "given. Never add facts, names, "
                               "numbers, or opinions that are not "
                               "there. Short sentences. No jargon."},
                   {"role": "user", "content": prompt}],
               "temperature": 0.2, "max_tokens": 260}
    req = urllib.request.Request(
        sc.MORPHEUS_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=150) as r:
        out = json.load(r)
    return out["choices"][0]["message"]["content"].strip()


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
    conn.close()
    if not m:
        print(cid, "capture missing")
        continue
    try:
        text = raw_model_head(m)
    except Exception as e:
        print(cid, "model call error:", type(e).__name__, e)
        continue
    print(f"--- {cid} raw model text:")
    print(text)
    if not text.startswith("WHAT THIS IS:"):
        print("    REJECTED: does not start with WHAT THIS IS:")
        continue
    head = sc.HEAD_MARKER + "\n" + text
    if not sc._head_plain_enough(head):
        print("    REJECTED by plainness:", why_fail(head))
        continue
    rest = q.partition("\n\nSCATTER PACKET")[2]
    conn = pm_core.conn()
    cur = conn.cursor()
    cur.execute("UPDATE atlas.nodes SET details = jsonb_set(details, "
                "'{question}', to_jsonb(%s::text)) WHERE node_key=%s",
                (head + "\n\nSCATTER PACKET" + rest, key))
    conn.commit()
    conn.close()
    print(cid, "UPGRADED")
print("TARGETED2_DONE")
