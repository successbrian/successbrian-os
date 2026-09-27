"""successbrian-os automation engine.

PURPOSE:
    The 90% rule, as code. Rules declare check -> confidence -> action; the
    engine acts at >=90% confidence (reversible), queues irreversible
    high-confidence actions for approval, and routes low-confidence triggers
    to research via the second brain.

WHY:
    Brian's standing rule ("90%+ correct, do it; below 90%, ask") was prose in
    cron bodies — unenforceable and invisible. Codifying it means every
    automated decision carries its confidence, every action is logged, and
    outcomes feed back into the second brain so rules gain or lose trust over
    time. This is the paperclipOS idea made executable: the OS acts on its
    own within bounds Brian set.

CALLED BY:
    - tools/automate/run.py (CLI; --live from heartbeats and night shift)
    - Heartbeat workers run it first each wake-up

NOTES:
    AUTONOMY_THRESHOLD = 0.90 is Brian's bar, not a tuning parameter — don't
    change it without his say-so. Dry-run is the default; --live is required
    to act. Action log: tools/staging/automation-actions.jsonl.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

TOOLS = Path(__file__).parent.parent
sys.path.insert(0, str(TOOLS))
from second_brain import record as sb_record  # noqa: E402

AUTONOMY_THRESHOLD = 0.90
ACTION_LOG = TOOLS / "staging" / "automation-actions.jsonl"


@dataclass
class Rule:
    name: str
    check: Callable[[], tuple[bool, dict]]
    confidence: Callable[[dict], float]
    act: Callable[[dict, bool], str]
    reversible: bool = True
    tags: list[str] = field(default_factory=list)


def log_action(name: str, ctx: dict, conf: float, result: str,
               acted: bool, dry_run: bool) -> None:
    ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    import json
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "rule": name,
        "confidence": conf,
        "acted": acted,
        "dry_run": dry_run,
        "context": {k: str(v)[:200] for k, v in ctx.items()},
        "result": result[:500],
    }
    with open(ACTION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_rules(rules: list[Rule], dry_run: bool = False) -> dict:
    """Evaluate all rules. Returns summary of what happened."""
    summary = {"acted": [], "queued": [], "needs_research": [], "skipped": []}
    for rule in rules:
        try:
            triggered, ctx = rule.check()
        except Exception as e:  # noqa: BLE001
            log_action(rule.name, {}, 0.0, f"check failed: {e}", False, dry_run)
            summary["skipped"].append((rule.name, f"check error: {e}"))
            continue
        if not triggered:
            summary["skipped"].append((rule.name, "not triggered"))
            continue
        try:
            conf = rule.confidence(ctx)
        except Exception as e:  # noqa: BLE001
            conf = 0.0
            ctx["confidence_error"] = str(e)

        if conf >= AUTONOMY_THRESHOLD and rule.reversible:
            try:
                result = rule.act(ctx, dry_run)
                acted = not dry_run
            except Exception as e:  # noqa: BLE001
                result, acted = f"action failed: {e}", False
            log_action(rule.name, ctx, conf, result, acted, dry_run)
            sb_record(
                topic=f"automation: {rule.name}",
                content=f"{'Would act' if dry_run else 'Acted'} "
                        f"(confidence {conf:.2f}): {result}",
                category="fact",
                confidence="high" if acted else "medium",
                source="automation-engine",
                verification="direct execution" if acted else "dry-run",
                tags=["automation"] + rule.tags,
            )
            summary["acted"].append((rule.name, result))
        elif conf >= AUTONOMY_THRESHOLD and not rule.reversible:
            log_action(rule.name, ctx, conf,
                       "queued for approval (irreversible)", False, dry_run)
            summary["queued"].append(
                (rule.name, f"confidence {conf:.2f} but irreversible — "
                            "needs Brian's approval"))
        else:
            log_action(rule.name, ctx, conf,
                       "below threshold — needs research", False, dry_run)
            sb_record(
                topic=f"automation needs research: {rule.name}",
                content=f"Rule triggered but confidence {conf:.2f} < 0.90. "
                        f"Context: {ctx}. Research before acting.",
                category="learning",
                confidence="medium",
                source="automation-engine",
                verification="rule check output, unverified cause",
                expires_days=7,
                tags=["automation", "needs-research"] + rule.tags,
            )
            summary["needs_research"].append((rule.name, f"{conf:.2f}"))
    return summary


def kssh(cmd: str, timeout: int = 60) -> str:
    out = subprocess.run(
        [str(Path.home() / "workspace" / "bin" / "kssh"), cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    return out.stdout.strip()
