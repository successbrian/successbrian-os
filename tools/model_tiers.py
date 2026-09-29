#!/usr/bin/env python3
"""
Model tier routing for SuccessBrian OS.

PURPOSE:
    Answer "which model should take this task?" One source of truth for the
    stack: Penny 7B (small/fast) -> DeepSeek 150B local (workhorse) ->
    DeepSeek V4 Pro cloud (top tier, hard tasks only when credits allow).

WHY:
    Brian's local-first principle: don't count tokens, optimize wall-clock
    and owned hardware. But hard tasks still sometimes need the cloud tier.
    Without a routing decision point, every worker guesses — burning V4 Pro
    credits on easy jobs or starving hard jobs on the slow 150B (~0.66 tok/s).
    This makes the choice explicit and checkable.

CALLED BY:
    - tools/automate/rules.py (v4pro_routing rule)
    - Night shift / heartbeat workers before assigning work
    - Humans: --v4pro available|exhausted flips the credit flag

NOTES:
    The v4pro credit flag (tools/automate/state/model-tiers.json) is manual
    until we have an API check — Brian or Spencer flips it when credits land
    or dry up. Local tier probes run from k11-alpha via kssh because this VM
    can't reach the tailnet directly.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(__file__).parent / "state" / "model-tiers.json"


def _remote_port_open(port: int) -> bool:
    """Is localhost:<port> listening ON k11-alpha?

    (2026-09-28: the old _port_open(host, port) took a host argument it
    silently ignored — the probe always ran on k11-alpha via kssh. Renamed
    and the dead parameter removed so the API can't mislead again.)
    """
    import subprocess
    try:
        out = subprocess.run(
            [str(Path.home() / "workspace" / "bin" / "kssh"),
             f"timeout 5 bash -c 'echo > /dev/tcp/localhost/{port}' "
             f"&& echo OPEN || echo CLOSED"],
            capture_output=True, text=True, timeout=15,
        )
        return "OPEN" in out.stdout
    except Exception:  # noqa: BLE001
        return False


def _read_flag() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"v4pro_credits": False, "updated_at": None, "updated_by": None}


def set_v4pro(available: bool, by: str = "manual") -> dict:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "v4pro_credits": available,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": by,
    }
    STATE.write_text(json.dumps(data, indent=2))
    return data


def get_tiers() -> dict:
    """Live tier status. v4pro comes from the credit flag; locals are probed."""
    flag = _read_flag()
    return {
        "penny_7b": {
            "available": _remote_port_open(11438),
            "role": "small fast jobs",
        },
        "deepseek_150b": {
            "available": _remote_port_open(8084),
            "role": "workhorse (serialized queue)",
        },
        "v4pro_cloud": {
            "available": bool(flag["v4pro_credits"]),
            "role": "top tier, hard tasks only",
            "flag_updated_at": flag["updated_at"],
            "flag_updated_by": flag["updated_by"],
        },
    }


def route_for(difficulty: str) -> str:
    """Which tier should take a task of this difficulty?"""
    tiers = get_tiers()
    if difficulty == "hard" and tiers["v4pro_cloud"]["available"]:
        return "v4pro_cloud"
    if difficulty in ("hard", "medium") and tiers["deepseek_150b"]["available"]:
        return "deepseek_150b"
    if tiers["penny_7b"]["available"]:
        return "penny_7b"
    return "none_available"


def main() -> int:
    ap = argparse.ArgumentParser(description="Model tier routing.")
    ap.add_argument("--v4pro", choices=["available", "exhausted"],
                    help="set the v4pro credit flag")
    ap.add_argument("--status", action="store_true", help="show tier status")
    ap.add_argument("--route", choices=["easy", "medium", "hard"],
                    help="which tier should take this difficulty?")
    args = ap.parse_args()

    if args.v4pro:
        data = set_v4pro(args.v4pro == "available")
        print(f"v4pro credits: {args.v4pro} "
              f"(updated {data['updated_at']})")
        return 0
    if args.route:
        print(route_for(args.route))
        return 0
    print(json.dumps(get_tiers(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
