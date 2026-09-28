"""Live state watchers for the automation engine.

PURPOSE:
    Replace hard-coded assumptions with measured reality. Each watcher
    returns structured state; rules consume it. All reads are side-effect
    free.

WHY:
    capacity.py and ecosystem_state.py still carry hard-coded fleet data and
    unverified estimates, which makes their verdicts untrustworthy. These
    watchers are the migration path: every hard-coded number gets a watcher,
    and the old tools get rewired onto live data one section at a time.

CALLED BY:
    - tools/automate/rules.py (rule check functions)
    - tools/automate/run.py --snapshot (debugging)

NOTES:
    pg_query reads ecosystem_central on k11-alpha via kssh. queue_depths
    returns -1 (not 0) when a table is missing — unknown is not zero.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from automate.engine import kssh

INBOX = Path.home() / "workspace" / "altair-brain"


def pg_query(sql: str) -> list[list[str]]:
    """Read query against ecosystem_central on k11-alpha."""
    wrapped = ('psql -h localhost -U successbrian -d ecosystem_central '
               f'-t -A -F\'\\x1f\' -c "{sql}"')
    raw = kssh(wrapped)
    return [line.split("\x1f") for line in raw.strip().split("\n")
            if line.strip()]


def pg_scalar(sql: str, default: str = "0") -> str:
    rows = pg_query(sql)
    return rows[0][0] if rows and rows[0] else default


def queue_depths() -> dict:
    """How much work is waiting across the ecosystem queues."""
    def count(table: str, where: str = "") -> int:
        try:
            return int(pg_scalar(
                f"SELECT COUNT(*) FROM {table} {where}".strip()))
        except Exception:  # noqa: BLE001
            return -1  # -1 = unknown, not zero

    return {
        "agent_questions_queue": count("agent_questions_queue"),
        "approval_queue": count("approval_queue",
                                "WHERE status NOT IN ('approved','rejected')"),
        "ai_task_queue": count("ai_task_queue",
                               "WHERE status NOT IN ('done','cancelled')"),
        "alerts_unresolved": count("alerts",
                                   "WHERE resolved_at IS NULL"),
        "action_items_open": count("altair.action_items",
                                  "WHERE status NOT IN ('done','cancelled')"),
    }


def alpha_disk() -> dict:
    """Disk pressure on k11-alpha (the box that matters most)."""
    try:
        out = kssh("df -h / /tmp /var 2>/dev/null | awk 'NR>1 {print $6, $5}'")
        disks = {}
        for line in out.split("\n"):
            parts = line.split()
            if len(parts) == 2:
                disks[parts[0]] = int(parts[1].rstrip("%"))
        return disks
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def inbox_status() -> dict:
    """Is the altair-brain inbox clean and pushed?"""
    def git(*args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(INBOX), *args],
            capture_output=True, text=True, timeout=30)
        return out.stdout.strip()

    try:
        git("fetch", "--quiet")
        local = git("rev-parse", "HEAD")
        remote = git("rev-parse", "@{u}")
        dirty = bool(git("status", "--porcelain"))
        return {
            "ok": True,
            "unpushed": local != remote,
            "dirty": dirty,
            "local": local[:8],
            "remote": remote[:8],
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def shift_window_active() -> dict:
    """Are we inside the Sunday 3pm-7:30pm shift window?"""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/Chicago"))
    active = (now.weekday() == 6 and
              now.hour >= 15 and
              (now.hour < 19 or (now.hour == 19 and now.minute < 30)))
    return {"active": active, "now": now.isoformat()}


def crew_reports() -> dict:
    """Which crew reports have landed in today's inbox?"""
    today = datetime.now().strftime("%Y%m%d")
    found: dict[str, bool] = {
        "deepseek_brief": False, "altair": False, "lyra": False,
        "morpheus": False, "penny": False,
    }
    try:
        names = [p.name.lower() for p in (INBOX / "inbox").glob(f"{today}*")]
        blob = " ".join(names)
        for key in found:
            found[key] = key in blob
    except Exception:  # noqa: BLE001
        pass
    return found


def snapshot() -> dict:
    """One call, everything the rules need."""
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "queues": queue_depths(),
        "disk": alpha_disk(),
        "inbox": inbox_status(),
        "shift": shift_window_active(),
        "crew": crew_reports(),
    }
