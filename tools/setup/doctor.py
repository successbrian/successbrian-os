#!/usr/bin/env python3
"""SuccessBrian OS: boot check — verifies the install tier by tier.

PURPOSE:
    `python3 tools/setup/doctor.py` answers "is this thing working?" with
    facts. Checks Python, repo layout, private config, the focus coach
    smoke test, and Postgres reachability — then reports Tier 1/2/3 status
    with exact reasons for anything missing. The first command a new user
    runs when something doesn't work, and the last step of init.py.

WHY:
    Brian 2026-10-04: onboarding without verification is a hope, not a
    boot sequence. Doctor turns "it doesn't work" into a named missing
    piece, which is the difference between a user who fixes it in a minute
    and a user who uninstalls.

CALLED BY:
    - Humans: python3 tools/setup/doctor.py (after init, or any time)
    - Nothing automated; it is a diagnostic, not a monitor.

NOTES:
    - Read-only: checks, never changes. Never prints secrets — it reports
      whether PGPASSWORD / ~/.pgpass exist, never their contents.
    - Postgres check is a TCP connect to host:port (default localhost:5432),
      not an authenticated login: "reachable" vs "not reachable" is the
      fact that matters at boot time.
"""

import json
import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))  # tools/setup/ -> repo root

PASS, FAIL, WARN = "READY", "MISSING", "CHECK"


def check_python():
    ok = sys.version_info >= (3, 10)
    return (PASS if ok else FAIL,
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            + (" (>= 3.10)" if ok else " — need 3.10+"))


def check_layout():
    need = ["tools/focus/focus.py", "tools/focus/user_focus.example.json",
            "tools/ventures", "tools/audience", "README.md", "LICENSE"]
    missing = [p for p in need if not os.path.exists(os.path.join(REPO, p))]
    if missing:
        return FAIL, "missing: " + ", ".join(missing)
    return PASS, "repo layout complete"


def check_registry():
    path = os.path.join(REPO, "tools", "focus", "user_focus.json")
    if not os.path.exists(path):
        return FAIL, "no user_focus.json — run python3 tools/setup/init.py first"
    try:
        data = json.load(open(path))
        n = len(data.get("streams", []))
        return PASS, f"registry present ({n} {'stream' if n == 1 else 'streams'})"
    except (json.JSONDecodeError, OSError) as e:
        return FAIL, f"user_focus.json unreadable: {e}"


def check_focus_smoke():
    fp = os.path.join(REPO, "tools", "focus", "focus.py")
    try:
        r = subprocess.run([sys.executable, fp, "review"],
                           capture_output=True, text=True, timeout=30,
                           cwd=os.path.join(REPO, "tools", "focus"))
    except Exception as e:  # noqa: BLE001 — diagnostic must not crash
        return FAIL, f"focus.py did not run: {e}"
    if r.returncode != 0:
        return FAIL, f"focus.py review exited {r.returncode}: {r.stderr.strip()[:120]}"
    return PASS, "focus coach review runs clean"


def tcp_reachable(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_postgres():
    host = os.environ.get("PGHOST", "localhost")
    try:
        port = int(os.environ.get("PGPORT", "5432"))
    except (TypeError, ValueError):
        port = 5432
    if not tcp_reachable(host, port):
        return FAIL, f"no Postgres on {host}:{port} — Tier 2 modules (ventures, audience) will not run"
    creds = bool(os.environ.get("PGPASSWORD")) or os.path.exists(
        os.path.expanduser("~/.pgpass"))
    if creds:
        return PASS, f"Postgres reachable at {host}:{port} + credentials present"
    return WARN, (f"Postgres reachable at {host}:{port} but no PGPASSWORD or ~/.pgpass found — "
                  "modules will fail to authenticate")


def check_git():
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return PASS, r.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return WARN, "git not found — you can still run everything, but not pull updates"


def main():
    print("=== SuccessBrian OS — boot check ===\n")
    results = [
        ("Python", *check_python()),
        ("Repo layout", *check_layout()),
        ("Your registry", *check_registry()),
        ("Focus coach", *check_focus_smoke()),
        ("Postgres (Tier 2)", *check_postgres()),
        ("Git (updates)", *check_git()),
    ]
    for name, status, detail in results:
        print(f"[{status:>7}] {name}: {detail}")

    by_status = {}
    for _, s, _ in results:
        by_status[s] = by_status.get(s, 0) + 1
    print()
    tier1 = all(s == PASS for n, s, _ in results if n in
                ("Python", "Repo layout", "Your registry", "Focus coach"))
    print(f"Tier 1 (runs anywhere): {'READY — the focus coach is usable now' if tier1 else 'NOT READY — fix MISSING items above'}")
    pg = next(s for n, s, _ in results if n == "Postgres (Tier 2)")
    print(f"Tier 2 (needs Postgres): {'READY' if pg == PASS else 'NOT READY — ' + next(d for n, s, d in results if n == 'Postgres (Tier 2)')}")
    print("Tier 3 (your own infra): MANUAL — adapt connectors per module docstrings.")
    return 0 if tier1 else 1


if __name__ == "__main__":
    sys.exit(main())
