#!/usr/bin/env python3
"""
PURPOSE:
    Shared constants for SuccessBrian OS tools: the durable paths and
    helpers every tool needs, defined once.

WHY:
    Five tools each hard-coded ~/workspace/bin/kssh and three inbox roots
    were in play at once (/tmp/altair-brain-inbox vs ~/workspace/altair-brain),
    which is how the Sunday shift silently wrote to a dead /tmp dir for
    weeks. One definition, imported everywhere, so a path change happens in
    one place.

CALLED BY:
    - tools/sunday_shift.py (INBOX, git_push)
    - (migrate: automate/rules.py, automate/watchers.py, capacity.py,
      model_tiers.py, decision_sync/sync.py, second_brain.py, v4pro_balance.py)

NOTES:
    INBOX must be the durable git clone, not /tmp (dead on this VM since
    before 2026-09-27 — see shift log). kssh() shells out to ~/workspace/bin/kssh;
    when that helper moves into the repo, update KSSH here only.
"""

import os
import subprocess
from pathlib import Path

# The one true inbox: durable clone the automation rules read from.
INBOX = Path.home() / "workspace" / "altair-brain" / "inbox"

# SSH-to-k11-alpha helper (tailnet CONNECT proxy).
KSSH = Path.home() / "workspace" / "bin" / "kssh"


def kssh(cmd: str, timeout: int = 60) -> str:
    """Run a command on k11-alpha. Raises RuntimeError on failure."""
    out = subprocess.run([str(KSSH), cmd], capture_output=True,
                         text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    return out.stdout.strip()


def git_push(repo: Path, message: str, paths: list[str]) -> bool:
    """git add/commit/push in repo. Returns False (and logs) on any failure.

    Unlike the old silent pattern (capture_output + unchecked returncode),
    a failed push is LOUD — a lost inbox push is a lost briefing.
    """
    try:
        for step in ([["git", "add", *paths]],
                     [["git", "commit", "-m", message]],
                     [["git", "push"]]):
            r = subprocess.run(step, cwd=repo, capture_output=True,
                               text=True, timeout=90)
            if r.returncode != 0:
                # "nothing to commit" is fine — not a failure.
                if "nothing to commit" in (r.stdout + r.stderr):
                    continue
                print(f"git_push FAILED at {' '.join(step)}: "
                      f"{(r.stderr or r.stdout)[-400:]}")
                return False
        print(f"git_push OK: {repo} — {message}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"git_push FAILED: {e}")
        return False


def pg_password(host="localhost", dbname="ecosystem_central",
                user="successbrian"):
    """Postgres password from the sanctioned stores only: PGPASSWORD env,
    then ~/.pgpass. Never hardcoded — a literal password in this public
    repo is a secret leak, and it breaks the per-user-database model where
    every user has their own credentials.

    WHY: eight tools hard-coded "postgres" as the DB password (found
    2026-10-04 during the per-user-database spec). They now call this.
    Raises RuntimeError (loud) when no credential is found.
    """
    env_pw = os.environ.get("PGPASSWORD")
    if env_pw:
        return env_pw
    pgpass = Path.home() / ".pgpass"
    try:
        with open(pgpass) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) >= 5:
                    h, d, u = parts[0], parts[2], parts[3]
                    pw = ":".join(parts[4:])
                    if h in (host, "*") and d in (dbname, "*") \
                            and u in (user, "*"):
                        return pw
    except FileNotFoundError:
        pass
    raise RuntimeError(
        "Postgres password not found: set PGPASSWORD or add a "
        f"{host}:5432:{dbname}:{user}:*** entry to ~/.pgpass")
