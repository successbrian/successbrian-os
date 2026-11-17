#!/usr/bin/env python3
"""ruling_census_sweep.py — the rulings census exception sweep.

Brian 2026-11-17: "this liveness check should be part of lyra/
successbrian os, right?" — yes. The census table and its QA probes
already live in SBOS; this sweep is the comparison step, and it runs
ON ALPHA every 30 minutes instead of on a cloud agent's cron:

- joins successbrian_os.ruling_census to its probes
  (pm_project_checks) and computes exceptions: a probe FAILING, a
  probe that has not run in 48h (the probe itself died), and — on
  Mondays only — rows marked gap;
- files exceptions as ONE Intel Bridge capture per changed
  exception set, so they surface through the ecosystem's own
  intake (clerk sorts them like everything else);
- writes its heartbeat DIRECTLY into Lyra's table every run
  (worker 'ruling-census-sweep', Brian's standing law) — if this
  sweep dies, Lyra's staleness watch flags the watcher itself.

Modes: run | dry-run | selftest. Exit 0 on a completed sweep —
finding exceptions is a success, not a failure.
"""
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common  # noqa: E402

STATE_FILE = os.path.expanduser("~/logs/.ruling_census_sweep_state.json")
STALE_AFTER = timedelta(hours=48)


def exceptions_from(rows, today):
    """Pure: rows are (id, ruling, subject, status, qa_check_id,
    check_key, last_status, last_run_at). Returns exception lines."""
    out = []
    now = datetime.now(timezone.utc)
    for (cid, ruling, subject, status, qa_id, check_key,
         last_status, last_run_at) in rows:
        if status == "gap":
            if today.weekday() == 0:  # Mondays: weekly gap reminder
                out.append(f"GAP (known, standing): {ruling} "
                           f"[{subject}]")
            continue
        if qa_id is None:
            continue  # manual rows are review items, not exceptions
        if last_status == "fail":
            out.append(f"PROBE FAILING: {ruling} [{subject}] "
                       f"(check {check_key})")
        elif last_run_at is None or now - last_run_at > STALE_AFTER:
            out.append(f"PROBE STALE (not run in 48h): {ruling} "
                       f"[{subject}] (check {check_key})")
    return out


def load_rows():
    return sbos_common.pg_rows(
        "SELECT c.id, c.ruling, c.subject, c.status, c.qa_check_id, "
        "q.check_key, q.last_status, q.last_run_at "
        "FROM successbrian_os.ruling_census c "
        "LEFT JOIN successbrian_os.pm_project_checks q "
        "ON q.id = c.qa_check_id ORDER BY c.id")


def heartbeat(summary):
    sbos_common.pg_exec(
        "INSERT INTO successbrian_os.worker_heartbeats "
        "(worker_name, last_heartbeat, last_status, last_error, "
        "is_important, last_run_output) VALUES "
        "('ruling-census-sweep', now(), 'ok', NULL, true, %s) "
        "ON CONFLICT (worker_name) DO UPDATE SET "
        "last_heartbeat = now(), last_status = 'ok', "
        "last_error = NULL, last_run_output = EXCLUDED.last_run_output",
        (summary,))


def file_capture(lines, today):
    body = "\n".join(lines)
    sbos_common.pg_exec(
        "INSERT INTO atlas.scattered_captures (title, raw_text, "
        "context) VALUES (%s, %s, %s)",
        (f"RULINGS CENSUS — exceptions {today.isoformat()}", body,
         "Filed by tools/pm/ruling_census_sweep.py on alpha: a "
         "standing ruling's liveness probe is failing, stale, or a "
         "known gap (Monday reminder). Repairs happen in chat with "
         "Brian; the census table is successbrian_os.ruling_census."))


def sweep(dry=False):
    rows = load_rows()
    today = date.today()
    lines = exceptions_from(rows, today)
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            state = json.load(open(STATE_FILE))
        except Exception:
            state = {}
    filed = False
    if lines and state.get("hash") != digest and not dry:
        file_capture(lines, today)
        filed = True
    summary = (f"{len(rows)} census rows, {len(lines)} exceptions"
               + ("; capture filed" if filed else ""))
    if not dry:
        heartbeat(summary)
        state["hash"] = digest if lines else None
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        json.dump(state, open(STATE_FILE, "w"), indent=1)
    print(summary)
    for ln in lines:
        print("  " + ln)
    return 0


def selftest():
    failures = []

    def check(name, got, want):
        ok = got == want
        print(f"  [{'ok' if ok else 'FAIL'}] {name}")
        if not ok:
            failures.append(name)

    now = datetime.now(timezone.utc)
    monday = date(2026, 11, 16)    # a Monday
    tuesday = date(2026, 11, 17)   # a Tuesday
    healthy = (1, "Rule A", "subj", "live", 10, "chk-a", "pass", now)
    failing = (2, "Rule B", "subj", "live", 11, "chk-b", "fail", now)
    stale = (3, "Rule C", "subj", "live", 12, "chk-c", "pass",
             now - timedelta(hours=72))
    never = (4, "Rule D", "subj", "live", 13, "chk-d", None, None)
    gap = (5, "Rule E", "subj", "gap", None, None, None, None)
    manual = (6, "Rule F", "subj", "manual", None, None, None, None)
    rows = [healthy, failing, stale, never, gap, manual]
    tue = exceptions_from(rows, tuesday)
    check("tuesday: failing probe flagged", len(
        [x for x in tue if "Rule B" in x]), 1)
    check("tuesday: stale probe flagged", len(
        [x for x in tue if "Rule C" in x]), 1)
    check("tuesday: never-run probe flagged", len(
        [x for x in tue if "Rule D" in x]), 1)
    check("tuesday: gap NOT flagged", len(
        [x for x in tue if "Rule E" in x]), 0)
    check("tuesday: healthy and manual silent", len(tue), 3)
    mon = exceptions_from(rows, monday)
    check("monday: gap flagged", len(
        [x for x in mon if "Rule E" in x]), 1)
    check("monday: total exceptions", len(mon), 4)
    print("CENSUS SWEEP SELFTEST:", "OK" if not failures
          else f"FAILED: {failures}")
    return 0 if not failures else 1


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "selftest":
        return selftest()
    if mode == "dry-run":
        return sweep(dry=True)
    if mode == "run":
        return sweep()
    print("usage: ruling_census_sweep.py [run|dry-run|selftest]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
