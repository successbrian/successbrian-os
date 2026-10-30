#!/usr/bin/env python3
"""
sonic_token_collector.py — Sonic's ACTUAL token production, from its
own server journal (no --metrics flag, no restart needed).

Brian 2026-10-29: track actual daily token/usage stats; figure out a
baseline production capacity; judge "need more Sonic" on something
highly accurate. llama-server logs a final print_timing block for every
completed request (prompt eval time / eval time with token counts) —
that is ground truth for TOTAL production across every consumer of
chat-Alpha Sonic (:11439): Altair chat, the task worker, heartbeat,
council, extraction. The pattern is proven in-ecosystem:
dealsdesk/token_collector.py did the same for Morpheus/Penny into
telemetry.token_daily until 2026-10-26.

Method: re-read the journal window (default last 50 hours; --hours N),
parse final blocks, dedupe by (slot, task), aggregate per hour into
successbrian_os.sonic_token_hourly with UPSERT — re-runs are
idempotent and self-healing. busy_slot_seconds sums prompt+eval time
across slots (max meaningful = slots * 3600 per hour).

Capacity math lives in chat_brief.py's CAPACITY section: demonstrated
ceiling = busiest hour's total tokens x 24; utilization = a day's
total / ceiling. Demand in this ecosystem is effectively unlimited
(deep backlog), so production vs ceiling + backlog drain is the
honest need signal (Brian 2026-10-29).
"""

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402

UNIT = "qwen-a3b.service"
INSTANCE = "chat-alpha:11439"

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):\d{2}:\d{2}([+-]\d{2}:\d{2})")
PROMPT_RE = re.compile(
    r"slot print_timing: id +(\d+) \| task +(-?\d+) \| "
    r"prompt eval time =\s*([\d.]+) ms / +(\d+) tokens")
GEN_RE = re.compile(
    r"slot print_timing: id +(\d+) \| task +(-?\d+) \| "
    r"+eval time =\s*([\d.]+) ms / +(\d+) tokens")

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.sonic_token_hourly (
    hour timestamptz NOT NULL,
    instance text NOT NULL DEFAULT 'chat-alpha:11439',
    requests int NOT NULL DEFAULT 0,
    prompt_tokens bigint NOT NULL DEFAULT 0,
    generated_tokens bigint NOT NULL DEFAULT 0,
    busy_slot_seconds numeric NOT NULL DEFAULT 0,
    PRIMARY KEY (hour, instance)
);
"""


def collect(hours):
    out = subprocess.run(
        ["journalctl", "-u", UNIT, "--since", "-%d hours" % hours,
         "--no-pager", "-o", "short-iso"],
        capture_output=True, text=True, timeout=600)
    tasks = {}  # (slot, task) -> dict of final-block values
    for line in out.stdout.splitlines():
        m = TS_RE.match(line)
        if not m:
            continue
        hour = "%sT%s:00:00%s" % (m.group(1), m.group(2), m.group(3))
        pm = PROMPT_RE.search(line)
        if pm:
            key = (pm.group(1), pm.group(2))
            t = tasks.setdefault(key, {"hour": hour})
            t["hour"] = hour
            t["prompt_ms"] = float(pm.group(3))
            t["prompt_tokens"] = int(pm.group(4))
            continue
        gm = GEN_RE.search(line)
        if gm:
            key = (gm.group(1), gm.group(2))
            t = tasks.setdefault(key, {"hour": hour})
            t["hour"] = hour
            t["gen_ms"] = float(gm.group(3))
            t["gen_tokens"] = int(gm.group(4))
    buckets = defaultdict(lambda: {"requests": 0, "prompt": 0,
                                   "gen": 0, "busy_s": 0.0})
    for t in tasks.values():
        b = buckets[t["hour"]]
        b["prompt"] += t.get("prompt_tokens", 0)
        if "gen_tokens" in t:
            b["requests"] += 1
            b["gen"] += t["gen_tokens"]
        b["busy_s"] += (t.get("prompt_ms", 0.0)
                        + t.get("gen_ms", 0.0)) / 1000.0
    return buckets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=50)
    args = ap.parse_args()
    sbos_common.pg_exec(DDL)
    buckets = collect(args.hours)
    for hour, b in sorted(buckets.items()):
        sbos_common.pg_exec(
            """INSERT INTO successbrian_os.sonic_token_hourly
                 (hour, instance, requests, prompt_tokens,
                  generated_tokens, busy_slot_seconds)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (hour, instance) DO UPDATE SET
                 requests = EXCLUDED.requests,
                 prompt_tokens = EXCLUDED.prompt_tokens,
                 generated_tokens = EXCLUDED.generated_tokens,
                 busy_slot_seconds = EXCLUDED.busy_slot_seconds""",
            (hour, INSTANCE, b["requests"], b["prompt"], b["gen"],
             round(b["busy_s"], 1)))
    print("sonic_token_collector: %d hour-buckets upserted (window %dh)"
          % (len(buckets), args.hours))
    return 0


if __name__ == "__main__":
    sys.exit(main())
