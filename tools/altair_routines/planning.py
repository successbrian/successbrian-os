#!/usr/bin/env python3
"""
Planning helper: turn a goal into a saved plan, one question at a time.

PURPOSE:
    `start` opens a plan and asks the first scaffolded question; `answer`
    stores each reply and advances through the type's question template;
    `save` writes the finished plan to disk and the second brain.

WHY:
    Brian (2026-09-27): Altair must "help me plan things" as a production
    tool on a 14B. An LLM planning free-form rambles or skips steps; a
    fixed question scaffold guarantees every plan covers what matters.
    Brian refined it the same night: "planning" is not generic — it is
    FIVE concrete plan types, each with its own template, because a blog
    site, a vibe-coded project, a hardware build, an ecosystem tool, and
    an ecosystem upgrade ask fundamentally different questions. Answers
    persist in state.db so an interrupted session resumes, not restarts.

CALLED BY:
    routine.py planning <cmd>; Altair's chat loop whenever Brian wants to
    plan something. Plans land in ~/.hermes/profiles/altair/plans/.

NOTES:
    `list` shows plans with their types. `save` is idempotent —
    re-saving the same plan overwrites the same dated file, never
    duplicates. Second-brain records carry a plan:<type> tag.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HOME, db, out, fail, today, sb_log  # noqa: E402

PLANS_DIR = os.path.join(HOME, ".hermes/profiles/altair/plans")

# Brian's five plan types (2026-09-27): each template asks what that kind
# of plan actually needs. Generic scaffold kept as fallback.
PLAN_TYPES = {
    "blog-site": [
        ("niche", "What's the niche or topic?"),
        ("traffic_filter", "Does it pass the 50K monthly visits filter — and why?"),
        ("monetization", "What's the monetization path?"),
        ("content_engine", "Which content engine produces it — factory, model, or workflow?"),
        ("launch_checklist", "What's on the launch checklist?"),
    ],
    "vibe-coded-project": [
        ("one_liner", "What does it do — in one line?"),
        ("callers", "Who or what calls it?"),
        ("stack", "What's the stack?"),
        ("repo", "Which GitHub repo does it live in?"),
        ("done_criteria", "How do we know it works — what are the done criteria?"),
    ],
    "new-build": [
        ("purpose", "What's the machine's purpose?"),
        ("parts", "What's the parts list?"),
        ("budget", "What's the budget ceiling?"),
        ("power_thermal", "Any power or thermal constraints?"),
        ("placement", "Where does it live in the home lab?"),
    ],
    "ecosystem-tool": [
        ("purpose", "What's its purpose?"),
        ("callers", "Called by whom or what?"),
        ("io", "Inputs to outputs — what goes in, what comes out?"),
        ("code_home", "Where does the code live?"),
        ("trigger", "How is it scheduled or triggered?"),
    ],
    "ecosystem-upgrade": [
        ("change", "What's changing?"),
        ("affected", "Which systems are affected?"),
        ("backup", "Backup taken — confirm?"),
        ("rollback", "What's the rollback plan?"),
        ("canary", "What's the canary or verification step?"),
    ],
}

GENERIC_QUESTIONS = [
    ("outcome", "What does done look like?"),
    ("first_step", "What's the very first step?"),
    ("blockers", "What could block it?"),
    ("needs", "Who or what do you need to pull this off?"),
    ("timeline", "When should this happen?"),
]

TYPE_LABELS = {
    "blog-site": "a blog site",
    "vibe-coded-project": "a vibe-coded project",
    "new-build": "a hardware build",
    "ecosystem-tool": "an ecosystem tool",
    "ecosystem-upgrade": "an ecosystem upgrade",
    "generic": "a general plan",
}


def normalize_type(t):
    """Map free-form type input to a known slug, or None."""
    if not t:
        return None
    s = re.sub(r"[\s_]+", "-", t.strip().lower())
    if s in PLAN_TYPES or s == "generic":
        return s
    return None


def questions_for(ptype):
    return PLAN_TYPES.get(ptype, GENERIC_QUESTIONS)


def _ensure_type_col(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info(plans)")]
    if "plan_type" not in cols:
        con.execute("ALTER TABLE plans ADD COLUMN plan_type TEXT DEFAULT 'generic'")
        con.commit()


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:50] or "plan"


def get_plan(con, pid):
    _ensure_type_col(con)
    row = con.execute("SELECT * FROM plans WHERE id=?", (pid,)).fetchone()
    if not row:
        fail(f"Unknown plan {pid}.")
    return row


def summary_text(goal, ptype, answers):
    L = [f"Plan: {goal}", f"Type: {ptype}", ""]
    for (key, q), a in zip(questions_for(ptype), answers):
        L.append(f"- {q} {a}")
    return "\n".join(L)


def ask_type(goal):
    """No (valid) type given: ask the 14B to classify into one of the five."""
    labels = "; ".join(f"{s} ({TYPE_LABELS[s]})" for s in PLAN_TYPES)
    out({"say": f"What kind of plan is this — {labels}?",
         "expect": "choice", "options": list(PLAN_TYPES.keys()),
         "goal": goal, "done": False,
         "hint": "Classify his answer into one of the five types and call "
                 "start again with --type. If it fits none of them, call "
                 "start with --type generic."})


def cmd_start(args):
    ptype = normalize_type(args.type)
    if ptype is None:
        ask_type(args.goal)
        return
    con = db()
    _ensure_type_col(con)
    cur = con.execute(
        "INSERT INTO plans (goal, plan_type) VALUES (?, ?)",
        (args.goal, ptype))
    pid = cur.lastrowid
    con.commit()
    qs = questions_for(ptype)
    key, q = qs[0]
    out({"say": f"Let's plan {TYPE_LABELS[ptype]}. {q}", "expect": "text",
         "plan": pid, "type": ptype, "question": 1, "of": len(qs),
         "question_key": key, "done": False})


def cmd_answer(args):
    con = db()
    row = get_plan(con, args.plan)
    if row["status"] == "saved":
        out({"say": "That plan's already saved. Want to start a fresh one?",
             "expect": "text", "plan": args.plan, "done": True})
        return
    ptype = row["plan_type"] or "generic"
    qs = questions_for(ptype)
    answers = json.loads(row["answers_json"] or "[]")
    answers.append(args.text)
    q_index = len(answers)
    con.execute("UPDATE plans SET answers_json=?, q_index=? WHERE id=?",
                (json.dumps(answers), q_index, args.plan))
    con.commit()
    if q_index < len(qs):
        key, q = qs[q_index]
        out({"say": q, "expect": "text", "plan": args.plan, "type": ptype,
             "question": q_index + 1, "of": len(qs),
             "question_key": key, "done": False})
        return
    con.execute("UPDATE plans SET status='complete' WHERE id=?",
                (args.plan,))
    con.commit()
    out({"say": summary_text(row["goal"], ptype, answers) +
         "\n\nWant me to save this plan?",
         "expect": "choice", "options": ["save it", "not yet"],
         "plan": args.plan, "type": ptype, "done": False})


def cmd_save(args):
    con = db()
    row = get_plan(con, args.plan)
    ptype = row["plan_type"] or "generic"
    qs = questions_for(ptype)
    answers = json.loads(row["answers_json"] or "[]")
    if len(answers) < len(qs):
        fail("Plan isn't finished — answer all questions first.")
    os.makedirs(PLANS_DIR, exist_ok=True)
    path = os.path.join(PLANS_DIR, f"{today()}-{slug(row['goal'])}.md")
    L = [f"# Plan: {row['goal']}", f"Type: {ptype}",
         f"Created: {today()} with Brian", ""]
    for (key, q), a in zip(qs, answers):
        L.append(f"## {q}")
        L.append(a)
        L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    con.execute("UPDATE plans SET status='saved', plan_path=? WHERE id=?",
                (path, args.plan))
    con.commit()
    sb_log(f"Plan: {row['goal'][:80]}", "\n".join(L),
           category="plan", confidence="high", source="brian-direct",
           tags=("plan", f"plan:{ptype}", "altair-routines"))
    out({"say": "Saved. The plan's filed and logged.",
         "plan": args.plan, "type": ptype, "path": path, "done": True,
         "expect": "text"})


def cmd_list(args):
    con = db()
    _ensure_type_col(con)
    rows = con.execute(
        "SELECT id, goal, plan_type, status, created_at, plan_path FROM plans "
        "ORDER BY id DESC LIMIT 20").fetchall()
    plans = [{"id": r["id"], "goal": r["goal"], "type": r["plan_type"],
              "status": r["status"], "created_at": r["created_at"],
              "path": r["plan_path"]} for r in rows]
    out({"plans": plans, "count": len(plans),
         "say": f"{len(plans)} plan{'s' if len(plans) != 1 else ''} on file.",
         "expect": "text", "done": True})


def main():
    ap = argparse.ArgumentParser(prog="planning.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("--goal", required=True)
    p.add_argument("--type", default=None,
                   help="one of: blog-site, vibe-coded-project, new-build, "
                        "ecosystem-tool, ecosystem-upgrade, generic")
    p = sub.add_parser("answer")
    p.add_argument("--plan", required=True)
    p.add_argument("--text", required=True)
    p = sub.add_parser("save")
    p.add_argument("--plan", required=True)
    sub.add_parser("list")
    args = ap.parse_args()
    try:
        {"start": cmd_start, "answer": cmd_answer, "save": cmd_save,
         "list": cmd_list}[args.cmd](args)
    except SystemExit:
        raise
    except Exception as e:
        fail(str(e))


if __name__ == "__main__":
    main()
