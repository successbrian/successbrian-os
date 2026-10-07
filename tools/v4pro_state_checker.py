#!/usr/bin/env python3
"""
v4pro_state_checker.py — Check DeepSeek V4 Pro rental balance every 30 min, record the current value.

PURPOSE: Single source of truth for DeepSeek V4 Pro cloud availability. Probes the live
         balance and writes the RAW current value to the shared state file. Nothing else
         hardcodes pricing, floors, or availability assumptions — all consumers read this file.
WHY: Brian's directive 2026-10-07: "do not pin or hard code pricing of deepseek; have
     something check every 30 minutes and altair's code relies on that current value only."
CALLED BY: Altair cron job `v4pro-state-checker` every 30 min (no_agent script job).
NOTES:
  - Balance via GET https://api.deepseek.com/user/balance using DEEPSEEK_API_KEY from
    /home/successbrian/.hermes/.env (the InstantlyClaw rental key — never Brian's).
    The key is never printed, logged, or written anywhere.
  - Writes ONLY raw values: is_available (from the API) and usd balance. No floors,
    no thresholds, no pinning — interpretation belongs to the consumer.
  - Canonical destination: successbrian_os.v4pro_balance_history (every check is a row;
    agents read the latest). The JSON file is a convenience mirror written in the same run.
  - On probe failure nothing is written (a stale value beats a false one);
    the failure is logged and the run exits non-zero.
  - State file: /home/successbrian/.hermes/shared/v4pro-state.json
"""

import datetime
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ENV_FILE = Path("/home/successbrian/.hermes/.env")
STATE_FILE = Path("/home/successbrian/.hermes/shared/v4pro-state.json")
BALANCE_URL = "https://api.deepseek.com/user/balance"
PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A"]


def log(msg):
    print(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def get_key():
    try:
        for line in ENV_FILE.read_text().splitlines():
            s = line.strip()
            if s.startswith("DEEPSEEK_API_KEY="):
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError as e:
        log(f"ERROR reading env file: {e}")
    return None


def get_balance(key):
    req = urllib.request.Request(
        BALANCE_URL,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
    )
    data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    usd = 0.0
    for info in data.get("balance_infos", []) or []:
        if info.get("currency") == "USD":
            try:
                usd += float(info.get("total_balance") or 0)
            except (TypeError, ValueError):
                pass
    return bool(data.get("is_available")), round(usd, 2)


def write_table(available: bool, usd: float) -> None:
    """Insert one row into the canonical history table. Raises on failure."""
    sql = (
        "INSERT INTO successbrian_os.v4pro_balance_history (available, usd, source) "
        f"VALUES ({'true' if available else 'false'}, {usd:.2f}, 'v4pro_state_checker.py');"
    )
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"psql insert failed: {r.stderr.strip()[:200]}")


def main():
    key = get_key()
    if not key:
        log("ERROR: DEEPSEEK_API_KEY not found; nothing written")
        return 2
    try:
        available, usd = get_balance(key)
    except Exception as e:  # noqa: BLE001 - never write on a probe failure
        log(f"ERROR: balance probe failed ({type(e).__name__}); nothing written")
        return 1

    try:
        write_table(available, usd)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: table write failed ({e}); nothing written")
        return 1

    state = {
        "available": available,
        "usd": usd,
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "v4pro_state_checker.py",
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1) + "\n")
    log(f"recorded: available={available} usd={usd:.2f} (table + state file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
