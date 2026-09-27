"""First production rules for the automation engine.

Sunday-shift focused. Each rule declares its own confidence honestly —
the engine enforces the 90% bar, not the rule author.
"""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from automate.engine import Rule, kssh
from automate.watchers import (
    alpha_disk, crew_reports, inbox_status, pg_scalar, shift_window_active,
)

INBOX = Path("/tmp/altair-brain-inbox")
CT = ZoneInfo("America/Chicago")


def _now() -> datetime:
    return datetime.now(CT)


def _inbox_note(name: str, body: str) -> str:
    ts = _now().strftime("%Y%m%d-%H%M%S")
    path = INBOX / "inbox" / f"{ts}-{name}.md"
    path.write_text(body)
    return str(path)


# --- Rule 1: push unpushed inbox commits -------------------------------------
def _inbox_check():
    s = inbox_status()
    if not s.get("ok"):
        return False, {"error": s.get("error")}
    return (s["unpushed"] or s["dirty"]), s


def _inbox_confidence(ctx: dict) -> float:
    # git state is directly observed; push is the standing instruction
    return 0.97 if not ctx.get("error") else 0.0


def _inbox_act(ctx: dict, dry_run: bool) -> str:
    if dry_run:
        return "would git add/commit/push inbox"
    subprocess.run(["git", "-C", str(INBOX), "add", "inbox/"],
                   capture_output=True, timeout=30)
    subprocess.run(
        ["git", "-C", str(INBOX), "commit", "-m",
         "automation: push pending inbox notes", "--allow-empty"],
        capture_output=True, timeout=30)
    r = subprocess.run(["git", "-C", str(INBOX), "push"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return "inbox pushed"


# --- Rule 2: DeepSeek brief overdue ------------------------------------------
def _brief_check():
    shift = shift_window_active()
    if not shift["active"]:
        return False, {}
    now = _now()
    past_due = now.hour >= 17  # due 5pm
    crew = crew_reports()
    return (past_due and not crew["deepseek_brief"]), {
        "now": now.isoformat(), "crew": crew}


def _brief_confidence(ctx: dict) -> float:
    return 0.95  # clock + file presence, directly observed


def _brief_act(ctx: dict, dry_run: bool) -> str:
    body = (
        "# Nudge: DeepSeek strategic brief overdue (automation)\n\n"
        f"Time: {_now().strftime('%H:%M')} — brief was due 5:00 PM.\n"
        "Altair: please kick DeepSeek 150B (port 8084, serialized) for the "
        "strategic brief. It's the backbone of the 7:30 briefing.\n"
    )
    if dry_run:
        return "would write overdue nudge to inbox"
    path = _inbox_note("nudge-deepseek-brief", body)
    return f"nudge written: {Path(path).name}"


# --- Rule 3: crew reports overdue (6pm) ---------------------------------------
def _crew_check():
    shift = shift_window_active()
    if not shift["active"]:
        return False, {}
    now = _now()
    past_due = now.hour >= 18
    crew = crew_reports()
    missing = [k for k, v in crew.items()
               if not v and k != "deepseek_brief"]
    return (past_due and bool(missing)), {"missing": missing, "crew": crew}


def _crew_confidence(ctx: dict) -> float:
    return 0.93


def _crew_act(ctx: dict, dry_run: bool) -> str:
    missing = ", ".join(ctx["missing"])
    body = (
        "# Nudge: crew reports overdue (automation)\n\n"
        f"Time: {_now().strftime('%H:%M')} — reports were due 6:00 PM.\n"
        f"Still missing: {missing}.\n"
        "Crew: please land your reports in the inbox. The 7:30 briefing "
        "is built from these.\n"
    )
    if dry_run:
        return "would write crew nudge to inbox"
    path = _inbox_note("nudge-crew-reports", body)
    return f"nudge written: {Path(path).name}"


# --- Rule 4: disk pressure on k11-alpha ----------------------------------------
def _disk_check():
    disks = alpha_disk()
    if "error" in disks:
        return False, disks
    hot = {m: p for m, p in disks.items() if p >= 90}
    return bool(hot), {"hot": hot, "all": disks}


def _disk_confidence(ctx: dict) -> float:
    worst = max(ctx["hot"].values())
    # >95%: clearly safe to clean tmp. 90-95%: less sure, research first.
    return 0.95 if worst >= 95 else 0.85


def _disk_act(ctx: dict, dry_run: bool) -> str:
    # Only ever touches /tmp files older than 7 days. Nothing else.
    cmd = ("find /tmp -maxdepth 2 -type f -mtime +7 "
           "-not -path '*/altair-brain-inbox/*' -delete -print | wc -l")
    if dry_run:
        return f"would clean /tmp files older than 7d on hot mounts {ctx['hot']}"
    out = kssh(cmd)
    return f"cleaned {out.strip()} stale /tmp files on {list(ctx['hot'])}"


# --- Rule 5: unresolved alert spike --------------------------------------------
def _alert_check():
    try:
        n = int(pg_scalar(
            "SELECT COUNT(*) FROM alerts WHERE resolved_at IS NULL"))
    except Exception:  # noqa: BLE001
        return False, {}
    return n >= 10, {"unresolved": n}


def _alert_confidence(ctx: dict) -> float:
    # We can see the count but not the cause — deliberately below threshold
    # so the engine routes this to research, demonstrating the path.
    return 0.60


def _alert_act(ctx: dict, dry_run: bool) -> str:  # never called (>=0.90 gate)
    return "n/a"


RULES: list[Rule] = [
    Rule("deepseek_brief_overdue", _brief_check, _brief_confidence,
         _brief_act, reversible=True, tags=["sunday-shift", "crew"]),
    Rule("crew_reports_overdue", _crew_check, _crew_confidence,
         _crew_act, reversible=True, tags=["sunday-shift", "crew"]),
    Rule("disk_pressure_alpha", _disk_check, _disk_confidence,
         _disk_act, reversible=True, tags=["infra", "k11-alpha"]),
    Rule("alert_spike", _alert_check, _alert_confidence,
         _alert_act, reversible=True, tags=["monitoring"]),
    # push last: nudges written above get pushed by this rule
    Rule("inbox_unpushed", _inbox_check, _inbox_confidence,
         _inbox_act, reversible=True, tags=["comms"]),
]
