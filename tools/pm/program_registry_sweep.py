#!/usr/bin/env python3
"""program_registry_sweep.py — the intended-function registry sweep.

Brian 2026-11-19: "we may need a better system of tracking what
software is actually supposed to do, and regular checks through that
documentation to make sure it's actually doing it — especially as we
do updates to code and functions." And: "Brian doesn't look. The
system needs to look for me."

Modelled on tools/pm/ruling_census_sweep.py (the pattern Brian
already trusts) and homed in Lyra (Brian 2026-11-19: "is this
something for that lyra table/dashboard?" — yes):

- the registry lives in successbrian_os.program_registry (one row per
  program: stated job in plain words, how doing-the-job is
  observable, expected cadence);
- this sweep probes every watched row (Lyra heartbeat age, output
  table freshness, log mtime, systemd unit active, QA check state),
  stamps last_proof_at / last_status back onto the row — that table
  IS the exception state the review-pass toolkit reads;
- exceptions file as ONE Intel Bridge capture per changed exception
  set, surfacing through the clerk and the twice-daily review passes
  (chat is the communicator; Brian never opens a dashboard);
- the sweep heartbeats DIRECTLY into Lyra's worker_heartbeats every
  run as 'program-registry-sweep', and is bound into the rulings
  census (row: program registry) so the watcher is watched;
- Lyra's status surface is the view successbrian_os.lyra_program_status
  (registry joined to Lyra heartbeats — stated job + cadence +
  last-proven-doing-it + exception state, beside the other workers).

Modes: run | dry-run | selftest. Exit 0 on a completed sweep —
finding exceptions is a success, not a failure.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common  # noqa: E402

STATE_FILE = os.path.expanduser("~/logs/.program_registry_sweep_state.json")
WORKER = "program-registry-sweep"


# ---------------------------------------------------------------- probes
def probe_heartbeat(ref):
    return sbos_common.pg_one(
        "SELECT last_heartbeat FROM successbrian_os.worker_heartbeats "
        "WHERE worker_name = %s", (ref,))


def probe_log_mtime(ref):
    try:
        return datetime.fromtimestamp(os.path.getmtime(ref),
                                      tz=timezone.utc)
    except OSError:
        return None


def probe_table_fresh(ref):
    # ref = schema.table:ts_column
    try:
        target, col = ref.rsplit(":", 1)
        schema, table = target.split(".", 1)
    except ValueError:
        return None
    return sbos_common.pg_one(
        'SELECT max("%s") FROM "%s"."%s"' % (col, schema, table))


def probe_service(ref):
    try:
        out = subprocess.run(["systemctl", "is-active", ref],
                             capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    if out.stdout.strip() == "active":
        return datetime.now(timezone.utc)
    return None


def probe_qa_check(ref):
    row = sbos_common.pg_one(
        "SELECT last_run_at, last_status FROM "
        "successbrian_os.pm_project_checks WHERE id = %s", (int(ref),))
    if not row:
        return None, None
    return row[0], row[1]


def probe_service_exit(ref):
    """Timer-triggered oneshot units sit 'inactive' between runs, so
    is-active is the wrong probe: use the unit's last exit stamp."""
    try:
        out = subprocess.run(
            ["systemctl", "show", ref, "--property=ExecMainExitTimestamp",
             "--property=Result"], capture_output=True, text=True,
            timeout=15)
    except Exception:
        return None
    props = {}
    for line in out.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    if props.get("Result") != "success":
        return None
    raw = props.get("ExecMainExitTimestamp", "")
    if not raw:
        return None
    # NOTE: no strptime — successbrian-os/tools shadows the stdlib
    # 'calendar' module, which strptime depends on. Parse numerically.
    try:
        from zoneinfo import ZoneInfo
        parts = raw.split()
        y, mo, d = (int(x) for x in parts[1].split("-"))
        hh, mm, ss = (int(x) for x in parts[2].split(":"))
        return datetime(y, mo, d, hh, mm, ss,
                        tzinfo=ZoneInfo("America/Chicago"))
    except Exception:
        return None


PROBES = {"heartbeat": probe_heartbeat, "log_mtime": probe_log_mtime,
          "table_fresh": probe_table_fresh, "service": probe_service,
          "service_exit": probe_service_exit}


def evaluate(row, proof, qa_status, now):
    """Pure: row is a registry dict; returns (status, exception|None)."""
    if row["watch_state"] != "watched":
        return "manual", None
    if row["probe_kind"] == "qa_check" and qa_status == "fail":
        return "failing", (f"FAILING: {row['name']} — its QA check is "
                           f"red ({row['probe_ref']})")
    if proof is None:
        return "no_proof", (f"NO PROOF: {row['name']} — probe "
                            f"{row['probe_kind']}:{row['probe_ref']} "
                            f"returned nothing")
    age_min = (now - proof).total_seconds() / 60.0
    if age_min > row["expected_cadence_min"]:
        return "stale", (f"STALE: {row['name']} — last proof "
                         f"{int(age_min)}m ago, cadence allows "
                         f"{row['expected_cadence_min']}m "
                         f"({row['probe_kind']}:{row['probe_ref']})")
    return "ok", None


def load_rows():
    cols = ("id, program_key, name, stated_job, probe_kind, probe_ref, "
            "expected_cadence_min, watch_state")
    return [dict(zip(
        ["id", "program_key", "name", "stated_job", "probe_kind",
         "probe_ref", "expected_cadence_min", "watch_state"], r))
        for r in sbos_common.pg_rows(
            f"SELECT {cols} FROM successbrian_os.program_registry "
            "ORDER BY id")]


def heartbeat(summary):
    sbos_common.pg_exec(
        "INSERT INTO successbrian_os.worker_heartbeats "
        "(worker_name, last_heartbeat, last_status, last_error, "
        "is_important, last_run_output) VALUES "
        "(%s, now(), 'ok', NULL, true, %s) "
        "ON CONFLICT (worker_name) DO UPDATE SET "
        "last_heartbeat = now(), last_status = 'ok', "
        "last_error = NULL, last_run_output = EXCLUDED.last_run_output",
        (WORKER, summary))


def file_capture(lines, today):
    body = "\n".join(lines)
    sbos_common.pg_exec(
        "INSERT INTO atlas.scattered_captures (title, raw_text, "
        "context) VALUES (%s, %s, %s)",
        (f"PROGRAM REGISTRY — exceptions {today.isoformat()}", body,
         "Filed by tools/pm/program_registry_sweep.py on alpha: a "
         "registered program has no fresh proof it is doing its "
         "stated job (successbrian_os.program_registry; Lyra surface "
         "successbrian_os.lyra_program_status). Brian does not look "
         "at boards — surface these in the review passes. Design: "
         "~/workspace/builds/intended-function-registry-design-"
         "2026-11-19.md."))


def sweep(dry=False):
    rows = load_rows()
    now = datetime.now(timezone.utc)
    lines = []
    for row in rows:
        proof, qa_status = None, None
        kind = row["probe_kind"]
        if row["watch_state"] == "watched":
            try:
                if kind == "qa_check":
                    proof, qa_status = probe_qa_check(row["probe_ref"])
                elif kind in PROBES:
                    proof = PROBES[kind](row["probe_ref"])
            except Exception:
                proof = None
            if proof is not None and proof.tzinfo is None:
                proof = proof.replace(tzinfo=timezone.utc)
        status, exc = evaluate(row, proof, qa_status, now)
        if exc:
            lines.append(exc)
        if not dry:
            sbos_common.pg_exec(
                "UPDATE successbrian_os.program_registry SET "
                "last_status = %s, last_sweep_at = now(), "
                "last_proof_at = COALESCE(%s, last_proof_at), "
                "updated_at = now() WHERE id = %s",
                (status, proof, row["id"]))
    today = date.today()
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
    watched = sum(1 for r in rows if r["watch_state"] == "watched")
    summary = (f"{len(rows)} registry rows ({watched} watched), "
               f"{len(lines)} exceptions"
               + ("; capture filed" if filed else ""))
    if not dry:
        heartbeat(summary)
        state["hash"] = digest if lines else None
        state["last_run"] = now.isoformat()
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        json.dump(state, open(STATE_FILE, "w"), indent=1)
    print(summary)
    for ln in lines:
        print("  " + ln)
    return 0


# ---------------------------------------------------------------- selftest
def selftest():
    checks = []

    def chk(name, cond):
        checks.append((name, bool(cond)))

    now = datetime.now(timezone.utc)
    base = {"name": "demo", "probe_kind": "log_mtime",
            "probe_ref": "/tmp/x.log", "expected_cadence_min": 120,
            "watch_state": "watched"}
    st, exc = evaluate(dict(base), now - timedelta(minutes=30), None, now)
    chk("fresh proof is ok", st == "ok" and exc is None)
    st, exc = evaluate(dict(base), now - timedelta(minutes=300), None, now)
    chk("old proof is stale", st == "stale" and exc is not None)
    st, exc = evaluate(dict(base), None, None, now)
    chk("missing proof fires", st == "no_proof" and exc is not None)
    st, exc = evaluate(dict(base, watch_state="manual"), None, None, now)
    chk("manual rows skipped", st == "manual" and exc is None)
    st, exc = evaluate(dict(base, probe_kind="qa_check", probe_ref="1"),
                       now, "fail", now)
    chk("red QA check fires", st == "failing" and exc is not None)
    st, exc = evaluate(dict(base, probe_kind="qa_check", probe_ref="1"),
                       now, "pass", now)
    chk("green QA check ok", st == "ok")
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(("  ok  " if ok else "  FAIL") + " " + n)
    if failed:
        print("SELFTEST FAIL")
        return 1
    print(f"SELFTEST OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "selftest":
        sys.exit(selftest())
    elif mode == "dry-run":
        sys.exit(sweep(dry=True))
    elif mode == "run":
        sys.exit(sweep())
    else:
        print(__doc__)
        sys.exit(2)
