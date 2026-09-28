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
