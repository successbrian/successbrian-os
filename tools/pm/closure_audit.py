#!/usr/bin/env python3
"""Closure auditor — the fix for the open closing end.

Brian's diagnosis (2026-10-24): the usual agentic loop leaves the
closing end open — work declared done on say-so, sessions ending with
loose ends nobody owns. This auditor is the mechanical counterweight.
Every 15 minutes it hunts open ends in the PM and files them back as
work, so an unfinished ending cannot evaporate:

  1. STUCK RUNNING: a step left 'running' past its kind's TTL by any
     actor (the runner's reaper covers only its own steps) is requeued,
     with a decision written to the stream.
  2. PROOFLESS DONE: steps finished in the last 24h with no result
     recorded are counted and filed as one audit step. Done means
     verified; a done with no proof is an open end wearing a costume.
  3. UNCOMMITTED WORK: files under tools/pm/ left dirty in git for
     over 2 hours are filed as a step — the exact failure Brian caught
     by hand on 2026-10-24 ('i never said hold off').
  4. DEAD LOOP CRONS: if a loop tool's log goes stale past its cadence,
     the loop has silently died — filed as a step before it rots.

Every pass also rewrites state/OPEN_ENDS.md, the standing answer to
'what is still open?' Deterministic code only; no model calls.
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

HOME = os.path.expanduser("~")
REPO = os.path.join(HOME, "successbrian-os")
STATE_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "state", "OPEN_ENDS.md")
TTL_S = {"command": 1800, "judgment": 3600, "build": 86400}
TTL_DEFAULT = 43200
LOG_LIMITS = {"pm-runner.log": 900, "chat-brief.log": 900,
              "repair-ladder.log": 1800, "pm-dashboard.log": 900,
              "morpheus-worker.log": 900}
GIT_PATH_PREFIX = "tools/pm/"
GIT_STALE_S = 7200


def open_step_exists(cur, key):
    cur.execute(
        """SELECT 1 FROM successbrian_os.pm_steps
            WHERE step_key=%s AND status IN ('queued','running','held_brian')""",
        (key,))
    return cur.fetchone() is not None


def ensure_step(cur, key, title, kind, priority, payload=None):
    if not open_step_exists(cur, key):
        pm_core.add_step(cur, key, title, kind=kind, origin="system",
                         priority=priority, payload=payload or {})
        return True
    return False


def check_stuck_running(cur, findings):
    cur.execute(
        """SELECT step_key, kind, actor,
                  EXTRACT(EPOCH FROM (now() - heartbeat_at)) AS age_s
             FROM successbrian_os.pm_steps
            WHERE status='running'
              AND (actor IS NULL OR actor NOT LIKE 'pm-runner%%')""")
    for r in cur.fetchall():
        key = r["step_key"] if isinstance(r, dict) else r[0]
        kind = r["kind"] if isinstance(r, dict) else r[1]
        age = float(r["age_s"] if isinstance(r, dict) else r[3])
        if age > TTL_S.get(kind, TTL_DEFAULT):
            cur.execute(
                """UPDATE successbrian_os.pm_steps
                      SET status='queued', actor=NULL, started_at=NULL,
                          updated_at=now()
                    WHERE step_key=%s""", (key,))
            pm_core.decide(
                cur, "closure-auditor",
                f"Requeued stuck step {key} (running {age/3600:.1f}h, "
                f"actor gone) — closing end was open", step_key=key,
                origin="system")
            findings.append(f"stuck running requeued: {key}")


def check_proofless_done(cur, findings):
    cur.execute(
        """SELECT step_key FROM successbrian_os.pm_steps
            WHERE status='done' AND finished_at > now() - interval '24 hours'
              AND (result IS NULL OR result = '{}'::jsonb)""")
    keys = [r["step_key"] if isinstance(r, dict) else r[0]
            for r in cur.fetchall()]
    if keys:
        if ensure_step(cur, "closure-missing-proof",
                       f"{len(keys)} step(s) marked done in 24h with no "
                       f"result recorded — done without proof",
                       kind="review", priority=65,
                       payload={"proofless": keys[:20]}):
            pm_core.decide(cur, "closure-auditor",
                           f"Filed closure audit step: {len(keys)} proofless "
                           f"done(s) in 24h", origin="system")
            findings.append(f"proofless done filed: {len(keys)}")


def check_uncommitted(cur, findings):
    try:
        out = subprocess.run(["git", "-C", REPO, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return
    dirty = []
    newest = 0.0
    for line in out.splitlines():
        path = line[3:].strip()
        if path.startswith(GIT_PATH_PREFIX):
            dirty.append(path)
            try:
                newest = max(newest, os.path.getmtime(os.path.join(REPO, path)))
            except OSError:
                pass
    if dirty and time.time() - newest > GIT_STALE_S:
        if ensure_step(cur, "closure-uncommitted-work",
                       f"Uncommitted work under tools/pm/ older than 2h: "
                       f"{len(dirty)} file(s)",
                       kind="build", priority=55, payload={"files": dirty[:20]}):
            pm_core.decide(cur, "closure-auditor",
                           "Filed closure audit step: uncommitted tools/pm "
                           "work older than 2h", origin="system")
            findings.append(f"uncommitted work filed: {len(dirty)} file(s)")


def check_dead_logs(cur, findings):
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True,
                              text=True, timeout=15).stdout
    except Exception:
        cron = ""
    tool_of = {"pm-runner.log": "pm_runner", "chat-brief.log": "chat_brief",
               "repair-ladder.log": "repair_ladder",
               "pm-dashboard.log": "dashboard",
               "morpheus-worker.log": "morpheus_worker"}
    for log, limit in LOG_LIMITS.items():
        if tool_of[log] not in cron:
            continue
        path = os.path.join(HOME, "logs", log)
        age = (time.time() - os.path.getmtime(path)) if os.path.exists(path) \
            else None
        if age is None or age > limit:
            key = f"closure-stale-log-{log.replace('.log', '')}"
            if ensure_step(cur, key,
                           f"Loop cron log {log} is stale "
                           f"({'missing' if age is None else f'{age/60:.0f}m old'}) "
                           f"— the loop may have silently died",
                           kind="repair", priority=70):
                pm_core.decide(cur, "closure-auditor",
                               f"Filed closure audit step: stale loop log {log}",
                               origin="system")
                findings.append(f"stale log filed: {log}")


def write_open_ends(cur, findings):
    cur.execute(
        """SELECT status, count(*) AS n FROM successbrian_os.pm_steps
            GROUP BY status ORDER BY status""")
    counts = {r["status"] if isinstance(r, dict) else r[0]:
              r["n"] if isinstance(r, dict) else r[1] for r in cur.fetchall()}
    cur.execute(
        """SELECT step_key, title, priority,
                  EXTRACT(EPOCH FROM (now() - created_at))/86400 AS age_d
             FROM successbrian_os.pm_steps WHERE status='queued'
            ORDER BY created_at LIMIT 5""")
    oldest = cur.fetchall()
    lines = ["# Open ends — closure auditor",
             f"Steps: " + ", ".join(f"{k} {v}" for k, v in
                                     sorted(counts.items()))]
    for r in oldest:
        k = r["step_key"] if isinstance(r, dict) else r[0]
        t = r["title"] if isinstance(r, dict) else r[1]
        a = float(r["age_d"] if isinstance(r, dict) else r[3])
        lines.append(f"- queued {a:.1f}d: {t} [{k}]")
    if findings:
        lines.append("Latest findings: " + "; ".join(findings))
    os.makedirs(os.path.dirname(STATE_OUT), exist_ok=True)
    with open(STATE_OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    return lines


def run_pass():
    c = pm_core.conn()
    cur = c.cursor()
    findings = []
    check_stuck_running(cur, findings)
    check_proofless_done(cur, findings)
    check_uncommitted(cur, findings)
    check_dead_logs(cur, findings)
    lines = write_open_ends(cur, findings)
    c.commit()
    c.close()
    for line in lines + findings:
        print(line)
    return findings


def selftest():
    tag = f"closure-audit-selftest-{int(time.time())}"
    c = pm_core.conn()
    cur = c.cursor()
    pm_core.add_step(cur, f"{tag}-stuck", "stuck running test step",
                     kind="command", priority=90)
    cur.execute(
        """UPDATE successbrian_os.pm_steps
              SET status='running', actor='audit-test',
                  started_at=now() - interval '3 hours',
                  heartbeat_at=now() - interval '3 hours'
            WHERE step_key=%s""", (f"{tag}-stuck",))
    pm_core.add_step(cur, f"{tag}-done", "proofless done test step",
                     kind="command", priority=90)
    cur.execute(
        """UPDATE successbrian_os.pm_steps
              SET status='done', finished_at=now(), result=NULL
            WHERE step_key=%s""", (f"{tag}-done",))
    c.commit()
    c.close()
    findings = run_pass()
    assert any("stuck running requeued" in f for f in findings), findings
    print("PASS stuck running step requeued by the auditor")
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute("SELECT status FROM successbrian_os.pm_steps WHERE step_key=%s",
                (f"{tag}-stuck",))
    row = cur.fetchone()
    assert (row["status"] if isinstance(row, dict) else row[0]) == "queued"
    assert open_step_exists(cur, "closure-missing-proof"), \
        "proofless-done audit step not filed"
    print("PASS proofless done filed as an audit step")
    cur.execute("DELETE FROM successbrian_os.pm_steps WHERE step_key LIKE %s",
                (tag + "%",))
    cur.execute("DELETE FROM successbrian_os.pm_decisions WHERE decision LIKE %s",
                (f"%{tag}%",))
    c.commit()
    c.close()
    print("PASS cleanup — closure auditor selftest green")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Closure auditor")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if args.once:
        run_pass()
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
