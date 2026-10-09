#!/usr/bin/env python3
"""V4 Pro status reader — the ONLY way Altair's code checks DeepSeek status.

PURPOSE:
    Single function any agent code calls to know if DeepSeek V4 Pro is
    available right now. Reads the 30-minute checker's latest row — never
    probes the DeepSeek API directly, never hardcodes.

WHY:
    Brian 2026-10-08: "why don't we code it for him in actual python."
    Prompts telling Altair to "read the table" rely on him remembering.
    This makes the check a function call — deterministic, no model needed.
    Replaces all direct DeepSeek API probing in Altair's code paths.

CALLED BY:
    Any Altair/Hermes Python code that needs V4 Pro availability:
        from v4pro_status import get_status
        status = get_status()
        if status.available:
            # use V4 Pro
        else:
            # fall back to local

NOTES:
    - Reads successbrian_os.v4pro_balance_history (written by
      v4pro_state_checker.py every 30 min). No API calls here.
    - Runs on k11 (direct psql) or Hatch VM (via kssh) — auto-detects.
    - Freshness: if the latest row is older than 45 min, the checker itself
      may be down — status.is_fresh is False and callers should treat
      availability as unknown (fall back to local, do NOT assume down).
    - Mirrors the JSON state file as fallback if the DB is unreachable.
"""

import datetime
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

KSSH = os.path.expanduser("~/workspace/bin/kssh")
STATE_FILE = Path("/home/successbrian/.hermes/shared/v4pro-state.json")
STALE_AFTER_MIN = 45


@dataclass
class V4ProStatus:
    available: bool
    usd: float
    checked_at: str
    is_fresh: bool
    source: str  # 'table' or 'state_file'


def _psql_cmd(sql):
    base = ("psql -h localhost -U successbrian -d ecosystem_central -t -A "
            "-F '|' -c \"%s\"" % sql.replace('"', '\\"'))
    if Path(KSSH).exists():
        return ["bash", KSSH, base]
    return ["bash", "-c", base]


def _query_table():
    out = subprocess.run(
        _psql_cmd("SELECT available, usd, checked_at FROM "
                  "successbrian_os.v4pro_balance_history "
                  "ORDER BY checked_at DESC LIMIT 1;"),
        capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        return None
    parts = out.stdout.strip().split("|")
    if len(parts) < 3:
        return None
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


def _read_state_file():
    try:
        data = json.loads(STATE_FILE.read_text())
        return (str(data.get("available", False)),
                str(data.get("usd", 0)),
                str(data.get("checked_at", "")))
    except Exception:
        return None


def get_status() -> V4ProStatus:
    """Current V4 Pro status from the 30-min checker. Never probes the API."""
    row = _query_table()
    source = "table"
    if row is None:
        row = _read_state_file()
        source = "state_file"
    if row is None:
        # No data at all — treat as unknown, not down
        return V4ProStatus(available=False, usd=0.0, checked_at="never",
                           is_fresh=False, source="none")

    avail_raw, usd_raw, checked_raw = row
    available = avail_raw.lower() in ("t", "true", "1")
    try:
        usd = float(usd_raw)
    except ValueError:
        usd = 0.0

    is_fresh = False
    try:
        checked_dt = datetime.datetime.fromisoformat(
            checked_raw.replace("Z", "+00:00"))
        if checked_dt.tzinfo is None:
            checked_dt = checked_dt.replace(
                tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) -
               checked_dt).total_seconds() / 60
        is_fresh = age <= STALE_AFTER_MIN
    except Exception:
        pass

    # Stale data = unknown, not down. Callers fall back to local.
    if not is_fresh:
        available = False

    return V4ProStatus(available=available, usd=usd,
                       checked_at=checked_raw, is_fresh=is_fresh,
                       source=source)


def main():
    s = get_status()
    print(f"available={s.available} usd={s.usd:.2f} "
          f"fresh={s.is_fresh} source={s.source} checked_at={s.checked_at}")


if __name__ == "__main__":
    main()
