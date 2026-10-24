#!/usr/bin/env python3
"""The Scatter Clerk — the board looks at new scatter entries daily.

Brian (2026-10-24): "every day the board should be looking at new
entries to the scatter — our clerk should be creating packets."

The clerk is a software role (the serious flow's build order starts
with 'packet builder in software'). Every morning, after SSB triage
(04:30) and the deadline radar (04:45), the clerk:

  1. Reads NEW raw captures from atlas.scattered_captures (a
     watermark guarantees each capture is packeted exactly once).
  2. Groups repeats: captures whose titles strongly overlap are one
     tangent said twice, so they share a packet.
  3. Builds each packet by packet law — it states WHY IT MATTERS,
     states THE DILEMMA, and asks MANY EASY QUESTIONS (never one big
     hard question; the complexity surfaces from the answer set).
  4. Files each packet as an atlas_task node whose details carry
     the full packet text in `question` — the exact field the board
     harness reads — so the packet is in the agenda the panel, the
     wave-2 closer, and the decider heartbeats already pull.
  5. Writes one decision-stream line per run that created packets.

The clerk never judges and never rules the scatter: promote / park /
discard stays Brian's SSB ruling. The board looks; the deciders
work the packet; the recommendation comes back through the stream.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
import pm_core  # noqa: E402

ATLAS_PY = os.path.expanduser("~/successbrian-os/tools/atlas/atlas.py")
STATE = os.path.expanduser("~/successbrian-os/board/state/scatter_clerk.json")

EASY_QUESTIONS = [
    "Is this connected to a standing goal or launch — which one?",
    "Is this new, or a repeat of something the ecosystem already holds?",
    "What is the smallest next step that would move it?",
    "What breaks, rots, or is lost if this waits a month?",
    "What single piece of research would settle whether it matters?",
    "Does this need Brian himself, or can the ecosystem carry it?",
    "If it works, what does it feed — a desk, a launch, the fleet, the graph?",
]

STOP = set("the a an and or of to for in on with is are it its this "
           "that from by at as be was were will would can could".split())


def words(title):
    return {w for w in re.findall(r"[a-z0-9]+", title.lower())
            if w not in STOP and len(w) > 2}


def group(captures):
    """Group by the SSB's own cluster_key (set at capture time);
    title-word overlap is the fallback for unclustered captures."""
    by_cluster = {}
    loose = []
    for cap in captures:
        if cap.get("cluster"):
            by_cluster.setdefault(cap["cluster"], []).append(cap)
        else:
            loose.append(cap)
    groups = list(by_cluster.values())
    for cap in loose:
        ws = words(cap["title"])
        placed = False
        for g in groups:
            gw = words(g[0]["title"])
            union = ws | gw
            sim = len(ws & gw) / len(union) if union else 0
            if sim >= 0.45:
                g.append(cap)
                placed = True
                break
        if not placed:
            groups.append([cap])
    return groups


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"last_capture_id": 0}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w"), indent=1)


def fetch_new(last_id):
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        "SELECT id, title, coalesce(context,''), "
        "coalesce(raw_text,''), score, coalesce(recommendation,''), "
        "cluster_key "
        "FROM atlas.scattered_captures "
        "WHERE status='raw' AND id > %s ORDER BY id", (last_id,))
    rows = cur.fetchall()
    c.close()
    return [{"id": r[0], "title": r[1], "context": r[2], "raw": r[3],
             "score": r[4], "recommendation": r[5], "cluster": r[6]}
            for r in rows]


def packet_text(members):
    lines = []
    titles = "; ".join(m["title"] for m in members)
    lines.append(f"SCATTER PACKET — {titles}")
    lines.append("")
    lines.append("WHY IT MATTERS:")
    for m in members:
        why = (m["context"] or m["raw"] or "").strip()
        if why:
            lines.append(f"- (capture #{m['id']}) {why[:600]}")
        if m["recommendation"]:
            lines.append(f"- SSB triage read: {m['recommendation']}"
                         + (f" (score {m['score']})" if m["score"]
                            is not None else ""))
    lines.append("")
    lines.append("THE DILEMMA: does this tangent deserve promotion "
                 "into planned work, parking until its moment, or "
                 "discard — and what would settle it? (The ruling "
                 "itself stays Brian's under SSB doctrine; the "
                 "board's job is to look, judge the questions, and "
                 "bring back a recommendation.)")
    lines.append("")
    lines.append("QUESTIONS FOR THE JUDGES:")
    for i, q in enumerate(EASY_QUESTIONS, 1):
        lines.append(f"{i}. {q}")
    lines.append("")
    lines.append("SOURCE: atlas.scattered_captures "
                 + ", ".join(f"#{m['id']}" for m in members))
    return "\n".join(lines)


def file_packet(members, dry_run=False):
    ids = "-".join(str(m["id"]) for m in members)
    key = f"task:ssb-packet-{ids}"
    title = ("Scatter packet: " + members[0]["title"])[:180]
    details = {
        "question": packet_text(members),
        "why_it_matters": (members[0]["context"]
                           or members[0]["raw"] or "")[:600],
        "dilemma": "promote into planned work, park, or discard — "
                   "and what research settles it",
        "easy_questions": EASY_QUESTIONS,
        "source_captures": [m["id"] for m in members],
        "theme": "scatter",
        "found_by": "scatter-clerk",
    }
    if dry_run:
        print(f"[dry-run] would file {key}: {title}")
        print(details["question"][:800])
        return key
    r = subprocess.run(
        ["python3", ATLAS_PY, "add-node", key, "atlas_task", title,
         "--status", "queued", "--details", json.dumps(details)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"add-node failed: {r.stderr[:300]}")
    return key


def run(dry_run=False):
    state = load_state()
    caps = fetch_new(state["last_capture_id"])
    if not caps:
        print("scatter clerk: no new raw captures")
        return []
    groups = group(caps)
    keys = []
    for g in groups:
        keys.append(file_packet(g, dry_run=dry_run))
        print(f"packet for captures {[m['id'] for m in g]} -> {keys[-1]}")
    if not dry_run:
        state["last_capture_id"] = max(m["id"] for m in caps)
        save_state(state)
        c = pm_core.conn()
        cur = c.cursor()
        pm_core.decide(
            cur, "scatter-clerk",
            f"Scatter clerk packeted {len(caps)} new capture(s) into "
            f"{len(keys)} board packet(s): {', '.join(keys)}",
            origin="system")
        c.commit()
        c.close()
    return keys


def main(argv=None):
    dry = "--dry-run" in (argv or sys.argv)
    run(dry_run=dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
