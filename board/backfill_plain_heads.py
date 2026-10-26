#!/usr/bin/env python3
"""Backfill the plain-words head onto every queued ssb packet.

Brian's fix order 2026-10-26 (capture #204): the ~112 queued
packets were built before the plain-words head existed. This
prepends the same head the (patched) packet builder now makes,
preserving each packet's original question text byte-for-byte
below the head. Idempotent: a packet whose question already
carries the marker is skipped. Only details.question changes;
every other field of the node is untouched.

Usage: python3 backfill_plain_heads.py [--dry-run]
       [--model-cap N] [--limit N]
Model use is bounded (default cap 3 across the whole run);
--model-cap 0 ships code-only heads.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/board"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
import pm_core  # noqa: E402
import scatter_clerk as sc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model-cap", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    sc._MODEL_BUDGET["left"] = args.model_cap

    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        "SELECT node_key, details FROM atlas.nodes "
        "WHERE node_key LIKE 'task:ssb-packet-%' AND status='queued' "
        "ORDER BY node_key")
    rows = cur.fetchall()
    if args.limit:
        rows = rows[:args.limit]

    total = len(rows)
    done = skipped = model_used = failed = 0
    for key, details in rows:
        if isinstance(details, str):
            details = json.loads(details)
        q = details.get("question") or ""
        if sc.HEAD_MARKER in q[:300]:
            skipped += 1
            continue
        ids = details.get("source_captures") or []
        if not ids:
            tail = key[len("task:ssb-packet-"):]
            ids = [int(x) for x in tail.split("-") if x.isdigit()]
        members = []
        for cid in ids:
            m = sc.fetch_capture(cid)
            if m:
                members.append(m)
        if not members:
            print(f"FAIL {key}: no source captures found")
            failed += 1
            continue
        head, how = sc.plain_head(members)
        if how == "morpheus":
            model_used += 1
        new_q = head + "\n\n" + q
        if args.dry_run:
            print(f"--- {key} (via {how}) would gain head:")
            print(head)
            print()
        else:
            cur.execute(
                "UPDATE atlas.nodes SET "
                "details = jsonb_set(details, '{question}', "
                "to_jsonb(%s::text)), updated_at = now() "
                "WHERE node_key = %s", (new_q, key))
        done += 1
    if not args.dry_run:
        c.commit()
    c.close()
    print(f"BACKFILL total={total} headed={done} skipped={skipped} "
          f"model={model_used} failed={failed} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
