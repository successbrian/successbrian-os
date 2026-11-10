#!/usr/bin/env python3
"""Scoped SSB drain for packeted-but-raw captures.

One-off for the 2026-11-09 clerk filing-flow repair (Leak 3).

Why this exists: the clerk's hourly sweep files board-bound
captures into packets (file_packet) but never marks them
triaged; they sit status='raw' below the sweep watermark until
the DAILY scattered_brain triage (04:40) scores them.
scattered_brain.triage() itself selects ALL raw captures --
running it globally outside its window would also mark any
brand-new UNSWEPT capture triaged, and the sweep's fetch_new
(status='raw' only) would then skip it forever: its board
packet / WF3 filing would never happen.

So this drain applies triage's OWN machinery -- the same
score_capture(), the same recommend(), the same UPDATE --
scoped to exactly the raw captures that already carry a
disposition (membership in a board packet's source_captures).
It then rebuilds the SSB digest exactly as triage() does.
Anything raw WITHOUT a packet is left untouched for the sweep.
"""

import os
import sys

sys.path.insert(0, os.path.expanduser(
    "~/successbrian-os/tools/atlas"))
sys.path.insert(0, os.path.expanduser(
    "~/successbrian-os/tools/pm"))
sys.path.insert(0, os.path.expanduser(
    "~/successbrian-os/board"))

import scattered_brain as ssb  # noqa: E402


def packeted_raw_ids(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.id FROM atlas.scattered_captures c "
            "WHERE c.status = 'raw' AND EXISTS ("
            "SELECT 1 FROM atlas.nodes n WHERE n.node_key "
            "LIKE 'task:ssb-packet-%' AND "
            "n.details->'source_captures' @> to_jsonb(c.id)) "
            "ORDER BY c.id")
        return [r[0] for r in cur.fetchall()]


def main():
    conn = ssb.pg()
    ssb.ensure(conn)
    ids = packeted_raw_ids(conn)
    print("packeted raw captures to drain: %d" % len(ids))
    if not ids:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cluster_key, count(*) FROM "
            "atlas.scattered_captures WHERE status <> "
            "'discarded' GROUP BY cluster_key")
        sizes = dict(cur.fetchall())
        cur.execute(
            "SELECT id, title, raw_text, context FROM "
            "atlas.scattered_captures WHERE id = ANY(%s) "
            "ORDER BY id", (ids,))
        rows = cur.fetchall()
    done = 0
    for row in rows:
        score, reasons, forced = ssb.score_capture(
            conn, row, sizes)
        rec = ssb.recommend(score, forced)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.scattered_captures SET "
                "status = 'triaged', score = %s, "
                "score_reasons = %s, recommendation = %s, "
                "triaged_at = now() WHERE id = %s AND "
                "status = 'raw'",
                (score, "; ".join(reasons), rec, row[0]))
        conn.commit()
        done += 1
    print("drained (scored + marked triaged): %d" % done)
    text = ssb.digest(conn)
    with open(ssb.DIGEST_PATH, "w") as f:
        f.write(text)
    try:
        import allm_embed
        allm_embed.embed_latest("scattered-second-brain",
                                "ssb-digest-latest.md", text)
        print("digest rebuilt + embedded")
    except Exception as e:
        print("warning: digest embed failed (R32): %s" % e)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
