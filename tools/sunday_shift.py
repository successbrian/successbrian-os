#!/usr/bin/env python3
"""
Sunday shift orchestrator for SuccessBrian OS.

PURPOSE:
    Run the full Sunday 3:00 PM shift pipeline: decision sync, capacity
    report, ecosystem snapshot, crew assignments, staging cleanup, and the
    inbox summary that feeds Altair's 7:30 briefing.

WHY:
    The whole shift exists for one thing: getting Altair ready for the 7:30
    PM weekly conversation with Brian. Every step feeds that briefing.
    Orchestrating it as code (instead of a checklist in a cron body) means
    the sequence is tested, repeatable, and improvable.

CALLED BY:
    - sunday-shift cron (weekly, Sundays 3:00 PM CDT)

NOTES:
    This writes assignments but does not invoke the crew — their
    participation is tracked by the 15-min heartbeat, not guaranteed here.
    The summary is written immediately after orchestration, before late crew
    work lands; the heartbeat appends as reports arrive.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from common import INBOX, git_push

TOOLS = Path(__file__).parent

DRY_RUN = False


def run(cmd: list[str], desc: str) -> bool:
    print(f"--- {desc} ---")
    if DRY_RUN:
        print(f"(dry run: would run {' '.join(cmd)})")
        return True
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

## Model crew (via Altair) — ORDER MATTERS, Sonic first
- **Sonic** (port 11439) — HIGHEST PRIORITY: the strategic brief is the
  backbone of Altair's 7:30 briefing. Read the week's decisions digest and
  write: what's converging, what's conflicting, what Brian should prioritize
  next week, and the 3-5 questions that most need his judgment. Due by 5 PM
  so Altair has time to absorb it. Serialized requests only (429 risk).
- **Morpheus** (port 11437): medium tasks — summarize AnythingLLM library
  growth, flag stale workspaces.
- **Penny** (port 11438): quick tasks — dedup check on inbox, triage new
  items since last Sunday.

## Fleet crew (as nodes come online — "when Brian sleeps the ecosystem cranks")
- **X79 nodes**: batch content generation — blog posts, sales pages, scripts,
  email sequences. Overnight content factory at full crank.
- **k11-bravo**: QLoRA adapter training runs, small-model experiments.
- **Aoostar nodes**: GLM 5.3 inference tasks, overflow batch work.
- **k11-alpha**: AnythingLLM nightly maintenance (dedup, embeddings, hygiene)
  — or hand off to X79s once they're online so alpha stays responsive.
- Each node reports utilization + output to the inbox by 6 PM.

## Spencer
- Orchestrates, runs decision_sync/capacity/ecosystem_state, writes the
  wake-up summary for Brian.

All reports back to the inbox by 6 PM. Brian wakes up to one summary.
"""
    INBOX.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = INBOX / f"{ts}-sunday-crew-assignments.md"
    if DRY_RUN:
        print(f"(dry run: would write {path})")
        return
    path.write_text(body)
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
        "Sonic (strategic brief), Morpheus (library), Penny (inbox triage).",
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
    path = INBOX / f"{ts}-sunday-shift-summary.md"
    if DRY_RUN:
        print(f"(dry run: would write {path})")
        return
    path.write_text("\n".join(lines))
    print("Summary written to inbox.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sunday shift orchestrator.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would run; skip writes and the push.")
    args = ap.parse_args()
    global DRY_RUN
    DRY_RUN = args.dry_run

    results = {}
    results["decision sync"] = run(
        [sys.executable, "decision_sync/sync.py"], "Decision sync")
    results["capacity report"] = run(
        [sys.executable, "capacity.py"], "Capacity report")
    results["ecosystem state"] = run(
        [sys.executable, "ecosystem_state.py"], "Ecosystem state")
    print("--- Cleanup ---")
    if DRY_RUN:
        print("(dry run: staging cleanup skipped)")
        results["staging cleanup"] = True
    else:
        cleanup_staging()
        results["staging cleanup"] = True
    print("--- Crew assignments ---")
    assign_crew()
    results["crew assignments"] = True
    write_summary(results)

    # Commit + push the durable inbox clone (NOT /tmp — that path is dead
    # on this VM; the old code swallowed the git failures silently).
    if DRY_RUN:
        print("(dry run: inbox push skipped)")
        return 0
    inbox_repo = INBOX.parent  # ~/workspace/altair-brain
    ok = git_push(inbox_repo, "Spencer: Sunday shift summary", ["inbox/"])
    results["inbox push"] = ok
    if not ok:
        print("WARNING: inbox push failed — briefing files are local-only.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
