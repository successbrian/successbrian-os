#!/usr/bin/env python3
"""
V4 Pro balance checker for SuccessBrian OS.

PURPOSE:
    Check the DeepSeek API credit balance and flip the v4pro credit flag
    automatically — no more manual `--v4pro available|exhausted`.

WHY:
    The model router (tools/model_tiers.py) gates the cloud top tier on
    credits. A human flipping a flag is a chore that gets forgotten; an
    hourly balance check keeps routing honest: credits land -> hard tasks
    flow to V4 Pro, credits dry up -> everything falls back to local.

CALLED BY:
    - tools/automate/rules.py (v4pro_balance_check rule, throttled to hourly)
    - Humans: python3 tools/v4pro_balance.py

AUTH:
    DeepSeek API key via the custom.deepseek connector (Secure Vault).
    Set up with the [Add a custom connector] card; the deepseek-balance
    skill (~/workspace/skills/deepseek-balance/) carries the credential
    mechanics. Falls back to DEEPSEEK_API_KEY env var.

NOTES:
    Endpoint: GET https://api.deepseek.com/user/balance (documented in
    DeepSeek's API reference). Balances are strings; "available" means
    total USD > MIN_USD (default $1.00 — enough for real work, not dust).
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model_tiers import set_v4pro  # noqa: E402

BALANCE_URL = "https://api.deepseek.com/user/balance"
MIN_USD = float(os.environ.get("V4PRO_MIN_USD", "1.00"))
STATE = Path(__file__).parent / "automate" / "state" / "v4pro-balance.json"


def get_api_key() -> str | None:
    # 1. Skill helper (connector-backed) if the skill is scaffolded.
    skill_helper = (Path.home() / "workspace" / "skills" /
                    "deepseek-balance" / "bin" / "get_key.py")
    if skill_helper.exists():
        import subprocess
        try:
            out = subprocess.run(
                [sys.executable, str(skill_helper)],
                capture_output=True, text=True, timeout=30)
            key = out.stdout.strip()
            if key:
                return key
        except Exception:  # noqa: BLE001
            pass
    # 2. Env var fallback.
    return os.environ.get("DEEPSEEK_API_KEY") or None


def fetch_balance(api_key: str) -> dict:
    req = urllib.request.Request(
        BALANCE_URL,
        headers={"Authorization": f"Bearer {api_key}",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"balance API returned HTTP {resp.status}")
        return json.loads(resp.read().decode())


def parse_usd(data: dict) -> float:
    total = 0.0
    for info in data.get("balance_infos", []):
        if info.get("currency") == "USD":
            try:
                total += float(info.get("total_balance") or 0)
            except (TypeError, ValueError):
                pass
    return total


def check() -> dict:
    key = get_api_key()
    if not key:
        return {"ok": False, "error": "no DeepSeek API key available"}
    try:
        data = fetch_balance(key)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    if not data.get("is_available", True):
        return {"ok": False, "error": "balance not available"}
    usd = parse_usd(data)
    available = usd > MIN_USD
    flag = set_v4pro(available, by="v4pro_balance.py")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "usd": usd, "available": available,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    return {"ok": True, "usd": round(usd, 2), "available": available,
            "flag": flag}


def main() -> int:
    result = check()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
