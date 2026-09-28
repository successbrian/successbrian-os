"""Production rules for the automation engine.

PURPOSE:
    The first set of codified 90% decisions: inbox pushes, crew deadline
    nudges, disk pressure cleanup, alert triage, and V4 Pro credit routing.

WHY:
    These were the highest-frequency judgment calls in the Sunday shift —
    the same decisions, made the same way, every week. Codifying them frees
    the heartbeat workers for judgment that actually needs judgment.

CALLED BY:
    - tools/automate/engine.py run_rules()

NOTES:
    Each rule declares its own confidence honestly; the ENGINE enforces the
    90% bar, not the rule author. The alert_spike rule deliberately returns
    0.60 — we can see the count but not the cause, so it must route to
    research, never act. disk_pressure only touches /tmp files older than 7
    days; it never deletes anything else. Nudge rules run BEFORE
    inbox_unpushed so their notes get pushed in the same pass.
"""
from __future__ import annotations

import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from automate.engine import Rule, kssh
from automate.watchers import (
    alpha_disk, crew_reports, inbox_status, pg_scalar, shift_window_active,
)

INBOX = Path.home() / "workspace" / "altair-brain"
CT = ZoneInfo("America/Chicago")


def _now() -> datetime:
    return datetime.now(CT)


def _inbox_note(name: str, body: str) -> str:
    ts = _now().strftime("%Y%m%d-%H%M%S")
    inbox_dir = INBOX / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)  # fresh checkouts lack it
    path = inbox_dir / f"{ts}-{name}.md"
    path.write_text(body)
    return str(path)


def _nudge_live(slug: str) -> bool:
    """True if a nudge with this slug is already in today's inbox.

    Overdue nudges fire once per shift per item — re-writing the same
    nudge every 15-minute heartbeat (2026-09-27: two identical
    nudge-deepseek-brief notes 15 min apart) is noise with no new
    information. The conductor's shift-log flags keep the overdue
    visible; the rule stays quiet once the nudge is live.
    """
    today = _now().strftime("%Y%m%d")
    return any((INBOX / "inbox").glob(f"{today}-*-{slug}.md"))


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
    already_nudged = _nudge_live("nudge-deepseek-brief")
    return (past_due and not crew["deepseek_brief"] and not already_nudged), {
        "now": now.isoformat(), "crew": crew, "already_nudged": already_nudged}


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
    already_nudged = _nudge_live("nudge-crew-reports")
    return (past_due and bool(missing) and not already_nudged), {
        "missing": missing, "crew": crew, "already_nudged": already_nudged}


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
    # (Old exclusion for */altair-brain-inbox/* removed 2026-09-28: that path
    # exists on neither this VM nor k11-alpha; the inbox lives in the durable
    # ~/workspace/altair-brain clone, not /tmp.)
    cmd = ("find /tmp -maxdepth 2 -type f -mtime +7 -delete -print | wc -l")
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


# --- Rule 6: v4pro credits available -> route hard tasks to cloud ------------
_V4PRO_STATE = Path(__file__).parent / "state" / "v4pro-announced.json"


def _v4pro_check():
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from model_tiers import get_tiers
    tiers = get_tiers()
    available = tiers["v4pro_cloud"]["available"]
    last = False
    if _V4PRO_STATE.exists():
        try:
            last = json.loads(_V4PRO_STATE.read_text()).get("announced", False)
        except Exception:  # noqa: BLE001
            pass
    # Fire only on the false->true edge (announce once per credit window),
    # or on true->false (stand down).
    if available and not last:
        return True, {"transition": "credits_available", "tiers": tiers}
    if not available and last:
        return True, {"transition": "credits_exhausted", "tiers": tiers}
    return False, {}


def _v4pro_confidence(ctx: dict) -> float:
    return 0.96  # flag + port probes, directly observed


def _v4pro_act(ctx: dict, dry_run: bool) -> str:
    import json as _json
    transition = ctx["transition"]
    _V4PRO_STATE.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return f"would announce v4pro transition: {transition}"
    _V4PRO_STATE.write_text(_json.dumps({
        "announced": transition == "credits_available",
        "at": _now().isoformat(),
    }))
    if transition == "credits_available":
        body = (
            "# V4 Pro credits available — route hard tasks to cloud (automation)\n\n"
            f"Time: {_now().strftime('%Y-%m-%d %H:%M')}.\n"
            "DeepSeek V4 Pro (cloud top tier) has credits. Until they run dry:\n"
            "- Hard tasks (strategy, hard coding, cross-system reasoning) go "
            "to V4 Pro via AnythingLLM deep research, NOT the local 150B.\n"
            "- 150B stays on medium work; Penny keeps the small fast jobs.\n"
            "When credits exhaust, flip the flag: "
            "`python3 tools/model_tiers.py --v4pro exhausted`.\n"
        )
        path = _inbox_note("v4pro-credits-available", body)
        return f"announced, note: {Path(path).name}"
    return "stood down: hard tasks back to local 150B (flag flipped)"


# --- Rule 7: v4pro balance check (hourly, keeps the credit flag honest) -----
_V4PRO_BAL_STATE = Path(__file__).parent / "state" / "v4pro-balance.json"


def _bal_check():
    last = 0.0
    if _V4PRO_BAL_STATE.exists():
        try:
            ts = json.loads(_V4PRO_BAL_STATE.read_text()).get("checked_at")
            last = datetime.fromisoformat(ts).timestamp()
        except Exception:  # noqa: BLE001
            pass
    import time
    if time.time() - last < 3600:
        return False, {"throttled": True}
    return True, {}


def _bal_confidence(ctx: dict) -> float:
    return 0.97  # API response is ground truth


def _bal_act(ctx: dict, dry_run: bool) -> str:
    if dry_run:
        return "would query DeepSeek balance API"
    import subprocess as _sp
    r = _sp.run([sys.executable, str(Path(__file__).parent.parent /
                                      "v4pro_balance.py")],
                capture_output=True, text=True, timeout=60)
    try:
        result = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        raise RuntimeError(f"balance check failed: {r.stderr[:200]}")
    # Stamp the check so the hourly throttle in _bal_check engages.
    _V4PRO_BAL_STATE.parent.mkdir(parents=True, exist_ok=True)
    _V4PRO_BAL_STATE.write_text(
        json.dumps({"checked_at": _now().isoformat(),
                    "result": result.get("error") or result.get("usd")}))
    if not result.get("ok"):
        # No key yet (or API down) — not a failure of the ecosystem.
        # Record once to the brain so we stop wondering, then stay quiet.
        return f"skipped: {result.get('error')}"
    return (f"balance ${result['usd']:.2f} -> "
            f"v4pro {'AVAILABLE' if result['available'] else 'exhausted'}")


RULES: list[Rule] = [
    Rule("v4pro_balance_check", _bal_check, _bal_confidence,
         _bal_act, reversible=True, tags=["routing", "v4pro"]),
    Rule("v4pro_routing", _v4pro_check, _v4pro_confidence,
         _v4pro_act, reversible=True, tags=["routing", "v4pro"]),    Rule("deepseek_brief_overdue", _brief_check, _brief_confidence,
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
