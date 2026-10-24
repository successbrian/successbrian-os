#!/usr/bin/env python3
"""Retry the Sonic CFO test call until Sonic is free enough to answer.

Brian, 2026-10-24: "keep trying as sonic becomes free to run it."
The first CFO test timed out at 240s because Sonic was saturated by a
long Hermes job (23k prompt, 65k max tokens). This loop retries the
same small 2-ruling CFO test, with a 600s call timeout, every 5 minutes,
until it succeeds or 48 attempts (~4 hours) pass. TEST ONLY: it writes
only to ~/logs/wave2-sonic-test.log, never to state, sink, Atlas, or
official minutes. The real wave-2 worker cron (every 30 min) separately
keeps retrying real batches the same way.
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/successbrian/successbrian-os")
sys.path.insert(0, "/home/successbrian/successbrian-os/board")
import wave2_worker
from board.harness.worker import parse_calls

wave2_worker.TIMEOUT_S = 600
LOG = "/home/successbrian/logs/wave2-sonic-test.log"
BATCH = [
    {"seat": "Chief Ecosystem Build Officer", "item_key": "task:board-bigger-packets",
     "call": "Approve the expansion of ruling packets to include comprehensive details, stakes, connections, and evidence",
     "rationale": "Bigger packets improve ruling quality"},
    {"seat": "Chief Trading Desk Officer", "item_key": "task:board-clerk-box",
     "call": "Approve the purchase of the dedicated mini for ecosystem decisions",
     "rationale": "A dedicated mini curates decisions all day"},
]


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def slots_processing():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11439/slots", timeout=10) as r:
            slots = json.loads(r.read().decode())
        return sum(1 for s in slots if s.get("is_processing")), len(slots)
    except Exception as e:
        return f"slots check failed: {e}", 0


for attempt in range(1, 49):
    proc, total = slots_processing()
    log(f"attempt {attempt}: Sonic slots processing={proc}/{total}")
    try:
        raw = wave2_worker.call_sonic(BATCH)
        calls = parse_calls(raw)
        log(f"SUCCESS attempt {attempt}: {calls}")
        log(f"RAW head: {raw[:1000]}")
        break
    except Exception as e:
        log(f"attempt {attempt} failed: {e}; retrying in 300s")
        if attempt < 48:
            time.sleep(300)
else:
    log("GAVE UP after 48 attempts (~4 hours); real wave-2 cron keeps retrying real batches")
