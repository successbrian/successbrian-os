#!/usr/bin/env python3
"""spencer_cycle.py — Spencer's 20-minute self-check cycle inside SuccessBrian OS.

Brian's order (2026-11-11 03:22 CST): "build functionality within
successbrian os to assist you in this... establish a 20 minute routine
that every 20 minutes you are checking your own tools built inside
successbrian os that allows you to turn yourself into a 24/7 automated
agentic system for me that continuously improves the ecosystem for me."

One cycle = one pass over Spencer's own SBOS toolset and the live
ecosystem state those tools read:

  1. ecosystem_pulse.py      — today's calendar, raw capture backlog,
                               latest decisions, build count, open issues
  2. QA layer                — successbrian_os.pm_project_checks whose
                               latest pm_project_qa_runs row is 'fail'
  3. Clerk / gamma road      — gamma liveness (successbrian_os.logs) and
                               the raw-capture backlog trend (feed the
                               road first: idle-while-waiting is a defect)
  4. Price intel shelf life  — successbrian_os.price_intel rows whose
                               valid_until has passed (recheck queue)
  5. Own open work           — local work queues Spencer is carrying
                               (default: the scalable spillover articles)

Findings are deduplicated against a state file: a finding is filed to
the Intel Bridge (bridge_dump.py) only the first time its key appears
(or when its measured value changes). Routine all-clear cycles file
nothing and print a one-line report — silence is the normal state.

Usage:
  python3 spencer_cycle.py              # check + report, file new findings
  python3 spencer_cycle.py --no-file    # check + report only
  python3 spencer_cycle.py --json       # machine-readable report

State: ~/workspace/spencer-cycle/state.json  (seen finding keys, raw
backlog history, last cycle time). Exit 0 = cycle ran (findings or not);
exit 2 = ecosystem unreachable (degrades loudly, never silently).
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HOME = Path.home()
TOOLS = HOME / "workspace/tools"
STATE_DIR = HOME / "workspace/spencer-cycle"
STATE_FILE = STATE_DIR / "state.json"
SSH = ["ssh", "-F", str(HOME / "workspace/k11-upgrade/ssh_config"), "k11"]
TZ = ZoneInfo("America/Chicago")

SQL = """
select 'RAW', count(*) from atlas.scattered_captures where status = 'raw';
select 'QA_FAIL', count(*) from successbrian_os.pm_project_checks c
  where (select r.status from successbrian_os.pm_project_qa_runs r
          where r.check_id = c.id order by r.ran_at desc limit 1) = 'fail';
select 'QA_FAIL_IDS', coalesce(string_agg(c.id::text, ',' order by c.id), '')
  from successbrian_os.pm_project_checks c
  where (select r.status from successbrian_os.pm_project_qa_runs r
          where r.check_id = c.id order by r.ran_at desc limit 1) = 'fail';
select 'GAMMA_AGE_MIN', coalesce(round(extract(epoch from (now() - max(created_at)))/60)::int, -1)
  from successbrian_os.logs where source_agent = 'gamma';
select 'PRICE_EXPIRED', count(*) from successbrian_os.price_intel
  where valid_until is not null and valid_until < current_date;
select 'ISSUES_OPEN', count(*) from altair.issues
  where status not in ('closed','done','resolved');
"""


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {"seen": {}, "raw_history": [], "cycles": 0}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE_FILE)


def alpha_query() -> dict | None:
    cmd = SSH + [f'psql ecosystem_central -Atc "{SQL}"']
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except Exception as e:  # noqa: BLE001
        print(f"!! ecosystem unreachable: {e}")
        return None
    if r.returncode != 0:
        print(f"!! ecosystem query failed: {(r.stderr or '').strip()[:300]}")
        return None
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 2:
            out[parts[0]] = parts[1]
    return out


def file_finding(title: str, context: str, raw: str) -> str:
    r = subprocess.run(
        [sys.executable, str(TOOLS / "bridge_dump.py"), "capture",
         "--kind", "discovery", "--title", title,
         "--context", context, "--raw", raw],
        capture_output=True, text=True, timeout=120)
    return (r.stdout or r.stderr or "").strip()[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-file", action="store_true",
                    help="report only; do not file findings to the Intel Bridge")
    ap.add_argument("--json", action="store_true", help="JSON report")
    args = ap.parse_args()

    now = datetime.now(TZ)
    state = load_state()
    data = alpha_query()
    if data is None:
        return 2

    raw = int(data.get("RAW", -1))
    qa_fail = int(data.get("QA_FAIL", -1))
    qa_ids = data.get("QA_FAIL_IDS", "")
    gamma_age = int(data.get("GAMMA_AGE_MIN", -1))
    price_expired = int(data.get("PRICE_EXPIRED", -1))
    issues_open = int(data.get("ISSUES_OPEN", -1))

    # backlog trend: last 3 raw counts including this one
    hist = (state.get("raw_history", []) + [raw])[-3:]
    state["raw_history"] = hist

    findings = []  # (key, title, context, raw_detail)

    if gamma_age < 0 or gamma_age > 60:
        findings.append((
            f"gamma_silent:{gamma_age // 60 if gamma_age >= 0 else 'never'}",
            "Spencer cycle: gamma road silent",
            "spencer_cycle.py 20-minute self-check (Brian's order 2026-11-11): "
            "gamma liveness check on successbrian_os.logs.",
            f"gamma_age_min={gamma_age} at {now.isoformat()} — no gamma log "
            f"rows within the 60-minute threshold (or none ever)."))
    if qa_fail > 0:
        findings.append((
            f"qa_failing:{qa_ids}",
            f"Spencer cycle: {qa_fail} QA checks failing",
            "spencer_cycle.py 20-minute self-check: QA layer read from "
            "successbrian_os.pm_project_checks / pm_project_qa_runs (latest run per check).",
            f"failing_check_ids={qa_ids} at {now.isoformat()}"))
    if price_expired > 0:
        findings.append((
            f"price_expired:{price_expired}:{now.date()}",
            f"Spencer cycle: {price_expired} price_intel rows past shelf life",
            "spencer_cycle.py 20-minute self-check: price_intel valid_until "
            "has passed; per Brian's 2026-10-25 rule these resurface for recheck.",
            f"expired_count={price_expired} at {now.isoformat()}"))
    if len(hist) == 3 and hist[0] < hist[1] < hist[2] and raw >= 10:
        findings.append((
            f"backlog_growing:{hist}",
            "Spencer cycle: raw capture backlog growing 3 cycles in a row",
            "spencer_cycle.py 20-minute self-check: atlas.scattered_captures "
            "status='raw' rose across three consecutive cycles while >=10 — "
            "the clerk/gamma road is not keeping up with intake.",
            f"raw_history={hist} at {now.isoformat()}"))

    new_filed = []
    for key, title, ctx, raw_detail in findings:
        if key not in state["seen"]:
            state["seen"][key] = now.isoformat()
            if not args.no_file:
                new_filed.append(f"{title} -> {file_finding(title, ctx, raw_detail)}")
            else:
                new_filed.append(f"{title} -> (not filed, --no-file)")

    state["cycles"] = state.get("cycles", 0) + 1
    state["last_cycle"] = now.isoformat()
    save_state(state)

    report = {
        "cycle_at": now.isoformat(),
        "raw_captures": raw,
        "qa_failing": qa_fail,
        "qa_failing_ids": qa_ids,
        "gamma_age_min": gamma_age,
        "price_expired": price_expired,
        "issues_open": issues_open,
        "findings_active": [k for k, *_ in findings],
        "findings_new_filed": new_filed,
        "cycles_total": state["cycles"],
    }
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        status = "FINDINGS" if findings else "all clear"
        print(f"[spencer-cycle {now.strftime('%H:%M')}] {status}: "
              f"raw={raw} qa_fail={qa_fail} gamma_age={gamma_age}m "
              f"price_expired={price_expired} issues_open={issues_open}")
        for f in new_filed:
            print(f"  filed: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
