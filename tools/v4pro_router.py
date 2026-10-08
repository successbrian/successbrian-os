#!/usr/bin/env python3
"""
v4pro_router.py — The Sonic/V4 Pro tradeoff router.

PURPOSE: Decide, per task, whether Sonic handles it now or writes a handoff
         for DeepSeek V4 Pro to sharpen async. Also queues handoffs and
         reports queue/tradeoff status.
WHY: Brian 2026-10-07: "when there is deepseek v4 pro api available, i want
     sonic to write things down for deepseek to do; and for sonic to come back
     to me right away in chat." Sonic = fast, free, immediate (always the chat
     face). V4 Pro = deep, costs credits, works in the background when available.
CALLED BY: Altair (Sonic) in TUI chat before deep work; v4pro_handoff_worker.py
           imports get_availability().
NOTES:
  - Availability comes ONLY from successbrian_os.v4pro_balance_history
    (written by v4pro_state_checker.py every 30 min). Never hardcoded.
  - A row older than 60 min is stale -> treated as unavailable.
  - Usable = fresh AND available=true AND usd > 0. No price floors, no
    thresholds — per Brian's no-hardcoding directive.
  - Hardness is a heuristic, not a verdict: explicit --kind wins, then
    keyword signals, defaulting to sonic (answer fast) when uncertain.
    Altair's judgment overrides the heuristic; the router owns the
    availability truth.

COMMANDS:
  route  --text "..." [--kind KIND] [--force sonic|v4pro]
  queue  --summary "..." --ask "..." [--kind KIND] [--context "..."]
         [--sonic-draft "..."] [--constraints "..."] [--requested-by altair]
  check  [--since-minutes N]          # recently finished handoffs
  status                              # availability + queue snapshot
"""

import argparse
import datetime
import json
import subprocess
import sys

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t"]

STALE_MINUTES = 60  # twice the checker interval

HARD_KINDS = {"architecture", "system-design", "hard-coding", "strategy",
              "deep-analysis", "tradeoff", "research-deep"}
EASY_KINDS = {"chat", "lookup", "summary", "draft", "quick", "status",
              "small-code", "chore"}

HARD_SIGNALS = ["architect", "tradeoff", "trade-off", "strategy", "algorithm",
                "prove", "derive", "root cause", "think hard", "deep dive",
                "complex", "design the", "redesign", "from scratch"]
EASY_SIGNALS = ["summarize", "summary of", "list ", "what is", "remind",
                "status of", "quick question", "translate"]


def pq(s):
    """Quote a Python string as a Postgres string literal."""
    return "'" + str(s or "").replace("'", "''") + "'"


def get_availability():
    """Read the latest checker row. Returns dict; never raises."""
    try:
        sql = ("SELECT EXTRACT(EPOCH FROM now() - checked_at), available, "
               "COALESCE(usd, 0) FROM successbrian_os.v4pro_balance_history "
               "ORDER BY checked_at DESC LIMIT 1;")
        r = subprocess.run(PSQL + ["-c", sql], capture_output=True,
                           text=True, timeout=30)
        if r.returncode != 0 or not r.stdout.strip():
            return {"fresh": False, "available": False, "usd": 0.0,
                    "usable": False, "reason": "no checker rows"}
        age_s, avail, usd = r.stdout.strip().split("\t")
        age_s, usd = float(age_s), float(usd)
        fresh = age_s < STALE_MINUTES * 60
        available = avail.strip().lower() == "t"
        if not fresh:
            reason = "checker row is stale (%.0f min old)" % (age_s / 60)
        elif not available:
            reason = "checker reports unavailable"
        elif usd <= 0:
            reason = "balance is $0.00"
        else:
            reason = "available ($%.2f)" % usd
        return {"fresh": fresh, "available": available, "usd": usd,
                "usable": fresh and available and usd > 0,
                "age_minutes": round(age_s / 60, 1), "reason": reason}
    except Exception as e:
        return {"fresh": False, "available": False, "usd": 0.0,
                "usable": False, "reason": "availability read failed: %s" % e}


def classify(text, kind):
    """Heuristic hardness -> (target, why). Target is 'sonic' or 'v4pro'."""
    kind = (kind or "").strip().lower()
    if kind in HARD_KINDS:
        return ("v4pro", "task kind '%s' is deep work" % kind)
    if kind in EASY_KINDS:
        return ("sonic", "task kind '%s' is fast work" % kind)
    t = (text or "").lower()
    hard_hits = [kw for kw in HARD_SIGNALS if kw in t]
    easy_hits = [kw for kw in EASY_SIGNALS if kw in t]
    if hard_hits and not easy_hits:
        return ("v4pro", "deep-work signals: %s" % ", ".join(hard_hits[:3]))
    if easy_hits:
        return ("sonic", "fast-work signals: %s" % ", ".join(easy_hits[:3]))
    return ("sonic", "no deep-work signals — answer fast")


def cmd_route(args):
    avail = get_availability()
    target, why = classify(args.text, args.kind)
    if args.force in ("sonic", "v4pro"):
        target, why = args.force, "manual override (--force)"
    if target == "v4pro" and not avail["usable"]:
        why = ("V4 Pro not usable (%s); wanted v4pro (%s) — "
               "Sonic handles it now and says the deep tier is dry" % (avail["reason"], why))
        target = "sonic"
    out = {"target": target, "reason": why, "v4pro": avail,
           "at": datetime.datetime.now().isoformat(timespec="seconds")}
    print("target=%s  (%s)  [v4pro: %s]" % (target, why, avail["reason"]))
    print(json.dumps(out))


def cmd_queue(args):
    if not args.ask or not args.ask.strip():
        print("error: --ask is required (what should V4 Pro do?)", file=sys.stderr)
        sys.exit(2)
    sql = ("INSERT INTO successbrian_os.v4pro_handoffs "
           "(requested_by, task_kind, task_summary, context, sonic_draft, ask, constraints) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;"
           % (pq(args.requested_by), pq(args.kind or "general"),
              pq(args.summary), pq(args.context), pq(args.sonic_draft),
              pq(args.ask), pq(args.constraints)))
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print("queue failed: %s" % r.stderr.strip()[:300], file=sys.stderr)
        sys.exit(1)
    hid = r.stdout.strip().splitlines()[0].strip()
    print("queued handoff id=%s (worker picks it up within ~15 min)" % hid)
    print(json.dumps({"handoff_id": int(hid), "status": "queued"}))


def cmd_check(args):
    sql = ("SELECT id, to_char(created_at,'YYYY-MM-DD HH24:MI'), task_summary, status, "
           "to_char(completed_at,'YYYY-MM-DD HH24:MI') "
           "FROM successbrian_os.v4pro_handoffs "
           "WHERE created_at > now() - interval '%d minutes' "
           "ORDER BY created_at DESC;" % args.since_minutes)
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    rows = [ln for ln in r.stdout.strip().split("\n") if ln.strip()] if r.returncode == 0 else []
    if not rows:
        print("no handoffs in the last %d min" % args.since_minutes)
        return
    for ln in rows:
        hid, created, summary, status, done = (ln.split("\t") + [""])[:5]
        print("#%s [%s] %s — %s" % (hid, status, summary[:70], done or created))


def cmd_result(args):
    sql = ("SELECT v4pro_result FROM successbrian_os.v4pro_handoffs WHERE id = %d;"
           % args.id)
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    print(r.stdout.strip() or "(no result yet)")


def cmd_status(args):
    avail = get_availability()
    sql = ("SELECT status, COUNT(*) FROM successbrian_os.v4pro_handoffs "
           "GROUP BY status;")
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    counts = dict(ln.split("\t") for ln in r.stdout.strip().split("\n") if "\t" in ln) \
        if r.returncode == 0 else {}
    print("V4 Pro: %s" % avail["reason"])
    q = int(counts.get("queued", 0)); w = int(counts.get("working", 0))
    d = int(counts.get("done", 0)); f = int(counts.get("failed", 0))
    print("handoffs: %d queued, %d working, %d done, %d failed" % (q, w, d, f))
    print(json.dumps({"v4pro": avail, "queue": counts}))


def main():
    ap = argparse.ArgumentParser(description="Sonic/V4 Pro tradeoff router")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("route", help="decide sonic vs v4pro for a task")
    p.add_argument("--text", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--force", choices=["sonic", "v4pro"], default="")
    p.set_defaults(fn=cmd_route)

    p = sub.add_parser("queue", help="queue a handoff for V4 Pro")
    p.add_argument("--summary", required=True)
    p.add_argument("--ask", required=True)
    p.add_argument("--kind", default="general")
    p.add_argument("--context", default="")
    p.add_argument("--sonic-draft", default="")
    p.add_argument("--constraints", default="")
    p.add_argument("--requested-by", default="altair")
    p.set_defaults(fn=cmd_queue)

    p = sub.add_parser("check", help="list recent handoffs")
    p.add_argument("--since-minutes", type=int, default=180)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("result", help="print a handoff's V4 Pro result")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(fn=cmd_result)

    p = sub.add_parser("status", help="availability + queue snapshot")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
