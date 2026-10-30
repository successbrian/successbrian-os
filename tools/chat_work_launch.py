#!/usr/bin/env python3
"""
chat_work_launch.py — One-command background launch for Altair chat work.

WHY (Brian, 2026-10-29): Altair chat must never sit and mull over routing.
The routing decision lives HERE, in code, not in the model's head:

  - DeepSeek V4 Pro usable (fresh checker row, available, usd > 0):
    the plan Sonic wrote in chat is queued as ONE V4 Pro handoff.
    v4pro_handoff_worker (cron */15) executes it in the background and
    re-checks the balance before every API call.
  - DeepSeek NOT usable:
    the plan is queued to successbrian_os.qwen_task_queue, drained by
    qwen-task-worker (Sonic) in the background.
    Plan steps prefixed "DEEP:" are ADDITIONALLY queued as a V4 Pro
    handoff (summary suffix "(deep steps)") — the handoff worker never
    fails queued items for lack of credits, so they execute when the
    balance returns. That is the "something larger if needed" path.

Altair's whole job is: write the plan (max 7 steps, one line each),
call this once, and report the JSON result to Brian in chat.
Availability truth comes only from v4pro_router.get_availability()
(v4pro_balance_history; stale >60 min = unusable). Never hardcoded.

Usage:
  chat_work_launch.py --summary "one line" --plan "step 1
  step 2
  DEEP: step needing deep reasoning" [--kind KIND] [--dry-run]

Output: one human line, then one JSON line (the launch receipt), then a
LAUNCHER_OK line (used by the project QA check).
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v4pro_router import get_availability  # noqa: E402
import sbos_common  # noqa: E402


def split_plan(plan_text):
    steps, deep = [], []
    for raw in (plan_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("DEEP:"):
            deep.append(line[5:].strip())
            steps.append(line[5:].strip())
        else:
            steps.append(line)
    return steps, deep


def main():
    ap = argparse.ArgumentParser(description="Launch chat work to the background")
    ap.add_argument("--summary", required=True, help="one-line summary of the work")
    ap.add_argument("--plan", required=True, help="plan steps, one per line; prefix deep steps with DEEP:")
    ap.add_argument("--kind", default="general")
    ap.add_argument("--requested-by", default="altair-chat")
    ap.add_argument("--dry-run", action="store_true", help="decide only; enqueue nothing")
    args = ap.parse_args()

    steps, deep = split_plan(args.plan)
    if not steps:
        print("error: --plan has no steps", file=sys.stderr)
        return 2
    plan_text = "\n".join("- " + s for s in steps)

    avail = get_availability()
    usable = bool(avail.get("usable"))

    if args.dry_run:
        target = "v4pro" if usable else "sonic"
        print(json.dumps({
            "dry_run": True, "target": target,
            "deep_steps": len(deep), "v4pro": avail,
        }))
        print("LAUNCHER_OK")
        return 0

    if usable:
        ask = ("Execute this plan, written by Sonic in Altair chat:\n"
               + plan_text)
        hid = sbos_common.handoff_enqueue(
            args.requested_by, args.kind, args.summary,
            context=("DeepSeek balance at launch: $%.2f (usable). "
                     "Launched from Altair chat via chat_work_launch."
                     % avail.get("usd", 0.0)),
            sonic_draft=plan_text, ask=ask)
        print("launched to DeepSeek V4 Pro (background): handoff #%s" % hid)
        print(json.dumps({"launched": "v4pro", "id": int(hid),
                          "summary": args.summary, "steps": len(steps)}))
        print("LAUNCHER_OK")
        return 0

    desc = ("Plan from Altair chat (DeepSeek not usable: %s).\n"
            "Execute in the background and record the result.\n\n%s"
            % (avail.get("reason", "unknown"), plan_text))
    tid = sbos_common.add_queue_task(
        args.summary, desc, source="altair-chat", priority=3)
    deep_id = None
    if deep:
        deep_text = "\n".join("- " + s for s in deep)
        deep_id = sbos_common.handoff_enqueue(
            args.requested_by, args.kind,
            args.summary + " (deep steps)",
            context=("Parked from Altair chat: DeepSeek not usable at "
                     "launch (%s). Runs when the balance returns."
                     % avail.get("reason", "unknown")),
            sonic_draft=deep_text,
            ask=("Execute only these deep-reasoning steps from the "
                 "Altair chat plan:\n" + deep_text))
    msg = "launched to Sonic background queue: task %s" % tid
    if deep_id:
        msg += "; deep steps parked for DeepSeek: handoff #%s" % deep_id
    print(msg)
    print(json.dumps({"launched": "sonic", "id": str(tid),
                      "deep_handoff_id": (int(deep_id) if deep_id else None),
                      "summary": args.summary, "steps": len(steps)}))
    print("LAUNCHER_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
