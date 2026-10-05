#!/usr/bin/env python3
"""
Model tier routing for SuccessBrian OS.

PURPOSE:
    Answer "which model should take this task?" One source of truth for the
    stack: Penny 7B (small/fast) -> Sonic Qwen3.6-35B-A3B local (workhorse)
    -> DeepSeek V4 Pro cloud (top tier, hard tasks only when credits allow).
    DeepSeek 150B stays listed as a RETIRED entry so history stays readable.

WHY:
    Brian's local-first principle: don't count tokens, optimize wall-clock
    and owned hardware. The 150B tier was retired 2026-10-02 (Qwen A3B
    switch) — routing to it after retirement silently sent hard work to a
    dark port. Without a routing decision point, every worker guesses —
    burning V4 Pro credits on easy jobs or starving hard jobs on the wrong
    tier. This makes the choice explicit and checkable.

CALLED BY:
    - tools/automate/rules.py (v4pro_routing rule reads get_tiers())
    - Night shift / heartbeat workers before assigning work
    - Humans: --v4pro available|exhausted flips the credit flag

NOTES:
    The v4pro credit flag (tools/state/model-tiers.json) is manual
    until we have an API check — Brian or Spencer flips it when credits land
    or dry up. Local tier probes run from k11-alpha via kssh because this VM
    can't reach the tailnet directly. --status output keeps the old key names
    (penny_7b / deepseek_150b / v4pro_cloud, each with "available") and adds
    "status" + "note" fields; consumers should treat status == "retired" as
    never-routable even if a probe ever answered.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(__file__).parent / "state" / "model-tiers.json"

# Local ports on k11-alpha. Verified 2026-10-04 via kssh:
#   11438 (penny) OPEN, 11439 (sonic) OPEN, 8084 (150b) CLOSED (retired).
_PORTS = {
    "penny_7b": 11438,
    "sonic": 11439,
    "deepseek_150b": 8084,
}

# Historical record for the retired tier. Probing a dark port is pointless;
# the entry exists so old reports and Brian's memory stay legible.
_RETIRED_150B = {
    "retired": True,
    "retired_on": "2026-10-02",
    "port": 8084,
}


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
    """Live tier status. v4pro comes from the credit flag; locals are probed.

    Key names are backward compatible with the pre-2026-10-04 output
    (penny_7b / deepseek_150b / v4pro_cloud, each with "available"); "sonic"
    is new, and every tier now carries "status" + "note".
    """
    flag = _read_flag()
    return {
        "penny_7b": {
            "available": _remote_port_open(_PORTS["penny_7b"]),
            "status": "live",
            "role": "small fast jobs",
            "note": "MiniCPM/Penny 7B Q6_K on k11-alpha localhost:11438.",
        },
        "sonic": {
            "available": _remote_port_open(_PORTS["sonic"]),
            "status": "live",
            "role": "workhorse",
            "note": ("Qwen3.6-35B-A3B Q6_K (Brian named it Sonic) on k11-alpha "
                     "localhost:11439. The local workhorse since the "
                     "2026-10-02 Qwen switch; also Altair's default chat "
                     "model. 780M Vulkan, 96K ctx."),
        },
        "deepseek_150b": {
            "available": False,
            "status": "retired",
            "role": "historical entry only — never routable",
            "note": (f"Retired {_RETIRED_150B['retired_on']}; port "
                     f"{_RETIRED_150B['port']} verified CLOSED 2026-10-04. "
                     "Kept so old digests/reports stay legible."),
        },
        "v4pro_cloud": {
            "available": bool(flag["v4pro_credits"]),
            "status": "live",
            "role": "top tier, hard tasks only",
            "note": "Credit flag is manual until an API check exists.",
            "flag_updated_at": flag["updated_at"],
            "flag_updated_by": flag["updated_by"],
        },
    }


def route_for(difficulty: str) -> str:
    """Which tier should take a task of this difficulty?

    hard   -> v4pro_cloud when credits allow, else sonic
    medium -> sonic
    easy   -> penny_7b
    Falls through to the next tier down when the pick is unavailable;
    "none_available" only when nothing local answers.
    """
    tiers = get_tiers()
    if difficulty == "hard" and tiers["v4pro_cloud"]["available"]:
        return "v4pro_cloud"
    if difficulty in ("hard", "medium") and tiers["sonic"]["available"]:
        return "sonic"
    if tiers["penny_7b"]["available"]:
        return "penny_7b"
    if tiers["sonic"]["available"]:
        return "sonic"
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
