#!/usr/bin/env python3
"""
V4 Pro availability checker for SuccessBrian OS.

PURPOSE:
    Check whether the DeepSeek V4 Pro rental key is live and flip the
    v4pro credit flag automatically — no manual flag, no human top-up.

WHY:
    Brian RENTS DeepSeek API access from InstantlyClaw.com — the API key
    belongs to them, not to Brian (standing order recorded in Altair's
    session dumps, Aug 2026). Topping up is the owner's job, not Brian's.
    The model router (tools/model_tiers.py) gates the cloud top tier on
    this flag, so an hourly live check keeps routing honest: rental refilled
    -> hard tasks flow to V4 Pro; rental dry -> everything stays local.

    Verified 2026-09-27: the rental key answers DeepSeek's own
    GET /user/balance with {"is_available": false, "total_balance": "-0.00"}
    — exhausted, which is why Altair's profile currently defaults to the
    local Morpheus model. When InstantlyClaw refills, this check sees it.

CALLED BY:
    - tools/automate/rules.py (v4pro_balance_check rule, throttled hourly)
    - Humans: python3 tools/v4pro_balance.py

AUTH:
    The rental key lives in k11-alpha's ~/.hermes/.env (DEEPSEEK_API_KEY).
    The HTTPS check runs ON k11-alpha via kssh, so the key never leaves
    that machine and is never stored on this VM, in files, or in memory
    notes. Only the parsed balance result crosses back.

NOTES:
    Endpoint: GET https://api.deepseek.com/user/balance (documented in
    DeepSeek's API reference; free call, spends no quota).
    "Available" means is_available=true AND total USD > MIN_USD
    (default $1.00 — dust doesn't count as a usable rental).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model_tiers import set_v4pro  # noqa: E402

MIN_USD = float(os.environ.get("V4PRO_MIN_USD", "1.00"))
STATE = Path(__file__).parent / "automate" / "state" / "v4pro-balance.json"
KSSH = Path.home() / "workspace" / "bin" / "kssh"

# Runs on k11-alpha; prints only the parsed result, never the key.
REMOTE_PROBE = """
import json, urllib.request
key = None
with open('/home/successbrian/.hermes/.env') as f:
    for line in f:
        s = line.strip()
        if s.startswith('DEEPSEEK_API_KEY='):
            key = s.split('=', 1)[1].strip().strip('"').strip(chr(39))
            break
print(json.dumps({'key_present': bool(key)}))
if key:
    req = urllib.request.Request(
        'https://api.deepseek.com/user/balance',
        headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
    b = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    print(json.dumps({'ok': True,
                      'is_available': b.get('is_available', False),
                      'balances': b.get('balance_infos', [])}))
"""


def probe() -> dict:
    import base64
    payload = base64.b64encode(REMOTE_PROBE.encode()).decode()
    try:
        out = subprocess.run(
            [str(KSSH), f"echo {payload} | base64 -d | python3"],
            capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"kssh failed: {e}"[:200]}
    lines = [ln for ln in out.stdout.splitlines() if ln.startswith("{")]
    if len(lines) < 2:
        return {"ok": False,
                "error": f"probe failed: {out.stderr[:150]}" or "no output"}
    try:
        presence = json.loads(lines[0])
        result = json.loads(lines[1])
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "unparseable probe output"}
    if not presence.get("key_present"):
        return {"ok": False, "error": "rental key missing from k11-alpha .env"}
    return result


def check() -> dict:
    data = probe()
    if not data.get("ok"):
        return data
    usd = 0.0
    for info in data.get("balances", []):
        if info.get("currency") == "USD":
            try:
                usd += float(info.get("total_balance") or 0)
            except (TypeError, ValueError):
                pass
    available = bool(data.get("is_available")) and usd > MIN_USD
    flag = set_v4pro(available, by="v4pro_balance.py")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "usd": usd, "is_available": data.get("is_available"),
        "available": available,
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
