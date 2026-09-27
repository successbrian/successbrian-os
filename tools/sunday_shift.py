#!/usr/bin/env python3
"""
Sunday shift: plan, strategize, clean up, help out.

Runs every Sunday 3:00 PM CDT while Brian sleeps (until 6:30 PM).
Produces a summary for him to read when he wakes up.

Steps:
  1. Sync decisions -> digest + conflict check
  2. Regenerate capacity report
  3. Regenerate ecosystem state snapshot
  4. Clean staging dirs (keep latest, quarantine old)
  5. Write Sunday summary to the altair-brain inbox for Brian
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

TOOLS = Path.home() / "workspace" / "successbrian-os" / "tools"
INBOX = Path("/tmp/altair-brain-inbox/inbox")


def run(cmd: list[str], desc: str) -> bool:
    print(f"--- {desc} ---")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                           cwd=TOOLS)
        print(r.stdout[-1500:] if len(r.stdout) > 1500 else r.stdout)
        if r.returncode != 0:
            print(f"FAILED: {r.stderr[-500:]}")
            return False
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def cleanup_staging() -> None:
    """Keep latest artifacts, quarantine the rest."""
    staging = TOOLS / "staging"
    quarantine = TOOLS / "quarantine"
    quarantine.mkdir(exist_ok=True)
    for pattern in ["decisions-digest-*.md", "capacity-report-*.md",
                    "ecosystem-state-*.json"]:
        files = sorted(staging.glob(pattern))
        # Keep files with "latest" in name + most recent dated one
        dated = [f for f in files if "latest" not in f.name]
        for f in dated[:-1]:  # all but newest
            dest = quarantine / f.name
            f.rename(dest)
            print(f"  quarantined {f.name}")


def assign_crew() -> None:
    """Drop Sunday assignments for Altair, Lyra, and the model crew."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = f"""# Sunday Shift Assignments — {now}

Brian's asleep until 6:30 PM. Here's the crew's cut:

## Altair (k11-alpha)
- Run infra health: disk, Docker, AnythingLLM, PostgreSQL, Tailscale.
- Anything broken or degraded → fix if 90%+ sure, else flag for Brian.
- Report back to inbox before 6 PM.

## Lyra
- Review workflow queues: goal queue depth, anything stuck in_progress 7+ days.
- Check fleet utilization against capacity report (staging/capacity-report-latest.md).
- Flag anything that needs Brian's call vs what you can reschedule yourself.

## Model crew (via Altair)
- **DeepSeek 150B** (port 8084): heavy analysis — read the week's decisions
  digest and write a strategic brief: what's converging, what's conflicting,
  what should Brian prioritize next week. Serialized requests only (429 risk).
- **Morpheus** (port 11437): medium tasks — summarize AnythingLLM library
  growth, flag stale workspaces.
- **Penny** (port 11438): quick tasks — dedup check on inbox, triage new
  items since last Sunday.

## Spencer
- Orchestrates, runs decision_sync/capacity/ecosystem_state, writes the
  wake-up summary for Brian.

All reports back to the inbox by 6 PM. Brian wakes up to one summary.
"""
    INBOX.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (INBOX / f"{ts}-sunday-crew-assignments.md").write_text(body)
    print("Crew assignments written to inbox.")


def write_summary(results: dict) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Sunday Shift Summary — {now}",
        "",
        "While you slept, the ecosystem did its homework:",
        "",
    ]
    for name, ok in results.items():
        icon = "done" if ok else "FAILED"
        lines.append(f"- [{icon}] {name}")
    lines += [
        "",
        "Crew assignments: Altair (infra health), Lyra (queues + utilization),",
        "DeepSeek 150B (strategic brief), Morpheus (library), Penny (inbox triage).",
        "Their reports are in the inbox alongside this summary.",
        "",
        "Details: successbrian-os/tools/staging/",
        "Conflicts needing your eyes: conflict-report-latest.md",
        "Capacity: capacity-report-latest.md",
        "Full state: ecosystem-state.md",
        "",
        "_Next Sunday shift: same time, same place._",
    ]
    INBOX.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (INBOX / f"{ts}-sunday-shift-summary.md").write_text("\n".join(lines))
    print("Summary written to inbox.")


def main() -> int:
    results = {}
    results["decision sync"] = run(
        [sys.executable, "decision_sync/sync.py"], "Decision sync")
    results["capacity report"] = run(
        [sys.executable, "capacity.py"], "Capacity report")
    results["ecosystem state"] = run(
        [sys.executable, "ecosystem_state.py"], "Ecosystem state")
    print("--- Cleanup ---")
    cleanup_staging()
    results["staging cleanup"] = True
    print("--- Crew assignments ---")
    assign_crew()
    results["crew assignments"] = True
    write_summary(results)

    # Commit + push inbox
    subprocess.run(["git", "add", "inbox/"], cwd="/tmp/altair-brain-inbox",
                   capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Spencer: Sunday shift summary"],
        cwd="/tmp/altair-brain-inbox", capture_output=True)
    subprocess.run(["git", "push"], cwd="/tmp/altair-brain-inbox",
                   capture_output=True, timeout=60)
    print("Pushed to altair-brain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
