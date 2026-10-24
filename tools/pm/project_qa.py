#!/usr/bin/env python3
"""Project registry + long-term QA — Brian's rule (2026-10-24).

When Brian asks Spencer (or any agent) to do something that is a
PROJECT, the project gets registered here, in SuccessBrian OS — so the
ecosystem tracks it after the conversation ends, and Spencer and the
other agents can QA-test it long term.

A project is a row in successbrian_os.pm_projects. Its QA checks are
rows in pm_project_checks, each with its own cadence:
  * command  — run an argv list; pass = exit 0 (+ optional substring).
  * http     — GET a URL; pass = expected status (+ optional substring).
  * judgment — filed as a Morpheus-sized PM step (kind 'judgment');
               pass/fail reconciles when the worker finishes it.

The runner (run-due, cron every 30 min) executes due checks, records
every run in pm_project_qa_runs, and on failure files a PM repair step
(deduped) and writes a decision. A check that passes again closes its
own repair step. Registration itself writes a decision, so a project
Brian asked for is on the record from minute one — never just a chat
promise. Deterministic code; judgment checks route through the
Morpheus worker like everything else.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

REPO = os.path.expanduser("~/successbrian-os")


def dict_conn():
    import psycopg2.extras
    return pm_core.psycopg2.connect(
        dbname="ecosystem_central", host="localhost",
        cursor_factory=psycopg2.extras.RealDictCursor)


def ensure_schema(cur):
    cur.execute(
        """CREATE TABLE IF NOT EXISTS successbrian_os.pm_projects (
             project_key TEXT PRIMARY KEY, title TEXT NOT NULL,
             requested_by TEXT, owner_agent TEXT,
             status TEXT NOT NULL DEFAULT 'active',
             description TEXT,
             created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
             updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    cur.execute(
        """CREATE TABLE IF NOT EXISTS successbrian_os.pm_project_checks (
             id SERIAL PRIMARY KEY,
             project_key TEXT NOT NULL
               REFERENCES successbrian_os.pm_projects(project_key),
             check_key TEXT NOT NULL, title TEXT NOT NULL,
             check_type TEXT NOT NULL
               CHECK (check_type IN ('command','http','judgment')),
             spec JSONB NOT NULL DEFAULT '{}'::jsonb,
             interval_s INT NOT NULL DEFAULT 86400,
             enabled BOOLEAN NOT NULL DEFAULT true,
             last_run_at TIMESTAMPTZ, last_status TEXT,
             next_due_at TIMESTAMPTZ,
             created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
             UNIQUE (project_key, check_key))""")
    cur.execute(
        """CREATE TABLE IF NOT EXISTS successbrian_os.pm_project_qa_runs (
             id SERIAL PRIMARY KEY,
             check_id INT NOT NULL
               REFERENCES successbrian_os.pm_project_checks(id),
             ran_at TIMESTAMPTZ NOT NULL DEFAULT now(),
             status TEXT NOT NULL, detail JSONB,
             pm_step_key TEXT)""")


def register_project(cur, key, title, requested_by=None, owner=None,
                     description=None, registrar="spencer"):
    cur.execute(
        """INSERT INTO successbrian_os.pm_projects
             (project_key, title, requested_by, owner_agent, description)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (project_key) DO UPDATE
             SET title=EXCLUDED.title, updated_at=now()
           RETURNING project_key""", (key, title, requested_by, owner,
                                      description))
    pm_core.decide(
        cur, registrar,
        f"Registered project '{key}' ({title}) in SuccessBrian OS for "
        f"long-term tracking and QA",
        why=f"requested_by={requested_by or 'unknown'}; "
            f"owner={owner or 'unassigned'}",
        origin="system")
    return key


def add_check(cur, project, check_key, title, check_type, spec, interval_s):
    cur.execute(
        """INSERT INTO successbrian_os.pm_project_checks
             (project_key, check_key, title, check_type, spec, interval_s,
              next_due_at)
           VALUES (%s, %s, %s, %s, %s::jsonb, %s, now())
           ON CONFLICT (project_key, check_key) DO UPDATE
             SET title=EXCLUDED.title, check_type=EXCLUDED.check_type,
                 spec=EXCLUDED.spec,
                 interval_s=EXCLUDED.interval_s, enabled=true
           RETURNING id""", (project, check_key, title, check_type,
                             json.dumps(spec), interval_s))
    row = cur.fetchone()
    return row["id"] if isinstance(row, dict) else row[0]


def record_run(cur, check_id, status, detail=None, pm_step_key=None):
    cur.execute(
        """INSERT INTO successbrian_os.pm_project_qa_runs
             (check_id, status, detail, pm_step_key)
           VALUES (%s, %s, %s::jsonb, %s)""",
        (check_id, status, json.dumps(detail or {}), pm_step_key))


def mark_check(cur, check, status, advance=True):
    if advance:
        cur.execute(
            """UPDATE successbrian_os.pm_project_checks
                  SET last_run_at=now(), last_status=%s,
                      next_due_at=now() + (%s || ' seconds')::interval
                WHERE id=%s""", (status, str(check["interval_s"]), check["id"]))
    else:
        cur.execute(
            """UPDATE successbrian_os.pm_project_checks
                  SET last_run_at=now(), last_status=%s WHERE id=%s""",
            (status, check["id"]))


def repair_step_key(check):
    return f"qa-fail-{check['project_key']}-{check['check_key']}"


def on_fail(cur, check, detail):
    key = repair_step_key(check)
    cur.execute(
        "SELECT 1 FROM successbrian_os.pm_steps WHERE step_key=%s "
        "AND status IN ('queued','running','held_brian')", (key,))
    if cur.fetchone() is None:
        pm_core.add_step(
            cur, key,
            f"QA failing: {check['project_key']}/{check['check_key']} — "
            f"{check['title']}", kind="repair", origin="system", priority=75,
            payload={"qa_check_id": check["id"], "detail": detail})
    if check["last_status"] != "fail":
        pm_core.decide(cur, "project-qa",
                       f"QA FAIL: {check['project_key']}/"
                       f"{check['check_key']} — repair step filed",
                       origin="system")


def on_pass(cur, check):
    key = repair_step_key(check)
    cur.execute(
        "SELECT status FROM successbrian_os.pm_steps WHERE step_key=%s", (key,))
    row = cur.fetchone()
    if row and (row["status"] if isinstance(row, dict) else row[0]) \
            in ("queued", "running", "held_brian"):
        pm_core.finish(cur, key, "done", {"note": "QA passing again"})
    if check["last_status"] == "fail":
        pm_core.decide(cur, "project-qa",
                       f"QA PASS again: {check['project_key']}/"
                       f"{check['check_key']} — repair step closed",
                       origin="system")


def run_command_check(spec):
    cmd = spec.get("cmd") or []
    if not cmd:
        return "fail", {"why": "command check without spec.cmd"}
    try:
        proc = subprocess.run(cmd, cwd=spec.get("cwd", REPO),
                              capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              timeout=int(spec.get("timeout_s", 300)))
        detail = {"exit": proc.returncode,
                  "stdout_tail": (proc.stdout or "")[-800:],
                  "stderr_tail": (proc.stderr or "")[-400:]}
        ok = proc.returncode == 0
        if ok and spec.get("contains"):
            ok = spec["contains"] in (proc.stdout or "")
            detail["contains"] = spec["contains"]
        return ("pass" if ok else "fail"), detail
    except Exception as e:
        return "fail", {"why": f"{type(e).__name__}: {e}"}


def run_http_check(spec):
    url = spec.get("url")
    if not url:
        return "fail", {"why": "http check without spec.url"}
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
        ok = status == int(spec.get("expect_status", 200))
        if ok and spec.get("contains"):
            ok = spec["contains"] in body
        return ("pass" if ok else "fail"), {"status": status, "url": url}
    except Exception as e:
        return "fail", {"why": f"{type(e).__name__}: {e}", "url": url}


def run_judgment_check(check, spec):
    """Judgment checks manage their own short-lived connection and
    persist their own outcome; returns (status, detail) where status
    'queued'/'pending' means a Morpheus step is still working."""
    c = dict_conn()
    cur = c.cursor()
    cur.execute(
        """SELECT pm_step_key FROM successbrian_os.pm_project_qa_runs
            WHERE check_id=%s AND status='queued' AND pm_step_key IS NOT NULL
            ORDER BY id DESC LIMIT 1""", (check["id"],))
    row = cur.fetchone()
    if row:
        step_key = row["pm_step_key"] if isinstance(row, dict) else row[0]
        cur.execute("SELECT status, result FROM successbrian_os.pm_steps "
                    "WHERE step_key=%s", (step_key,))
        s = cur.fetchone()
        if s:
            st = s["status"] if isinstance(s, dict) else s[0]
            if st in ("queued", "running"):
                c.commit()
                c.close()
                return "pending", {}
            result = s["result"] if isinstance(s, dict) else s[1]
            status = "pass" if st == "done" else "fail"
            detail = {"judgment_step": step_key, "result": result}
            record_run(cur, check["id"], status, detail)
            if status == "fail":
                on_fail(cur, check, detail)
            else:
                on_pass(cur, check)
            mark_check(cur, check, status, advance=True)
            c.commit()
            c.close()
            return status, detail
    step_key = f"qa-{check['project_key']}-{check['check_key']}-{int(time.time())}"
    pm_core.add_step(
        cur, step_key,
        f"QA judgment: {check['project_key']}/{check['check_key']} — "
        f"{check['title']}", kind="judgment", origin="system", priority=45,
        payload={"instruction": spec.get("instruction", ""),
                 "context": spec.get("context", ""),
                 "output_keys": spec.get("output_keys", []),
                 "max_tokens": int(spec.get("max_tokens", 800))})
    record_run(cur, check["id"], "queued", {"filed_step": step_key},
               pm_step_key=step_key)
    mark_check(cur, check, "queued", advance=False)
    c.commit()
    c.close()
    return "queued", {"filed_step": step_key}


def fetch_due_checks():
    c = dict_conn()
    cur = c.cursor()
    ensure_schema(cur)
    cur.execute(
        """SELECT * FROM successbrian_os.pm_project_checks
            WHERE enabled AND (next_due_at IS NULL OR next_due_at <= now())
            ORDER BY project_key, check_key""")
    checks = [dict(r) for r in cur.fetchall()]
    c.commit()
    c.close()
    return checks


def persist_result(check, status, detail):
    """Record one finished check on a FRESH connection. The runner never
    holds a database connection open while an external check executes —
    a long check (or one that uses the DB itself) must not strand the
    runner's connection; that is what killed the first live run."""
    c = dict_conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM successbrian_os.pm_project_checks "
                "WHERE id=%s", (check["id"],))
    fresh = cur.fetchone()
    record_run(cur, check["id"], status, detail)
    if status == "fail":
        on_fail(cur, fresh, detail)
    else:
        on_pass(cur, fresh)
    mark_check(cur, fresh, status, advance=True)
    c.commit()
    c.close()


def run_due():
    checks = fetch_due_checks()
    lines = []
    for check in checks:
        spec = check["spec"] or {}
        if check["check_type"] == "command":
            status, detail = run_command_check(spec)
            persist_result(check, status, detail)
        elif check["check_type"] == "http":
            status, detail = run_http_check(spec)
            persist_result(check, status, detail)
        else:
            status, detail = run_judgment_check(check, spec)
        lines.append(f"{check['project_key']}/{check['check_key']}: "
                     f"{status.upper()}")
    for line in lines:
        print(line)
    if not lines:
        print("no QA checks due")
    return lines


def selftest():
    tag = f"project-qa-selftest-{int(time.time())}"
    c = dict_conn()
    cur = c.cursor()
    ensure_schema(cur)
    register_project(cur, tag, "QA selftest project", requested_by="selftest",
                     owner="spencer", registrar="project-qa-selftest")
    add_check(cur, tag, "ok-cmd", "passing command check", "command",
              {"cmd": ["python3", "-c", "print('qa-ok')"],
               "contains": "qa-ok"}, 0)
    add_check(cur, tag, "bad-cmd", "failing command check", "command",
              {"cmd": ["python3", "-c", "import sys; sys.exit(3)"]}, 0)
    c.commit()
    c.close()
    lines = run_due()
    joined = "\n".join(lines)
    assert f"{tag}/ok-cmd: PASS" in joined, lines
    assert f"{tag}/bad-cmd: FAIL" in joined, lines
    print("PASS project registered; passing check recorded as pass")
    c = dict_conn()
    cur = c.cursor()
    cur.execute(
        "SELECT 1 FROM successbrian_os.pm_steps WHERE step_key=%s "
        "AND status IN ('queued','running','held_brian')",
        (f"qa-fail-{tag}-bad-cmd",))
    assert cur.fetchone() is not None, "repair step not filed on QA failure"
    print("PASS QA failure filed a repair step in the PM")
    cur.execute(
        """DELETE FROM successbrian_os.pm_project_qa_runs
            WHERE check_id IN (SELECT id FROM
              successbrian_os.pm_project_checks WHERE project_key=%s)""",
        (tag,))
    cur.execute("DELETE FROM successbrian_os.pm_project_checks "
                "WHERE project_key=%s", (tag,))
    cur.execute("DELETE FROM successbrian_os.pm_projects "
                "WHERE project_key=%s", (tag,))
    cur.execute("DELETE FROM successbrian_os.pm_steps WHERE step_key LIKE %s",
                (f"qa-fail-{tag}-%",))
    cur.execute("DELETE FROM successbrian_os.pm_decisions "
                "WHERE decision LIKE %s", (f"%{tag}%",))
    c.commit()
    c.close()
    print("PASS cleanup — project QA selftest green")


def main(argv=None):
    ap = argparse.ArgumentParser(description="SBOS project registry + QA")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    rg = sub.add_parser("register")
    rg.add_argument("--key", required=True)
    rg.add_argument("--title", required=True)
    rg.add_argument("--requested-by")
    rg.add_argument("--owner")
    rg.add_argument("--description")
    rg.add_argument("--registrar", default="spencer")
    ac = sub.add_parser("add-check")
    ac.add_argument("--project", required=True)
    ac.add_argument("--key", required=True)
    ac.add_argument("--title", required=True)
    ac.add_argument("--type", required=True,
                    choices=["command", "http", "judgment"])
    ac.add_argument("--interval-min", type=int, default=1440)
    ac.add_argument("--spec", required=True, help="JSON spec for the check")
    sub.add_parser("run-due")
    sub.add_parser("list")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        selftest()
        return 0
    if args.cmd == "run-due":
        run_due()
        return 0
    c = dict_conn()
    cur = c.cursor()
    ensure_schema(cur)
    if args.cmd == "init":
        print("project registry schema ready")
    elif args.cmd == "register":
        register_project(cur, args.key, args.title, args.requested_by,
                         args.owner, args.description, args.registrar)
        print(f"registered project {args.key}")
    elif args.cmd == "add-check":
        cid = add_check(cur, args.project, args.key, args.title, args.type,
                        json.loads(args.spec), args.interval_min * 60)
        print(f"check {cid} added to {args.project}")
    elif args.cmd == "list":
        cur.execute(
            """SELECT p.project_key, p.title, p.status, c.check_key,
                      c.check_type, c.last_status, c.next_due_at
                 FROM successbrian_os.pm_projects p
                 LEFT JOIN successbrian_os.pm_project_checks c
                   ON c.project_key = p.project_key
                ORDER BY p.project_key, c.check_key""")
        for r in cur.fetchall():
            print(f"{r['project_key']} [{r['status']}] {r['title']} :: "
                  f"{r['check_key'] or '-'} {r['check_type'] or ''} "
                  f"last={r['last_status'] or '-'}")
    c.commit()
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
