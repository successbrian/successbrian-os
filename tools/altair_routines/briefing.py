#!/usr/bin/env python3
"""
Briefing conductor: walks Brian through a generated briefing, topic by topic.

PURPOSE:
    Turn a static briefing .md file into a guided conversation. `start`
    parses the file into ordered topics and opens a session; `next` stores
    Brian's feedback and advances; the 14B paraphrases `say` and classifies
    replies — it never decides flow.

WHY:
    Brian (2026-09-27): Altair must "run through a briefing with me" as a
    chat-focused production tool, and it must work on a 14B without a
    high-level LLM. Flow control in Python means the small model can't lose
    the thread, skip topics, or dump the whole briefing as a wall of text.
    Feedback is stored per topic so nothing Brian says evaporates.

CALLED BY:
    routine.py briefing <cmd>; Altair's chat loop via SUNDAY-BRIEFING.md.
    Reads ~/.hermes/profiles/altair/briefings/<date>-<slot>.md on k11.

NOTES:
    Parser handles the to_markdown() render shape from altair_briefing.py:
    `## Section` headers, `### Topic` headings, `Options:` / `**Needs from
    Brian:**` / `**Recommendation:**` lines. Unknown sections are skipped,
    not fatal. Sessions are idempotent: re-running `start` for the same
    date+slot reuses the existing session.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HOME, db, out, fail, today  # noqa: E402

BRIEF_DIR = os.path.join(HOME, ".hermes/profiles/altair/briefings")

SECTIONS = {
    "operational": "Operational",
    "blog_idea": "New Blog Ideas",
    "build_idea": "Build Ideas",
    "ecosystem_knowledge": "Ecosystem Knowledge",
    "decision": "Decisions Needed",
}
SECTION_BY_TITLE = {v.lower(): k for k, v in SECTIONS.items()}

AREA_LABEL = {
    "operational": "Operations",
    "blog_idea": "Blog idea",
    "build_idea": "Build idea",
    "ecosystem_knowledge": "Heads-up",
    "decision": "Decision",
}


def parse_briefing(path):
    """Parse briefing md into [(area, title, detail, needs, options, rec)]."""
    topics = []
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    area = None
    cur = None

    def flush():
        if cur and cur["title"]:
            topics.append(cur)

    for line in lines:
        s = line.strip()
        m = re.match(r"^##\s+(.*)$", s)
        if m:
            flush()
            cur = None
            area = SECTION_BY_TITLE.get(m.group(1).strip().lower())
            continue
        m = re.match(r"^###\s+(.*)$", s)
        if m and area:
            flush()
            title = m.group(1).strip()
            prio = None
            pm = re.match(r"^\[(HIGH|MEDIUM|LOW)\]\s+(.*)$", title, re.I)
            if pm:
                prio, title = pm.group(1).upper(), pm.group(2).strip()
            cur = {"area": area, "title": title, "priority": prio,
                   "body": [], "needs": None, "options": [], "rec": None}
            continue
        if cur is None:
            continue
        m = re.match(r"^\*\*Needs from Brian:\*\*\s*(.*)$", s, re.I)
        if m:
            cur["needs"] = m.group(1).strip()
            continue
        m = re.match(r"^Options:\s*(.*)$", s, re.I)
        if m:
            cur["options"] = [o.strip() for o in m.group(1).split("|")
                              if o.strip()]
            continue
        m = re.match(r"^\*\*Recommendation:\*\*\s*(.*)$", s, re.I)
        if m:
            cur["rec"] = m.group(1).strip()
            continue
        if s and not s.startswith("#"):
            cur["body"].append(s)
    flush()
    out_topics = []
    for t in topics:
        detail = " ".join(t["body"]).strip()
        detail = re.sub(r"_FYI only_", "FYI only — no action needed.", detail)
        out_topics.append((t["area"], t["title"], detail, t["needs"],
                           t["options"], t["rec"], t["priority"]))
    return out_topics


def say_for(area, title, detail, needs, options, rec, prio):
    """Compose the `say` text for one topic — phrased for Brian."""
    label = AREA_LABEL.get(area, "Topic")
    parts = [f"{label}: {title}."]
    if prio and prio != "LOW":
        parts.append(f"Priority {prio.lower()}.")
    if detail:
        parts.append(detail[:400])
    if rec:
        parts.append(f"My take: {rec}")
    if needs and "approve/reject/park" in needs.lower():
        parts.append("Approve, reject, or park it?")
    elif needs and "fyi" not in needs.lower():
        parts.append(needs)
    return " ".join(parts)


def current_topic(con, session):
    return con.execute(
        "SELECT * FROM briefing_topics WHERE session=? AND covered=0 "
        "ORDER BY ord LIMIT 1", (session,)).fetchone()


def topic_json(con, session, row):
    total = con.execute(
        "SELECT COUNT(*) FROM briefing_topics WHERE session=?",
        (session,)).fetchone()[0]
    covered = con.execute(
        "SELECT COUNT(*) FROM briefing_topics WHERE session=? AND covered=1",
        (session,)).fetchone()[0]
    options = json.loads(row["options_json"] or "[]")
    say = say_for(row["area"], row["title"], row["detail"], row["needs"],
                  options, None, None)
    # Pull recommendation out of detail is overkill; it was folded into say
    # at start time.
    obj = {"say": say, "session": session,
           "topic": covered + 1, "total": total, "done": False}
    if row["area"] == "decision" and options:
        obj["expect"] = "choice"
        obj["options"] = options
    else:
        obj["expect"] = "feedback"
    return obj


def cmd_start(args):
    path = os.path.join(BRIEF_DIR, f"{args.date}-{args.slot}.md")
    if not os.path.exists(path):
        fail(f"No briefing file at {path}. Say so plainly; never fabricate.")
    topics = parse_briefing(path)
    sid = f"brief-{args.date}-{args.slot}"
    con = db()
    row = con.execute("SELECT done FROM sessions WHERE id=?",
                      (sid,)).fetchone()
    if row:
        cur = current_topic(con, sid)
        if cur is None or row["done"]:
            out({"say": "We've already been through this briefing — "
                        "anything you want to revisit?",
                 "expect": "text", "session": sid, "done": True})
            return
        out(topic_json(con, sid, cur))
        return
    con.execute("INSERT INTO sessions (id, kind, ref_date, slot) "
                "VALUES (?, 'briefing', ?, ?)", (sid, args.date, args.slot))
    if not topics:
        con.execute("UPDATE sessions SET done=1 WHERE id=?", (sid,))
        con.commit()
        out({"say": "Nothing urgent on the briefing — all clear. "
                    "Anything else on your mind?",
             "expect": "text", "session": sid, "topic": 0,
             "total": 0, "done": True})
        return
    for i, (area, title, detail, needs, options, rec, prio) in enumerate(topics):
        # Fold recommendation into detail so `next` needs no re-parse.
        if rec:
            detail = (detail + f" Recommendation: {rec}").strip()
        con.execute(
            "INSERT INTO briefing_topics (session, ord, area, title, detail, "
            "needs, options_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, i, area, title, detail, needs, json.dumps(options)))
    con.commit()
    cur = current_topic(con, sid)
    first = topic_json(con, sid, cur)
    if len(topics) == 1:
        first["say"] = "One thing on the briefing. " + first["say"]
    else:
        first["say"] = (f"I've got {len(topics)} things on the briefing. "
                        f"Let's walk through them. " + first["say"])
    out(first)


def cmd_next(args):
    con = db()
    row = con.execute("SELECT done FROM sessions WHERE id=?",
                      (args.session,)).fetchone()
    if not row:
        fail(f"Unknown session {args.session}.")
    cur = current_topic(con, args.session)
    if cur is None:
        out({"say": "That's the whole briefing. Anything you want to "
                    "revisit, or are we good?",
             "expect": "text", "session": args.session, "done": True})
        return
    if args.feedback:
        con.execute("UPDATE briefing_topics SET feedback=?, covered=1 "
                    "WHERE id=?", (args.feedback, cur["id"]))
    else:
        con.execute("UPDATE briefing_topics SET covered=1 WHERE id=?",
                    (cur["id"],))
    con.commit()
    nxt = current_topic(con, args.session)
    if nxt is None:
        con.execute("UPDATE sessions SET done=1 WHERE id=?",
                    (args.session,))
        con.commit()
        out({"say": "That's everything on the briefing. Nice and clean. "
                    "Anything else, or are you heading back to your game?",
             "expect": "text", "session": args.session, "done": True})
        return
    out(topic_json(con, args.session, nxt))


def cmd_status(args):
    con = db()
    row = con.execute("SELECT done FROM sessions WHERE id=?",
                      (args.session,)).fetchone()
    if not row:
        fail(f"Unknown session {args.session}.")
    total = con.execute("SELECT COUNT(*) FROM briefing_topics WHERE session=?",
                        (args.session,)).fetchone()[0]
    covered = con.execute("SELECT COUNT(*) FROM briefing_topics "
                          "WHERE session=? AND covered=1",
                          (args.session,)).fetchone()[0]
    remaining = [r["title"] for r in con.execute(
        "SELECT title FROM briefing_topics WHERE session=? AND covered=0 "
        "ORDER BY ord", (args.session,))]
    out({"session": args.session, "covered": covered, "total": total,
         "remaining": remaining, "done": bool(row["done"]),
         "say": f"{covered} of {total} covered.",
         "expect": "text"})


def main():
    ap = argparse.ArgumentParser(prog="briefing.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("--date", default=today())
    p.add_argument("--slot", default="sunday")
    p = sub.add_parser("next")
    p.add_argument("--session", required=True)
    p.add_argument("--feedback", default="")
    p = sub.add_parser("status")
    p.add_argument("--session", required=True)
    args = ap.parse_args()
    try:
        {"start": cmd_start, "next": cmd_next,
         "status": cmd_status}[args.cmd](args)
    except SystemExit:
        raise
    except Exception as e:  # never strand the 14B without JSON
        fail(str(e))


if __name__ == "__main__":
    main()
