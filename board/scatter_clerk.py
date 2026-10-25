#!/usr/bin/env python3
"""The Scatter Clerk — the board looks at new scatter entries daily.

Brian (2026-10-24): "every day the board should be looking at new
entries to the scatter — our clerk should be creating packets."

The clerk is a software role (the serious flow's build order starts
with 'packet builder in software'). The clerk looks THROUGH THE DAY,
every day (Brian: the 04:50-only cadence became an hourly sweep the
same morning he ordered the clerk — a capture should never wait
overnight to become a packet). On every pass, the clerk:

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

WORKFLOW #3 — THE KEEPING WORKFLOW (Brian, 2026-10-25: "create
workflow #3"): the sort is now three-way. A capture that arrives
as INTEL (a research result from a requested lookup — a video
analyzed, a page read, a price checked; today recognized by the
producer's INTEL provenance stamp in its context) does not need
judging and is not a task to do: it needs to be KEPT. The clerk
files it as a document into its determined AnythingLLM workspace
(determine() + allm_embed, the R32 sanctioned home), marks the
capture wf3-kept with its workspace_slug, and creates NO board
packet. If the filing cannot complete (workspace determined but
not yet created, embed failure), the kick-aside law applies: the
item goes to Workflow #2 as an atlas task for Altair, with the
reason — never forced, never silently dropped.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/atlas"))
import pm_core  # noqa: E402
import allm_embed  # noqa: E402
import allm_workspaces as allm  # noqa: E402

ATLAS_PY = os.path.expanduser("~/successbrian-os/tools/atlas/atlas.py")
STATE = os.path.expanduser("~/successbrian-os/board/state/scatter_clerk.json")

# Workflow #3 class marker (v1, deterministic): a capture is intel
# when its producer stamped it as an INTEL filing. Muse's bridge
# dump pipe stamps "chat INTEL dump" into the context of every
# --kind intel filing (Brian's ruling, 2026-10-25). New producers
# adopt the same stamp; the sort never guesses from content.
INTEL_MARKER = "INTEL dump"

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


def is_wf3(cap):
    """Workflow #3 class test: intel filings carry the stamp."""
    return INTEL_MARKER in (cap.get("context") or "")


def fetch_capture(cid):
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        "SELECT id, title, coalesce(context,''), "
        "coalesce(raw_text,''), score, coalesce(recommendation,''), "
        "cluster_key, status "
        "FROM atlas.scattered_captures WHERE id = %s", (cid,))
    r = cur.fetchone()
    c.close()
    if not r:
        return None
    return {"id": r[0], "title": r[1], "context": r[2], "raw": r[3],
            "score": r[4], "recommendation": r[5], "cluster": r[6],
            "status": r[7]}


def _wf3_subject(title):
    """The subject determine() routes on: the title minus the
    producer's filing tags (INTEL —, VIDEO:, ...)."""
    s = re.sub(r"^INTEL\s*[—-]\s*", "", title or "")
    s = re.sub(r"^(VIDEO|PAGE|PRICE|WEB|RESEARCH)\s*:\s*", "", s,
               flags=re.I)
    return s.strip() or (title or "")


def _wf3_mark(cap_id, recommendation, slug=None):
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        "UPDATE atlas.scattered_captures SET status='triaged', "
        "triaged_at=now(), recommendation=%s, workspace_slug=%s "
        "WHERE id=%s", (recommendation, slug, cap_id))
    c.commit()
    c.close()


def _wf3_kick(cap, reason, dry_run=False):
    """Kick-aside to Workflow #2: an atlas task for Altair carrying
    the filing failure. The clerk never forces a misfit and never
    drops one silently."""
    key = f"task:wf3-kickaside-{cap['id']}"
    title = (f"WF3 filing failed for capture #{cap['id']} — "
             f"Altair to place: {cap['title']}")[:180]
    details = {
        "question": (
            f"Workflow #3 (the keeping workflow) could not file "
            f"Intel Bridge capture #{cap['id']} ('{cap['title']}')."
            f"\n\nREASON: {reason}\n\nCONTEXT: "
            f"{(cap['context'] or '')[:800]}\n\nINTEL: "
            f"{(cap['raw'] or '')[:2000]}\n\nAltair: file this intel "
            f"into its proper knowledge home (or create the "
            f"workspace it waits on), then close this task."),
        "theme": "wf3-kickaside",
        "found_by": "scatter-clerk-wf3",
        "source_captures": [cap["id"]],
    }
    if dry_run:
        print(f"[dry-run] would kick capture #{cap['id']} -> {key} "
              f"({reason})")
        return key
    r = subprocess.run(
        ["python3", ATLAS_PY, "add-node", key, "atlas_task", title,
         "--status", "queued", "--details", json.dumps(details)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"kick-aside add-node failed: "
                           f"{r.stderr[:300]}")
    _wf3_mark(cap["id"], "wf3-kicked-to-wf2")
    return key


def file_wf3(cap, dry_run=False):
    """File one intel capture into its knowledge home (WF3).

    Returns {"id", "outcome": kept|kicked, "workspace", "detail"}.
    """
    subject = _wf3_subject(cap["title"])
    c = pm_core.conn()
    try:
        d = allm.determine(c, subject)
    finally:
        c.close()
    slug = d.get("workspace") or d.get("proposed_slug")
    if not slug:
        reason = f"determine() returned no workspace ({d})"
        _wf3_kick(cap, reason, dry_run=dry_run)
        return {"id": cap["id"], "outcome": "kicked",
                "workspace": None, "detail": reason}
    live = allm.live_workspaces()
    if slug not in live:
        reason = (f"workspace '{slug}' determined "
                  f"(verdict {d.get('verdict')}) but not created in "
                  f"AnythingLLM yet — filing waits on its creation")
        _wf3_kick(cap, reason, dry_run=dry_run)
        return {"id": cap["id"], "outcome": "kicked",
                "workspace": slug, "detail": reason}
    text = (f"# {cap['title']}\n\n"
            f"Intel Bridge capture #{cap['id']}, filed by Workflow "
            f"#3 (the keeping workflow).\n\n"
            f"## Context\n{cap['context'] or ''}\n\n"
            f"## Intel\n{cap['raw'] or ''}\n")
    filename = f"intel-capture-{cap['id']}.md"
    if dry_run:
        print(f"[dry-run] would file capture #{cap['id']} -> "
              f"{slug}/{filename}")
        return {"id": cap["id"], "outcome": "kept",
                "workspace": slug, "detail": "dry-run"}
    try:
        loc = allm_embed.embed_latest(slug, filename, text)
    except Exception as e:
        reason = f"embed into '{slug}' failed: {type(e).__name__}: {e}"
        _wf3_kick(cap, reason, dry_run=dry_run)
        return {"id": cap["id"], "outcome": "kicked",
                "workspace": slug, "detail": reason}
    _wf3_mark(cap["id"], "wf3-kept", slug=slug)
    return {"id": cap["id"], "outcome": "kept",
            "workspace": slug, "detail": loc}


def run(dry_run=False):
    state = load_state()
    caps = fetch_new(state["last_capture_id"])
    if not caps:
        print("scatter clerk: no new raw captures")
        return [], []
    wf3_caps = [c for c in caps if is_wf3(c)]
    board_caps = [c for c in caps if not is_wf3(c)]
    wf3_results = []
    for cap in wf3_caps:
        res = file_wf3(cap, dry_run=dry_run)
        wf3_results.append(res)
        print(f"wf3 {res['outcome']} capture #{res['id']} -> "
              f"{res['workspace'] or 'wf2'} ({res['detail']})")
    groups = group(board_caps)
    keys = []
    for g in groups:
        keys.append(file_packet(g, dry_run=dry_run))
        print(f"packet for captures {[m['id'] for m in g]} -> {keys[-1]}")
    if not dry_run:
        state["last_capture_id"] = max(m["id"] for m in caps)
        save_state(state)
        c = pm_core.conn()
        cur = c.cursor()
        if keys:
            pm_core.decide(
                cur, "scatter-clerk",
                f"Scatter clerk packeted {len(board_caps)} new "
                f"capture(s) into {len(keys)} board packet(s): "
                f"{', '.join(keys)}",
                origin="system")
        if wf3_results:
            kept = [r for r in wf3_results if r["outcome"] == "kept"]
            kicked = [r for r in wf3_results
                      if r["outcome"] == "kicked"]
            pm_core.decide(
                cur, "scatter-clerk",
                f"Workflow #3 filed {len(kept)} intel capture(s) to "
                f"their knowledge homes "
                f"({', '.join('#%d->%s' % (r['id'], r['workspace']) for r in kept) or 'none'}); "
                f"{len(kicked)} kicked to Workflow #2 "
                f"({', '.join('#%d' % r['id'] for r in kicked) or 'none'})",
                origin="system")
        c.commit()
        c.close()
    return keys, wf3_results


def main(argv=None):
    dry = "--dry-run" in (argv or sys.argv)
    run(dry_run=dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
