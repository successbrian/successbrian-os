#!/usr/bin/env python3
"""
Planning helper: turn a goal into a saved plan, one question at a time.

PURPOSE:
    `start` opens a plan and asks the first scaffolded question; `answer`
    stores each reply and advances through outcome → first step → blockers →
    needs → timeline; `save` writes the finished plan to disk and the
    second brain.

WHY:
    Brian (2026-09-27): Altair must "help me plan things" as a production
    tool on a 14B. An LLM planning free-form rambles or skips steps; a
    fixed question scaffold guarantees every plan covers what done looks
    like, the first step, blockers, needs, and timing — the five things
    that turn an idea into something executable. Answers persist in
    state.db so an interrupted session resumes, not restarts.

CALLED BY:
    routine.py planning <cmd>; Altair's chat loop whenever Brian wants to
    plan something. Plans land in ~/.hermes/profiles/altair/plans/.

NOTES:
    `list` shows plans with status. `save` is idempotent — re-saving the
    same plan overwrites the same dated file, never duplicates.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HOME, db, out, fail, today, sb_log  # noqa: E402

PLANS_DIR = os.path.join(HOME, ".hermes/profiles/altair/plans")

QUESTIONS = [
    ("outcome", "What does done look like?"),
    ("first_step", "What's the very first step?"),
    ("blockers", "What could block it?"),
    ("needs", "Who or what do you need to pull this off?"),
    ("timeline", "When should this happen?"),
]


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:50] or "plan"


def get_plan(con, pid):
    row = con.execute("SELECT * FROM plans WHERE id=?", (pid,)).fetchone()
    if not row:
        fail(f"Unknown plan {pid}.")
    return row


def summary_text(goal, answers):
    L = [f"Plan: {goal}", ""]
    for (key, q), a in zip(QUESTIONS, answers):
        L.append(f"- {q} {a}")
    return "\n".join(L)


def cmd_start(args):
    con = db()
    cur = con.execute(
        "INSERT INTO plans (goal) VALUES (?)", (args.goal,))
    pid = cur.lastrowid
    con.commit()
    key, q = QUESTIONS[0]
    out({"say": f"Let's plan it. {q}", "expect": "text",
         "plan": pid, "question": 1, "of": len(QUESTIONS),
         "question_key": key, "done": False})


def cmd_answer(args):
    con = db()
    row = get_plan(con, args.plan)
    if row["status"] == "saved":
        out({"say": "That plan's already saved. Want to start a fresh one?",
             "expect": "text", "plan": args.plan, "done": True})
        return
    answers = json.loads(row["answers_json"] or "[]")
    answers.append(args.text)
    q_index = len(answers)
    con.execute("UPDATE plans SET answers_json=?, q_index=? WHERE id=?",
                (json.dumps(answers), q_index, args.plan))
    con.commit()
    if q_index < len(QUESTIONS):
        key, q = QUESTIONS[q_index]
        out({"say": q, "expect": "text", "plan": args.plan,
             "question": q_index + 1, "of": len(QUESTIONS),
             "question_key": key, "done": False})
        return
    con.execute("UPDATE plans SET status='complete' WHERE id=?",
                (args.plan,))
    con.commit()
    out({"say": summary_text(row["goal"], answers) +
         "\n\nWant me to save this plan?",
         "expect": "choice", "options": ["save it", "not yet"],
         "plan": args.plan, "done": False})


def cmd_save(args):
    con = db()
    row = get_plan(con, args.plan)
    answers = json.loads(row["answers_json"] or "[]")
    if len(answers) < len(QUESTIONS):
        fail("Plan isn't finished — answer all questions first.")
    os.makedirs(PLANS_DIR, exist_ok=True)
    path = os.path.join(PLANS_DIR, f"{today()}-{slug(row['goal'])}.md")
    L = [f"# Plan: {row['goal']}", f"Created: {today()} with Brian", ""]
    for (key, q), a in zip(QUESTIONS, answers):
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
           tags=("plan", "altair-routines"))
    out({"say": f"Saved. The plan's filed and logged.",
         "plan": args.plan, "path": path, "done": True,
         "expect": "text"})


def cmd_list(args):
    con = db()
    rows = con.execute(
        "SELECT id, goal, status, created_at, plan_path FROM plans "
        "ORDER BY id DESC LIMIT 20").fetchall()
    plans = [{"id": r["id"], "goal": r["goal"], "status": r["status"],
              "created_at": r["created_at"],
              "path": r["plan_path"]} for r in rows]
    out({"plans": plans, "count": len(plans),
         "say": f"{len(plans)} plan{'s' if len(plans) != 1 else ''} on file.",
         "expect": "text", "done": True})


def main():
    ap = argparse.ArgumentParser(prog="planning.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("--goal", required=True)
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
