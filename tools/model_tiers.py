#!/usr/bin/env python3
"""
Model tier routing for SuccessBrian OS.

The stack (per Brian):
  penny (7B local)  -> small, fast jobs. Always available.
  150B (local)      -> workhorse. Always available, serialized queue.
  v4pro (cloud)     -> top tier. ONLY when credits are available.

The v4pro credit flag is the source of truth until we have an API check:
    python3 tools/model_tiers.py --v4pro available    # credits landed
    python3 tools/model_tiers.py --v4pro exhausted    # credits dry
    python3 tools/model_tiers.py --status             # show all tiers

Workers consult get_tiers() before assigning work: hard tasks go to v4pro
when it's available, otherwise they stay local (150B serialized).
"""
import argparse
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(__file__).parent / "state" / "model-tiers.json"


def _port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    # My VM can't reach the tailnet directly; probe from k11-alpha via kssh.
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
            "available": _port_open("100.118.53.47", 11438),
            "role": "small fast jobs",
        },
        "deepseek_150b": {
            "available": _port_open("100.118.53.47", 8084),
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
