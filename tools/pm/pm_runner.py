#!/usr/bin/env python3
"""SBOS main PM runner — slice 2 of the coded-loop upgrade.

The scheduler half of the control plane. On each pass it:
  1. REAPS stale runner steps: a step left 'running' by a dead runner
     (heartbeat older than the stale limit) goes back to 'queued', and the
     requeue is written to the decision stream (origin 'system').
  2. CLAIMS ready steps of executable kinds (dependency-gated, effective
     priority first — see pm_core.claim) and runs them CONCURRENTLY.

Slice-2 executor registry: kind 'command' only — payload {"cmd": [...],
"timeout_s": 600}. The command runs as-is (argv list, no shell); exit 0 =
done, anything else = failed, with stdout/stderr tails stored in the
step's result. Other kinds (build, research, ...) are claimed by agents
and people through pm_core's CLI, not by this runner — the runner never
touches kinds it has no executor for.

Deterministic code only: no model calls, so the runner is safe to run on
a short cron cadence inside the machine's quiet windows.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

EXECUTABLE_KINDS = ["command"]
STALE_S = int(os.environ.get("PM_RUNNER_STALE_S", "1800"))
TAIL = 2000


def reap_stale(cur, stale_s=STALE_S):
    cur.execute(
        """UPDATE successbrian_os.pm_steps
              SET status='queued', actor=NULL, started_at=NULL, updated_at=now()
            WHERE status='running' AND actor LIKE 'pm-runner%%'
              AND heartbeat_at < now() - (%s || ' seconds')::interval
            RETURNING step_key""", (str(stale_s),))
    keys = [r[0] if not isinstance(r, dict) else r["step_key"] for r in cur.fetchall()]
    for key in keys:
        pm_core.decide(cur, "pm-runner", f"Requeued stale step {key}",
                       step_key=key, origin="system")
    return keys


def run_one(row):
    """Execute one claimed step on its own connection. Returns a summary line."""
    _sid, key, _title, _kind, _pri, _origin = row
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute("SELECT payload FROM successbrian_os.pm_steps WHERE step_key=%s", (key,))
    payload = cur.fetchone()[0] or {}
    cmd = payload.get("cmd")
    timeout_s = int(payload.get("timeout_s", 600))
    if not cmd or not isinstance(cmd, list):
        pm_core.finish(cur, key, "failed", {"why": "command step without payload.cmd list"})
        c.commit()
        c.close()
        return f"{key}: FAILED (no cmd)"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        result = {"exit": proc.returncode,
                  "stdout_tail": (proc.stdout or "")[-TAIL:],
                  "stderr_tail": (proc.stderr or "")[-TAIL:]}
        status = "done" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        result = {"why": f"timeout after {timeout_s}s"}
        status = "failed"
    pm_core.finish(cur, key, status, result)
    c.commit()
    c.close()
    return f"{key}: {status.upper()} (exit {result.get('exit', '-')})"


def run_once(limit=4, actor=None):
    actor = actor or f"pm-runner-{os.getpid() % 10000}"
    c = pm_core.conn()
    cur = c.cursor()
    reaped = reap_stale(cur)
    c.commit()
    for key in reaped:
        print(f"reaped stale step -> requeued: {key}")
    rows = pm_core.claim(cur, actor, limit=limit,
                         location=socket.gethostname(), kinds=EXECUTABLE_KINDS)
    c.commit()
    c.close()
    if not rows:
        print("nothing executable ready")
        return []
    lines = []
    with ThreadPoolExecutor(max_workers=len(rows)) as pool:
        for line in pool.map(run_one, rows):
            lines.append(line)
            print(line)
    return lines


def selftest():
    tag = f"pm-runner-selftest-{int(time.time())}"
    c = pm_core.conn()
    cur = c.cursor()
    pm_core.init_schema(cur)
    pm_core.add_step(cur, f"{tag}-ok", "runner selftest ok", kind="command",
                     priority=95, payload={"cmd": ["python3", "-c",
                                                  "print('pm-runner-ok')"]})
    pm_core.add_step(cur, f"{tag}-bad", "runner selftest bad", kind="command",
                     priority=94, payload={"cmd": ["python3", "-c",
                                                   "import sys; sys.exit(3)"]})
    c.commit()
    c.close()
    lines = run_once(limit=8)
    joined = "\n".join(lines)
    assert f"{tag}-ok: DONE" in joined, f"ok step not done: {lines}"
    assert f"{tag}-bad: FAILED" in joined, f"bad step not failed: {lines}"
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute("SELECT result FROM successbrian_os.pm_steps WHERE step_key=%s",
                (f"{tag}-ok",))
    result = cur.fetchone()[0]
    assert "pm-runner-ok" in (result or {}).get("stdout_tail", ""), \
        f"stdout not captured: {result}"
    print("PASS runner executed command step, captured stdout, marked done")
    print("PASS failing command marked failed with its exit code")
    cur.execute("DELETE FROM successbrian_os.pm_steps WHERE step_key LIKE %s",
                (tag + "-%",))
    c.commit()
    c.close()
    print("PASS cleanup — runner selftest green")


def main(argv=None):
    ap = argparse.ArgumentParser(description="SBOS main PM runner (slice 2)")
    ap.add_argument("--once", action="store_true", help="single pass, then exit")
    ap.add_argument("--limit", type=int, default=4)
    ap.add_argument("--actor")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if args.once:
        run_once(limit=args.limit, actor=args.actor)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
