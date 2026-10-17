#!/usr/bin/env python3
"""dash-actions — action API behind the successbrian-os dashboard.

PURPOSE: turn the dashboard from read-only into operable. The inbox has
         rendered answer buttons for months calling answerQuestion(), which
         exists nowhere — this API finally implements them, plus task
         completion and on-demand runs of safe watcher jobs.

CALLED BY: systemd user service dash-actions.service (port 5057); nginx on
           Node Zero proxies /successbrian-os/dash-actions/ ->
           100.118.53.47:5057/.

AUTH: shared token in X-Dash-Token header. Token lives in
      /home/successbrian/.dash_actions_token (chmod 600); fragment builders
      embed it in dashboard JS at build time. The token is visible in page
      source to anyone who looks — the real safety is that every endpoint
      is narrow: fixed SQL by integer id, and /api/run only executes an
      explicit allowlist (no shell, no arbitrary commands).

NOTES: stdlib + flask + psycopg2. Uses ~/.pgpass for DB auth (no passwords
       in code), same as podcast-api.
"""
import os
import subprocess

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request

app = Flask(__name__)

TOKEN_FILE = os.path.expanduser("~/.dash_actions_token")


def _token():
    try:
        return open(TOKEN_FILE).read().strip()
    except OSError:
        return ""


def _authed():
    tok = _token()
    return bool(tok) and request.headers.get("X-Dash-Token") == tok


def db():
    return psycopg2.connect(host="localhost", user="successbrian",
                            dbname="ecosystem_central",
                            cursor_factory=RealDictCursor)


@app.before_request
def _gate():
    if request.path == "/api/health":
        return None
    if not _authed():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "dash-actions"})


@app.route("/api/questions/answer", methods=["POST"])
def answer_question():
    """Record Brian's answer to an inbox pending_question."""
    d = request.get_json(force=True) or {}
    try:
        qid = int(d.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "id required"}), 400
    answer = (d.get("answer") or "")[:2000]
    if not answer:
        return jsonify({"ok": False, "error": "answer required"}), 400
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE successbrian_os.pending_questions "
                "SET answer=%s, status='answered', updated_at=now() "
                "WHERE id=%s AND status='open' RETURNING id", (answer, qid))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "not found or not open"}), 404
    return jsonify({"ok": True, "id": qid})


@app.route("/api/tasks/done", methods=["POST"])
def task_done():
    """Complete a task from the dashboard.

    source 'pm' -> successbrian_os.tasks id
    source 'life_ops' -> life_ops.event_tasks id (mirrors to PM too)
    """
    d = request.get_json(force=True) or {}
    try:
        tid = int(d.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "id required"}), 400
    source = d.get("source", "pm")
    conn = db()
    cur = conn.cursor()
    if source == "life_ops":
        cur.execute("UPDATE life_ops.event_tasks SET status='done' "
                    "WHERE id=%s RETURNING pm_task_id", (tid,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            cur.close(); conn.close()
            return jsonify({"ok": False, "error": "not found"}), 404
        if row["pm_task_id"]:
            cur.execute("UPDATE successbrian_os.tasks SET status='completed', "
                        "completed_at=now() WHERE id=%s", (row["pm_task_id"],))
    else:
        cur.execute("UPDATE successbrian_os.tasks SET status='completed', "
                    "completed_at=now() WHERE id=%s RETURNING id", (tid,))
        if not cur.fetchone():
            conn.rollback()
            cur.close(); conn.close()
            return jsonify({"ok": False, "error": "not found"}), 404
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "id": tid, "source": source})


# job name -> argv (no shell, ever). Only safe, idempotent watchers.
RUN_ALLOWLIST = {
    "personal_os_watch": ["/usr/bin/python3",
                          "/home/successbrian/successbrian-os/tools/"
                          "personal_os_watch/watch.py"],
    "life_ops_watch": ["/usr/bin/python3",
                       "/home/successbrian/successbrian-os/tools/life_ops/"
                       "plan.py", "--watch"],
    "ops_console_rebuild": ["/usr/bin/python3",
                            "/home/successbrian/successbrian-os/tools/"
                            "dashboard/build_ops_console.py"],
}


@app.route("/api/run", methods=["POST"])
def run_job():
    """Run an allowlisted watcher job on demand. Returns its tail output."""
    d = request.get_json(force=True) or {}
    job = d.get("job")
    argv = RUN_ALLOWLIST.get(job)
    if not argv:
        return jsonify({"ok": False,
                        "error": f"unknown job; allowed: "
                                 f"{sorted(RUN_ALLOWLIST)}"}), 400
    env = dict(os.environ)
    env.update({"PGHOST": "localhost", "PGDATABASE": "ecosystem_central",
                "PGUSER": "successbrian"})
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           env=env, timeout=300)
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "timed out after 300s"}), 504
    tail = (p.stdout.strip() + "\n" + p.stderr.strip()).strip()[-1500:]
    return jsonify({"ok": p.returncode == 0, "job": job,
                    "returncode": p.returncode, "output": tail})


@app.route("/api/run/allowed", methods=["GET"])
def run_allowed():
    return jsonify({"ok": True, "jobs": sorted(RUN_ALLOWLIST)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5057)
