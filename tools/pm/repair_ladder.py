#!/usr/bin/env python3
"""Repair ladder — slice 3 of the coded-loop upgrade (SBOS main PM).

Implements Brian's self-repair ladder at the worker layer:
  workers fail -> the ladder restarts them -> only what restart cannot
  fix becomes a PM step, and repeat failures escalate to held_brian.

Each pass:
  1. Checks every registered worker's health endpoint.
  2. A dead worker with a known launch command is restarted (Lyra's job:
     restart first, verify recovery, report — not just alert).
  3. Outcomes are written to the PM decision stream (origin 'system');
     a worker that will not come back becomes a 'repair' step, and after
     3 consecutive failed passes an escalation step held for Brian.
  4. Intake: pressing sources become PM steps (deduped) — unread
     critical/high messages on the knowledge bridge, a stale Altair
     context bundle. This is the consumer the bus never had.

Deterministic code only; no model calls.
"""
import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

HOME = os.path.expanduser("~")
LLAMA = os.path.join(HOME, "llama.cpp/build/bin/llama-server")
MODELS = os.path.join(HOME, "models")

WORKERS = [
    {"name": "sonic", "port": 11439, "health": "http://127.0.0.1:11439/health",
     "argv": [LLAMA, "--model", f"{MODELS}/Qwen3.6-35B-A3B-UD-Q6_K.gguf",
              "--alias", "qwen-a3b", "--port", "11439", "--ctx-size", "98304",
              "--n-gpu-layers", "999", "--flash-attn", "on",
              "--reasoning-budget", "256", "--cache-type-k", "q8_0",
              "--cache-type-v", "q8_0", "--batch-size", "2048"]},
    {"name": "morpheus", "port": 11437, "health": "http://127.0.0.1:11437/health",
     "argv": [LLAMA, "--model",
              f"{MODELS}/qwen2.5-14b-instruct-q6_k-00001-of-00004.gguf",
              "--alias", "morpheus", "--port", "11437", "--ctx-size", "32768",
              "--n-gpu-layers", "0", "--threads", "6", "--flash-attn", "on",
              "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
              "--batch-size", "4096"]},
    {"name": "penny", "port": 11438, "health": "http://127.0.0.1:11438/health",
     "argv": [LLAMA, "--model",
              f"{MODELS}/qwen2.5-7b-instruct-q6_k-00001-of-00002.gguf",
              "--alias", "penny", "--port", "11438", "--ctx-size", "32768",
              "--n-gpu-layers", "0", "--threads", "8"]},
]

ESCALATE_AFTER = 3
BUNDLE = os.path.join(HOME, ".hermes/profiles/altair/150b_context.md")


def healthy(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def find_pid(port):
    out = subprocess.run(["pgrep", "-f", f"llama-server.*--port {port}"],
                         capture_output=True, text=True).stdout.strip()
    return int(out.splitlines()[0]) if out else None


def restart(worker):
    pid = find_pid(worker["port"])
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(0.5)
            if find_pid(worker["port"]) is None:
                break
        else:
            os.kill(pid, signal.SIGKILL)
    log = open(os.path.join(HOME, "logs", f"{worker['name']}-server.log"), "ab")
    subprocess.Popen(worker["argv"], stdout=log, stderr=log,
                     start_new_session=True)
    for _ in range(30):
        time.sleep(2)
        if healthy(worker["health"], timeout=2):
            return True
    return healthy(worker["health"], timeout=2)


def ensure_schema(cur):
    cur.execute(
        """CREATE TABLE IF NOT EXISTS successbrian_os.pm_ladder_state (
             worker TEXT PRIMARY KEY, failures INT NOT NULL DEFAULT 0,
             last_status TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


def bump_state(cur, worker, ok):
    cur.execute(
        """INSERT INTO successbrian_os.pm_ladder_state (worker, failures, last_status)
           VALUES (%s, %s, %s)
           ON CONFLICT (worker) DO UPDATE
             SET failures = CASE WHEN %s THEN 0
                                 ELSE successbrian_os.pm_ladder_state.failures + 1 END,
                 last_status = %s, updated_at = now()
           RETURNING failures""",
        (worker, 0 if ok else 1, "ok" if ok else "down", ok, "ok" if ok else "down"))
    row = cur.fetchone()
    return row["failures"] if isinstance(row, dict) else row[0]


def open_step_exists(cur, key):
    cur.execute(
        """SELECT 1 FROM successbrian_os.pm_steps
            WHERE step_key=%s AND status IN ('queued','running','held_brian')""",
        (key,))
    return cur.fetchone() is not None


def ensure_step(cur, key, title, kind, priority, payload=None):
    if not open_step_exists(cur, key):
        pm_core.add_step(cur, key, title, kind=kind, origin="system",
                         priority=priority, payload=payload or {})
        return True
    return False


def check_worker(cur, worker, do_restart=True):
    name = worker["name"]
    if healthy(worker["health"]):
        bump_state(cur, name, True)
        return f"{name}: ok"
    failures = bump_state(cur, name, False)
    if not do_restart:
        return f"{name}: DOWN (check-only, failures={failures})"
    ok = restart(worker)
    if ok:
        bump_state(cur, name, True)
        pm_core.decide(cur, "repair-ladder",
                       f"Worker {name} was down; restarted it; health verified OK",
                       origin="system")
        return f"{name}: DOWN -> restarted -> ok"
    pm_core.decide(cur, "repair-ladder",
                   f"Worker {name} down and restart failed (pass failures={failures})",
                   origin="system")
    ensure_step(cur, f"repair-{name}",
                f"Worker {name} is down and the ladder could not restart it",
                kind="repair", priority=85)
    if failures >= ESCALATE_AFTER:
        cur.execute(
            """UPDATE successbrian_os.pm_steps SET status='held_brian'
                WHERE step_key=%s AND status='queued'""", (f"repair-{name}",))
    return f"{name}: DOWN, restart FAILED (failures={failures})"


def intake(cur):
    notes = []
    cur.execute(
        """SELECT count(*) AS n FROM altair.knowledge_bridge
            WHERE read_at IS NULL AND urgency IN ('critical','high')""")
    row = cur.fetchone()
    n = row["n"] if isinstance(row, dict) else row[0]
    if n:
        if ensure_step(cur, "intake-bridge-criticals",
                       f"Unread critical/high messages on the knowledge bridge: {n}",
                       kind="review", priority=85, payload={"unread_critical": n}):
            notes.append(f"intake: filed bridge-criticals step ({n} unread)")
    if os.path.exists(BUNDLE):
        age_h = (time.time() - os.path.getmtime(BUNDLE)) / 3600
        if age_h > 48:
            if ensure_step(cur, "intake-stale-context-bundle",
                           f"Altair context bundle stale ({age_h:.0f}h old, since Oct 18)",
                           kind="repair", priority=60, payload={"age_hours": round(age_h)}):
                notes.append("intake: filed stale-context-bundle step")
    return notes


def run_pass(do_restart=True):
    c = pm_core.conn()
    cur = c.cursor()
    ensure_schema(cur)
    lines = [check_worker(cur, w, do_restart=do_restart) for w in WORKERS]
    lines += intake(cur)
    c.commit()
    c.close()
    for line in lines:
        print(line)
    return lines


def selftest():
    dummy = {"name": "ladder-dummy", "port": 18991,
             "health": "http://127.0.0.1:18991/",
             "argv": ["python3", "-m", "http.server", "18991",
                      "--bind", "127.0.0.1"]}
    proc = subprocess.Popen(dummy["argv"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        for _ in range(15):
            if healthy(dummy["health"], timeout=1):
                break
            time.sleep(0.4)
        assert healthy(dummy["health"], timeout=1), "dummy did not start"
        proc.terminate()
        proc.wait(timeout=5)
        assert not healthy(dummy["health"], timeout=1), "dummy still up"
        c = pm_core.conn()
        cur = c.cursor()
        ensure_schema(cur)
        line = check_worker(cur, dummy, do_restart=True)
        c.commit()
        assert "restarted -> ok" in line, line
        print("PASS ladder detected dead worker, restarted it, health verified")
        cur.execute("DELETE FROM successbrian_os.pm_ladder_state WHERE worker='ladder-dummy'")
        cur.execute("DELETE FROM successbrian_os.pm_decisions WHERE decision LIKE '%%ladder-dummy%%' OR decision LIKE '%%Worker ladder-dummy%%'")
        c.commit()
        c.close()
        print("PASS cleanup — repair ladder selftest green")
    finally:
        subprocess.run(["pkill", "-f", "http.server 18991"],
                       capture_output=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="SBOS repair ladder (slice 3)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--check-only", action="store_true",
                    help="report worker health without restarting")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if args.once or args.check_only:
        run_pass(do_restart=not args.check_only)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
